"""CapsWriter ASR 协议 v2 文件客户端。"""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
import shutil
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import websockets


class AsrError(Exception):
    """服务端或 SDK 可识别的转录失败。"""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        *,
        recovery_path=None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.recovery_path = recovery_path


@dataclass
class Transcript:
    text: str
    tokens: list[str]
    timestamps: list[float]
    duration: float
    raw: dict
    task_id: str | None = None
    is_final: bool = True
    time_start: float | None = None
    time_submit: float | None = None
    time_complete: float | None = None
    text_accu: str | None = None


_CHUNK_BYTES = 256 * 1024
_RAW_SAMPLE_RATE = 16000

# 服务端协议错误码；本地 timeout/connection_lost 等 SDK 异常不在此集合内。
PROTOCOL_ERROR_CODES = frozenset({
    "bad_request",
    "unsupported_encoding",
    "decode_failed",
    "decode_stalled",
    "task_conflict",
    "audio_too_long",
    "inference_failed",
    "inference_timeout",
    "overloaded",
    "slow_consumer",
    "no_backend",
    "internal",
})
_RAW_FRAME_SECONDS = 60


async def _run_process(*args: str) -> tuple[int, bytes, bytes]:
    """执行媒体工具，并在取消时杀死和回收子进程。"""
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_task = asyncio.create_task(process.stdout.read())
    stderr_task = asyncio.create_task(process.stderr.read())
    try:
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        await process.wait()
        return process.returncode, stdout, stderr
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)


async def _transcode(path: Path, encoding: str) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AsrError("decode_failed", "找不到 ffmpeg")
    # 显式只取第一条音轨：ffmpeg 自动选流会把视频轨拉进解码图，白付解码成本。
    # 不带 "?" 是为了无音轨文件 fail fast（报错）而不是静默产出空音频。
    args = [
        ffmpeg, "-nostdin", "-i", str(path),
        "-map", "0:a:0",
        "-ar", "16000", "-ac", "1",
    ]
    if encoding == "ogg_opus":
        args.extend(["-c:a", "libopus", "-b:a", "32k", "-f", "ogg"])
    else:
        args.extend(["-f", encoding])
    args.append("pipe:1")
    try:
        code, stdout, stderr = await _run_process(*args)
    except OSError as exc:
        raise AsrError("decode_failed", f"无法启动 ffmpeg: {exc}") from exc
    if code != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise AsrError("decode_failed", detail or f"ffmpeg 退出码 {code}")
    if encoding == "f32le":
        if len(stdout) % 4:
            raise AsrError("decode_failed", "ffmpeg 输出的 f32le 数据未按样本对齐")
        samples = np.frombuffer(stdout, dtype="<f4").size
        return stdout[:samples * 4]
    if encoding == "s16le":
        if len(stdout) % 2:
            raise AsrError("decode_failed", "ffmpeg 输出的 s16le 数据未按样本对齐")
        samples = np.frombuffer(stdout, dtype="<i2").size
        return stdout[:samples * 2]
    return stdout


async def _count_decoded_samples(audio: bytes, encoding: str) -> int:
    """从 SDK 将要发送的压缩字节流累计解码样本数。"""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AsrError("decode_failed", "找不到 ffmpeg")
    input_format = {"flac": "flac", "ogg_opus": "ogg"}[encoding]
    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-nostdin",
            "-f", input_format,
            "-i", "pipe:0",
            "-ar", str(_RAW_SAMPLE_RATE),
            "-ac", "1",
            "-f", "s16le",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise AsrError("decode_failed", f"无法启动 ffmpeg: {exc}") from exc

    async def feed_input() -> None:
        try:
            for offset in range(0, len(audio), _CHUNK_BYTES):
                process.stdin.write(audio[offset:offset + _CHUNK_BYTES])
                await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            # 解码进程已退出并关闭管道（flac/ogg 流长度已知时 ffmpeg 不必读到 EOF），
            # 属正常管道生命周期；成败由下方退出码与输出字节数裁决。
            pass

    async def count_output() -> int:
        byte_count = 0
        while chunk := await process.stdout.read(_CHUNK_BYTES):
            byte_count += len(chunk)
        return byte_count

    tasks = (
        asyncio.create_task(feed_input()),
        asyncio.create_task(count_output()),
        asyncio.create_task(process.stderr.read()),
    )
    try:
        _, output_bytes, stderr = await asyncio.gather(*tasks)
        code = await process.wait()
    except OSError as exc:
        raise AsrError("decode_failed", f"无法读取 ffmpeg 解码输出: {exc}") from exc
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
        await asyncio.gather(*tasks, return_exceptions=True)
    if code != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise AsrError("decode_failed", detail or f"ffmpeg 退出码 {code}")
    if output_bytes % 2:
        raise AsrError("decode_failed", "ffmpeg 解码输出未按样本对齐")
    return output_bytes // 2


