"""SDK v2 的跨 HTTP、子进程和 WebSocket 契约测试。"""
from __future__ import annotations

import asyncio
import ast
import base64
import functools
import inspect
import json
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio
import soundfile as sf
import websockets
from websockets.datastructures import Headers

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_PACKAGE = REPO_ROOT / "sdk" / "capswriter_asr"
sys.path.insert(0, str(REPO_ROOT / "sdk"))

import capswriter_asr.client as sdk_client
from capswriter_asr import AsrError, Transcript, transcribe_file
from capswriter_asr.client import _count_decoded_samples as _real_count_decoded_samples
from capswriter_asr.client import _transcode
from capswriter_asr.outputs import _fmt_timestamp, write_srt


@pytest_asyncio.fixture(autouse=True)
async def assert_async_processes_are_reaped(monkeypatch):
    original = asyncio.create_subprocess_exec
    processes = []

    async def tracked(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", tracked)
    yield
    assert all(process.returncode is not None for process in processes), [
        process.pid for process in processes if process.returncode is None
    ]


@pytest.fixture(autouse=True)
def fake_media_tools(tmp_path, monkeypatch):
    """CI runner 不保证安装 ffmpeg；脚本保留真实 argv/stdout 子进程边界。

    只 stub ffmpeg：SDK 已不依赖 ffprobe，改从自己发出的字节流解码累计样本数。
    """
    tool_dir = tmp_path / "media-tools"
    tool_dir.mkdir()
    args_log = tmp_path / "ffmpeg-argv.txt"
    ffmpeg = tool_dir / "ffmpeg"
    ffmpeg.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPSWRITER_TEST_FFMPEG_ARGV\"\n"
        "printf 'synthetic-flac-stream0'\n",
        encoding="utf-8",
    )
    ffmpeg.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tool_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CAPSWRITER_TEST_FFMPEG_ARGV", str(args_log))

    async def fake_decoded_samples(*_args):
        return 16000

    monkeypatch.setattr(sdk_client, "_count_decoded_samples", fake_decoded_samples)
    return args_log


def make_audio(path: Path, seconds: float = 1.0) -> Path:
    samples = np.zeros(int(16000 * seconds), dtype=np.float32)
    sf.write(path, samples, 16000)
    return path


def final_result(**overrides):
    result = {
        "type": "result",
        "is_final": True,
        "text": "你好，世界。",
        "tokens": ["你", "好", "，", "世", "界", "。"],
        "timestamps": [0.0, 0.3, 0.5, 0.7, 0.9, 1.1],
        "duration": 2.0,
    }
    result.update(overrides)
    return result


def _release_waiter(waiter: asyncio.Future, *args) -> None:
    if not waiter.done():
        waiter.set_result(None)


async def _cancel_and_wait(fut, loop) -> None:
    """复刻 asyncio.tasks._cancel_and_wait。"""
    waiter = loop.create_future()
    _release_waiter_arg = functools.partial(_release_waiter, waiter)
    fut.add_done_callback(_release_waiter_arg)
    try:
        fut.cancel()
        await waiter
    finally:
        fut.remove_done_callback(_release_waiter_arg)


async def _legacy_wait_for(fut, timeout):
    """逐行复刻 CPython ≤3.11 的 asyncio.wait_for（含吞取消分支）。

    Python 3.12 起 wait_for 改写成 `async with timeouts.timeout(...)`，取消了
    「被等待对象已完成时把 CancelledError 吞掉并返回结果」这个分支。生产容器是
    python:3.11-slim（下游 VideoTranscriptAPI@ff92a175 的 docker/Dockerfile），
    所以 3.12 的 CI 上复现不到 issue #65；用这个 fixture 把旧语义装回去。
    """
    loop = asyncio.get_running_loop()
    if timeout is None:
        return await fut
    waiter = loop.create_future()
    timeout_handle = loop.call_later(timeout, _release_waiter, waiter)
    cb = functools.partial(_release_waiter, waiter)
    fut = asyncio.ensure_future(fut)
    fut.add_done_callback(cb)
    try:
        try:
            await waiter
        except asyncio.CancelledError:
            if fut.done():
                return fut.result()  # ← 旧版本在这里吞掉取消
            fut.remove_done_callback(cb)
            await _cancel_and_wait(fut, loop)
            raise
        if fut.done():
            return fut.result()
        fut.remove_done_callback(cb)
        await _cancel_and_wait(fut, loop)
        try:
            return fut.result()
        except asyncio.CancelledError as exc:
            raise asyncio.TimeoutError from exc
    finally:
        timeout_handle.cancel()


