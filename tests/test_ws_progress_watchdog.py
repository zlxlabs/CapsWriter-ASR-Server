# coding: utf-8
"""WS 上行进展看门狗（issue #76）验收。

被验收的不变式：每个非终态 WS 任务在任意时刻恰好有一个看门狗负责——
``pending_segments`` 非空时归 ``CW_SEGMENT_TIMEOUT``，否则归「最近一次进展 +
``CW_UPLOAD_IDLE_SECONDS``」；到点后不仅关 socket，还要真正回收接收协程与
ffmpeg 子进程。

停滞用真实 SIGSTOP 制造：对解码器子进程发 SIGSTOP 后，ffmpeg 停止读取 stdin，
``_feed_compressed`` 的写侧与 ``_consume_compressed_pcm`` 的读侧随即互等，
接收协程再也回不到 ``websocket.recv()``——与现场观测到的「不抛异常、不打日志、
不发错误帧」同形。
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pytest
import websockets

from core.protocol import AudioMessage
from tests.harness.client import collect_terminal
from tests.harness.server import ManagedFakeServerHarness
from tests.test_protocol_v2 import _encode_flac

CHUNK = 64 * 1024
SEG_DURATION = 5.0
SEG_OVERLAP = 0.0


# --------------------------------------------------------------- /proc 探针
# ffmpeg 是服务主进程的直接子进程，pid 与命令名都取自 /proc 本身，
# 不断言「进程名像 ffmpeg」，也不把探针结果当回显。

def _proc_rows(pid: int):
    """返回 (pid, comm, state, ppid)，全部读自 /proc/<pid>/stat。"""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    _, _, tail = stat.partition(") ")
    head_comm = stat[stat.index("(") + 1:stat.index(")")]
    fields = tail.split()
    return int(pid), head_comm, fields[0], int(fields[1])


def _ffmpeg_children(pid: int) -> list[int]:
    rows = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        row = _proc_rows(int(entry.name))
        if row is not None and row[1] == "ffmpeg" and row[3] == pid:
            rows.append(row[0])
    return rows


async def _wait_for_ffmpeg(pid: int, timeout: float = 15.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = _ffmpeg_children(pid)
        if found:
            return found[0]
        await asyncio.sleep(0.02)
    raise AssertionError(f"{timeout}s 内没有出现服务主进程 {pid} 的 ffmpeg 子进程")


async def _wait_for_stopped(pid: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = _proc_rows(pid)
        if row is None:
            raise AssertionError(f"ffmpeg {pid} 在 SIGSTOP 生效前就消失了")
        if row[2] == "T":
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"ffmpeg {pid} 未进入 T（停止）状态：{_proc_rows(pid)!r}")


async def _wait_for_reaped(pid: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _proc_rows(pid) is None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(
        f"ffmpeg {pid} 在 {timeout}s 内仍存活：{_proc_rows(pid)!r}（解码子进程没被回收）"
    )


def _force_kill_ffmpeg(pid: int) -> None:
    row = _proc_rows(pid)
    if row is not None and row[1] == "ffmpeg":
        os.kill(pid, signal.SIGKILL)


def _health_active_tasks(websocket_url: str) -> int:
    """从服务端真实 /health 读回当前非终态任务数（跨进程证据，不是推断）。"""
    url = websocket_url.replace("ws://", "http://", 1) + "/health"
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read())["active_tasks"]


async def _wait_for_active_tasks(websocket_url: str, expected: int, timeout: float = 15.0):
    deadline = time.monotonic() + timeout
    seen = None
    while time.monotonic() < deadline:
        seen = await asyncio.to_thread(_health_active_tasks, websocket_url)
        if seen == expected:
            return seen
        await asyncio.sleep(0.05)
    raise AssertionError(f"{timeout}s 内 /health 的 active_tasks 未变成 {expected}，最后读到 {seen}")


# ------------------------------------------------------------------ 客户端
def _flac_frame(task_id: str, payload: bytes, *, final: bool = False,
                samples_total: int = 0) -> str:
    return AudioMessage(
        task_id=task_id, source="mic",
        data=base64.b64encode(payload).decode("ascii"),
        is_final=final, time_start=time.time(),
        seg_duration=SEG_DURATION, seg_overlap=SEG_OVERLAP,
        encoding="flac", samples_total=samples_total if final else None,
    ).to_json()


def _raw_frame(task_id: str, payload: bytes, *, final: bool = False) -> str:
    return AudioMessage(
        task_id=task_id, source="mic",
        data=base64.b64encode(payload).decode("ascii"),
        is_final=final, time_start=time.time(),
        seg_duration=SEG_DURATION, seg_overlap=SEG_OVERLAP,
    ).to_json()


async def _send_flac(client, task_id: str, payload: bytes, *, final: bool = False,
                     samples_total: int = 0) -> None:
    for start in range(0, len(payload), CHUNK):
        piece = payload[start:start + CHUNK]
        is_last_piece = start + CHUNK >= len(payload)
        await client.send(_flac_frame(
            task_id, piece, final=final and is_last_piece,
            samples_total=samples_total,
        ))


async def _pump(client, task_id: str, payload: bytes, *, final: bool = False,
                samples_total: int = 0) -> None:
    """后台持续上行；连接被服务端关闭时正常结束（不等它把音频发完）。"""
    try:
        await _send_flac(client, task_id, payload, final=final,
                         samples_total=samples_total)
    except websockets.ConnectionClosed:
        return


async def _drain_results(client, quiet: float = 0.6, timeout: float = 30.0):
    """读到 quiet 秒没有新消息为止：确认此前提交的片段已全部确认（无在途片段）。"""
    messages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = json.loads(await asyncio.wait_for(client.recv(), quiet))
        except (TimeoutError, websockets.ConnectionClosed):
            return messages
        messages.append(message)
        if message.get("type") == "error":
            return messages
    raise AssertionError(f"{timeout}s 内结果流没有安静下来，已收到 {messages!r}")


def _only_error(messages):
    errors = [m for m in messages if m.get("type") == "error"]
    assert errors, f"没有收到 error 帧，已收到: {messages!r}"
    assert not any(m.get("is_final") for m in messages), (
        f"停滞任务不得先收到 final，已收到: {messages!r}"
    )
    return errors[0]


async def _assert_closed(client, timeout: float = 8.0) -> None:
    """错误帧之后连接必须被服务端关闭（不靠 collect_terminal 的 closed 标志）。"""
    try:
        message = await asyncio.wait_for(client.recv(), timeout)
    except TimeoutError as exc:
        raise AssertionError(f"错误帧之后 {timeout}s 内连接仍未关闭") from exc
    except websockets.ConnectionClosed:
        return
    raise AssertionError(f"错误帧之后连接仍未关闭，又收到 {message!r}")


# ---------------------------------------------------------------------- 用例
@pytest.mark.skipif(sys.platform != "linux", reason="定位 ffmpeg 子进程依赖 /proc")
@pytest.mark.asyncio
async def test_s1_upload_midway_decode_stall_returns_decode_stalled_and_reaps_ffmpeg():
    """S1 上传途中停滞：ffmpeg 停推后客户端拿到 decode_stalled，ffmpeg 被 kill。"""
    samples = np.random.default_rng(76).uniform(-0.8, 0.8, 60 * 16000).astype(np.float32)
    flac = _encode_flac(samples)
    idle = 3.0
    head, tail = flac[:len(flac) // 3], flac[len(flac) // 3:]
    server = await ManagedFakeServerHarness.start(
        server_config={"upload_idle_seconds": idle}, monitor_interval=0.5
    )
    ffmpeg_pid = None
    pumping = None
    try:
        task_id = "s1-upload-stall"
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            # 先把头一段灌完：解码确实推进过、片段确实被确认过（无在途片段），
            # 这才让「停滞」只可能来自 ffmpeg 停推。
            await _send_flac(client, task_id, head)
            drained = await _drain_results(client)
            assert drained and all(m.get("type") == "result" for m in drained), (
                f"停滞前的片段应当全部识别完成: {drained!r}"
            )
            ffmpeg_pid = await _wait_for_ffmpeg(server.process.pid)
            os.kill(ffmpeg_pid, signal.SIGSTOP)
            await _wait_for_stopped(ffmpeg_pid)

            pumping = asyncio.create_task(_pump(client, task_id, tail))
            started = time.monotonic()
            messages, _closed = await collect_terminal(
                client, task_id=task_id, timeout=idle + 8
            )
            elapsed = time.monotonic() - started
            # 上行已经完成（或早已排进 socket 缓冲），此后再堵着发送队列只会把关闭
            # 握手压在音频帧后面（关闭帧排在客户端写缓冲末尾），对断言无贡献。
            pumping.cancel()
            await asyncio.gather(pumping, return_exceptions=True)
            pumping = None
            # 服务端关闭握手要排在客户端仍在写的音频帧之后（websockets 的
            # close_timeout 默认 10s），因此这里的等待上限按那个量级给。
            await _assert_closed(client, timeout=20)
        error = _only_error(messages)
        assert error["code"] == "decode_stalled", error
        assert error["retryable"] is True, error
        assert "当前：解码阶段" in error["message"], error
        assert "无在途识别片段" in error["message"], error
        assert elapsed <= idle + 8, elapsed
        await _wait_for_reaped(ffmpeg_pid)
        await _wait_for_active_tasks(server.url, 0)
        assert server.process.is_alive(), "单任务停滞不得让服务主进程退出"
    finally:
        if pumping is not None and not pumping.done():
            pumping.cancel()
            await asyncio.gather(pumping, return_exceptions=True)
        if ffmpeg_pid is not None:
            _force_kill_ffmpeg(ffmpeg_pid)
        await server.stop()


@pytest.mark.skipif(sys.platform != "linux", reason="定位 ffmpeg 子进程依赖 /proc")
@pytest.mark.asyncio
async def test_s2_final_frame_decode_stall_returns_decode_stalled_and_reaps_ffmpeg():
    """S2 末帧后停滞：末帧走 AudioDecoder.finish() 那条路径，停滞同样被判定。"""
    samples = np.random.default_rng(762).uniform(-0.8, 0.8, 20 * 16000).astype(np.float32)
    flac = _encode_flac(samples)
    idle = 3.0
    server = await ManagedFakeServerHarness.start(
        server_config={"upload_idle_seconds": idle}, monitor_interval=0.5
    )
    ffmpeg_pid = None
    try:
        task_id = "s2-final-stall"
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            await _send_flac(client, task_id, flac)
            drained = await _drain_results(client)
            assert drained and all(m.get("type") == "result" for m in drained), drained
            ffmpeg_pid = await _wait_for_ffmpeg(server.process.pid)
            os.kill(ffmpeg_pid, signal.SIGSTOP)
            await _wait_for_stopped(ffmpeg_pid)
            # 末帧不带新音频字节：feed 立即返回，服务端必然停在 finish() 里
            # （关闭 stdin 后的 wait_closed / _reader_task 等待 ffmpeg 退出）。
            await client.send(_flac_frame(
                task_id, b"", final=True, samples_total=int(samples.size)
            ))
            started = time.monotonic()
            messages, _closed = await collect_terminal(
                client, task_id=task_id, timeout=idle + 8
            )
            elapsed = time.monotonic() - started
            await _assert_closed(client)
        error = _only_error(messages)
        assert error["code"] == "decode_stalled", error
        assert error["retryable"] is True, error
        assert "当前：解码阶段" in error["message"], error
        assert elapsed <= idle + 8, elapsed
        await _wait_for_reaped(ffmpeg_pid)
        await _wait_for_active_tasks(server.url, 0)
        assert server.process.is_alive()
    finally:
        if ffmpeg_pid is not None:
            _force_kill_ffmpeg(ffmpeg_pid)
        await server.stop()


@pytest.mark.asyncio
async def test_s3_slow_inference_with_inflight_segment_is_not_judged_stalled():
    """S3 不误杀慢推理：空闲上限远小于单段推理耗时，任务仍须正常收到 final。"""
    idle = 2.0
    server = await ManagedFakeServerHarness.start(
        options={"delay_on_call": 1, "delay_seconds": 8.0},
        server_config={"upload_idle_seconds": idle, "max_inflight_segments": 1},
        monitor_interval=0.5,
    )
    try:
        task_id = "s3-slow-inference"
        pcm = np.zeros(5 * 16000, dtype="<f4").tobytes()
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            await client.send(_raw_frame(task_id, pcm))
            await server.wait_for_calls(1)
            # 在途片段存在 → 归段推理看门狗；此处比空闲上限多等两拍，
            # 任何 decode_stalled 都是误杀。
            seen = await _drain_results(client, quiet=idle * 2, timeout=idle * 2 + 2)
            assert not [m for m in seen if m.get("type") == "error"], (
                f"慢推理期间不得被判停滞: {seen!r}"
            )
            await client.send(_raw_frame(task_id, pcm, final=True))
            messages, closed = await collect_terminal(client, task_id=task_id, timeout=20)
        assert closed is False, closed
        assert not [m for m in messages if m.get("type") == "error"], messages
        assert messages[-1].get("is_final") is True, messages
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_s4_client_stops_sending_is_reported_as_upload_stage_stall():
    """S4 客户端停发：两个入口都要终止，且 message 必须落在上传阶段。"""
    idle = 3.0
    server = await ManagedFakeServerHarness.start(
        server_config={"upload_idle_seconds": idle}, monitor_interval=0.5
    )
    try:
        # 入口一：连上以后一个帧都不发
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            started = time.monotonic()
            messages, _closed = await collect_terminal(
                client, task_id="", timeout=idle + 8
            )
            elapsed = time.monotonic() - started
            await _assert_closed(client)
        error = _only_error(messages)
        assert error["code"] == "decode_stalled", error
        assert error["retryable"] is True, error
        assert "上传阶段未推进" in error["message"], error
        assert "未收到任何上行音频帧" in error["message"], error
        assert elapsed <= idle + 8, elapsed

        # 入口二：发了帧但客户端不再继续（任务级上传停滞）
        task_id = "s4-upload-stall"
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            await client.send(_raw_frame(
                task_id, np.zeros(16000, dtype="<f4").tobytes()
            ))
            messages, _closed = await collect_terminal(
                client, task_id=task_id, timeout=idle + 8
            )
            await _assert_closed(client)
        error = _only_error(messages)
        assert error["code"] == "decode_stalled", error
        assert "当前：上传阶段" in error["message"], error
        assert "无在途识别片段" in error["message"], error
        await _wait_for_active_tasks(server.url, 0)
        assert server.process.is_alive()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_s5_segment_timeout_fails_only_that_task_and_keeps_server_alive(monkeypatch):
    """S5 反向约束：段推理超时不退出服务，只终结该任务并关闭它的连接。"""
    monkeypatch.setenv("CW_SEGMENT_TIMEOUT", "2")
    server = await ManagedFakeServerHarness.start(
        options={"delay_on_call": 1, "delay_seconds": 4.0},
        server_config={"upload_idle_seconds": 300.0},
        monitor_interval=0.5,
    )
    try:
        task_id = "s5-segment-timeout"
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            await client.send(_raw_frame(
                task_id, np.zeros(5 * 16000, dtype="<f4").tobytes()
            ))
            await server.wait_for_calls(1)
            messages, _closed = await collect_terminal(client, task_id=task_id, timeout=15)
            await _assert_closed(client)
        error = _only_error(messages)
        assert error["code"] == "inference_timeout", error
        assert error["retryable"] is True, error
        await _wait_for_active_tasks(server.url, 0)
        assert server.process.is_alive(), (
            f"段推理超时不得退出服务主进程（exitcode={server.process.exitcode}）"
        )
        # 服务仍然可用：另一个任务能正常跑完。先等假引擎那 4s 卡顿真正结束，
        # 否则第二段会再次落进同一个 2s 段超时（那正是本用例要区分的两种机制）。
        await asyncio.sleep(4)
        other = "s5-after-timeout"
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            await client.send(_raw_frame(
                other, np.zeros(5 * 16000, dtype="<f4").tobytes()
            ))
            await client.send(_raw_frame(
                other, np.zeros(16000, dtype="<f4").tobytes(), final=True
            ))
            messages, closed = await collect_terminal(client, task_id=other, timeout=30)
        assert not closed and messages[-1].get("is_final") is True, messages
    finally:
        await server.stop()