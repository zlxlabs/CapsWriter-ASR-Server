# coding: utf-8
"""#87：真实 WS 上传途中 ffmpeg 死亡时，客户端必须收到 decode_failed。"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pytest
import websockets

from core.server.connection.audio_decoder import AudioDecodeError

import core.server.connection.ws_recv as ws_recv_module
from tests.harness.client import collect_terminal
from tests.harness.server import ManagedFakeServerHarness
from tests.test_protocol_v2 import _encode_flac, _frame

FORBIDDEN = {"internal", "connection_lost", "decode_stalled"}
_LINUX_PROC = pytest.mark.skipif(
    sys.platform != "linux",
    reason="定位 ffmpeg 子进程依赖 /proc/<pid>/stat",
)
_HAS_SIGKILL = pytest.mark.skipif(
    not hasattr(signal, "SIGKILL"),
    reason="本平台没有 SIGKILL",
)


def _direct_children(ppid: int) -> set[int]:
    kids = set()
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (proc / entry.name / "stat").read_text()
        except OSError:
            continue
        _, _, tail = stat.partition(") ")
        if int(tail.split()[1]) == ppid:
            kids.add(int(entry.name))
    return kids


async def _wait_new_child(ppid: int, known: set[int], timeout: float = 15.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        extra = _direct_children(ppid) - known
        if len(extra) == 1:
            return extra.pop()
        await asyncio.sleep(0.02)
    raise AssertionError(
        f"{timeout}s 内进程 {ppid} 没有出现唯一新子进程，known={known!r} "
        f"now={_direct_children(ppid)!r}"
    )


async def _wait_pid_reaped(pid: int, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"pid {pid} 在 {timeout}s 内仍未被回收")


def _health_active_tasks(websocket_url: str) -> int:
    url = websocket_url.replace("ws://", "http://", 1) + "/health"
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read())["active_tasks"]


async def _wait_active_tasks(url: str, expected: int, timeout: float = 15.0) -> int:
    deadline = time.monotonic() + timeout
    seen = None
    while time.monotonic() < deadline:
        seen = await asyncio.to_thread(_health_active_tasks, url)
        if seen == expected:
            return seen
        await asyncio.sleep(0.05)
    raise AssertionError(f"/health active_tasks 未变成 {expected}，最后 {seen}")


def _assert_decode_failed(error: dict, *, returncode: int | None = None) -> None:
    assert error.get("type") == "error", error
    assert error["code"] == "decode_failed", error
    assert error["code"] not in FORBIDDEN, error
    assert error.get("retryable") is False, error
    if returncode is not None:
        assert f"退出码 {returncode}" in error["message"], error


def _long_flac(seconds: float = 12.0):
    samples = np.random.default_rng(87).uniform(-0.8, 0.8, int(seconds * 16000)).astype(
        np.float32
    )
    return samples, _encode_flac(samples)


@_LINUX_PROC
@_HAS_SIGKILL
@pytest.mark.asyncio
async def test_ws_kill_while_waiting_next_frame_sends_decode_failed():
    """等下一帧时 SIGKILL 真 ffmpeg：客户端秒级收到 decode_failed，任务与进程回收。"""
    _, flac = _long_flac()
    server = await ManagedFakeServerHarness.start()
    ffmpeg_pid = None
    try:
        known = _direct_children(server.process.pid)
        task_id = str(uuid.uuid4())
        started = time.monotonic()
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            await client.send(_frame(task_id, flac, encoding="flac", final=False))
            ffmpeg_pid = await _wait_new_child(server.process.pid, known)
            deadline = time.monotonic() + 10
            while not server.calls:
                assert time.monotonic() < deadline, "解码未推进，不能把启动失败当中途死亡"
                await asyncio.sleep(0.02)
            os.kill(ffmpeg_pid, signal.SIGKILL)
            messages, _ = await collect_terminal(client, task_id=task_id, timeout=5)
            try:
                await asyncio.wait_for(client.recv(), 8)
                raise AssertionError("错误帧之后连接仍未关闭")
            except websockets.ConnectionClosed:
                pass
        elapsed = time.monotonic() - started
        error = next(m for m in messages if m.get("type") == "error")
        _assert_decode_failed(error)
        assert "退出码 " in error["message"], error
        assert not any(m.get("is_final") for m in messages), messages
        assert elapsed < 15, elapsed
        await _wait_pid_reaped(ffmpeg_pid)
        await _wait_active_tasks(server.url, 0)
        assert server.process.is_alive()
    finally:
        if ffmpeg_pid is not None and Path(f"/proc/{ffmpeg_pid}").exists():
            os.kill(ffmpeg_pid, signal.SIGKILL)
        await server.stop()


@_HAS_SIGKILL
@pytest.mark.asyncio
async def test_ws_kill_while_feeding_sends_decode_failed(fake_asr_server, monkeypatch):
    """正在 feed 下一帧时 ffmpeg 死亡：走 _feed_compressed，仍发 decode_failed。"""
    _, flac = _long_flac(8)
    decoders = []
    feed_started = asyncio.Event()

    class TrackingDecoder(ws_recv_module.AudioDecoder):
        def __init__(self, encoding):
            super().__init__(encoding)
            decoders.append(self)

        async def feed(self, data: bytes) -> None:
            if self.samples_emitted > 0:
                feed_started.set()
            await super().feed(data)

    monkeypatch.setattr(ws_recv_module, "AudioDecoder", TrackingDecoder)
    task_id = str(uuid.uuid4())
    split = max(64 * 1024, len(flac) // 3)
    async with websockets.connect(
        fake_asr_server.url, max_size=None, ping_interval=None
    ) as client:
        await client.send(_frame(task_id, flac[:split], encoding="flac", final=False))
        deadline = time.monotonic() + 8
        while not decoders or decoders[0].samples_emitted == 0:
            assert time.monotonic() < deadline, "解码未推进，不能把启动失败当中途死亡"
            await asyncio.sleep(0.02)
        process = decoders[0].process
        assert process is not None and process.returncode is None
        pid = process.pid
        sending = asyncio.create_task(
            client.send(_frame(task_id, flac[split:], encoding="flac", final=False))
        )
        await asyncio.wait_for(feed_started.wait(), timeout=5)
        os.kill(pid, signal.SIGKILL)
        returncode = await asyncio.wait_for(process.wait(), timeout=5)
        await asyncio.gather(sending, return_exceptions=True)
        messages, _ = await collect_terminal(client, task_id=task_id, timeout=5)
    error = next(m for m in messages if m.get("type") == "error")
    _assert_decode_failed(error, returncode=returncode)
    assert not any(m.get("is_final") for m in messages), messages
    assert process.pid == pid
    assert returncode not in (None, 0)


@_HAS_SIGKILL
@pytest.mark.asyncio
async def test_ws_final_arriving_with_death_prefers_decode_failed(
    fake_asr_server, monkeypatch,
):
    """末帧与解码失败同时到达时失败优先，不得发出成功 final。"""
    samples, flac = _long_flac(6)
    decoders = []

    class TrackingDecoder(ws_recv_module.AudioDecoder):
        def __init__(self, encoding):
            super().__init__(encoding)
            decoders.append(self)

    monkeypatch.setattr(ws_recv_module, "AudioDecoder", TrackingDecoder)
    task_id = str(uuid.uuid4())
    async with websockets.connect(
        fake_asr_server.url, max_size=None, ping_interval=None
    ) as client:
        await client.send(_frame(task_id, flac, encoding="flac", final=False))
        deadline = time.monotonic() + 8
        while not decoders or decoders[0].samples_emitted == 0:
            assert time.monotonic() < deadline
            await asyncio.sleep(0.02)
        process = decoders[0].process
        os.kill(process.pid, signal.SIGKILL)
        await client.send(
            _frame(task_id, b"", encoding="flac", samples_total=int(samples.size))
        )
        returncode = await asyncio.wait_for(process.wait(), timeout=5)
        messages, _ = await collect_terminal(client, task_id=task_id, timeout=5)
    error = next(m for m in messages if m.get("type") == "error")
    _assert_decode_failed(error, returncode=returncode)
    assert not any(m.get("is_final") and m.get("type") == "result" for m in messages)


@pytest.mark.asyncio
async def test_ws_normal_flac_still_gets_final(fake_asr_server):
    samples, flac = _long_flac(3)
    task_id = str(uuid.uuid4())
    async with websockets.connect(
        fake_asr_server.url, max_size=None, ping_interval=None
    ) as client:
        await client.send(
            _frame(task_id, flac, encoding="flac", samples_total=int(samples.size))
        )
        messages, _ = await collect_terminal(client, task_id=task_id, timeout=15)
    assert messages[-1]["type"] == "result" and messages[-1]["is_final"] is True
    assert all(m.get("code") != "decode_failed" for m in messages)


@pytest.mark.asyncio
async def test_receive_compressed_frame_same_tick_prefers_decode_failed(monkeypatch):
    """consumer 与 recv 同 tick 都完成时，真实 helper 必须让 AudioDecodeError 压过帧。"""
    loop = asyncio.get_running_loop()
    recv_fut = loop.create_future()
    consume_fut = loop.create_future()
    seen = {}

    class ImmediatePairSocket:
        async def recv(self):
            return await recv_fut

    async def consume():
        await consume_fut

    real_wait = ws_recv_module.asyncio.wait

    async def spy_wait(aws, *args, **kwargs):
        done, pending = await real_wait(aws, *args, **kwargs)
        seen["n_done"] = len(done)
        seen["both_done"] = all(task.done() for task in aws)
        return done, pending

    monkeypatch.setattr(ws_recv_module.asyncio, "wait", spy_wait)
    consumer = asyncio.create_task(consume())
    helper = asyncio.create_task(
        ws_recv_module._receive_compressed_frame(ImmediatePairSocket(), consumer)
    )
    await asyncio.sleep(0)
    consume_fut.set_exception(AudioDecodeError("decode_failed", "same-tick"))
    recv_fut.set_result('{"is_final": true}')
    try:
        result = await helper
    except AudioDecodeError as exc:
        caught = exc
    else:
        raise AssertionError(
            f"同 tick 已知 decode_failed 必须压过 receive 结果，实际得到 {result!r}"
        )
    assert caught.code == "decode_failed"
    assert seen.get("n_done") == 2, seen
    assert seen.get("both_done") is True, seen
