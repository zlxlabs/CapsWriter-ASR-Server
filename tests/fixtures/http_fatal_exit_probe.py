#!/usr/bin/env python3
# coding: utf-8
"""fatal 清理 → 真实进程退出与资源回收的边界探针。

在**自有进程**（systemd 瞬态 unit 或裸 shell）里跑真实 ``CapsWriterServer.start()``：
真实 ``SocketManager`` / ``HttpServer`` / ``HttpFileRunner`` / multiprocessing
识别子进程 / ``Manager`` / ffmpeg / SQLite。按卡面要求只 stub ASR 引擎与权重
初始化（``check_model`` 与 ``start_worker`` 的引擎），不加载真实模型。

探针只写**白名单结构化事实**（单行 ``PROBE=`` JSON + 报告文件），不回显环境变量、
凭据或原始响应体；PID/argv/cgroup 取自 ``/proc`` 与进程自身的真实对象。

模式（``CW_PROBE_MODE``）：
  * ``fatal``               真实 HTTP 上传 → ffmpeg 解码 → DONE → 老化七天 →
                             释放 runner 引用 → 对**该具体源**注入 unlink
                             PermissionError，等待 listener 监督链 fatal。
  * ``sigterm``             正常启动后向自己发 SIGTERM，回归主动 stop 的 0 退出。
  * ``http_init_failure``   HTTP 显式启用但数据目录无法初始化，回归启动失败路径；
                             在真实装配点记录已建好的共享 Manager 的 PID 与 /proc 事实。
  * ``ws_only``             不提供 CW_HTTP_PORT，回归默认 WS 与 HTTP disabled。
  * ``same_turn_observer``  不启动完整 App：真实 ``HttpServer._mark_fatal`` 与
                             ``loop.stop`` 同一调度 turn，用来锁死 10ms 轮询契约。

无论哪种模式，进程退出码就是被测行为本身：脚本不吞异常、不代替被测代码退出。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import signal
import struct
import sys
import time
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REPORT_PREFIX = "PROBE="
# 探针自身可观测的合成音频时长/体积上限（卡面：<=3s、<=1MiB）
PROBE_AUDIO_SECONDS = 2.0
PROBE_AUDIO_MAX_BYTES = 1024 * 1024
# 清理周期缩短到探针可观测的尺度；谓词本身仍是生产的七天 terminal_at 阈值
PROBE_CLEANUP_INTERVAL_SECONDS = 0.05
# 跨 _mark_fatal 包装与 scenario 的只读快照：worker 构造期绑定的是 class 方法，
# 实例晚绑覆盖不了 I/O callback；source 路径在 unlink 注入时才知道。
_FATAL_SNAPSHOT: dict = {}


# ------------------------------------------------------------------ 白名单事实


def _read_proc(pid: int, name: str):
    """只读取白名单字段；进程不存在或字段缺失一律显式 None，不猜。"""
    try:
        raw = Path(f"/proc/{pid}/{name}").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    return raw.decode("utf-8", errors="replace").strip()


def _proc_cmdline(pid: int) -> list[str]:
    raw = _read_proc(pid, "cmdline")
    if not raw:
        return []
    return [part for part in raw.split("\0") if part]


def _cgroup_path(pid: int) -> str:
    raw = _read_proc(pid, "cgroup") or ""
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[1] == "":
            return parts[2]
    return ""


def _sha256_file(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "bytes": 0, "sha256": None}
    payload = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def emit(report: dict) -> None:
    """报告以 JSONL 追加落盘，并以单行 JSON 打到 stdout（消费方按前缀白名单取行）。

    追加而不是覆盖：pre_fatal 与 post_fatal 两段都必须留在磁盘上，
    消费方才能核对「fatal 之前」与「fatal 之后」的同一组 PID/字节。
    """
    line = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(REPORT_PREFIX + line + "\n")
    sys.stdout.flush()
    target = os.environ.get("CW_PROBE_REPORT")
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())


# ------------------------------------------------------------------ 生产 stub


def _install_stubbed_inference() -> None:
    """只替换 ASR 引擎与权重检查；进程管理、队列协议与 pipeline 全是生产代码。"""
    from config_server import ServerConfig
    from core.server.worker import process_manager as pm

    # 真 VAD 模型不在探针边界内；与既有跨进程 harness 同一口径回到固定时长盲切
    ServerConfig.seg_cut_snap = False
    pm.check_model = lambda: None

    def stub_start_worker(queue_in, queue_out, sockets_id, stdin_fn, active_http_jobs=None):
        # recording worker 与生产 worker 同一条就绪协议与同一条 active_http_jobs
        # 边界；只有引擎是可编程假引擎，队列/TaskHandler/pipeline 都是生产代码。
        from tests.harness.worker import run_recording_worker

        run_recording_worker(
            queue_in, queue_out, sockets_id, active_http_jobs, {
                "supports_timestamps": True,
                "result_text": "探针正文",
                "result_tokens": ["探", "针", "正", "文"],
                "result_timestamps": [0.1, 0.2, 0.3, 0.4],
            }, [], [],
        )

    pm.start_worker = stub_start_worker


def _shorten_cleanup_interval() -> None:
    from core.server import http_server as server_module

    server_module.SOURCE_CLEANUP_INTERVAL_SECONDS = PROBE_CLEANUP_INTERVAL_SECONDS


def _emit_post_fatal(server, stored: BaseException) -> None:
    """在原 _mark_fatal 已经写入 self.fatal 之后同步落盘；失败必须 fail-loud。"""
    app = getattr(server, "_app", None)
    worker = getattr(getattr(app, "state", None), "recognize_process", None)
    source = _FATAL_SNAPSHOT.get("source")
    source_path = _FATAL_SNAPSHOT.get("source_path")
    if source is None and source_path:
        source = _sha256_file(Path(source_path))
    emit({
        "phase": "post_fatal",
        "mode": _FATAL_SNAPSHOT.get("mode") or os.environ.get("CW_PROBE_MODE", "fatal"),
        "app_pid": os.getpid(),
        "worker_pid": (
            worker.pid if worker is not None else _FATAL_SNAPSHOT.get("worker_pid")
        ),
        "worker_alive": worker.is_alive() if worker is not None else None,
        "fatal_type": type(stored).__name__,
        "fatal_message": str(stored),
        "source": source,
        "job_id": _FATAL_SNAPSHOT.get("job_id"),
        "observer": "HttpServer._mark_fatal",
    })


def _install_mark_fatal_observer() -> None:
    """把观察点绑到 HttpServer._mark_fatal：真实存储 fatal 之后、loop 停之前落盘。

    必须在 HttpServer 实例化 / HttpIoWorker(self._mark_fatal) 之前包到 class：
    I/O worker 构造器保存当时的 bound method；生产 ``_on_source_cleanup_done``
    本来就通过 ``self._mark_fatal`` 查到 class 包装，不得替换该回调函数。
    """
    from core.server import http_server as server_module

    if getattr(server_module.HttpServer._mark_fatal, "_cw_probe_observed", False):
        return
    real_mark = server_module.HttpServer._mark_fatal

    def observed_mark(self, exc: BaseException) -> None:
        already = self.fatal is not None
        real_mark(self, exc)
        if already:
            return
        stored = self.fatal
        if stored is None:
            raise AssertionError("HttpServer._mark_fatal 执行后 fatal 仍未存储")
        _emit_post_fatal(self, stored)

    observed_mark._cw_probe_observed = True
    server_module.HttpServer._mark_fatal = observed_mark


def _write_probe_wav(path: Path) -> bytes:
    """真实可解码的合成 WAV（真实 producer，不是静音占位）。"""
    rate = 16000
    frames = bytearray()
    for index in range(round(PROBE_AUDIO_SECONDS * rate)):
        t = index / rate
        value = 0.2 * math.sin(2 * math.pi * 220 * t) * math.sin(2 * math.pi * 0.7 * t + 0.3)
        frames += struct.pack("<h", int(value * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    payload = path.read_bytes()
    assert len(payload) <= PROBE_AUDIO_MAX_BYTES, len(payload)
    return payload


async def _wait_until(predicate, message: str, timeout: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(message)


# ------------------------------------------------------------------ fatal 场景


async def _upload_and_wait_done(base_url: str, token: str, payload: bytes) -> dict:
    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=20) as client:
        created = await client.post(
            f"{base_url}/v1/uploads",
            headers={**headers, "Idempotency-Key": "probe-fatal-key"},
            json={"size_bytes": len(payload),
                  "sha256": hashlib.sha256(payload).hexdigest()},
        )
        assert created.status_code == 201, created.status_code
        upload_id = created.json()["upload_id"]
        patched = await client.patch(
            f"{base_url}/v1/uploads/{upload_id}",
            headers={**headers, "Upload-Offset": "0"},
            content=payload,
        )
        assert patched.status_code == 204, patched.status_code
        committed = await client.post(
            f"{base_url}/v1/uploads/{upload_id}/commit", headers=headers, content=b"",
        )
        assert committed.status_code == 202, committed.status_code
        job_id = committed.json()["job_id"]

        async def state() -> str:
            response = await client.get(
                f"{base_url}/v1/jobs/{job_id}", headers=headers
            )
            if response.status_code != 200:
                return f"HTTP{response.status_code}"
            return response.json()["state"]

        await _wait_until_done(state, "探针上传的真实 Job 没有在期限内进入 DONE")
        result = await client.get(f"{base_url}/v1/jobs/{job_id}/result", headers=headers)
        assert result.status_code == 200, result.status_code
        return {"upload_id": upload_id, "job_id": job_id,
                "result_payload": result.json()}


async def _wait_until_done(state, message: str, timeout: float = 60.0) -> None:
    """轮询真实 Job 状态直到终态；每次都让出调度，server 与 worker 才能推进。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if await state() == "DONE":
            return
        if loop.time() > deadline:
            raise AssertionError(message)
        await asyncio.sleep(0.02)


