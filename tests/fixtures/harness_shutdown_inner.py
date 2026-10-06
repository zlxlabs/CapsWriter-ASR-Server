# coding: utf-8
"""卡 C（#85）跨进程验收的**内层 pytest**：只被 ``tests/test_harness_shutdown.py``
用 ``python -m pytest <本文件>`` 显式执行，不参与常规收集（文件名不匹配
``test_*.py``，与本目录既有探针脚本同一约定）。

被验收的不变式：受控服务主进程名下的解码子进程被 SIGSTOP 停住、**测试主体断言
先失败**时，收尾路径本身必须仍然有界——owner（``ManagedFakeServerHarness.stop``）
负责把解码子进程收干净，服务主进程走正常退出，pytest 以失败态有界退出，且不留下
本 owner 的残留进程。

本文件刻意**不**在 finally 里预杀 ffmpeg：那正是本卡要删掉的非法状态（回收责任
不许散落在单个测试的 finally 里）。finally 里的 kill 只在最后按精确 pid 兜底，
保证即使被测代码坏了也不给外层留残留，并且兜底动作发生在写 marker **之后**，
不会把 owner 的回收结果掩盖掉。

本文件把实测事实写进 ``CW_HARNESS_SHUTDOWN_MARKER`` 指向的 JSON（真实 pid、
真实 /proc 状态、真实退出码、真实耗时），外层据此断言，不靠子进程自述。
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

import numpy as np
import pytest
import websockets

from core.protocol import AudioMessage
from tests.harness.server import ManagedFakeServerHarness
from tests.test_protocol_v2 import _encode_flac

CHUNK = 64 * 1024
MARKER = Path(os.environ["CW_HARNESS_SHUTDOWN_MARKER"])


def _proc_row(pid):
    """(comm, state, ppid)，全部读自 /proc/<pid>/stat；进程不在则 None。"""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        fields = stat[stat.rindex(") ") + 2:].split()
        return {"comm": comm, "state": fields[0], "ppid": int(fields[1])}
    except (ValueError, IndexError):
        return None


def _decoder_children(server_pid):
    """服务主进程名下的 ffmpeg 直接子进程（本地实现，不依赖被测模块的私有函数）。"""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        row = _proc_row(int(entry.name))
        if row is not None and row["comm"] == "ffmpeg" and row["ppid"] == server_pid:
            found.append(int(entry.name))
    return found


async def _wait_for_decoder(server_pid, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = _decoder_children(server_pid)
        if found:
            return found[0]
        await asyncio.sleep(0.02)
    raise AssertionError(f"{timeout}s 内服务主进程 {server_pid} 没有 ffmpeg 子进程")


async def _wait_for_stopped(pid, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = _proc_row(pid)
        if row is None:
            raise AssertionError(f"ffmpeg {pid} 在 SIGSTOP 生效前就消失了")
        if row["state"] == "T":
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"ffmpeg {pid} 未进入 T（停止）状态：{_proc_row(pid)!r}")


def _kill(pid):
    """兜底回收：只按精确 pid 发信号，且只在本 owner 记录的 pid 上发。"""
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _flac_frame(task_id, payload, final=False):
    return AudioMessage(
        task_id=task_id, source="mic",
        data=base64.b64encode(payload).decode("ascii"),
        is_final=final, time_start=time.time(),
        seg_duration=5.0, seg_overlap=0.0, encoding="flac",
        samples_total=None,
    ).to_json()


async def _send_flac(client, task_id, payload):
    for start in range(0, len(payload), CHUNK):
        piece = payload[start:start + CHUNK]
        await client.send(_flac_frame(task_id, piece))


async def _pump(client, task_id, payload):
    """后台持续上行；连接被服务端关闭时正常结束（不等它把音频发完）。

    故障形态要求「客户端在主体失败那一刻仍在上传」：服务端写侧因此卡在
    停住的 ffmpeg 的 stdin 上，与 issue 现场同构。
    """
    try:
        await _send_flac(client, task_id, payload)
    except websockets.ConnectionClosed:
        return


async def _drain_results(client, quiet=0.6, timeout=20.0):
    """读到 quiet 秒没有新消息为止：确认此前提交的片段已全部确认。"""
    import json as _json

    messages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = _json.loads(await asyncio.wait_for(client.recv(), quiet))
        except (TimeoutError, websockets.ConnectionClosed):
            return messages
        messages.append(message)
    raise AssertionError(f"{timeout}s 内结果流没有安静下来，已收到 {messages!r}")


@pytest.mark.skipif(sys.platform != "linux", reason="定位 ffmpeg 子进程依赖 /proc")
@pytest.mark.asyncio
async def test_body_fails_while_holding_a_paused_decoder():
    samples = np.random.default_rng(8500).uniform(-0.8, 0.8, 30 * 16000).astype(np.float32)
    flac = _encode_flac(samples)
    # upload_idle_seconds 极大：进展看门狗与 ws_recv 自身的 recv 超时在本用例窗口内
    # 都不可能到点，被停住的解码子进程只能由 owner 回收。纯测试侧参数，不改生产。
    server = await ManagedFakeServerHarness.start(
        server_config={"upload_idle_seconds": 100000.0}, monitor_interval=0.5
    )
    facts = {"server_pid": server.process.pid, "worker_pid": server.worker_pid,
             "ffmpeg_pid": None}
    ffmpeg_pid = None
    pumping = None
    try:
        task_id = "shutdown-inner"
        async with websockets.connect(
            server.url, max_size=None, ping_interval=None
        ) as client:
            # 先让解码真的跑起来、片段真的被确认过：ffmpeg 是这条路径 fork 出来的。
            await _send_flac(client, task_id, flac[: len(flac) // 3])
            drained = await _drain_results(client)
            assert drained and all(m.get("type") == "result" for m in drained), drained
            ffmpeg_pid = await _wait_for_decoder(server.process.pid)
            facts["ffmpeg_pid"] = ffmpeg_pid
            os.kill(ffmpeg_pid, signal.SIGSTOP)
            await _wait_for_stopped(ffmpeg_pid)
            # 客户端继续上传：服务端写侧卡在停住的 ffmpeg 的 stdin 上（上传途中停滞）。
            pumping = asyncio.create_task(_pump(client, task_id, flac[len(flac) // 3:]))
            await asyncio.sleep(1.0)
            row = _proc_row(ffmpeg_pid)
            assert row is not None and row["state"] == "T", (
                f"故障注入前提不成立：解码子进程不在 T 态：{row!r}"
            )
            facts["ffmpeg_before_stop"] = row
            # 主体断言必然失败，且失败瞬间持有被停住的解码子进程。
            raise AssertionError(
                "主体断言必然失败：验证 owner 在失败路径上回收被暂停的解码子进程"
            )
    finally:
        if pumping is not None and not pumping.done():
            pumping.cancel()
            await asyncio.gather(pumping, return_exceptions=True)
        started = time.monotonic()
        stop_error = None
        try:
            await server.stop()
        except BaseException as exc:  # noqa: BLE001 - 记录 teardown 的真实结果
            stop_error = exc
        facts["stop_seconds"] = round(time.monotonic() - started, 2)
        facts["stop_error"] = None if stop_error is None else repr(stop_error)
        facts["server_exitcode"] = server.process.exitcode
        facts["ffmpeg_after_stop"] = _proc_row(ffmpeg_pid)
        # 先落 marker 再兜底：兜底只保证不留残留，不参与回收判据。
        MARKER.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
        _kill(ffmpeg_pid)
        _kill(server.process.pid)
        if stop_error is not None:
            raise stop_error