def _health_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = {"ws": "http", "wss": "https"}.get(parts.scheme)
    if scheme is None:
        raise AsrError("connection_lost", f"不支持的服务端 URL 协议: {parts.scheme}")
    path = parts.path.rstrip("/") + "/health"
    return urlunsplit((scheme, parts.netloc, path, "", ""))


def _get_health(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


async def _check_server(url: str, encoding: str, model: str | None = None) -> None:
    try:
        status, body = await asyncio.to_thread(_get_health, _health_url(url))
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        if isinstance(exc, TimeoutError):
            raise AsrError("timeout", "读取服务端 /health 超时") from exc
        if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
            raise AsrError("timeout", "读取服务端 /health 超时") from exc
        raise AsrError("connection_lost", f"无法读取服务端 /health: {exc}") from exc
    if status != 200:
        raise AsrError("server_too_old", f"服务端 /health 返回 HTTP {status}，需要协议 v2")
    try:
        health = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AsrError("server_too_old", "服务端 /health 不是有效 JSON") from exc
    version = health.get("protocol_version") if isinstance(health, dict) else None
    if isinstance(version, bool) or not isinstance(version, int) or version < 2:
        raise AsrError("server_too_old", "服务端协议版本低于 v2")
    encodings = health.get("encodings", [])
    if not isinstance(encodings, list) or encoding not in encodings:
        raise AsrError("unsupported_encoding", f"服务端不支持编码 {encoding}")
    if model is not None and health.get("role") == "server" and health.get("model") != model:
        raise AsrError("bad_request", f"请求模型 {model!r} 与服务端模型 {health.get('model')!r} 不符")


def _audio_frame_bytes(data_length: int, encoding: str) -> int:
    """单帧字节上限：原始 PCM 按 60 秒切，压缩流按固定块切。"""
    if encoding in {"f32le", "s16le"}:
        sample_bytes = 4 if encoding == "f32le" else 2
        return _RAW_SAMPLE_RATE * _RAW_FRAME_SECONDS * sample_bytes
    return _CHUNK_BYTES


def _audio_frame_count(data_length: int, encoding: str) -> int:
    """总帧数。停滞消息要报「已发/总帧」，所以在发送前就能算出分母。"""
    frame_bytes = _audio_frame_bytes(data_length, encoding)
    return max(1, (data_length + frame_bytes - 1) // frame_bytes)


def _audio_frames(data: bytes, encoding: str):
    frame_bytes = _audio_frame_bytes(len(data), encoding)
    count = _audio_frame_count(len(data), encoding)
    for index in range(count):
        yield data[index * frame_bytes:(index + 1) * frame_bytes], index == count - 1


def _audio_frame(
    data: bytes,
    *,
    task_id: str,
    time_start: float,
    is_final: bool,
    samples_total: int,
    encoding: str,
    seg_duration: float,
    seg_overlap: float,
    language: str | None,
    context: str | None,
    model: str | None,
) -> str:
    frame = {
        "task_id": task_id,
        "source": "file",
        "data": base64.b64encode(data).decode("ascii"),
        "is_final": is_final,
        "time_start": time_start,
        "seg_duration": seg_duration,
        "seg_overlap": seg_overlap,
        "encoding": encoding,
    }
    if is_final:
        frame["samples_total"] = samples_total
    if language is not None:
        frame["language"] = language
    if context is not None:
        frame["context"] = context
    if model is not None:
        frame["model"] = model
    return json.dumps(frame, ensure_ascii=False)


def _transcript(result: dict) -> Transcript:
    return Transcript(
        text=result["text"],
        tokens=result.get("tokens", []),
        timestamps=result.get("timestamps", []),
        duration=float(result.get("duration", 0.0)),
        raw=result,
        task_id=result.get("task_id"),
        is_final=result.get("is_final", True),
        time_start=result.get("time_start"),
        time_submit=result.get("time_submit"),
        time_complete=result.get("time_complete"),
        text_accu=result.get("text_accu"),
    )


async def _receive(
    ws,
    *,
    task_id: str,
    on_progress,
    idle_messages: asyncio.Queue,
    mark_progress: Callable[..., None],
) -> Transcript:
    while True:
        try:
            message = await ws.recv()
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            raise AsrError("connection_lost", f"服务端关闭连接且未发送错误帧: {exc}") from exc
        result = json.loads(message)
        kind = result.get("type")
        # 协议只定义了 result / error 两种服务端消息（core/protocol.py），且两者都必带
        # task_id。未知 type 与陌生 task_id 一律忽略，且**不**刷新 idle：否则只发垃圾帧的
        # 服务端能把停滞一路藏到绝对墙钟总预算才暴露，而不是在 idle 上暴露。
        if kind not in {"result", "error"} or result.get("task_id") != task_id:
            continue
        # 匹配消息本身就是进展：idle 计时与诊断快照读同一个 last_at，不另建镜像状态。
        mark_progress(is_result=kind == "result" and not result.get("is_final", False))
        if kind == "error":
            raise AsrError(
                result["code"],
                result.get("message", "服务端转录失败"),
                result.get("retryable", False),
            )
        if result.get("is_final", False):
            return _transcript(result)
        if on_progress is not None:
            on_progress(result)


async def _transcribe_connected(
    url: str,
    data: bytes,
    *,
    encoding: str,
    samples_total: int,
    language: str | None,
    context: str | None,
    model: str | None,
    seg_duration: float,
    seg_overlap: float,
    idle_timeout: float,
    on_progress: Callable[[dict], object] | None,
) -> Transcript:
    connect_options = {"ping_interval": None, "max_size": None, "max_queue": None}
    if "proxy" in inspect.signature(websockets.connect).parameters:
        connect_options["proxy"] = None
    task_id = str(uuid.uuid4())
    time_start = time.time()
    idle_messages: asyncio.Queue = asyncio.Queue(maxsize=1)
    # 进展快照：只放 SDK 自己掌握的事实（阶段/已发帧/中间结果条数/最近进展时刻）。
    # 超时消息按这些事实措辞，不据此推断网络状况或服务端责任。
    # 生产者：upload 每成功发出一帧、_receive 每收到一条匹配本任务的已知消息，都经
    # mark_progress 写入；消费者：idle_watch 读令牌计时，stall_error 读这些字段出文案。
    progress = {
        "stage": "上传",
        "frames_sent": 0,
        "frames_total": _audio_frame_count(len(data), encoding),
        "results": 0,
        "last_at": time.monotonic(),
    }

    def mark_progress(*, is_result: bool = False) -> None:
        """记一次真实进展：刷新最近进展时刻并唤醒 idle 监视。"""
        progress["last_at"] = time.monotonic()
        if is_result:
            progress["results"] += 1
        if not idle_messages.full():
            idle_messages.put_nowait(None)

    def stall_error() -> AsrError:
        return AsrError(
            "timeout",
            f"{progress['stage']}连续 {idle_timeout:.0f} 秒没有进展："
            f"已发送 {progress['frames_sent']}/{progress['frames_total']} 帧，"
            f"收到中间结果 {progress['results']} 条，"
            f"距最近进展 {time.monotonic() - progress['last_at']:.0f} 秒",
        )

    # 不用 `async with`：异常路径上对端可能已经停止读取（正常背压或挂死），而
    # websockets 的 close() 会先 send_data()+drain()，drain() 等的是一个永远不来的
    # TCP 写窗口 —— 证据见 docs/sessions/261006-issue-root-fixes/progress/
    # sdk-progress-progress.md 探针 E：那一次 idle 失败就卡死在这里，调用永不返回。
    # 所以自己接管进入/退出：成功路径仍走优雅关闭，异常/取消路径直接中止传输。
    # completed 只由「已拿到最终结果」那一条返回置真，用来区分该不该做优雅关闭。
    completed = False
    connection = websockets.connect(url, **connect_options)
    ws = await connection.__aenter__()
    try:
        async def upload() -> None:
            for chunk, is_final in _audio_frames(data, encoding):
                frame = _audio_frame(
                    chunk,
                    task_id=task_id,
                    time_start=time_start,
                    is_final=is_final,
                    samples_total=samples_total,
                    encoding=encoding,
                    seg_duration=seg_duration,
                    seg_overlap=seg_overlap,
                    language=language,
                    context=context,
                    model=model,
                )
                # 逐帧 send 时限已删除：一次 send 耗时长只说明这一帧进了内核发送缓冲，
                # 不是任务是否推进的证据——服务端停止读取但仍在回中间结果时（正常背压）
                # 会被旧判据误杀。真正的判据在 idle_watch：距上次**真实进展**的上限。
                # 这里直接 await：发送异常原样上抛到 upload 任务，由外层 FIRST_COMPLETED
                # 按 upload → receive → idle 的固定顺序裁决，不另开异常通道。
                await ws.send(frame)
                progress["frames_sent"] += 1
                # 上传阶段的进展只认「这一帧真的发送成功」；上传结束后不再有 send，
                # 于是发送自然不再刷新（progress["stage"] 也随之切到等待结果）。
                mark_progress()
            progress["stage"] = "等待结果"

        async def idle_watch() -> None:
            # 从连接建立就监视，覆盖上传阶段：上传中同样可能双向静默。
            while True:
                # 用 asyncio.wait 而不是 asyncio.wait_for：后者在 Python ≤3.11 上会在
                # 「令牌到达与 task.cancel() 落在同一 tick」时吞掉取消
                # （asyncio/tasks.py：except CancelledError: if fut.done(): return fut.result()），
                # 于是本协程吞掉这一轮取消后又进入下一轮全新等待，而那次取消已被消费，
                # 永远等不到新的取消 —— finally 里的 gather 便永久挂起（issue #65）。
                # asyncio.wait 的内部 _wait 没有这个分支，取消一定向上抛。
                getter = asyncio.ensure_future(idle_messages.get())
                try:
                    done, _ = await asyncio.wait({getter}, timeout=idle_timeout)
                    if not done:
                        raise stall_error()
                finally:
                    # 实测：只 cancel 不 await 在本代码结构下也不会留下可观测的 pending
                    # getter（外层 finally 的 gather 会把事件循环驱动到它收尾），因此不额外
                    # 加一次 await；证据见 docs/sessions/261004-sdk65/root-cause.md 第 4 节。
                    getter.cancel()

        upload_task = asyncio.create_task(upload())
        receive_task = asyncio.create_task(
            _receive(
                ws,
                task_id=task_id,
                on_progress=on_progress,
                idle_messages=idle_messages,
                mark_progress=mark_progress,
            )
        )
        idle_task = asyncio.create_task(idle_watch())
        # ordered 决定多个任务同时完成时的上抛顺序；tasks 只交给 asyncio.wait。
        ordered = (upload_task, receive_task, idle_task)
        tasks = set(ordered)
        try:
            while True:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                # 同时完成时的裁决：任一已完成的子任务带异常，就先按 upload → receive → idle
                # 的固定顺序上抛。上传失败/idle 超时不能因为同轮收到了 final 就被改判成成功；
                # set 的遍历顺序不定，用 ordered 消掉这个不确定性。
                for task in ordered:
                    if task not in done:
                        continue
                    if task.cancelled():
                        raise asyncio.CancelledError
                    error = task.exception()
                    if error is not None:
                        raise error
                if receive_task in done:
                    result = receive_task.result()
                    completed = True
                    return result
                tasks.difference_update(done)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        # 中止传输覆盖整个连接生命周期，不只是连接主体：
        # · 异常/停滞/取消（completed 为假）先中止，否则 close() 会卡在 drain 上等一个
        #   永远不来的写窗口（progress 存档探针 E）。
        # · 成功路径的优雅 close 若被绝对截止或取消打断（首审 P2-1：final 已真实收到、
        #   close 已开始，但 transport 仍停在 CLOSING、对端会话仍存活），收尾再补一次中止，
        #   保证连接一定被回收。abort 对已关闭的传输是空操作，不是第二次 close。
        if not completed:
            ws.transport.abort()
        try:
            await connection.__aexit__(None, None, None)
        finally:
            ws.transport.abort()


def _auto_budget(duration: float) -> float:
    """远端转录阶段的自动预算（秒）。

    这是 **watchdog**（挂死检测），不是识别时限 SLA：它唯一的职责是在服务端不再推进
    时把调用救回来，正常识别远快于它，所以必须按实测耗时留足余量。93 秒音频的一次
    真实识别约需 306 秒（~3.3× 实时因子），旧公式 ``max(120, 时长 + 60)`` 给到的
    153 秒会在识别仍在跑时就误杀（issue #69），故改为时长 4 倍 + 120 秒。

    ``+ 120`` 同时覆盖了旧公式 ``max(120, …)`` 的下限语义：时长为 0 或短音频时
    仍不低于 120 秒，无需双分支。
    """
    return duration * 4 + 120


async def _operation(
    path: Path,
    url: str,
    *,
    encoding: str,
    language: str | None,
    context: str | None,
    model: str | None,
    seg_duration: float,
    seg_overlap: float,
    idle_timeout: float,
    on_progress: Callable[[dict], object] | None,
    set_deadline,
) -> Transcript:
    if not path.is_file():
        raise AsrError("decode_failed", f"音频文件不存在: {path}")
    await _check_server(url, encoding, model)
    audio = await _transcode(path, encoding)
    if encoding == "f32le":
        samples_total = np.frombuffer(audio, dtype="<f4").size
    elif encoding == "s16le":
        samples_total = np.frombuffer(audio, dtype="<i2").size
    else:
        samples_total = await _count_decoded_samples(audio, encoding)
    duration = samples_total / _RAW_SAMPLE_RATE
    set_deadline(_auto_budget(duration), duration=duration)
    try:
        return await _transcribe_connected(
            url,
            audio,
            encoding=encoding,
            samples_total=samples_total,
            language=language,
            context=context,
            model=model,
            seg_duration=seg_duration,
            seg_overlap=seg_overlap,
            idle_timeout=idle_timeout,
            on_progress=on_progress,
        )
    except (OSError, websockets.exceptions.WebSocketException) as exc:
        raise AsrError("connection_lost", f"无法连接服务端 WebSocket: {exc}") from exc


async def transcribe_file(
    path,
    url,
    *,
    encoding="flac",
    language=None,
    context=None,
    seg_duration=15.0,
    seg_overlap=2.0,
    deadline_total=None,
    idle_timeout=300.0,
    on_progress=None,
    model=None,
) -> Transcript:
    """转录音频文件；不会降级或自动重试。"""
    started = time.monotonic()
    deadline = {"at": started + (120.0 if deadline_total is None else deadline_total)}
    deadline_changed = asyncio.Event()
    # 阶段标记：本地准备（健康检查/转码/样本计数）结束后由 set_deadline 翻到远端转录，
    # 只用于让 timeout 消息能区分卡在哪一段，不对外暴露。
    stage = {"name": "本地准备"}
    # 被超过的预算快照：显式传参时是入口的 deadline_total，默认路径在本地准备结束后
    # 由 set_deadline 改写成自动预算的秒数；duration 为 None 表示音频时长还没算出来。
    budget = {
        "seconds": 120.0 if deadline_total is None else float(deadline_total),
        "duration": None,
    }

    def set_deadline(seconds: float, *, duration: float | None = None) -> None:
        stage["name"] = "远端转录"
        if duration is not None:
            # 超时消息要能对照「预算多少秒 / 音频多长」，duration 由 _operation 算出后
            # 随预算一起回传，不走全局变量。
            budget["duration"] = duration
        if deadline_total is None:
            budget["seconds"] = seconds
            # 默认时限：本地准备阶段结束后重新锚定，转码耗时不再算进远端转录预算。
            deadline["at"] = time.monotonic() + seconds
            deadline_changed.set()

    def timeout_error() -> AsrError:
        # 默认路径下调用方从未传过 deadline_total，被超过的是自动预算；写错名字会让人
        # 误以为自己把预算设太紧了。
        name = "自动预算" if deadline_total is None else "deadline_total"
        detail = f"{budget['seconds']:.0f} 秒"
        if budget["duration"] is not None:
            detail += f"（音频 {budget['duration']:.1f} 秒）"
        return AsrError("timeout", f"转录超过{name} {detail}：{stage['name']}阶段超时")

    async def operation() -> Transcript:
        return await _operation(
            Path(path),
            url,
            encoding=encoding,
            language=language,
            context=context,
            seg_duration=seg_duration,
            seg_overlap=seg_overlap,
            idle_timeout=idle_timeout,
            on_progress=on_progress,
            model=model,
            set_deadline=set_deadline,
        )

    async def deadline_watch() -> None:
        while True:
            remaining = deadline["at"] - time.monotonic()
            if remaining <= 0:
                raise timeout_error()
            # 用 asyncio.wait 而不是 asyncio.wait_for：后者在 Python ≤3.11 上会在
            # 「deadline_changed.set() 与 task.cancel() 落在同一 tick」时吞掉取消，
            # 本协程吞掉这一轮取消后又进入下一轮全新等待，而那次取消已被消费，
            # transcribe_file 的 finally 里的 gather 便永久挂起（issue #67）。
            waiter = asyncio.ensure_future(deadline_changed.wait())
            try:
                done, _ = await asyncio.wait({waiter}, timeout=remaining)
                if waiter in done:
                    deadline_changed.clear()
                    continue
                # 等待超时：只有确实越过预算才上抛，计时器与 set_deadline 同 tick 时
                # 以真实时钟为准（asyncio.wait 的计时器精度不保证先于事件投递）。
                if deadline["at"] <= time.monotonic():
                    raise timeout_error()
            finally:
                waiter.cancel()

    operation_task = asyncio.create_task(operation())
    timer_task = asyncio.create_task(deadline_watch())
    try:
        done, _ = await asyncio.wait(
            {operation_task, timer_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if timer_task in done:
            timer_task.result()
        if time.monotonic() >= deadline["at"]:
            raise timeout_error()
        return operation_task.result()
    finally:
        for task in (operation_task, timer_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(operation_task, timer_task, return_exceptions=True)


def transcribe_file_sync(
    path,
    url,
    *,
    encoding="flac",
    language=None,
    context=None,
    seg_duration=15.0,
    seg_overlap=2.0,
    deadline_total=None,
    idle_timeout=300.0,
    on_progress=None,
    model=None,
) -> Transcript:
    """同步入口，适用于非 asyncio 调用方。"""
    return asyncio.run(
        transcribe_file(
            path,
            url,
            encoding=encoding,
            language=language,
            context=context,
            seg_duration=seg_duration,
            seg_overlap=seg_overlap,
            deadline_total=deadline_total,
            idle_timeout=idle_timeout,
            on_progress=on_progress,
            model=model,
        )
    )