def _store_row(app, sql: str, params: tuple):
    """在受监督的单 I/O worker 线程里读真实 SQLite（SQLite 连接只在该线程）。"""
    return app.http_server._worker.run_sync(
        lambda: app.http_server._store.conn.execute(sql, params).fetchone()
    )


async def run_fatal_scenario(app) -> None:
    """真实 DONE + 七天老化 + 释放引用后注入具体 unlink PermissionError。"""
    token = "probe-fatal-token"
    data_dir = Path(os.environ["CW_HTTP_DATA_DIR"])
    payload = _write_probe_wav(Path(os.environ["CW_PROBE_WAV"]))
    await _wait_until(
        lambda: app.http_server is not None and app.http_server._bound_port,
        "HTTP listener 未在期限内就绪",
        timeout=60,
    )
    base_url = f"http://127.0.0.1:{app.http_server._bound_port}"
    submitted = await _upload_and_wait_done(base_url, token, payload)

    source_row = _store_row(
        app,
        "SELECT source_name, state FROM uploads WHERE upload_id=?",
        (submitted["upload_id"],),
    )
    source_path = data_dir / "sources" / source_row["source_name"]
    job_id = submitted["job_id"]

    # 已终态且 runner 已释放引用：active_jobs 不再含该 Job（释放时序的真实证据）
    await _wait_until(
        lambda: job_id not in app.http_file_runner.active_jobs,
        "runner 在终态落库后仍未释放 Job 引用",
        timeout=30,
    )
    released_jobs = list(app.http_file_runner.active_jobs)

    terminal_cutoff = time.time() - 8 * 24 * 3600
    app.http_server._worker.run_sync(
        lambda: app.http_server._store.conn.execute(
            "UPDATE jobs SET terminal_at=? WHERE job_id=?", (terminal_cutoff, job_id)
        )
    )

    # 对**这一条具体源**的 unlink 注入 PermissionError；命中即写下真实痕迹
    denial_log = Path(os.environ["CW_PROBE_DENIAL_LOG"])
    real_unlink = os.unlink

    def denied_unlink(path, *args, **kwargs):
        if Path(path) == source_path:
            with open(denial_log, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "event": "unlink_denied",
                    "path": str(path),
                    "job_id": job_id,
                    "pid": os.getpid(),
                }) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            raise PermissionError("injected source unlink denial")
        return real_unlink(path, *args, **kwargs)

    from core.server import http_store as store_module

    store_module.os.unlink = denied_unlink

    result_row = _store_row(
        app, "SELECT payload FROM results WHERE job_id=?", (job_id,)
    )
    job_row = _store_row(
        app, "SELECT state, terminal_at FROM jobs WHERE job_id=?", (job_id,)
    )
    emit({
        "phase": "pre_fatal",
        "mode": "fatal",
        "app_pid": os.getpid(),
        "worker_pid": app.state.recognize_process.pid,
        "manager_pid": app.process_manager._manager._process.pid,
        "worker_alive": app.state.recognize_process.is_alive(),
        "app_cgroup": _cgroup_path(os.getpid()),
        "worker_cgroup": _cgroup_path(app.state.recognize_process.pid),
        "app_argv": _proc_cmdline(os.getpid()),
        "worker_argv": _proc_cmdline(app.state.recognize_process.pid),
        "http_port": app.http_server._bound_port,
        "ws_port": int(os.environ["CW_PORT"]),
        "job_id": job_id,
        "job_state": job_row["state"],
        "terminal_at": job_row["terminal_at"],
        "terminal_cutoff": terminal_cutoff,
        "released_runner_jobs": released_jobs,
        "source": _sha256_file(source_path),
        "upload_state": source_row["state"],
        "result_sha256": hashlib.sha256(
            str(result_row["payload"]).encode("utf-8")
        ).hexdigest(),
        "result_bytes": len(str(result_row["payload"]).encode("utf-8")),
        "result_payload": submitted["result_payload"],
        "uploaded_bytes": len(payload),
        "uploaded_sha256": hashlib.sha256(payload).hexdigest(),
    })
    _FATAL_SNAPSHOT.clear()
    _FATAL_SNAPSHOT.update({
        "mode": "fatal",
        "job_id": job_id,
        "source_path": str(source_path),
        "source": _sha256_file(source_path),
        "worker_pid": app.state.recognize_process.pid,
    })

    # post_fatal 由 class 上的 _mark_fatal 观察点在真实存储之后同步写入，
    # 不再用 10ms 轮询和 loop 收尾抢调度。
    return


