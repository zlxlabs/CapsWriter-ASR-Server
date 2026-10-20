from __future__ import annotations

import asyncio
import json
import queue
from collections import deque
from types import SimpleNamespace

import pytest

from core.server.connection.ws_send import ws_send
from core.server.schema import Result
from core.server.state import ServerState, TaskLifecycle, make_task_key


def make_result(task_id: str, owner_kind: str, *, text: str, is_final: bool = False) -> Result:
    return Result(
        task_id=task_id,
        socket_id="mic-socket" if owner_kind == "ws" else "",
        type="mic" if owner_kind == "ws" else "file",
        owner_kind=owner_kind,
        text=text,
        text_accu=text,
        tokens=list(text),
        timestamps=[float(index) for index, _ in enumerate(text)],
        is_final=is_final,
    )


def sender_app(sink):
    queue_out = queue.Queue()
    state = ServerState(queue_out=queue_out)
    state.http_result_sink = sink
    state.active_http_jobs = []
    http_key = make_task_key("http", "file-job")
    ws_key = make_task_key("ws", "mic-job", "mic-socket")
    state.tasks[http_key] = TaskLifecycle(status="RUNNING")
    state.tasks[ws_key] = TaskLifecycle(status="RUNNING")
    state.sockets["mic-socket"] = object()
    outbound = asyncio.Queue()
    state.out_queues["mic-socket"] = outbound
    return SimpleNamespace(state=state), queue_out, outbound


@pytest.mark.asyncio
async def test_blocked_http_sink_does_not_delay_websocket_result():
    sink_started = asyncio.Event()
    release_sink = asyncio.Event()
    sink_finished = asyncio.Event()

    async def blocked_sink(result):
        sink_started.set()
        await release_sink.wait()
        sink_finished.set()

    app, queue_out, outbound = sender_app(blocked_sink)
    sender = asyncio.create_task(ws_send(app))
    try:
        queue_out.put(make_result("file-job", "http", text="文件结果"))
        await asyncio.wait_for(sink_started.wait(), timeout=1)

        queue_out.put(make_result("mic-job", "ws", text="麦克风结果"))
        message = json.loads(await asyncio.wait_for(outbound.get(), timeout=0.5))
        assert message["task_id"] == "mic-job"
        assert message["text"] == "麦克风结果"
        assert not sink_finished.is_set()

        release_sink.set()
        await asyncio.wait_for(sink_finished.wait(), timeout=1)
    finally:
        release_sink.set()
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)


@pytest.mark.asyncio
async def test_blocked_sink_keeps_unconsumed_http_segments_backpressured():
    sink_started = asyncio.Event()
    release_sink = asyncio.Event()
    final_received = asyncio.Event()

    async def blocked_sink(result):
        sink_started.set()
        await release_sink.wait()
        if result.is_final:
            final_received.set()

    app, queue_out, outbound = sender_app(blocked_sink)
    state = app.state
    key = make_task_key("http", "file-job")
    state.pending_segments[key] = deque(["first", "second", "third"])
    sender = asyncio.create_task(ws_send(app))
    try:
        queue_out.put(make_result("file-job", "http", text="第一段"))
        await asyncio.wait_for(sink_started.wait(), timeout=1)
        queue_out.put(make_result("file-job", "http", text="第二段"))
        queue_out.put(make_result("file-job", "http", text="最终段", is_final=True))
        queue_out.put(make_result("mic-job", "ws", text="仍可发送"))

        message = json.loads(await asyncio.wait_for(outbound.get(), timeout=0.5))
        assert message["text"] == "仍可发送"
        assert list(state.pending_segments[key]) == ["second", "third"]

        release_sink.set()
        await asyncio.wait_for(final_received.wait(), timeout=1)
    finally:
        release_sink.set()
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)


@pytest.mark.asyncio
async def test_http_jobs_have_independent_sink_consumers():
    blocked_started = asyncio.Event()
    release_blocked = asyncio.Event()
    other_finished = asyncio.Event()

    async def sink(result):
        if result.task_id == "file-job":
            blocked_started.set()
            await release_blocked.wait()
        else:
            other_finished.set()

    app, queue_out, _ = sender_app(sink)
    other_key = make_task_key("http", "other-job")
    app.state.tasks[other_key] = TaskLifecycle(status="RUNNING")
    sender = asyncio.create_task(ws_send(app))
    try:
        queue_out.put(make_result("file-job", "http", text="阻塞的文件结果"))
        await asyncio.wait_for(blocked_started.wait(), timeout=1)
        queue_out.put(make_result("other-job", "http", text="另一个文件结果"))
        await asyncio.wait_for(other_finished.wait(), timeout=0.5)
    finally:
        release_blocked.set()
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)


@pytest.mark.asyncio
async def test_same_http_job_sink_receives_segments_in_queue_order():
    received = []
    all_received = asyncio.Event()

    async def sink(result):
        received.append(result.text)
        if result.is_final:
            all_received.set()

    app, queue_out, _ = sender_app(sink)
    sender = asyncio.create_task(ws_send(app))
    try:
        queue_out.put(make_result("file-job", "http", text="第一段"))
        queue_out.put(make_result("file-job", "http", text="第二段"))
        queue_out.put(make_result("file-job", "http", text="最终段", is_final=True))

        await asyncio.wait_for(all_received.wait(), timeout=1)
        assert received == ["第一段", "第二段", "最终段"]
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