@pytest.fixture
def legacy_wait_for_semantics(monkeypatch):
    """让本测试跑在 CPython ≤3.11 的 wait_for 取消语义下（见 _legacy_wait_for）。"""
    monkeypatch.setattr(asyncio, "wait_for", _legacy_wait_for)


def _pending_sdk_tasks() -> list[str]:
    """列出仍未结束的 SDK 内部任务；假服务端的任务不在此列。

    只收 SDK 自己的协程名：idle_watch 每轮新建的 Queue.get getter 实测在
    transcribe_file 返回前一定会被事件循环收尾（见 root-cause.md 第 4 节的注入实验），
    把它写进断言并不能在“取消后不 await”时转红，属于恒真断言，故不收。
    """
    pending = []
    for task in asyncio.all_tasks():
        qualname = getattr(task.get_coro(), "__qualname__", "")
        if qualname.startswith(("_transcribe_connected.", "transcribe_file.", "_operation.")):
            if not task.done():
                pending.append(qualname)
    return pending


@asynccontextmanager
async def fake_v2_server(handler, *, health=None, status=200):
    state = {"connections": 0, "frames": [], "final_received": False}
    if isinstance(health, bytes):
        health_body = health
    else:
        health_body = json.dumps(
            health or {"protocol_version": 2, "encodings": ["flac", "ogg_opus", "f32le", "s16le"]}
        ).encode()

    async def process_request(connection, request):
        path = request.path if hasattr(request, "path") else connection
        if path != "/health":
            return None
        headers = Headers()
        headers["Content-Type"] = "application/json"
        if hasattr(request, "path"):
            from websockets.http11 import Response

            return Response(status, HTTPStatus(status).phrase, headers, health_body)
        return HTTPStatus(status), headers, health_body

    async def receive(ws):
        state["connections"] += 1
        await handler(ws, state)

    async with websockets.serve(
        receive,
        "127.0.0.1",
        0,
        process_request=process_request,
        ping_interval=None,
        max_size=None,
        max_queue=None,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}", state


async def accept_and_finish(ws, state):
    async for message in ws:
        frame = json.loads(message)
        state["frames"].append(frame)
        if frame["is_final"]:
            state["final_received"] = True
            await ws.send(json.dumps(final_result()))
            return


@pytest.mark.asyncio
async def test_flac_upload_matches_transcode_and_v2_frames(fake_media_tools, tmp_path):
    audio_path = make_audio(tmp_path / "source.wav", 5)
    expected = await _transcode(audio_path, "flac")
    assert fake_media_tools.read_text(encoding="utf-8").splitlines() == [
        "-nostdin",
        "-i",
        str(audio_path),
        "-map",
        "0:a:0",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "flac",
        "pipe:1",
    ]
    async with fake_v2_server(accept_and_finish) as (url, state):
        transcript = await transcribe_file(audio_path, url)
    assert isinstance(transcript, Transcript)
    assert b"".join(base64.b64decode(frame["data"]) for frame in state["frames"]) == expected
    assert state["frames"]
    task_ids = {frame["task_id"] for frame in state["frames"]}
    assert len(task_ids) == 1
    assert all(frame["encoding"] == "flac" for frame in state["frames"])
    assert all(len(base64.b64decode(frame["data"])) <= 256 * 1024 for frame in state["frames"])
    assert state["frames"][-1]["is_final"] is True
    assert state["frames"][-1]["samples_total"] == 16000
    assert all("samples_total" not in frame for frame in state["frames"][:-1])
    assert transcript.raw["type"] == "result"