def run_same_turn_observer_contract() -> None:
    """真实子进程：_mark_fatal 与 loop.stop 安排在同一调度 turn。

    观察点必须在原方法写入 fatal 之后、stop 之前落盘；不能再靠 10ms 轮询。
    """
    from types import SimpleNamespace

    from core.server.http_server import HttpServer

    data_dir = Path(os.environ["CW_HTTP_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = SimpleNamespace(
        loop=loop,
        state=SimpleNamespace(recognize_process=None),
    )
    _FATAL_SNAPSHOT.clear()
    _FATAL_SNAPSHOT.update({
        "mode": "same_turn_observer",
        "job_id": "same-turn-job",
        "source_path": str(data_dir / "missing-source.bin"),
    })
    _install_mark_fatal_observer()
    server = HttpServer(app, "127.0.0.1", 0, data_dir)

    def fire() -> None:
        server._mark_fatal(PermissionError("injected source unlink denial"))
        loop.stop()

    loop.call_soon(fire)
    loop.run_forever()
    loop.close()


async def run_ready_then_sigterm(app, mode: str, wait_http: bool) -> None:
    """正常启动后向自己发 SIGTERM：主动 stop 必须保持 0 退出。

    wait_http=True 用于显式启用 HTTP 的场景（等真实 HTTP listener），
    False 用于 HTTP disabled（只等默认 WS listener）。
    """
    if wait_http:
        ready = lambda: app.http_server is not None and app.http_server._bound_port
    else:
        ready = lambda: app.socket_manager._server is not None
    await _wait_until(ready, "listener 未在期限内就绪", timeout=60)
    emit({
        "phase": "ready",
        "mode": mode,
        "app_pid": os.getpid(),
        "worker_pid": app.state.recognize_process.pid,
        "manager_pid": app.process_manager._manager._process.pid,
        "app_cgroup": _cgroup_path(os.getpid()),
        "http_server_is_none": app.http_server is None,
        "http_port": app.http_server._bound_port if app.http_server else None,
        "ws_port": int(os.environ["CW_PORT"]),
        "app_argv": _proc_cmdline(os.getpid()),
    })
    os.kill(os.getpid(), signal.SIGTERM)
    await asyncio.sleep(3600)


# ------------------------------------------------------------------ 入口


def _redirect_output() -> None:
    """把探针自己的 stdout/stderr 落成真实日志文件。

    systemd 把 unit 输出交给 journald，而 journald 是异步落盘、并且已回收的
    transient unit 事后未必还能按 unit 名检索。探针自己掌握一份文件，消费者
    才有一个与进程退出无关的证据源。
    """
    target = os.environ.get("CW_PROBE_LOG")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "wb", buffering=0)
    os.dup2(handle.fileno(), 1)
    os.dup2(handle.fileno(), 2)
    sys.stdout = open(1, "w", buffering=1, errors="replace", closefd=False)
    sys.stderr = sys.stdout


