# coding: utf-8
"""harness 受控子进程回收验收（issue #85 / 设计卡 C）。

被验收的不变式：**受控服务主进程名下的解码子进程，是这个 harness 自己 fork 出来
的，回收责任就落在 harness（owner）身上**，而不是散落在每个测试的 finally 里。
具体断言三件事：

1. 解码子进程被 ``SIGSTOP`` 停住（``/proc`` 实读 state=T、ppid=服务主进程）时，
   ``stop()`` 仍然整体有界：先按所有权把解码子进程收干净，再让服务主进程走正常
   退出路径；不给它兜底强杀的那 10s，也不抛与故障无关的二次断言。
2. 正常收尾不退化：没被停住的解码子进程时，``stop()`` 依旧干净退出。
3. 所有权是按 ppid 划的：与本 owner 无关的对照 ffmpeg（comm 同名但不是它的子
   进程）绝不会被发信号。

外加一条跨进程验收（E2E）：把「主体断言必然失败 + 持有已暂停解码子进程」放进
独立 pytest 子进程里真跑一遍，断言它**有界非零退出**、原始断言可见、teardown
不再二次失败，且它记录的精确 pid 全部回收干净。

反过度设计说明：本文件不引入任何进程管理库或全局注册表；owner 侧只多了
「按 ppid 找直接 ffmpeg 子进程 → SIGKILL → 轮询确认不再占用资源」这一段，
删掉的是「回收责任取决于测试作者记不记得在 finally 里补一刀」这个非法状态。
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import signal
import subprocess
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
REPO_ROOT = Path(__file__).resolve().parent.parent
INNER_PYTEST = REPO_ROOT / "tests" / "fixtures" / "harness_shutdown_inner.py"
# 让进展看门狗与 ws_recv 自身的 recv 超时在本用例窗口内都不可能到点：
# 被停住的解码子进程因此只能由 owner 回收，测的才是 owner 而不是看门狗。
STALLED_FOREVER = {"upload_idle_seconds": 100000.0}


# ------------------------------------------------------------------ /proc 事实
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
    """服务主进程名下的 ffmpeg 直接子进程（本地实现，不复用被测模块的私有函数）。"""
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
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def _force_cleanup(server):
    """本文件自身的安全网，与被测 owner 无关：按精确 pid 收干净本用例启动的服务。

    先记解码子进程再杀主进程：主进程一死，子进程就被 init 收养，按 ppid 就找不到了。
    """
    if server is None:
        return
    pids = _decoder_children(server.process.pid) if server.process.pid else []
    if server.process.is_alive():
        server.process.kill()
        await asyncio.to_thread(server.process.join, 5)
    for pid in pids:
        _kill(pid)
    server.info_queue.close()
    server.manager.shutdown()


# ------------------------------------------------------------------ 音频上行
def _flac_frame(task_id, payload, final=False, samples_total=None):
    return AudioMessage(
        task_id=task_id, source="mic",
        data=base64.b64encode(payload).decode("ascii"),
        is_final=final, time_start=time.time(),
        seg_duration=5.0, seg_overlap=0.0, encoding="flac",
        samples_total=samples_total,
    ).to_json()


async def _send_flac(client, task_id, payload, final=False, samples_total=None):
    for start in range(0, len(payload), CHUNK):
        piece = payload[start:start + CHUNK]
        await client.send(_flac_frame(
            task_id, piece,
            final=final and start + CHUNK >= len(payload),
            samples_total=samples_total if final else None,
        ))


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
    messages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = json.loads(await asyncio.wait_for(client.recv(), quiet))
        except (TimeoutError, websockets.ConnectionClosed):
            return messages
        messages.append(message)
    raise AssertionError(f"{timeout}s 内结果流没有安静下来，已收到 {messages!r}")


async def _wedge_with_paused_decoder(server, task_id, samples):
    """把服务端楔进「写侧卡在被停住的解码子进程 stdin 上」的状态，再关掉连接。

    上传途中停滞：头一段已经解码并确认过（ffmpeg 确实被 fork 出来、确实在推进），
    随后 SIGSTOP 停住它，客户端继续把剩下的音频推上去。实测（S1 现场同构）：
    此时关掉客户端连接**解不开**这个互等——接收协程回不到 ``websocket.recv()``，
    它的 finally 也就跑不到，停在 T 态的解码子进程继续挂在服务主进程名下。

    返回那个仍处于 T 态、ppid 仍是本服务主进程的解码子进程 pid。
    """
    flac = _encode_flac(samples)
    async with websockets.connect(
        server.url, max_size=None, ping_interval=None
    ) as client:
        await _send_flac(client, task_id, flac[: len(flac) // 3])
        drained = await _drain_results(client)
        assert drained and all(m.get("type") == "result" for m in drained), (
            f"停住解码子进程之前，片段应当全部识别完成: {drained!r}"
        )
        pid = await _wait_for_decoder(server.process.pid)
        os.kill(pid, signal.SIGSTOP)
        await _wait_for_stopped(pid)
        pump = asyncio.create_task(_pump(client, task_id, flac[len(flac) // 3:]))
        try:
            await asyncio.sleep(1.0)
            row = _proc_row(pid)
            assert row == {"comm": "ffmpeg", "state": "T", "ppid": server.process.pid}, (
                f"故障注入前提不成立：解码子进程不在本 owner 名下的 T 态：{row!r}"
            )
        finally:
            if not pump.done():
                pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
    row = _proc_row(pid)
    assert row == {"comm": "ffmpeg", "state": "T", "ppid": server.process.pid}, (
        f"连接关闭后解码子进程本应仍被楔住，实际 {row!r}；现场不成立"
    )
    return pid


async def _upload_completed_normally(server, task_id, samples):
    """真上传一路跑到 final：解码子进程正常退出的那条路径。"""
    flac = _encode_flac(samples)
    async with websockets.connect(
        server.url, max_size=None, ping_interval=None
    ) as client:
        await _send_flac(client, task_id, flac, final=True,
                         samples_total=int(samples.size))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = json.loads(await asyncio.wait_for(client.recv(), 10))
            if message.get("is_final"):
                return
        raise AssertionError("正常上传没有收到 final")


def _bystander_ffmpeg(tmp_path):
    """造一个 comm 同为 ffmpeg、但不是本 owner 子进程的对照进程。

    从真 ffmpeg 复制一份并让它阻塞在读 stdin 上：按进程名兜底的实现会误杀它，
    按 ppid 划所有权的实现不会。它是本用例「回收路径确实跑过」的对照。
    """
    source = shutil.which("ffmpeg")
    if source is None:
        pytest.fail("测试环境缺少 ffmpeg：无法构造对照进程，缺依赖必须失败而非静默 skip")
    target = tmp_path / "ffmpeg"
    shutil.copy2(source, target)
    proc = subprocess.Popen(
        [str(target), "-nostdin", "-f", "flac", "-i", "pipe:0", "-f", "null", "-"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = _proc_row(proc.pid)
        if row is not None and row["comm"] == "ffmpeg" and row["state"] != "Z":
            return proc
        if proc.poll() is not None:
            pytest.fail(f"对照 ffmpeg 进程没能存活：exitcode={proc.returncode}")
        time.sleep(0.05)
    pytest.fail("对照 ffmpeg 进程 10s 内没有进入可用的停止/运行态")


# ---------------------------------------------------------------------- 用例
@pytest.mark.asyncio
async def test_stop_of_untouched_service_stays_clean():
    """对照：没有解码子进程时 stop() 不退化（有界、干净、不抛二次断言）。"""
    server = await ManagedFakeServerHarness.start(monitor_interval=0.5)
    try:
        started = time.monotonic()
        await server.stop()
        elapsed = time.monotonic() - started
        assert elapsed < 5.0, f"空服务 stop() 耗时 {elapsed:.2f}s，超出有界预期"
        assert server.process.exitcode == 0, (
            f"空服务应正常退出，实际 exitcode={server.process.exitcode}"
        )
    finally:
        await _force_cleanup(server)


@pytest.mark.skipif(sys.platform != "linux", reason="定位 ffmpeg 子进程依赖 /proc")
@pytest.mark.asyncio
async def test_stop_after_a_normal_upload_stays_clean():
    """对照：解码子进程已经正常退出的那条路径，stop() 不得退化。"""
    samples = np.random.default_rng(853).uniform(-0.8, 0.8, 10 * 16000).astype(np.float32)
    server = await ManagedFakeServerHarness.start(
        server_config={"upload_idle_seconds": 30.0}, monitor_interval=0.5,
    )
    try:
        await _upload_completed_normally(server, "normal-upload", samples)
        assert _decoder_children(server.process.pid) == [], (
            "正常上传后解码子进程应当已自行退出"
        )
        started = time.monotonic()
        await server.stop()
        elapsed = time.monotonic() - started
        assert elapsed < 5.0, f"正常上传后 stop() 耗时 {elapsed:.2f}s，超出有界预期"
        assert server.process.exitcode == 0, (
            f"正常上传后服务主进程应正常退出，实际 exitcode={server.process.exitcode}"
        )
    finally:
        await _force_cleanup(server)


@pytest.mark.skipif(sys.platform != "linux", reason="定位 ffmpeg 子进程依赖 /proc")
@pytest.mark.asyncio
async def test_owner_reclaims_paused_decoder_before_stopping_the_service():
    """owner 在服务主进程收尾之前收回自己 fork 出来的解码子进程，且整体有界。"""
    samples = np.random.default_rng(851).uniform(-0.8, 0.8, 30 * 16000).astype(np.float32)
    server = await ManagedFakeServerHarness.start(
        server_config=dict(STALLED_FOREVER), monitor_interval=0.5,
    )
    try:
        ffmpeg_pid = await _wedge_with_paused_decoder(server, "owner-reclaim", samples)

        started = time.monotonic()
        # 不预杀 ffmpeg：回收是 owner 的职责，测试不替它做。
        await server.stop()
        elapsed = time.monotonic() - started

        assert elapsed < 5.0, (
            f"stop() 耗时 {elapsed:.2f}s：owner 没有在服务主进程收尾前收回解码子进程，"
            f"而是走完了兜底强杀路径（实测旧行为 10.02s）"
        )
        assert server.process.exitcode == 0, (
            f"服务主进程应走正常退出路径，实际 exitcode={server.process.exitcode}"
            f"（-15 表示被 SIGTERM 强杀，说明收尾被卡住后兜底）"
        )
        assert _proc_row(ffmpeg_pid) is None, (
            f"解码子进程 {ffmpeg_pid} 在 stop() 返回后仍在 /proc："
            f"{_proc_row(ffmpeg_pid)!r}"
        )
    finally:
        await _force_cleanup(server)


@pytest.mark.skipif(sys.platform != "linux", reason="定位 ffmpeg 子进程依赖 /proc")
@pytest.mark.asyncio
async def test_owner_never_signals_a_bystander_ffmpeg(tmp_path):
    """所有权按 ppid 划：同名但不属于本 owner 的 ffmpeg 一个信号都不许收。"""
    bystander = _bystander_ffmpeg(tmp_path)
    samples = np.random.default_rng(852).uniform(-0.8, 0.8, 30 * 16000).astype(np.float32)
    server = await ManagedFakeServerHarness.start(
        server_config=dict(STALLED_FOREVER), monitor_interval=0.5,
    )
    try:
        ffmpeg_pid = await _wedge_with_paused_decoder(server, "bystander", samples)

        await server.stop()

        # 非空洞：owner 自己的解码子进程确实在这一步被回收了。
        assert _proc_row(ffmpeg_pid) is None, (
            f"owner 自己的解码子进程 {ffmpeg_pid} 没被回收，对照组就没有约束力"
        )
        assert bystander.poll() is None, (
            f"owner 误杀了不属于它的 ffmpeg（pid={bystander.pid}，"
            f"exitcode={bystander.returncode}）"
        )
        assert _proc_row(bystander.pid)["state"] != "Z", (
            f"对照进程 {bystander.pid} 已被收掉：{_proc_row(bystander.pid)!r}"
        )
    finally:
        await _force_cleanup(server)
        if bystander.poll() is None:
            bystander.kill()
        bystander.wait(timeout=10)


@pytest.mark.skipif(sys.platform != "linux", reason="内层验收依赖 /proc 与真 ffmpeg")
def test_failing_body_with_paused_decoder_exits_nonzero_and_reclaims(tmp_path):
    """E2E：独立 pytest 里主体断言必失败且持有已暂停解码子进程 → 有界非零退出。"""
    marker = tmp_path / "inner-facts.json"
    log = tmp_path / "inner-pytest.log"
    started = time.monotonic()
    # 输出写文件而不是管道：内层跑砸时会选留下孤儿进程，孤儿继承管道写端会让
    # communicate() 永远等不到 EOF，把「pytest 已退出」误报成「pytest 挂死」。
    with open(log, "wb") as sink:
        inner = subprocess.Popen(
            [
                sys.executable, "-m", "pytest", str(INNER_PYTEST),
                "-q", "-p", "no:cacheprovider", "-o", "faulthandler_timeout=45",
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "CW_HARNESS_SHUTDOWN_MARKER": str(marker)},
            stdout=sink, stderr=subprocess.STDOUT,
        )
        try:
            returncode = inner.wait(timeout=90)
        except subprocess.TimeoutExpired:
            inner.kill()
            inner.wait(timeout=10)
            elapsed = time.monotonic() - started
            pytest.fail(
                f"内层 pytest {elapsed:.1f}s 仍未退出（收尾路径挂死）：\n"
                f"{log.read_text(encoding='utf-8', errors='replace')[-4000:]}"
            )
    elapsed = time.monotonic() - started
    output = log.read_text(encoding="utf-8", errors="replace")

    assert returncode != 0, f"主体断言必然失败，内层 pytest 应非零退出：\n{output}"
    assert elapsed < 60, f"内层 pytest 用了 {elapsed:.1f}s 才退出，超出有界预期：\n{output}"
    # 主体原失败必须可见，且不再被 teardown 的二次异常顶掉。
    assert "主体断言必然失败" in output, f"内层 pytest 没有暴露主体原断言：\n{output}"
    assert "服务主进程未在 5 秒内响应 worker 停止信号" not in output, (
        f"teardown 仍在服务故障之外二次失败（收尾被卡住的旧症状）：\n{output}"
    )

    facts = json.loads(marker.read_text(encoding="utf-8"))
    assert facts["ffmpeg_before_stop"] == {
        "comm": "ffmpeg", "state": "T", "ppid": facts["server_pid"]
    }, f"故障注入前提不成立：{facts!r}"
    assert facts["stop_error"] is None, f"owner 收尾抛了异常：{facts['stop_error']}"
    assert facts["stop_seconds"] < 5.0, f"owner 收尾耗时 {facts['stop_seconds']}s，不有界"
    assert facts["server_exitcode"] == 0, (
        f"服务主进程应正常退出，实际 exitcode={facts['server_exitcode']}"
    )
    assert facts["ffmpeg_after_stop"] is None, (
        f"解码子进程 {facts['ffmpeg_pid']} 在 owner 收尾后仍在 /proc："
        f"{facts['ffmpeg_after_stop']!r}"
    )
    # 内层记录的精确 pid 在外层再核一遍：跨进程边界上按真实 pid 判回收。
    assert _proc_row(facts["server_pid"]) is None, "服务主进程没被回收"
    assert _proc_row(facts["ffmpeg_pid"]) is None, "解码子进程没被回收"
    assert _proc_row(facts["worker_pid"]) is None, "识别子进程没被回收"
