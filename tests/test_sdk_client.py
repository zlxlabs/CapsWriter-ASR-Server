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

    idle_watch 的 Queue.get getter 由 sdk_queue_getter_tasks 直接保留 Task 身份，
    不在这里按协程名猜测；这个列表只用于 SDK 外层协程的现有收尾断言。
    """
    pending = []
    for task in asyncio.all_tasks():
        qualname = getattr(task.get_coro(), "__qualname__", "")
        if (
            qualname == sdk_client._receive.__qualname__
            or qualname.startswith(("_transcribe_connected.", "transcribe_file.", "_operation."))
        ):
            if not task.done():
                pending.append(qualname)
    return pending


@pytest.fixture
def sdk_queue_getter_tasks(monkeypatch):
    """按 asyncio.Queue.get 的代码对象追踪 ensure_future 返回的真实 Task。"""
    tasks = []
    created = asyncio.Event()
    original_ensure_future = asyncio.ensure_future
    queue_get_code = asyncio.Queue.get.__code__

    def tracked_ensure_future(coro, *args, **kwargs):
        task = original_ensure_future(coro, *args, **kwargs)
        caller = inspect.currentframe().f_back
        if (
            inspect.iscoroutine(coro)
            and coro.cr_code is queue_get_code
            and caller.f_code.co_filename == sdk_client.__file__
        ):
            tasks.append(task)
            created.set()
        return task

    monkeypatch.setattr(asyncio, "ensure_future", tracked_ensure_future)
    return tasks, created


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
            # 服务端回帧必带 task_id（core/protocol.py）：SDK 只把与本任务匹配的消息
            # 当进展，不带 task_id 的回帧会被按协议忽略。
            await ws.send(json.dumps(final_result(task_id=frame["task_id"])))
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

        @property
        def transport(self):
            # SDK 在异常路径上靠它中止传输；测试替身必须和真实连接暴露同一个出口。
            return self.ws.transport

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
                await ws.send(json.dumps({"type": "result", "is_final": False,
                                          "text": "进度", "task_id": frame["task_id"]}))
            if frame["is_final"]:
                state["final_received"] = True
                await ws.send(json.dumps(final_result(task_id=frame["task_id"])))
                return

    async with fake_v2_server(reply_on_first_frame) as (url, state):
        await transcribe_file(
            audio_path,
            url,
            encoding="flac",
            on_progress=lambda result: progress_observed.append((result, sent["final_send_returned"])),
        )
    assert [result for result, _ in progress_observed] == [
        {"type": "result", "is_final": False, "text": "进度",
         "task_id": state["frames"][0]["task_id"]}
    ]
    assert [flag for _, flag in progress_observed] == [False]
    assert state["final_received"]


@pytest.mark.asyncio
async def test_final_result_returns_without_server_close(
    tmp_path, fake_media_tools, legacy_wait_for_semantics, sdk_queue_getter_tasks
):
    """issue #65 回归：final 已到达就必须返回，不等服务端关连接、不留悬挂任务。

    复现形态对齐生产：短音频 → 单帧 is_final；服务端回完 final 后**保持连接打开**
    （仓库里的 accept_and_finish 会立刻关连接，恰好避开了这个竞态）。
    legacy_wait_for_semantics 把 CPython ≤3.11（= 生产 python:3.11-slim）的
    wait_for 吞取消语义装回去，使 3.12 的 CI 也能覆盖这条失效边界。
    """
    audio_path = make_audio(tmp_path / "source.wav")
    release = asyncio.Event()
    allow_final = asyncio.Event()
    getter_tasks, getter_created = sdk_queue_getter_tasks

    async def final_then_hold(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if frame["is_final"]:
                state["final_received"] = True
                await allow_final.wait()
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
        getter_waiter = asyncio.create_task(getter_created.wait())
        getter_done, _ = await asyncio.wait({getter_waiter}, timeout=5)
        getter_observed = getter_waiter in getter_done
        pending_before_final = _pending_sdk_tasks()
        allow_final.set()
        done, _ = await asyncio.wait({caller}, timeout=10)
        release.set()
        returned = caller in done
        if not getter_waiter.done():
            getter_waiter.cancel()
            await asyncio.gather(getter_waiter, return_exceptions=True)
        leaked = _pending_sdk_tasks()

    assert returned, (
        f"final 已到达服务端但 transcribe_file 10 秒内没有返回（issue #65）；outcome={outcome}"
    )
    assert getter_observed, "final 返回路径没有观察到 SDK 创建的 Queue.get Task"
    assert sdk_client._receive.__qualname__ in pending_before_final, pending_before_final
    assert getter_tasks and all(task.done() for task in getter_tasks), getter_tasks
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
async def test_upload_failure_is_not_masked_by_final_when_both_tasks_done(
    tmp_path, fake_media_tools, monkeypatch
):
    """真实 wire final 与 send 异常进入同一 done 集合时，异常仍按契约优先上抛。"""
    audio_path = make_audio(tmp_path / "source.wav")
    original_connect = websockets.connect
    original_receive = sdk_client._receive
    original_wait = asyncio.wait
    original_create_task = asyncio.create_task
    receive_ready = asyncio.Event()
    release_server = asyncio.Event()
    loop = asyncio.get_running_loop()
    upload_gate = loop.create_future()
    receive_gate = loop.create_future()
    upload_task = {}
    receive_task = {}
    observed_same_done = []

    def tracked_create_task(coro, *args, **kwargs):
        task = original_create_task(coro, *args, **kwargs)
        code = getattr(coro, "cr_code", None)
        if (
            code is not None
            and code.co_filename == sdk_client.__file__
            and code.co_name == "upload"
        ):
            upload_task["task"] = task
        elif code is tracked_receive.__code__:
            receive_task["task"] = task
        return task

    monkeypatch.setattr(asyncio, "create_task", tracked_create_task)

    class FailingSendConnection:
        def __init__(self, context_manager):
            self.context_manager = context_manager
            self.ws = None

        async def __aenter__(self):
            self.ws = await self.context_manager.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.context_manager.__aexit__(*args)

        @property
        def transport(self):
            # SDK 在异常路径上靠它中止传输；测试替身必须和真实连接暴露同一个出口。
            return self.ws.transport

        async def send(self, message):
            await self.ws.send(message)
            await receive_ready.wait()
            await upload_gate
            raise OSError("connection reset by peer")

        async def recv(self):
            return await self.ws.recv()

    def failing_connect(url, **kwargs):
        options = {k: v for k, v in kwargs.items() if v is not None or k == "proxy"}
        return FailingSendConnection(original_connect(url, **options))

    failing_connect.__signature__ = inspect.signature(original_connect)
    monkeypatch.setattr(sdk_client.websockets, "connect", failing_connect)

    async def tracked_receive(ws, *, task_id, on_progress, idle_messages, mark_progress):
        result = await original_receive(
            ws, task_id=task_id, on_progress=on_progress,
            idle_messages=idle_messages, mark_progress=mark_progress,
        )
        receive_ready.set()
        # Queue both task resumptions before asyncio.wait handles either completion.
        loop.call_soon(upload_gate.set_result, None)
        loop.call_soon(receive_gate.set_result, None)
        await receive_gate
        return result

    async def tracked_wait(tasks, *args, **kwargs):
        done, pending = await original_wait(tasks, *args, **kwargs)
        upload = upload_task.get("task")
        receive = receive_task.get("task")
        if upload is not None and receive is not None and upload in tasks and receive in tasks:
            # Test-only scheduler gate: wait for both real SDK tasks to finish before
            # returning the actual completed Task identities as one decision set.
            if upload not in done or receive not in done:
                together, _ = await original_wait(
                    {upload, receive}, return_when=asyncio.ALL_COMPLETED
                )
                done = done | together
            observed_same_done.append(upload in done and receive in done)
        return done, pending

    monkeypatch.setattr(sdk_client, "_receive", tracked_receive)
    monkeypatch.setattr(asyncio, "wait", tracked_wait)

    async def final_then_hold(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if frame["is_final"]:
                state["final_received"] = True
                state["response_task_id"] = frame["task_id"]
                await ws.send(json.dumps(final_result(task_id=frame["task_id"])))
                await release_server.wait()
                return

    caught_error = None
    async with fake_v2_server(final_then_hold) as (url, state):
        try:
            try:
                await transcribe_file(audio_path, url, deadline_total=20)
            except AsrError as exc:
                caught_error = exc
            else:
                assert False, "同轮合法 final 覆盖了 upload 的 send 异常"
        finally:
            release_server.set()

    assert caught_error is not None
    assert caught_error.code == "connection_lost"
    assert "connection reset by peer" in caught_error.message
    assert state["connections"] == 1
    assert state["final_received"]
    assert len(state["frames"]) == 1
    frame = state["frames"][0]
    assert frame["is_final"] is True
    assert state["response_task_id"] == frame["task_id"]
    assert observed_same_done == [True], "send 异常与合法 final 未同轮进入 asyncio.wait done"
    assert _pending_sdk_tasks() == []


@pytest.mark.asyncio
async def test_idle_timeout_still_fires_after_upload(tmp_path, fake_media_tools):
    """上传结束且服务端不再回消息：按 idle_timeout 上抛，消息报「等待结果」与已发帧数。"""
    audio_path = make_audio(tmp_path / "source.wav")

    async def swallow_everything(ws, state):
        async for message in ws:
            state["frames"].append(json.loads(message))

    async with fake_v2_server(swallow_everything) as (url, state):
        started = time.monotonic()
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url, idle_timeout=2, deadline_total=30)
    assert caught.value.code == "timeout"
    assert caught.value.message.startswith("等待结果连续 2 秒没有进展")
    assert "已发送 1/1 帧" in caught.value.message
    assert "收到中间结果 0 条" in caught.value.message
    assert time.monotonic() - started < 10
    assert state["frames"][-1]["is_final"] is True


@pytest.mark.asyncio
async def test_receive_idle_budget_does_not_fire_while_uploads_keep_succeeding(
    tmp_path, monkeypatch, sdk_queue_getter_tasks
):
    """上传耗时超过一个 idle 窗口仍活着：每帧都真的发出去就算真实进展。

    idle_watch 从连接建立就启动（旧实现要等 upload_done 才启动），所以本用例同时锁住
    「上传阶段已在监视」；上传完成后上行一停，就按 idle 失败。
    """
    audio_path = make_audio(tmp_path / "source.wav")
    pcm = b"\0" * (5 * 256 * 1024)
    monkeypatch.setattr(sdk_client, "_transcode", lambda *_: asyncio.sleep(0, result=pcm))
    original_connect = websockets.connect
    idle_timeout = 1.0
    send_delay = 0.5
    final_send_entered = asyncio.Event()
    release_final_send = asyncio.Event()
    four_frames_received = asyncio.Event()
    getter_tasks, getter_created = sdk_queue_getter_tasks
    received_messages = []
    send_durations = []
    first_send_at = None
    final_send_returned_at = None

    class SlowSendConnection:
        def __init__(self, context_manager):
            self.context_manager = context_manager
            self.ws = None

        async def __aenter__(self):
            self.ws = await self.context_manager.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.context_manager.__aexit__(*args)

        @property
        def transport(self):
            # SDK 在异常路径上靠它中止传输；测试替身必须和真实连接暴露同一个出口。
            return self.ws.transport

        async def send(self, message):
            nonlocal first_send_at, final_send_returned_at
            frame = json.loads(message)
            started = time.monotonic()
            if first_send_at is None:
                first_send_at = started
            await asyncio.sleep(send_delay)
            if frame["is_final"]:
                final_send_entered.set()
                await release_final_send.wait()
            await self.ws.send(message)
            send_durations.append(time.monotonic() - started)
            if frame["is_final"]:
                final_send_returned_at = time.monotonic()

        async def recv(self):
            message = await self.ws.recv()
            received_messages.append(message)
            return message

    def slow_connect(url, **kwargs):
        options = {k: v for k, v in kwargs.items() if v is not None or k == "proxy"}
        return SlowSendConnection(original_connect(url, **options))

    slow_connect.__signature__ = inspect.signature(original_connect)
    monkeypatch.setattr(sdk_client.websockets, "connect", slow_connect)

    async def swallow_everything(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if len(state["frames"]) == 4:
                four_frames_received.set()

    async with fake_v2_server(swallow_everything) as (url, state):
        caller = asyncio.create_task(
            transcribe_file(audio_path, url, idle_timeout=idle_timeout, deadline_total=15)
        )
        final_gate_waiter = asyncio.create_task(final_send_entered.wait())
        final_gate_done, _ = await asyncio.wait({final_gate_waiter}, timeout=5)
        four_frames_waiter = asyncio.create_task(four_frames_received.wait())
        four_frames_done, _ = await asyncio.wait({four_frames_waiter}, timeout=3)
        upload_elapsed_at_gate = time.monotonic() - first_send_at if first_send_at else 0
        caller_alive_during_upload = not caller.done()
        no_receive_during_upload = received_messages == []
        getter_created_during_upload = getter_created.is_set()
        frames_before_final = [frame["is_final"] for frame in state["frames"]]
        release_final_send.set()
        getter_waiter = asyncio.create_task(getter_created.wait())
        getter_done, _ = await asyncio.wait({getter_waiter}, timeout=5)
        getter_observed_after_upload = getter_waiter in getter_done
        caller_done, _ = await asyncio.wait({caller}, timeout=5)
        caller_finished = caller in caller_done
        error = caller.exception() if caller_finished and not caller.cancelled() else None
        if not caller_finished:
            caller.cancel()
            caller_cleanup_done, _ = await asyncio.wait({caller}, timeout=5)
            caller_finished = caller in caller_cleanup_done
            if caller_finished and not caller.cancelled():
                error = caller.exception()
        for waiter in (final_gate_waiter, four_frames_waiter, getter_waiter):
            if not waiter.done():
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)

    assert final_gate_done and four_frames_done, "慢上传屏障未到达"
    assert upload_elapsed_at_gate > idle_timeout * 1.5
    assert caller_alive_during_upload, "idle 预算在上传期间终止了调用"
    assert no_receive_during_upload, "上传期间 SDK 收到了服务端消息"
    assert getter_created_during_upload, "上传期间没有创建 idle Queue.get"
    assert frames_before_final == [False, False, False, False]
    assert caller_finished, "上传完成后 idle 未在有界时间内结束调用"
    assert isinstance(error, AsrError) and error.code == "timeout", error
    # 上传完成后上行彻底停下：只能在「等待结果」阶段按 idle 失败，不能回退到
    # 「上传结束后等待服务端消息超时」这种把上传当成已完成前提的措辞。
    assert error.message.startswith("等待结果连续"), error.message
    assert "已发送 5/5 帧" in error.message, error.message
    assert getter_observed_after_upload
    assert getter_tasks and all(task.done() for task in getter_tasks), getter_tasks
    assert final_send_returned_at is not None and first_send_at is not None
    upload_duration = final_send_returned_at - first_send_at
    assert upload_duration > idle_timeout * 1.8
    assert len(send_durations) == 5
    # 逐帧 send 时限已删除：这里的每帧耗时仍短于 idle，但不再是判据。
    assert received_messages == []
    assert [frame["is_final"] for frame in state["frames"]] == [False, False, False, False, True]


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_and_reclaims(
    tmp_path, fake_media_tools, sdk_queue_getter_tasks
):
    """调用方取消仍然上抛 CancelledError，且不遗留 SDK 内部任务。"""
    audio_path = make_audio(tmp_path / "source.wav")
    getter_tasks, getter_created = sdk_queue_getter_tasks

    async def never_reply(ws, state):
        async for message in ws:
            state["frames"].append(json.loads(message))

    async with fake_v2_server(never_reply) as (url, state):
        task = asyncio.create_task(
            transcribe_file(audio_path, url, idle_timeout=1, deadline_total=3)
        )
        getter_waiter = asyncio.create_task(getter_created.wait())
        getter_done, _ = await asyncio.wait({getter_waiter}, timeout=5)
        getter_observed = getter_waiter in getter_done
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=6)
        cancelled = task in done and task.cancelled()
        if not getter_waiter.done():
            getter_waiter.cancel()
            await asyncio.gather(getter_waiter, return_exceptions=True)
        leaked = _pending_sdk_tasks()

    assert getter_observed, "调用方取消路径没有观察到 SDK 创建的 Queue.get Task"
    assert getter_tasks and all(task.done() for task in getter_tasks), getter_tasks
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
async def test_server_error_code_and_retryable_are_preserved(
    tmp_path, sdk_queue_getter_tasks
):
    audio_path = make_audio(tmp_path / "source.wav")
    getter_tasks, getter_created = sdk_queue_getter_tasks
    allow_error = asyncio.Event()

    async def send_error(ws, state):
        async for message in ws:
            frame = json.loads(message)
            state["frames"].append(frame)
            if frame["is_final"]:
                await allow_error.wait()
                await ws.send(json.dumps({
                    "type": "error", "task_id": frame["task_id"],
                    "code": "inference_failed", "message": "engine failed",
                    "retryable": True,
                }))
                return

    async with fake_v2_server(send_error) as (url, _):
        caller = asyncio.create_task(transcribe_file(audio_path, url))
        getter_waiter = asyncio.create_task(getter_created.wait())
        getter_done, _ = await asyncio.wait({getter_waiter}, timeout=5)
        getter_observed = getter_waiter in getter_done
        allow_error.set()
        caller_done, _ = await asyncio.wait({caller}, timeout=10)
        caller_finished = caller in caller_done
        error = None
        if caller_finished and not caller.cancelled():
            try:
                caller.result()
            except AsrError as exc:
                error = exc
        if not getter_waiter.done():
            getter_waiter.cancel()
            await asyncio.gather(getter_waiter, return_exceptions=True)
    assert caller_finished, "服务端 error 后调用没有在有界时间内结束"
    assert getter_observed, "服务端 error 路径没有观察到 SDK 创建的 Queue.get Task"
    assert getter_tasks and all(task.done() for task in getter_tasks), getter_tasks
    assert isinstance(error, AsrError)
    assert error.code == "inference_failed"
    assert error.retryable is True
    assert error.message == "engine failed"


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
async def test_blocked_send_with_silent_server_reports_idle_stall(tmp_path, monkeypatch):
    """ws.send 永久阻塞且下行静默：在「上传」阶段的 idle 上失败，而不是逐帧 send 超时。

    逐帧 send 时限已删除（一次 send 耗时长不等于任务没推进）；本例无任何真实进展，
    因此仍必须有界失败，且消息指向 SDK 自己掌握的事实而不是「服务端不给力」。
    """
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

        @property
        def transport(self):
            # SDK 在异常路径上靠它中止传输；测试替身必须和真实连接暴露同一个出口。
            return self.ws.transport

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
    assert caught.value.message.startswith("上传连续 2 秒没有进展"), caught.value.message
    assert "已发送 0/1 帧" in caught.value.message, caught.value.message
    assert "收到中间结果 0 条" in caught.value.message, caught.value.message
    assert time.monotonic() - started < 5


@pytest.mark.asyncio
async def test_total_deadline_expires_despite_continuous_progress(tmp_path):
    """即使匹配本任务的中间结果一直到达，显式 deadline_total 仍按用户要求终止。

    回帧必须走真实协议 schema 且带 task_id，否则会被 _receive 当噪声滤掉，
    本用例就从「持续进展」退化成「毫无进展」，成了假噪声路径。
    """
    from core.protocol import RecognitionMessage

    audio_path = make_audio(tmp_path / "source.wav")
    sent = {"progress": 0}

    async def progress_forever(ws, _state):
        frame = json.loads(await ws.recv())
        while True:
            await ws.send(RecognitionMessage(
                task_id=frame["task_id"], is_final=False, duration=0.0,
                time_start=0.0, time_submit=0.0, time_complete=0.0, text="进度",
            ).to_json())
            sent["progress"] += 1
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
    assert "转录超过deadline_total" in caught.value.message
    # 被测前提：确实是「持续有效进展」而不是噪声路径。
    assert sent["progress"] >= 5, sent


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
            # 只验证连接异常映射；显式短预算避免该用例等待默认远端预算的取消收尾。
            await transcribe_file(audio_path, url, deadline_total=2)
    assert caught.value.code == "connection_lost"


@pytest.mark.asyncio
async def test_default_budget_connection_refused_returns_in_seconds(tmp_path, monkeypatch):
    """#67：默认预算下连接拒绝必须秒级返回 connection_lost，不得挂到自动预算（120s）。

    这是与上一条用例互补的锁：显式 deadline_total 从不触发 deadline_changed.set()，
    走不到 deadline_watch 的默认预算重锚定，因此上一条用例结构上锁不住 #67。
    断言入口是公共 API transcribe_file，不传 deadline_total。
    """
    audio_path = make_audio(tmp_path / "source.wav")

    def refuse_connection(_url, **_kwargs):
        raise OSError("connection refused")

    async with fake_v2_server(accept_and_finish) as (url, _):
        monkeypatch.setattr(sdk_client.websockets, "connect", refuse_connection)
        started = time.monotonic()
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url)
        elapsed = time.monotonic() - started

    assert caught.value.code == "connection_lost"
    assert elapsed < 5, f"连接拒绝耗时 {elapsed:.3f}s，超过 5s 说明挂到了自动预算"


@pytest.mark.asyncio
async def test_send_failure_surfaces_as_connection_lost(tmp_path, monkeypatch):
    """发送帧抛 WebSocket 异常时必须经Future 结果上抛，映射成 connection_lost。

    upload 改成 asyncio.wait 后，发送失败不再由 await 直接抛出，而是走 sender.result()；
    这条用例盯住该分支不被改写成静默吞错。
    """
    audio_path = make_audio(tmp_path / "source.wav")
    original_connect = websockets.connect
    closed = websockets.exceptions.ConnectionClosedError(None, None)

    class FailingSendConnection:
        def __init__(self, context_manager):
            self.context_manager = context_manager
            self.ws = None

        async def __aenter__(self):
            self.ws = await self.context_manager.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.context_manager.__aexit__(*args)

        @property
        def transport(self):
            # SDK 在异常路径上靠它中止传输；测试替身必须和真实连接暴露同一个出口。
            return self.ws.transport

        async def send(self, _message):
            raise closed

        async def recv(self):
            return await self.ws.recv()

    def failing_connect(url, *, ping_interval=None, max_size=None, max_queue=None, proxy=None):
        options = {"ping_interval": ping_interval, "max_size": max_size, "max_queue": max_queue}
        if proxy is not None:
            options["proxy"] = proxy
        return FailingSendConnection(original_connect(url, **options))

    monkeypatch.setattr(sdk_client.websockets, "connect", failing_connect)

    async with fake_v2_server(accept_and_finish) as (url, _state):
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio_path, url, deadline_total=5, idle_timeout=5)
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