@pytest.mark.asyncio
async def test_raw_f32le_frames_are_at_most_sixty_seconds(tmp_path, monkeypatch):
    audio_path = make_audio(tmp_path / "source.wav")
    pcm = b"\0" * (61 * 16000 * 4 + 4)
    monkeypatch.setattr(sdk_client, "_transcode", lambda *_: asyncio.sleep(0, result=pcm))
    async with fake_v2_server(accept_and_finish) as (url, state):
        await transcribe_file(audio_path, url, encoding="f32le")
    chunks = [base64.b64decode(frame["data"]) for frame in state["frames"]]
    assert len(chunks) == 2
    assert all(len(chunk) // 4 <= 60 * 16000 for chunk in chunks)
    assert [frame["is_final"] for frame in state["frames"]] == [False, True]
    assert state["frames"][-1]["samples_total"] == len(pcm) // 4


@pytest.mark.asyncio
async def test_progress_is_received_before_upload_finishes(tmp_path, monkeypatch):
    audio_path = make_audio(tmp_path / "source.wav")
    pcm = b"\0" * (3 * 256 * 1024)
    monkeypatch.setattr(sdk_client, "_transcode", lambda *_: asyncio.sleep(0, result=pcm))
    sent = {"final_send_returned": False}
    original_connect = websockets.connect

    class DelayedConnection:
        def __init__(self, context_manager):
            self.context_manager = context_manager
            self.ws = None
            self.calls = 0

        async def __aenter__(self):
            self.ws = await self.context_manager.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.context_manager.__aexit__(*args)

        async def send(self, message):
            await self.ws.send(message)
            self.calls += 1
            if json.loads(message)["is_final"]:
                sent["final_send_returned"] = True
            if self.calls == 1:
                await asyncio.sleep(0.1)

        async def recv(self):
            return await self.ws.recv()

    def delayed_connect(url, *args, **kwargs):
        assert kwargs["ping_interval"] is None
        assert kwargs["max_size"] is None
        assert kwargs["max_queue"] is None
        if "proxy" in inspect.signature(original_connect).parameters:
            assert kwargs["proxy"] is None
        return DelayedConnection(original_connect(url, *args, **kwargs))

    delayed_connect.__signature__ = inspect.signature(original_connect)

    monkeypatch.setattr(sdk_client.websockets, "connect", delayed_connect)
    progress_observed = []

    async def reply_on_first_frame(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if len(state["frames"]) == 1:
                await ws.send(json.dumps({"type": "result", "is_final": False, "text": "进度"}))
            if frame["is_final"]:
                state["final_received"] = True
                await ws.send(json.dumps(final_result()))
                return

    async with fake_v2_server(reply_on_first_frame) as (url, state):
        await transcribe_file(
            audio_path,
            url,
            encoding="flac",
            on_progress=lambda result: progress_observed.append((result, sent["final_send_returned"])),
        )
    assert progress_observed == [({"type": "result", "is_final": False, "text": "进度"}, False)]
    assert state["final_received"]


@pytest.mark.asyncio
async def test_final_result_returns_without_server_close(
    tmp_path, fake_media_tools, legacy_wait_for_semantics
):
    """issue #65 回归：final 已到达就必须返回，不等服务端关连接、不留悬挂任务。

    复现形态对齐生产：短音频 → 单帧 is_final；服务端回完 final 后**保持连接打开**
    （仓库里的 accept_and_finish 会立刻关连接，恰好避开了这个竞态）。
    legacy_wait_for_semantics 把 CPython ≤3.11（= 生产 python:3.11-slim）的
    wait_for 吞取消语义装回去，使 3.12 的 CI 也能覆盖这条失效边界。
    """
    audio_path = make_audio(tmp_path / "source.wav")
    release = asyncio.Event()

    async def final_then_hold(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if frame["is_final"]:
                state["final_received"] = True
                await ws.send(json.dumps(final_result(
                    task_id=frame["task_id"], text="保持连接的 final。",
                )))
                await release.wait()  # 生产形态：回完 final 不关连接
                return

    outcome = {}

    async def call():
        try:
            outcome["transcript"] = await transcribe_file(audio_path, url)
        except BaseException as exc:  # noqa: BLE001 - 错误也要当结果记下来
            outcome["error"] = exc

    async with fake_v2_server(final_then_hold) as (url, state):
        caller = asyncio.create_task(call())
        done, _ = await asyncio.wait({caller}, timeout=10)
        release.set()
        returned = caller in done
        leaked = _pending_sdk_tasks()

    assert returned, (
        f"final 已到达服务端但 transcribe_file 10 秒内没有返回（issue #65）；outcome={outcome}"
    )
    assert "error" not in outcome, outcome.get("error")
    assert leaked == [], f"SDK 内部任务未被回收：{leaked}"
    transcript = outcome["transcript"]
    assert transcript.text == "保持连接的 final。"
    assert state["final_received"]
    # 跨序列化契约：fake server 只按真实收到的帧回 final。
    assert [frame["is_final"] for frame in state["frames"]] == [True]
    assert len({frame["task_id"] for frame in state["frames"]}) == 1
    assert state["frames"][0]["samples_total"] == 16000
    assert transcript.task_id == state["frames"][0]["task_id"]


@pytest.mark.asyncio
async def test_final_result_returns_without_server_close_no_shim(
    tmp_path, fake_media_tools
):
    """同一形态、不装旧 wait_for 语义的对照：确保上面的红不是 shim 自己造的。"""
    audio_path = make_audio(tmp_path / "source.wav")
    release = asyncio.Event()

    async def final_then_hold(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if frame["is_final"]:
                state["final_received"] = True
                await ws.send(json.dumps(final_result(task_id=frame["task_id"])))
                await release.wait()
                return

    outcome = {}

    async def call():
        try:
            outcome["transcript"] = await transcribe_file(audio_path, url)
        except BaseException as exc:  # noqa: BLE001
            outcome["error"] = exc

    async with fake_v2_server(final_then_hold) as (url, state):
        caller = asyncio.create_task(call())
        done, _ = await asyncio.wait({caller}, timeout=10)
        release.set()
        returned = caller in done
        leaked = _pending_sdk_tasks()

    assert returned, f"对照用例也不返回；outcome={outcome}"
    assert "error" not in outcome, outcome.get("error")
    assert leaked == [], f"SDK 内部任务未被回收：{leaked}"
    assert state["frames"][0]["is_final"] is True


@pytest.mark.asyncio
async def test_upload_failure_is_not_masked_by_final(
    tmp_path, fake_media_tools, monkeypatch
):
    """上传失败不能被改判成成功的转录：必须上抛 AsrError，而不是返回 Transcript。

    注意：这里**故意不复现「同拍完成」**——upload 是否恰好停在最后一帧的 send 上取决于
    真实 socket 时序，实测在 3.12 修前红、3.11 修后绿，同一个场景两种结果，无法确定性构造。
    因此只锁「失败不被 final 盖掉」这条契约本身（顺序确定即可），同拍的不确定性另在
    root-cause.md 记录，不写成会飘的断言。
    """
    audio_path = make_audio(tmp_path / "source.wav")
    original_connect = websockets.connect

    class FailingSendConnection:
        def __init__(self, context_manager):
            self.context_manager = context_manager
            self.ws = None

        async def __aenter__(self):
            self.ws = await self.context_manager.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.context_manager.__aexit__(*args)

        async def send(self, _message):
            raise OSError("connection reset by peer")

        async def recv(self):
            return await self.ws.recv()

    def failing_connect(url, **kwargs):
        options = {k: v for k, v in kwargs.items() if v is not None or k == "proxy"}
        return FailingSendConnection(original_connect(url, **options))

    failing_connect.__signature__ = inspect.signature(original_connect)
    monkeypatch.setattr(sdk_client.websockets, "connect", failing_connect)

    async def silent(ws, state):
        async for message in ws:
            state["frames"].append(json.loads(message))

    async with fake_v2_server(silent) as (url, state):
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url, deadline_total=20)

    assert caught.value.code == "connection_lost"
    assert "connection reset by peer" in caught.value.message
    # 失败发生在上传阶段：连接已建立，但服务端没收到任何帧。
    assert state["connections"] == 1
    assert state["frames"] == []
    assert _pending_sdk_tasks() == []


@pytest.mark.asyncio
async def test_idle_timeout_still_fires_after_upload(tmp_path, fake_media_tools):
    """修复后 idle 预算仍然生效：上传结束且服务端不再回消息，按 idle_timeout 上抛。"""
    audio_path = make_audio(tmp_path / "source.wav")

    async def swallow_everything(ws, state):
        async for message in ws:
            state["frames"].append(json.loads(message))

    async with fake_v2_server(swallow_everything) as (url, state):
        started = time.monotonic()
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url, idle_timeout=2, deadline_total=30)
    assert caught.value.code == "timeout"
    assert "上传结束后等待服务端消息超时" in caught.value.message
    assert time.monotonic() - started < 10
    assert state["frames"][-1]["is_final"] is True


@pytest.mark.asyncio
async def test_receive_idle_budget_does_not_fire_during_upload(tmp_path, monkeypatch):
    """发送与接收并行：上传期间不被接收 idle 预算提前终止，上传完成后 idle 才生效。"""
    audio_path = make_audio(tmp_path / "source.wav")
    pcm = b"\0" * (3 * 256 * 1024)
    monkeypatch.setattr(sdk_client, "_transcode", lambda *_: asyncio.sleep(0, result=pcm))
    original_connect = websockets.connect

    class SlowSendConnection:
        def __init__(self, context_manager):
            self.context_manager = context_manager
            self.ws = None

        async def __aenter__(self):
            self.ws = await self.context_manager.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.context_manager.__aexit__(*args)

        async def send(self, message):
            await asyncio.sleep(0.3)  # 每帧 0.3s，总上传 ~0.9s > idle_timeout/3
            await self.ws.send(message)

        async def recv(self):
            return await self.ws.recv()

    def slow_connect(url, **kwargs):
        options = {k: v for k, v in kwargs.items() if v is not None or k == "proxy"}
        return SlowSendConnection(original_connect(url, **options))

    slow_connect.__signature__ = inspect.signature(original_connect)
    monkeypatch.setattr(sdk_client.websockets, "connect", slow_connect)

    async def reply_final(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if frame["is_final"]:
                state["final_received"] = True
                await ws.send(json.dumps(final_result(task_id=frame["task_id"])))

    async with fake_v2_server(reply_final) as (url, state):
        started = time.monotonic()
        transcript = await transcribe_file(audio_path, url, idle_timeout=1, deadline_total=30)
        elapsed = time.monotonic() - started

    assert transcript.text == "你好，世界。"
    assert state["final_received"]
    assert [frame["is_final"] for frame in state["frames"]] == [False, False, True]
    assert elapsed >= 0.9, "上传被提前截断"


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_and_reclaims(tmp_path, fake_media_tools):
    """调用方取消仍然上抛 CancelledError，且不遗留 SDK 内部任务。"""
    audio_path = make_audio(tmp_path / "source.wav")

    async def never_reply(ws, state):
        async for message in ws:
            state["frames"].append(json.loads(message))

    async with fake_v2_server(never_reply) as (url, state):
        task = asyncio.create_task(
            transcribe_file(audio_path, url, idle_timeout=30, deadline_total=60)
        )
        while not state["frames"]:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # 上传已结束、接收仍在等
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=10)
        cancelled = task in done and task.cancelled()
        leaked = _pending_sdk_tasks()

    assert cancelled, "调用方取消后任务既没结束也没处于 cancelled 状态"
    assert leaked == [], f"SDK 内部任务未被回收：{leaked}"


def test_sync_entrypoint_returns_transcript_in_subprocess(tmp_path, fake_media_tools):
    """transcribe_file_sync 在独立子进程里验收，避免 asyncio.run 收尾掩盖异步结论。

    子进程同样装上 CPython ≤3.11 的 wait_for 语义（生产 python:3.11-slim）。
    """
    script = f'''
import asyncio, json, struct, sys, wave
from http import HTTPStatus

sys.path.insert(0, {str(REPO_ROOT)!r})
sys.path.insert(0, {str(REPO_ROOT / "sdk")!r})
import websockets
from websockets.datastructures import Headers
from websockets.http11 import Response

from tests.test_sdk_client import _legacy_wait_for
from capswriter_asr import transcribe_file_sync

asyncio.wait_for = _legacy_wait_for
WAV = {str(tmp_path / "sync.wav")!r}


def make_wav(path, seconds=5.5):
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(struct.pack("<h", 0) * int(16000 * seconds))
    return path


async def process_request(connection, request):
    if request.path != "/health":
        return None
    headers = Headers()
    headers["Content-Type"] = "application/json"
    body = json.dumps({{
        "protocol_version": 2, "role": "server",
        "encodings": ["flac", "ogg_opus", "f32le", "s16le"],
    }}).encode()
    return Response(200, HTTPStatus.OK.phrase, headers, body)


observed = {{"frames": []}}
hold = asyncio.Event()


async def handler(ws):
    async for message in ws:
        frame = json.loads(message)
        observed["frames"].append(frame)
        if frame["is_final"]:
            await ws.send(json.dumps({{
                "type": "result", "is_final": True,
                "task_id": frame["task_id"], "text": "子进程同步入口。",
                "tokens": [], "timestamps": [], "duration": 5.5,
            }}))
            # 生产形态：回完 final 不关连接，等客户端自己返回；
            # 必须有上限，否则外层取消时 Server.__aexit__ 会等这个 handler 等到天荒地老。
            await asyncio.wait_for(hold.wait(), timeout=30)
            return


async def main():
    async with websockets.serve(
        handler, "127.0.0.1", 0, process_request=process_request,
        ping_interval=None, max_size=None, max_queue=None,
    ) as srv:
        url = "ws://127.0.0.1:%d" % srv.sockets[0].getsockname()[1]
        # 同步入口在自己的事件循环里跑（相当于非 asyncio 调用方）
        transcript = await asyncio.to_thread(transcribe_file_sync, WAV, url)
        hold.set()
    print(json.dumps({{
        "text": transcript.text,
        "task_id_matches": transcript.task_id == observed["frames"][0]["task_id"],
        "frames": len(observed["frames"]),
    }}, ensure_ascii=False))


make_wav(WAV)
asyncio.run(asyncio.wait_for(main(), timeout=45))
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=dict(
            os.environ,
            PYTHONPATH=str(REPO_ROOT / "sdk"),
            CAPSWRITER_TEST_FFMPEG_ARGV=str(tmp_path / "child-ffmpeg-argv.txt"),
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {"text": "子进程同步入口。", "task_id_matches": True, "frames": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("status,health,expected_code", [
    (426, None, "server_too_old"),
    (200, {"protocol_version": 1, "encodings": ["flac"]}, "server_too_old"),
    (200, {"protocol_version": "2", "encodings": ["flac"]}, "server_too_old"),
    (200, b"not json", "server_too_old"),
    (200, {"protocol_version": 2, "encodings": ["f32le"]}, "unsupported_encoding"),
])
async def test_health_gate_rejects_before_websocket(tmp_path, status, health, expected_code):
    audio_path = make_audio(tmp_path / "source.wav")
    async with fake_v2_server(accept_and_finish, health=health, status=status) as (url, state):
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url)
    assert caught.value.code == expected_code
    assert state["connections"] == 0


@pytest.mark.asyncio
async def test_server_error_code_and_retryable_are_preserved(tmp_path):
    audio_path = make_audio(tmp_path / "source.wav")

    async def send_error(ws, state):
        await ws.recv()
        await ws.send(json.dumps({
            "type": "error", "code": "inference_failed", "message": "engine failed", "retryable": True
        }))

    async with fake_v2_server(send_error) as (url, _):
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url)
    assert caught.value.code == "inference_failed"
    assert caught.value.retryable is True
    assert caught.value.message == "engine failed"


@pytest.mark.asyncio
async def test_idle_timeout_is_independent_of_incoming_messages(tmp_path):
    audio_path = make_audio(tmp_path / "source.wav")

    async def never_reply(ws, _state):
        await ws.recv()
        await ws.recv()

    async with fake_v2_server(never_reply) as (url, _):
        started = time.monotonic()
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url, idle_timeout=2, deadline_total=10)
    assert caught.value.code == "timeout"
    assert time.monotonic() - started < 5


@pytest.mark.asyncio
async def test_blocked_send_uses_idle_timeout(tmp_path, monkeypatch):
    audio_path = make_audio(tmp_path / "source.wav")
    original_connect = websockets.connect
    proxy_unspecified = object()

    class BlockedSendConnection:
        def __init__(self, context_manager):
            self.context_manager = context_manager
            self.ws = None

        async def __aenter__(self):
            self.ws = await self.context_manager.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.context_manager.__aexit__(*args)

        async def send(self, _message):
            await asyncio.Future()

        async def recv(self):
            return await self.ws.recv()

    def blocked_connect(url, *, ping_interval=None, max_size=None, max_queue=None, proxy=proxy_unspecified):
        options = {"ping_interval": ping_interval, "max_size": max_size, "max_queue": max_queue}
        if proxy is not proxy_unspecified:
            options["proxy"] = proxy
        return BlockedSendConnection(original_connect(url, **options))

    blocked_connect.__signature__ = inspect.signature(original_connect)
    monkeypatch.setattr(sdk_client.websockets, "connect", blocked_connect)

    async with fake_v2_server(accept_and_finish) as (url, _state):
        started = time.monotonic()
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url, idle_timeout=2, deadline_total=10)
    assert caught.value.code == "timeout"
    assert "发送音频帧" in caught.value.message
    assert time.monotonic() - started < 5


@pytest.mark.asyncio
async def test_total_deadline_expires_despite_continuous_progress(tmp_path):
    audio_path = make_audio(tmp_path / "source.wav")

    async def progress_forever(ws, _state):
        await ws.recv()
        while True:
            await ws.send(json.dumps({"type": "result", "is_final": False, "text": "进度"}))
            await asyncio.sleep(0.05)

    async with fake_v2_server(progress_forever) as (url, _):
        with pytest.raises(AsrError) as caught:
            await transcribe_file(
                audio_path,
                url,
                deadline_total=3,
                idle_timeout=10,
                on_progress=lambda _result: None,
            )
    assert caught.value.code == "timeout"


@pytest.mark.asyncio
async def test_close_without_error_frame_maps_to_connection_lost(tmp_path):
    audio_path = make_audio(tmp_path / "source.wav")

    async def close_without_error(ws, _state):
        await ws.recv()
        await ws.close(code=4000)

    async with fake_v2_server(close_without_error) as (url, _):
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url)
    assert caught.value.code == "connection_lost"


@pytest.mark.asyncio
async def test_websocket_connection_failure_maps_to_connection_lost(tmp_path, monkeypatch):
    audio_path = make_audio(tmp_path / "source.wav")

    def refuse_connection(_url, **_kwargs):
        raise OSError("connection refused")

    async with fake_v2_server(accept_and_finish) as (url, _):
        monkeypatch.setattr(sdk_client.websockets, "connect", refuse_connection)
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url)
    assert caught.value.code == "connection_lost"


@pytest.mark.asyncio
async def test_transcode_failure_uses_decode_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(sdk_client.shutil, "which", lambda _name: None)
    with pytest.raises(AsrError) as caught:
        await _transcode(tmp_path / "source.wav", "flac")
    assert caught.value.code == "decode_failed"


def test_sdk_package_does_not_import_server_core():
    for source in SDK_PACKAGE.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("core") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("core")


def test_legacy_srt_segmentation_and_timestamp_rounding(tmp_path):
    transcript = Transcript(
        text="你好，世界！测试完毕。",
        tokens=["你", "好", "，", "世", "界", "！", "测", "试", "完", "毕", "。"],
        timestamps=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        duration=1.5,
        raw={},
    )
    out = tmp_path / "legacy.srt"
    write_srt(transcript, out)
    assert out.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:00,600\n你好，世界！\n\n"
        "2\n00:00:00,600 --> 00:00:01,500\n测试完毕。\n"
    )
    assert [_fmt_timestamp(value) for value in (3661.5, 1.9999, 59.9995, 0.1234)] == [
        "01:01:01,500",
        "00:00:02,000",
        "00:01:00,000",
        "00:00:00,123",
    ]


@pytest.mark.asyncio
async def test_count_decoded_samples_allows_decoder_exit_before_stdin_close(
    tmp_path, monkeypatch
):
    """回归锁死：解码子进程不读 stdin 即退出 0 时，样本计数不得误报 decode_failed。

    经真实 asyncio 子进程路径复现 CI 偶发「无法读取 ffmpeg 解码输出:
    Connection lost」：输入大于管道缓冲，feed 的 drain 必然在子进程退出后返回，
    修复前稳定红。
    """
    tool_dir = tmp_path / "decoder-exit-tools"
    tool_dir.mkdir()
    ffmpeg = tool_dir / "ffmpeg"
    ffmpeg.write_text("#!/bin/sh\nprintf 'synthetic-flac-stream0'\n", encoding="utf-8")
    ffmpeg.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tool_dir}{os.pathsep}{os.environ['PATH']}")
    large_audio = b"synthetic-flac-stream0" * (1024 * 1024 // 22 + 1)
    samples = await _real_count_decoded_samples(large_audio, "flac")
    assert samples == 11


@pytest.mark.asyncio
async def test_missing_audio_raises_decode_failed(tmp_path):
    with pytest.raises(AsrError) as caught:
        await transcribe_file(tmp_path / "missing.wav", "ws://127.0.0.1:1")
    assert caught.value.code == "decode_failed"


def test_cli_help_exits_successfully():
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "sdk"))
    result = subprocess.run(
        [sys.executable, "-m", "capswriter_asr", "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--url" in result.stdout


@pytest.mark.asyncio
async def test_cli_writes_srt_txt_and_json_with_legacy_srt_layout(tmp_path):
    audio_path = make_audio(tmp_path / "clip.wav")
    out_dir = tmp_path / "outputs"

    async def finish_with_legacy_fixture(ws, state):
        await accept_and_finish(ws, state)

    async with fake_v2_server(finish_with_legacy_fixture) as (url, _state):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "capswriter_asr",
            str(audio_path),
            "--url",
            url,
            "--out-dir",
            str(out_dir),
            "--format",
            "srt,txt,json",
            env=dict(os.environ, PYTHONPATH=str(REPO_ROOT / "sdk")),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    assert process.returncode == 0, (stdout, stderr)
    assert (out_dir / "clip.srt").read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:01,600\n你好，世界。\n"
    )
    assert (out_dir / "clip.txt").read_text(encoding="utf-8") == "你好，世界。"
    assert json.loads((out_dir / "clip.json").read_text(encoding="utf-8"))["type"] == "result"