def _observe_manager_before_http_assembly(app) -> None:
    """在真实 HTTP 装配点记录共享 Manager 的真实 PID 与 /proc 事实。

    启动失败模式下 Manager 是在 ProcessManager.start() 里先建好的，装配失败发生在
    之后的 HttpServer.prepare()——那正是「Manager 已经活着」的最后一个观测点。
    这里只包一层记录，prepare() 本体照旧执行并照旧抛真实异常：不改 factory 去不建
    Manager，也不吞错。
    """
    from core.server import http_server as server_module

    real_prepare = server_module.HttpServer.prepare

    def observed_prepare(self):
        manager = app.process_manager._manager
        process = getattr(manager, "_process", None)
        pid = process.pid if process is not None else None
        emit({
            "phase": "pre_http_assembly",
            "mode": "http_init_failure",
            "app_pid": os.getpid(),
            "manager_pid": pid,
            # 「确实建过」与「确实活过」分开记录：只有 pid 非空还不够，
            # 还要有同一时刻从 /proc 读出的真实痕迹，消费方才不会拿到 None 恒真。
            "manager_process_created": process is not None,
            "manager_process_alive": bool(process is not None and process.is_alive()),
            "manager_argv": _proc_cmdline(pid) if pid else [],
            "manager_cgroup": _cgroup_path(pid) if pid else "",
            "worker_pid": app.state.recognize_process.pid,
            "app_cgroup": _cgroup_path(os.getpid()),
            "http_data_dir": os.environ.get("CW_HTTP_DATA_DIR", ""),
            "http_port": int(os.environ.get("CW_HTTP_PORT", "0")),
            "ws_port": int(os.environ["CW_PORT"]),
        })
        return real_prepare(self)

    server_module.HttpServer.prepare = observed_prepare


def main() -> int:
    mode = os.environ.get("CW_PROBE_MODE", "fatal")
    _redirect_output()
    _shorten_cleanup_interval()
    if mode == "same_turn_observer":
        run_same_turn_observer_contract()
        return 0
    from core.server.app import CapsWriterServer

    app = CapsWriterServer()
    if mode == "http_init_failure":
        _install_stubbed_inference()
        emit({
            "phase": "pre_start",
            "mode": mode,
            "app_pid": os.getpid(),
            "app_cgroup": _cgroup_path(os.getpid()),
            "app_argv": _proc_cmdline(os.getpid()),
            "http_port": int(os.environ.get("CW_HTTP_PORT", "0")),
            "ws_port": int(os.environ["CW_PORT"]),
        })
        _observe_manager_before_http_assembly(app)
        # 装配失败必须让 start() 抛错：这里不吞异常、不代替被测代码退出
        app.start()
        return 0

    _install_stubbed_inference()
    if mode == "fatal":
        _install_mark_fatal_observer()
    scenario = (
        run_fatal_scenario(app)
        if mode == "fatal"
        else run_ready_then_sigterm(app, mode, mode == "sigterm")
    )
    app.loop.call_soon(asyncio.ensure_future, scenario)
    app.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
