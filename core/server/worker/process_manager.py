# coding: utf-8
"""
识别子进程管理器 (ProcessManager)

负责维护单机识别进程的生命周期，包括启动、模型加载监控、异常退出捕获。
"""
from __future__ import annotations
import asyncio
import sys
import os
import queue
import time
from multiprocessing import Process, Manager
from typing import TYPE_CHECKING
from ..state import console
from ..state import PHASE_LABELS, PROGRESS_LABELS
from config_server import ServerConfig as Config
from . import start_worker
from .check_model import check_model
from . import logger
if TYPE_CHECKING:
    from ..app import CapsWriterServer

PROCESS_MONITOR_INTERVAL_SECONDS = 1

# 停滞看门狗的消息：同时写出「最后一次进展在哪个阶段」和「任务当前在哪个阶段」。
# 只报其中一个都会在另一种停滞上误导：只报最后阶段，末帧后卡在 finish() 的解码
# 会被说成「上传阶段」（而客户端确实已经发完了）；只报当前阶段，客户端主动停发
# 又会被说成「解码阶段」。
_IDLE_STALL_MESSAGE = (
    "上行停滞 {idle:.1f}s（最后进展：{progress}阶段；当前：{phase}阶段）；"
    "任务无在途识别片段，服务端已回收该连接的接收协程与解码子进程并关闭连接"
)


async def _cancel_ws_handler(state, key) -> None:
    """看门狗到点后真正回收接收协程（只关 socket 解不开解码阶段的互等）。

    cancel 之后必须等它跑完 finally：那里才会 kill ffmpeg 子进程并摘除任务记录。
    """
    handler = state.handler_tasks.get(key[1])
    if handler is None or handler.done():
        return
    handler.cancel()
    await asyncio.wait({handler})
    logger.warning(f"进展看门狗到点，已回收接收协程 task={key[2]} owner={key[1]}")


async def _fail_stalled_ws_uploads(state, now: float) -> None:
    """无在途片段的 WS 任务：最近一次进展超过上限即判定停滞。

    I-owner：每个非终态 WS 任务在任意时刻恰好有一个看门狗负责——
    ``pending_segments`` 非空时归 CW_SEGMENT_TIMEOUT，否则归这里。两者互斥且
    无缝交接（提交片段与确认结果两处打点都刷新 last_progress_at），因此不存在
    「两边都不管」的时间窗，也不存在用状态推迟超时的空间。
    """
    limit = float(Config.upload_idle_seconds)
    stalled = [
        (record.last_progress_at, key)
        for key, record in state.tasks.items()
        if key[0] == 'ws'
        and record.status not in {'DONE', 'FAILED'}
        and not state.pending_segments.get(key)
        and now - record.last_progress_at > limit
    ]
    for idle_at, key in sorted(stalled):
        websocket = state.sockets.get(key[1])
        if websocket is None:
            # 无连接的 ws 任务由 ws_recv 的 finally 收尾（那里也会置终态并
            # kill ffmpeg），看门狗无从发帧，不在这里重复释放。
            continue
        from ..connection.ws_send import schedule_error_close
        record = state.tasks[key]
        await schedule_error_close(
            state,
            websocket,
            key[1],
            key[2],
            'decode_stalled',
            _IDLE_STALL_MESSAGE.format(
                idle=now - idle_at,
                progress=PROGRESS_LABELS.get(
                    record.progress_stage, record.progress_stage
                ),
                phase=PHASE_LABELS.get(record.phase, record.phase),
            ),
            True,
        )
        await _cancel_ws_handler(state, key)


