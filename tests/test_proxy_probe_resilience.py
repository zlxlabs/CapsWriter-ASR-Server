# coding: utf-8

import asyncio
import contextlib
import http.client
import logging

import pytest

from core.proxy.backend import BackendState
from core.proxy.proxy_server import ProxyServer

PROBE_HTTP_EXCEPTION_WARNING = "后端探活 HTTP 协议异常"
PROBE_LOOP_EXIT_ERROR = "探活循环意外结束"


@pytest.mark.asyncio
async def test_incomplete_read_counts_as_backend_failure_and_keeps_probe_loop_running(
    monkeypatch, caplog
):
    """截断的 /health 响应只记该后端失败，探活循环必须继续下一轮。"""
    caplog.set_level(logging.WARNING)
    backend_a = BackendState(id="a", url="ws://a")
    backend_b = BackendState(id="b", url="ws://b")
    proxy = ProxyServer(
        "127.0.0.1",
        0,
        [backend_a, backend_b],
        probe_interval=0.05,
    )
    probe_calls = []

    def fake_read(url):
        probe_calls.append(url)
        if url == "ws://a":
            raise http.client.IncompleteRead(b"{")
        return 200, b'{"protocol_version": 2, "encodings": ["pcm"]}'

    monkeypatch.setattr("core.proxy.proxy_server._read_backend_health", fake_read)

    task = asyncio.create_task(proxy._health_probe_loop())
    try:
        for _ in range(40):
            await asyncio.sleep(0.05)
            if probe_calls.count("ws://a") >= 2:
                break
            if task.done():
                break
        loop_exc = task.exception() if task.done() and not task.cancelled() else None
        assert probe_calls.count("ws://a") >= 2, (
            f"下一轮探活未执行: calls={probe_calls!r} task_exc={loop_exc!r}"
        )
        assert backend_a.health_probe_failed is True
        assert backend_a.healthy is False
        warnings = [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
        assert any(PROBE_HTTP_EXCEPTION_WARNING in message for message in warnings), warnings
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        else:
            task.exception()


@pytest.mark.asyncio
async def test_unexpected_probe_error_logs_and_reraises(monkeypatch, caplog):
    """探活循环若仍因意外异常结束，必须留下可 grep 的 error 日志并上抛。"""
    caplog.set_level(logging.ERROR)
    backend = BackendState(id="a", url="ws://a")
    proxy = ProxyServer("127.0.0.1", 0, [backend], probe_interval=0.05)

    def fake_read(_url):
        raise RuntimeError("synthetic probe bug")

    monkeypatch.setattr("core.proxy.proxy_server._read_backend_health", fake_read)

    with pytest.raises(RuntimeError, match="synthetic probe bug"):
        await asyncio.wait_for(proxy._health_probe_loop(), timeout=2)
    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert any(PROBE_LOOP_EXIT_ERROR in message for message in errors), errors
