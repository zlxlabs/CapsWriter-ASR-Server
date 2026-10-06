"""#76：SDK 从连接建立起就覆盖上传阶段的双向真实进展判据（card B）。

被测条件全部经真实 ``transcribe_file`` 入口与 SDK 真实产出的上传帧（假服务端只替代远端
服务端，SDK 内部不做替换）。本地假服务端刻意**不用** ``websockets.serve``：它的帧
组装器会把未读完整的帧无限缓冲进用户态，回环 socket 的真实背压根本到不了客户端
（见 docs/sessions/261006-issue-root-fixes/progress/sdk-progress-progress.md 探针 D），
因此这里用最小 raw-socket WebSocket 对端，读到哪一帧由测试自己控制。

矩阵（每条都走真实上传帧，task_id 取自服务端实际收到的帧）：
1. 发送阻塞 + 下行静默 → 上传尚未完成即在 idle 上失败，报阶段/已发帧/中间结果/距进展时间。
2. 持续成功发送但无回复 → 上传途中不得误报；上传完成后无结果仍按 idle 失败。
3. 发送阻塞但合法结果连续到达 → 超过单次 idle 也不误杀，解除背压后能拿到 final；
   未知 type 与非当前 task_id 的消息不得刷新 idle，必须在 idle 上暴露。
4. error 帧上传途中透传；连接提前关闭且无 error/final → connection_lost；
   任务异常不得被同轮 final 改判成功。
5. 显式 deadline_total 在连续有效结果下仍按用户要求终止；取消后无遗留任务。
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import inspect
import json
import re
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from sdk.capswriter_asr import AsrError, Transcript, transcribe_file
from sdk.capswriter_asr import client as sdk_client

# 本文件要造真实 socket 背压，必须让 SDK 把真实音频转码成足量的线上字节，
# 因此依赖真 ffmpeg（与 tests/test_sdk_transcode_track.py 同一约定）：缺工具明确失败，
# 不静默 skip，否则 CI 会以「矩阵没跑」的形式假绿（issue #75）。
if shutil.which("ffmpeg") is None:
    pytest.fail(
        "测试环境缺少 ffmpeg：本文件用真实音频造真实上传帧与真实 socket 背压，"
        "缺 ffmpeg 必须失败而非 skip",
        pytrace=False,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]

# 60 秒 s16le 帧 = 1 920 000 字节原始 + base64 后的 2 560 000 字节 wire。
# 10 帧 ≈ 19.2 MB，远超回环 socket 在「对端停止读取」时能吞下的量，上传必然被卡住。
AUDIO_SECONDS = 600
FRAME_SECONDS = 60
FRAME_TOTAL = AUDIO_SECONDS // FRAME_SECONDS
IDLE = 3.0


# --------------------------------------------------------------------------- #
# 最小 raw-socket WebSocket 对端：自己完成 /health 与 RFC6455 握手/帧解析。
# --------------------------------------------------------------------------- #

_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_HEALTH_BODY = json.dumps({"protocol_version": 2, "encodings": ["s16le"]}).encode()


def _encode_server_text(payload: str) -> bytes:
    data = payload.encode("utf-8")
    header = bytearray([0x81])
    if len(data) < 126:
        header.append(len(data))
    elif len(data) < 65536:
        header.append(126)
        header += len(data).to_bytes(2, "big")
    else:
        header.append(127)
        header += len(data).to_bytes(8, "big")
    return bytes(header) + data


def _unmask(data: bytes, mask: bytes) -> bytes:
    """整数异或整段去掩码：2.5 MB 帧不能用逐字节 Python 循环。"""
    repeats = -(-len(data) // 4)
    key = (mask * repeats)[: len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(len(data), "big")


class FakeRemote:
    """一次 WS 会话的观测与控制面板。"""

    def __init__(self) -> None:
        self.frames: list[dict] = []
        self.task_id: str | None = None
        self.results_sent = 0
        self.noise_sent = 0
        self.final_sent = False
        self.error_sent: dict | None = None
        self.session_ended = False
        # 读闸：清零后对端不再从 socket 取数据，内核接收窗口随即关闭，
        # 客户端 ws.send 会在真实背压下阻塞。
        self.read_gate = asyncio.Event()
        self.read_gate.set()

    @property
    def frames_read(self) -> int:
        return len(self.frames)


class FakeRemoteServer:
    """按测试脚本行事的本地假服务端。

    progress_kind:
        ``none``    —— 下行完全静默
        ``matched`` —— 持续发与当前 task_id 匹配的合法中间结果
        ``unknown`` —— 持续发协议未定义的 type
        ``foreign`` —— 持续发别的 task_id 的合法中间结果
    on_upload_complete:
        ``final`` / ``error`` / ``close`` / ``silent``
    """

    def __init__(
        self,
        *,
        read_interval: float = 0.0,
        progress_kind: str = "none",
        progress_interval: float = 0.4,
        on_upload_complete: str = "final",
        error_code: str = "decode_stalled",
    ) -> None:
        self.read_interval = read_interval
        self.progress_kind = progress_kind
        self.progress_interval = progress_interval
        self.on_upload_complete = on_upload_complete
        self.error_code = error_code
        self.remote = FakeRemote()
        self._server: asyncio.AbstractServer | None = None
        self._writers: list[asyncio.StreamWriter] = []
        self._sessions: list[asyncio.Task] = []

    # -- 帧层 ------------------------------------------------------------- #

    async def _read_frame(self, reader: asyncio.StreamReader) -> dict | None:
        try:
            header = await reader.readexactly(2)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return None
        length = header[1] & 0x7F
        try:
            if length == 126:
                length = int.from_bytes(await reader.readexactly(2), "big")
            elif length == 127:
                length = int.from_bytes(await reader.readexactly(8), "big")
            mask = await reader.readexactly(4)
            payload = await reader.readexactly(length)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return None
        return json.loads(_unmask(payload, mask))

    def _progress_payload(self) -> str | None:
        remote = self.remote
        if self.progress_kind == "none":
            return None
        if self.progress_kind == "unknown":
            return json.dumps({"type": "heartbeat", "task_id": remote.task_id})
        task_id = remote.task_id if self.progress_kind == "matched" else "ffffffff-not-mine"
        return json.dumps({
            "type": "result", "task_id": task_id, "is_final": False,
            "text": "进度", "duration": 0.0,
        })

    async def _session(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        remote = self.remote

        async def keep_sending_results() -> None:
            while True:
                await asyncio.sleep(self.progress_interval)
                payload = self._progress_payload()
                if payload is None or (remote.task_id is None and self.progress_kind != "unknown"):
                    continue
                writer.write(_encode_server_text(payload))
                await writer.drain()
                if self.progress_kind == "matched":
                    remote.results_sent += 1
                else:
                    remote.noise_sent += 1

        async def read_frames() -> None:
            while True:
                # 读闸关闭后不再从 socket 取数据：内核接收窗口随即关闭，
                # 客户端 ws.send 在真实背压下阻塞。
                await remote.read_gate.wait()
                if self.read_interval:
                    await asyncio.sleep(self.read_interval)
                frame = await self._read_frame(reader)
                if frame is None:
                    return
                remote.frames.append(frame)
                remote.task_id = frame["task_id"]
                if not frame["is_final"]:
                    continue
                await self._finish(writer)
                if self.on_upload_complete != "silent":
                    return
                # silent 形态：收完上传后仍保持连接，让客户端自己在 idle 上失败。

        sender = asyncio.create_task(keep_sending_results())
        try:
            await read_frames()
        finally:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender

    async def _finish(self, writer: asyncio.StreamWriter) -> None:
        remote = self.remote
        if self.on_upload_complete == "final":
            writer.write(_encode_server_text(json.dumps({
                "type": "result", "task_id": remote.task_id, "is_final": True,
                "text": "背压之后的结果。", "tokens": [], "timestamps": [], "duration": 1.0,
            })))
            await writer.drain()
            remote.final_sent = True
        elif self.on_upload_complete == "error":
            remote.error_sent = {
                "type": "error", "task_id": remote.task_id,
                "code": self.error_code, "message": f"服务端拒绝：{self.error_code}",
                "retryable": False,
            }
            writer.write(_encode_server_text(json.dumps(remote.error_sent)))
            await writer.drain()
        elif self.on_upload_complete == "close":
            # 提前关闭且不发 error/final：客户端必须报 connection_lost。
            writer.transport.abort()

    # -- 连接层 ----------------------------------------------------------- #

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._sessions.append(asyncio.current_task())
        self._writers.append(writer)
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
            if head.startswith(b"GET /health"):
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(_HEALTH_BODY)).encode()
                    + b"\r\nConnection: close\r\n\r\n"
                    + _HEALTH_BODY
                )
                await writer.drain()
                return
            key = re.search(rb"Sec-WebSocket-Key:\s*(\S+)", head, re.I)
            accept = base64.b64encode(
                hashlib.sha1(key.group(1) + _WS_GUID).digest()
            ).decode()
            writer.write(
                b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept.encode() + b"\r\n\r\n"
            )
            await writer.drain()
            await self._session(reader, writer)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionResetError,
                asyncio.CancelledError):
            return
        finally:
            self.remote.session_ended = True
            with contextlib.suppress(Exception):
                writer.close()

    async def __aenter__(self) -> "FakeRemoteServer":
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *_exc) -> None:
        # 先中止 WS 会话协程，再关监听：start_server 派生的任务不在 _server 里，
        # 不显式收尾会让 teardown 挂死（#85 同类形态）。
        for task in self._sessions:
            task.cancel()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._sessions:
            await asyncio.gather(*self._sessions, return_exceptions=True)
        self._sessions.clear()
        self._writers.clear()

    @property
    def url(self) -> str:
        port = self._server.sockets[0].getsockname()[1]
        return f"ws://127.0.0.1:{port}"


@pytest.fixture
def long_s16le_audio(tmp_path) -> Path:
    """真实音频文件：s16le 不压缩，帧字节数与时长一一对应，便于核对帧数。"""
    path = tmp_path / "long.wav"
    samples = np.zeros(16000 * AUDIO_SECONDS, dtype=np.int16)
    sf.write(path, samples, 16000, subtype="PCM_16")
    return path


@pytest.fixture
def short_s16le_audio(tmp_path) -> Path:
    """1 秒真实音频：经真 ffmpeg 转码后恰好一帧（is_final）。"""
    path = tmp_path / "short.wav"
    sf.write(path, np.zeros(16000, dtype=np.int16), 16000, subtype="PCM_16")
    return path


def _parse_stall_counts(message: str) -> tuple[int, int, int]:
    """从停滞消息里解出「已发送 N/M 帧」与「收到中间结果 K 条」。"""
    frames = re.search(r"已发送 (\d+)/(\d+) 帧", message)
    results = re.search(r"收到中间结果 (\d+) 条", message)
    assert frames and results, f"停滞消息缺少计数事实：{message}"
    return int(frames.group(1)), int(frames.group(2)), int(results.group(1))


def _pending_sdk_tasks() -> list[str]:
    pending = []
    for task in asyncio.all_tasks():
        qualname = getattr(task.get_coro(), "__qualname__", "")
        if qualname.startswith(("_transcribe_connected.", "transcribe_file.", "_operation.")):
            if not task.done():
                pending.append(qualname)
    return pending


# --------------------------------------------------------------------------- #
# 1. 发送阻塞 + 下行静默：上传未完成即在 idle 上失败
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_blocked_upload_with_silent_server_fails_on_idle_before_upload_done(
    long_s16le_audio,
):
    """真实背压 + 完全静默：上传还没发完就得在 idle 上失败，而不是等总预算。"""
    async with FakeRemoteServer(progress_kind="none", on_upload_complete="silent") as server:
        remote = server.remote
        caller = asyncio.create_task(
            transcribe_file(long_s16le_audio, server.url, encoding="s16le",
                            idle_timeout=IDLE, deadline_total=90)
        )
        # 先让第一帧真的上传出去（拿到真实 task_id），随后对端停止读取。
        assert await _wait_for_frames(remote, 1, timeout=20), "服务端没有收到任何上传帧"
        remote.read_gate.clear()  # 真实背压：客户端卡在 ws.send
        started = time.monotonic()
        done, _ = await asyncio.wait({caller}, timeout=30)
        elapsed = time.monotonic() - started

        assert caller in done, "发送阻塞且下行静默时调用没有在有界时间内结束"
        error = caller.exception()
        leaked = _pending_sdk_tasks()

    assert isinstance(error, AsrError) and error.code == "timeout", error
    sent, total, results = _parse_stall_counts(error.message)
    assert total == FRAME_TOTAL, f"总帧数应等于真实上传帧数：{error.message}"
    assert sent < total, (
        f"被测前提不成立：上传其实已经发完（{sent}/{total}），本用例没有造出背压"
    )
    assert results == 0
    assert error.message.startswith("上传连续"), error.message
    assert "距最近进展" in error.message
    assert 0 < elapsed < IDLE * 2, f"应在 idle（{IDLE}s）附近失败，实际 {elapsed:.1f}s"
    assert leaked == [], f"失败后 SDK 内部任务未回收：{leaked}"


# --------------------------------------------------------------------------- #
# 2. 持续成功发送但无回复
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_successful_sends_keep_upload_alive_past_one_idle_window(long_s16le_audio):
    """上传耗时超过一个 idle 窗口，但每帧都真的发出去 → 上传途中不得误报无进展。"""
    read_interval = 0.9  # 每 ~0.9 秒放行一帧 < idle 3 秒
    async with FakeRemoteServer(
        read_interval=read_interval, progress_kind="none", on_upload_complete="silent"
    ) as server:
        remote = server.remote
        caller = asyncio.create_task(
            transcribe_file(long_s16le_audio, server.url, encoding="s16le",
                            idle_timeout=IDLE, deadline_total=90)
        )
        mid = await _wait_for_frames(remote, 4, timeout=20)
        alive_mid_upload = not caller.done()
        frames_mid_upload = remote.frames_read
        done, _ = await asyncio.wait({caller}, timeout=60)
        leaked = _pending_sdk_tasks()

    assert mid, "假服务端在超时前没有收到任何帧"
    assert frames_mid_upload < FRAME_TOTAL, "观察点必须落在上传途中"
    assert alive_mid_upload, "上传仍在推进时被误报为双向无进展"
    assert caller in done
    error = caller.exception()
    assert isinstance(error, AsrError) and error.code == "timeout", error
    sent, total, results = _parse_stall_counts(error.message)
    assert (sent, total, results) == (FRAME_TOTAL, FRAME_TOTAL, 0), error.message
    # 上传发完后不再有 send 刷新，上行一停就该按 idle 失败。
    assert error.message.startswith("等待结果连续"), error.message
    assert leaked == [], f"SDK 内部任务未回收：{leaked}"


@pytest.mark.asyncio
async def test_idle_fires_after_upload_completes_without_any_result(short_s16le_audio):
    """上传完成且一条结果都没有：按 idle 失败，消息如实报「已发满」。"""
    async with FakeRemoteServer(progress_kind="none", on_upload_complete="silent") as server:
        remote = server.remote
        with pytest.raises(AsrError) as caught:
            await transcribe_file(short_s16le_audio, server.url, encoding="s16le",
                                  idle_timeout=IDLE, deadline_total=60)

    assert caught.value.code == "timeout"
    assert _parse_stall_counts(caught.value.message) == (1, 1, 0)
    assert caught.value.message.startswith("等待结果连续"), caught.value.message
    assert remote.frames_read == 1 and remote.frames[-1]["is_final"] is True


# --------------------------------------------------------------------------- #
# 3. 背压 + 持续合法结果 / 噪声不刷新 idle
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_backpressure_with_continuous_results_survives_and_finalizes(long_s16le_audio):
    """正常背压：服务端停止读取但仍在回中间结果 → 超过一个 idle 也不误杀，松开后能 final。"""
    async with FakeRemoteServer(
        progress_kind="matched", progress_interval=0.4, on_upload_complete="final"
    ) as server:
        remote = server.remote
        caller = asyncio.create_task(
            transcribe_file(long_s16le_audio, server.url, encoding="s16le",
                            idle_timeout=IDLE, deadline_total=120,
                            on_progress=lambda _r: None)
        )
        await _wait_for_frames(remote, 2, timeout=20)
        remote.read_gate.clear()  # 真实背压：客户端 ws.send 阻塞
        await asyncio.sleep(IDLE * 3)
        alive_under_backpressure = not caller.done()
        results_under_backpressure = remote.results_sent
        frames_under_backpressure = remote.frames_read
        remote.read_gate.set()  # 解除背压
        done, _ = await asyncio.wait({caller}, timeout=60)
        leaked = _pending_sdk_tasks()
        transcript = caller.result() if caller in done else None

    assert alive_under_backpressure, "有持续合法中间结果时被背压误杀"
    assert results_under_backpressure >= 5, (
        f"背压期间没有持续收到合法中间结果（{results_under_backpressure} 条），"
        "被测前提不成立"
    )
    assert frames_under_backpressure < FRAME_TOTAL, (
        f"背压期间上传其实已经发完（{frames_under_backpressure}/{FRAME_TOTAL}），"
        "被测前提不成立"
    )
    assert caller in done, "解除背压后没有拿到最终结果"
    assert isinstance(transcript, Transcript) and transcript.text == "背压之后的结果。"
    assert transcript.task_id == remote.task_id
    assert remote.frames[-1]["is_final"] is True
    assert leaked == [], f"SDK 内部任务未回收：{leaked}"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,noise_field", [("unknown", "noise_sent"), ("foreign", "noise_sent")])
async def test_messages_that_are_not_task_progress_do_not_refresh_idle(
    short_s16le_audio, kind, noise_field
):
    """未知 type 与陌生 task_id 持续到达：必须在 idle 上暴露，不得拖到总预算。"""
    async with FakeRemoteServer(
        progress_kind=kind, progress_interval=0.2, on_upload_complete="silent"
    ) as server:
        remote = server.remote
        started = time.monotonic()
        with pytest.raises(AsrError) as caught:
            await transcribe_file(short_s16le_audio, server.url, encoding="s16le",
                                  idle_timeout=IDLE, deadline_total=90)
        elapsed = time.monotonic() - started

    assert caught.value.code == "timeout", caught.value
    assert _parse_stall_counts(caught.value.message)[2] == 0, caught.value.message
    assert elapsed < 15, f"应在 idle 上暴露，实际拖了 {elapsed:.1f}s（总预算是 90s）"
    assert getattr(remote, noise_field) >= 5, (
        f"噪声消息没有持续到达（{getattr(remote, noise_field)} 条），被测前提不成立"
    )


# --------------------------------------------------------------------------- #
# 4. 服务端错误帧与连接关闭
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["decode_stalled", "audio_too_long", "inference_failed"])
async def test_server_error_frame_during_upload_is_propagated(long_s16le_audio, code):
    """上传途中到达的 error 帧按原 code 透传，不被改写成 timeout 或成功。"""
    async with FakeRemoteServer(
        progress_kind="none", on_upload_complete="error", error_code=code
    ) as server:
        remote = server.remote
        with pytest.raises(AsrError) as caught:
            await transcribe_file(long_s16le_audio, server.url, encoding="s16le",
                                  idle_timeout=IDLE, deadline_total=60)

    assert caught.value.code == code
    assert caught.value.message == f"服务端拒绝：{code}"
    assert remote.error_sent == {
        "type": "error", "task_id": remote.task_id,
        "code": code, "message": f"服务端拒绝：{code}", "retryable": False,
    }
    assert remote.final_sent is False


@pytest.mark.asyncio
async def test_connection_closed_without_error_frame_reports_connection_lost(
    long_s16le_audio,
):
    """连接提前关闭且没有 error/final：报 connection_lost，不静默成功。"""
    async with FakeRemoteServer(progress_kind="none", on_upload_complete="close") as server:
        remote = server.remote
        with pytest.raises(AsrError) as caught:
            await transcribe_file(long_s16le_audio, server.url, encoding="s16le",
                                  idle_timeout=IDLE, deadline_total=60)

    assert caught.value.code == "connection_lost", caught.value
    assert remote.final_sent is False


@pytest.mark.asyncio
async def test_error_frame_wins_over_final_sent_in_the_same_tick(short_s16le_audio):
    """error 与合法 final 紧邻到达：任务异常不得被同轮结果改判成功。"""
    async with FakeRemoteServer(progress_kind="none", on_upload_complete="silent") as server:
        remote = server.remote
        caller = asyncio.create_task(
            transcribe_file(short_s16le_audio, server.url, encoding="s16le",
                            idle_timeout=IDLE, deadline_total=60)
        )
        assert await _wait_for_frames(remote, 1, timeout=20)
        # 连续写入 error 后紧跟 final：服务端一次 flush，SDK 可能在同一轮收到两条。
        writer = server._writers[-1]
        writer.write(_encode_server_text(json.dumps({
            "type": "error", "task_id": remote.task_id, "code": "decode_stalled",
            "message": "先到的是错误", "retryable": False,
        })))
        writer.write(_encode_server_text(json.dumps({
            "type": "result", "task_id": remote.task_id, "is_final": True,
            "text": "不该被采纳", "duration": 1.0,
        })))
        await writer.drain()
        done, _ = await asyncio.wait({caller}, timeout=30)

    assert caller in done
    with pytest.raises(AsrError) as caught:
        caller.result()
    assert caught.value.code == "decode_stalled"
    assert "不该被采纳" not in str(caught.value)


# --------------------------------------------------------------------------- #
# 5. 绝对墙钟预算与取消
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_explicit_deadline_total_still_wins_with_continuous_results(long_s16le_audio):
    """连续有效结果下，显式 deadline_total 仍按用户要求终止（它是绝对墙钟）。"""
    async with FakeRemoteServer(
        progress_kind="matched", progress_interval=0.3, on_upload_complete="silent"
    ) as server:
        remote = server.remote
        caller = asyncio.create_task(
            transcribe_file(long_s16le_audio, server.url, encoding="s16le",
                            idle_timeout=IDLE, deadline_total=5,
                            on_progress=lambda _r: None)
        )
        await _wait_for_frames(remote, 1, timeout=20)
        remote.read_gate.clear()
        started = time.monotonic()
        done, _ = await asyncio.wait({caller}, timeout=30)
        elapsed = time.monotonic() - started
        leaked = _pending_sdk_tasks()

    assert caller in done
    error = caller.exception()
    assert isinstance(error, AsrError) and error.code == "timeout", error
    assert "转录超过deadline_total" in error.message
    assert elapsed < 20, f"显式 deadline_total=5 未在有界时间内终止，实际 {elapsed:.1f}s"
    assert remote.results_sent >= 3, "被测前提不成立：期间没有持续有效结果"
    assert leaked == [], f"SDK 内部任务未回收：{leaked}"


@pytest.mark.asyncio
async def test_cancellation_under_backpressure_reclaims_everything(long_s16le_audio):
    """真实背压（上传协程正卡在 ws.send）下取消：CancelledError 上抛且不留内部任务。"""
    async with FakeRemoteServer(
        progress_kind="none", on_upload_complete="silent"
    ) as server:
        remote = server.remote
        caller = asyncio.create_task(
            transcribe_file(long_s16le_audio, server.url, encoding="s16le",
                            idle_timeout=IDLE, deadline_total=90)
        )
        await _wait_for_frames(remote, 1, timeout=20)
        remote.read_gate.clear()
        await asyncio.sleep(IDLE / 2)
        caller.cancel()
        done, _ = await asyncio.wait({caller}, timeout=20)
        leaked = _pending_sdk_tasks()

    assert caller in done and caller.cancelled(), "调用方取消没有传播为 CancelledError"
    assert leaked == [], f"取消后 SDK 内部任务未回收：{leaked}"


async def _wait_for_frames(remote: FakeRemote, count: int, *, timeout: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while remote.frames_read < count and loop.time() < deadline:
        await asyncio.sleep(0.05)
    return remote.frames_read >= count


def test_scenario_constants_match_the_real_frame_layout():
    """场景常量必须与真实上传帧布局一致，否则矩阵测的不是被测条件。"""
    from sdk.capswriter_asr.client import _audio_frame_count

    assert _audio_frame_count(16000 * 2 * AUDIO_SECONDS, "s16le") == FRAME_TOTAL
    assert FRAME_TOTAL >= 6, "帧数太少，回环 socket 可能把整份负载吞下，背压前提不成立"
    assert inspect.iscoroutinefunction(transcribe_file)