class ProcessManager:
    """
    识别子进程管理器

    由 CapsWriterServer 调用，专注于进程层级的控制。
    """
    def __init__(self, app: CapsWriterServer):
        self._process = None
        self._manager = None
        self.app = app
        self.is_alive = False
        self.models_ready = False
        self.aligner_status = "not_required"

    def start(self):
        """
        启动识别子进程并等待模型加载完成

        Returns:
            Process: 启动成功的子进程对象
        """
        # 防连续触发
        if self.is_alive: return
        self.is_alive = True
        self.models_ready = False
        self.aligner_status = "not_required"

        # 1. 前置检查
        check_model()

        # 2. 初始化共享资源
        # 使用 Manager 管理共享列表，用于追踪活动连接
        state = self.app.state
        self._manager = Manager()
        state.sockets_id = self._manager.list()
        state.active_http_jobs = self._manager.list()

        # 获取标准输入文件描述符，用于 Windows 下的信号传递补丁
        stdin_fn = sys.stdin.fileno()

        # 3. 创建并启动进程
        self._process = Process(
            target=start_worker,
            args=(state.queue_in,
                  state.queue_out,
                  state.sockets_id,
                  stdin_fn,
                  state.active_http_jobs),
            daemon=True
        )
        self._process.start()

        # 存入状态以便其他模块引用
        state.recognize_process = self._process
        logger.info(f"识别子进程已拉起 (PID: {self._process.pid})")

        # 4. 等待模型加载完成 (轮询方式)
        self._wait_for_models()

        return self._process

    def _wait_for_models(self):
        """轮询队列直到收到模型加载完成状态或发生错误"""
        logger.info("正在等待子进程加载模型...")

        while self.is_alive:
            try:
                # 阻塞最多 100ms
                status = self.app.state.queue_out.get(timeout=0.1)
                if status["loaded"] is True:
                    self.aligner_status = status["aligner"]
                    self.models_ready = True
                    break
            except (queue.Empty, OSError):
                if self._process and not self._process.is_alive():
                    self._handle_unexpected_exit()
                    return
                continue

        if not self.is_alive: return
        logger.info("模型加载完成，ASR 服务就绪")
        console.rule('[green3]开始服务')
        console.line()

    def _handle_unexpected_exit(self):
        """处理子进程加载模型时的意外退出"""
        exit_code = self._process.exitcode
        if exit_code != 0:
            logger.error(f"识别子进程意外退出! ExitCode: {exit_code}")
            logger.error("这通常是由于模型损坏、底层库冲突或系统资源不足导致的。")

        raise SystemExit(1)

    async def monitor(self):
        """就绪后监控推理进程存活、上行停滞与最老的未完成推理段。"""
        from ..state import ensure_server_runtime
        ensure_server_runtime(self.app.state)
        state = self.app.state
        while self.is_alive:
            await asyncio.sleep(PROCESS_MONITOR_INTERVAL_SECONDS)
            if not self._process.is_alive():
                from ..connection.ws_send import fail_active_tasks
                message = f"推理进程退出 exitcode={self._process.exitcode}"
                await fail_active_tasks(state, 'internal', message)
                raise SystemExit(1)

            now = time.monotonic()
            await _fail_stalled_ws_uploads(state, now)
            timeout = float(os.environ.get('CW_SEGMENT_TIMEOUT', '600'))
            expired = [
                (key, submitted[0])
                for key, submitted in state.pending_segments.items()
                if submitted
                and now - submitted[0] > timeout
                and (record := state.tasks.get(key)) is not None
                and record.status not in {'DONE', 'FAILED'}
            ]
            if expired:
                key, submitted_at = min(expired, key=lambda item: item[1])
                websocket = (
                    state.sockets.get(key[1])
                    if key[0] == 'ws'
                    else None
                )
                if websocket is not None:
                    from ..connection.ws_send import schedule_error_close
                    timeout_close = schedule_error_close(
                        state,
                        websocket,
                        key[1],
                        key[2],
                        'inference_timeout',
                        f"推理段超时，最早提交时间距今 {now - submitted_at:.3f}s",
                        True,
                    )
                    await timeout_close
                    # 单个任务超时不得把整个服务拉下：worker 可能只是被一段慢
                    # 推理卡住，其余任务仍可继续。只终结本任务并回收其接收协程。
                    await _cancel_ws_handler(state, key)
                    continue
                if key[0] == 'http':
                    # HTTP 分支：先可靠落库 FAILED，成功后才释放 owner/唤醒
                    # 等待者；落库超时或失败不释放，随后仍 SystemExit(1)
                    # 非零退出，交由重启收敛兜底。
                    from ..http_file_runner import finalize_http_job
                    await finalize_http_job(
                        state, key, 'FAILED', 'inference_timeout',
                        f"推理段超时，最早提交时间距今 {now - submitted_at:.3f}s",
                    )
                else:
                    from ..state import transition_terminal
                    transition_terminal(
                        state, key, 'FAILED', code='inference_timeout'
                    )
                from ..connection.ws_send import fail_active_tasks
                await fail_active_tasks(
                    state,
                    'internal',
                    '推理进程卡死，服务端即将退出',
                    skip_key=key,
                )
                raise SystemExit(1)

    def stop(self):
        """停止子进程"""

        # 防连续触发
        if not self.is_alive: return
        self.is_alive = False

        if self._process and self._process.is_alive():
            logger.info(f"正在终止识别子进程 (PID: {self._process.pid})...")
            # 发送 None 任务通知优雅退出 (作为兜底)

            self.app.state.queue_in.put(None)

            # 如果 2 秒内没退，则强制 kill
            self._process.join(timeout=2)
            if self._process.is_alive():
                logger.debug("子进程未响应优雅退出，执行强制终止")
                self._process.terminate()
                self._process.join(timeout=2)
                if self._process.is_alive():
                    raise RuntimeError("识别子进程在强制终止后 2 秒内仍存活")
        if self._manager is not None:
            self._manager.shutdown()
            self._manager = None
