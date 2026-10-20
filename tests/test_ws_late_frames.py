# coding: utf-8
"""同一 WS 连接上已终态 task_id 的迟到音频帧不重新准入。"""
from __future__ import annotations

import asyncio
import base64
import functools
import queue
import time
from types import SimpleNamespace

import numpy as np
import pytest
import websockets

from config_server import ServerConfig
from core.protocol import AudioMessage
from core.server.connection.ws_recv import ws_recv
from core.server.state import ServerState, count_active_tasks, transition_terminal


def _raw_frame(task_id: str, payload: bytes) -> str:
    return AudioMessage(
        task_id=task_id,
        source="mic",
        data=base64.b64encode(payload).decode("ascii"),
        is_final=False,
        time_start=time.time(),
        seg_duration=5.0,
        seg_overlap=0.0,
    ).to_json()


@pytest.mark.asyncio
async def test_failed_task_late_frame_is_dropped_before_admission(monkeypatch):
    """FAILED 后同 task_id 迟到帧不登记新任务，也不进入 worker 队列。"""
    monkeypatch.setattr(ServerConfig, "seg_cut_snap", False)
    state = ServerState(queue_in=queue.Queue(), queue_out=queue.Queue())
    state.sockets_id = []
    app = SimpleNamespace(state=state)
    server = await websockets.serve(
        functools.partial(ws_recv, app=app),
        "127.0.0.1", 0, max_size=None, ping_interval=None,
    )
    url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    try:
        task_id = "failed-then-late"
        short_pcm = np.zeros(16000, dtype="<f4").tobytes()
        late_pcm = np.zeros(5 * 16000, dtype="<f4").tobytes()
        async with websockets.connect(url, max_size=None, ping_interval=None) as client:
            await client.send(_raw_frame(task_id, short_pcm))

            deadline = asyncio.get_running_loop().time() + 5
            while not state.connection_tasks:
                if asyncio.get_running_loop().time() >= deadline:
                    raise AssertionError("首帧未登记 WS 任务")
                await asyncio.sleep(0.01)
            socket_id = next(iter(state.connection_tasks))
            key = state.connection_tasks[socket_id]
            deadline = asyncio.get_running_loop().time() + 5
            while state.tasks[key].samples_total != 16000:
                if asyncio.get_running_loop().time() >= deadline:
                    raise AssertionError("首帧 PCM 未进入当前任务")
                await asyncio.sleep(0.01)
            assert await count_active_tasks(state) == 1
            assert state.queue_in.empty(), "短于分段阈值的首帧不应投 worker"

            assert transition_terminal(state, key, "FAILED", code="inference_failed")
            assert await count_active_tasks(state) == 0

            # 迟到的 5 秒音频若被当成新任务准入，会与首帧缓冲合并并提交识别段。
            await client.send(_raw_frame(task_id, late_pcm))
            await asyncio.sleep(0.2)

            assert state.tasks[key].status == "FAILED"
            assert await count_active_tasks(state) == 0
            assert state.queue_in.empty(), "终态任务迟到帧不得进入识别队列"
            assert client.state.name == "OPEN"
    finally:
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=5)
