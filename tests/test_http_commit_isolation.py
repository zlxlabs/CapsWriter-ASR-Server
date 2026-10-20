# coding: utf-8
"""HTTP commit 整文件哈希不得堵住 WS 准入与 fail_job 写库；过期上传必须释放源预留。"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import threading
import time
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from core.server.http_store import HttpStore, HttpStoreError
from core.server.state import count_active_tasks

needs_aiohttp = pytest.mark.skipif(
    importlib.util.find_spec("aiohttp") is None,
    reason="未安装 aiohttp==3.14.3，HTTP listener 默认关闭",
)

HASH_BLOCK_ADMISSION_SECONDS = 2.0
HASH_BLOCK_FAIL_JOB_SECONDS = 5.5


class _StubApp:
    def __init__(self, loop):
        self.loop = loop
        self.state = SimpleNamespace(tasks={})


@contextlib.asynccontextmanager
async def _running_server(data_dir: Path, inference: bool = True):
    from core.server.http_server import HttpServer

    loop = asyncio.get_running_loop()
    server = HttpServer(_StubApp(loop), "127.0.0.1", 0, data_dir)
    server.inference_available = inference
    server.prepare()
    await server._runner.setup()
    site = server._web.TCPSite(server._runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield server, f"http://127.0.0.1:{port}"
    finally:
        await server.stop()


def _install_slow_verify(monkeypatch, duration: float):
    """让真实 ``_verify_source`` 在算哈希前同步阻塞，便于观察锁 / I/O worker 是否被占住。"""
    started = threading.Event()
    finished = threading.Event()
    real = HttpStore._verify_source

    def slow(self, row):
        started.set()
        time.sleep(duration)
        try:
            return real(self, row)
        finally:
            finished.set()

    monkeypatch.setattr(HttpStore, "_verify_source", slow)
    return started, finished


async def _http_create(client, base, payload: bytes, token: str, key: str):
    return await client.post(
        f"{base}/v1/uploads",
        content=json.dumps({
            "size_bytes": len(payload),
            "sha256": sha256(payload).hexdigest(),
            "options": {},
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key,
            "Content-Type": "application/json",
        },
    )


async def _http_patch(client, base, upload_id: str, token: str, data: bytes):
    return await client.patch(
        f"{base}/v1/uploads/{upload_id}",
        content=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Upload-Offset": "0",
            "Content-Type": "application/octet-stream",
        },
    )


async def _http_commit(client, base, upload_id: str, token: str):
    return await client.post(
        f"{base}/v1/uploads/{upload_id}/commit",
        content=b"",
        headers={"Authorization": f"Bearer {token}", "Content-Length": "0"},
    )


async def _prepare_upload(client, base, payload: bytes, token: str, key: str) -> str:
    created = await _http_create(client, base, payload, token, key)
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload_id"]
    patched = await _http_patch(client, base, upload_id, token, payload)
    assert patched.status_code == 204, patched.text
    return upload_id


@needs_aiohttp
@pytest.mark.asyncio
async def test_ws_admission_completes_while_commit_hash_still_running(tmp_path, monkeypatch):
    """commit 哈希持续 ≥2 秒期间，共享准入锁上的 count_active_tasks 必须在 1 秒内完成。"""
    payload = b"isolation-admission-payload"
    async with _running_server(tmp_path / "httpdata") as (server, base):
        async with httpx.AsyncClient(timeout=30) as client:
            upload_id = await _prepare_upload(client, base, payload, "tok-a", "key-a")
            started, finished = _install_slow_verify(monkeypatch, HASH_BLOCK_ADMISSION_SECONDS)
            commit_task = asyncio.create_task(_http_commit(client, base, upload_id, "tok-a"))
            assert await asyncio.to_thread(started.wait, 5.0), "commit 没有进入源文件哈希"
            t0 = time.monotonic()
            async with server._app.state.admission_lock:
                total = await count_active_tasks(server._app.state)
            elapsed = time.monotonic() - t0
            assert not finished.is_set(), "哈希已结束，无法证明准入没有等待整文件 SHA-256"
            assert elapsed < 1.0, (
                f"WS 准入在哈希进行中耗时 {elapsed:.3f}s，超过 1 秒"
            )
            assert total >= 0
            committed = await commit_task
            assert committed.status_code == 202, committed.text


@needs_aiohttp
@pytest.mark.asyncio
async def test_fail_job_write_completes_during_commit_hash(tmp_path, monkeypatch):
    """commit 哈希占用期间排入的 fail_job 写库必须在 5 秒内完成，且不把进程打成退出。"""
    first = b"isolation-fail-job-existing"
    second = b"isolation-fail-job-hashing"
    async with _running_server(tmp_path / "httpdata") as (server, base):
        async with httpx.AsyncClient(timeout=30) as client:
            first_id = await _prepare_upload(client, base, first, "tok-1", "key-1")
            first_commit = await _http_commit(client, base, first_id, "tok-1")
            assert first_commit.status_code == 202, first_commit.text
            job_id = first_commit.json()["job_id"]
            second_id = await _prepare_upload(client, base, second, "tok-2", "key-2")
            started, finished = _install_slow_verify(monkeypatch, HASH_BLOCK_FAIL_JOB_SECONDS)
            commit_task = asyncio.create_task(_http_commit(client, base, second_id, "tok-2"))
            assert await asyncio.to_thread(started.wait, 5.0), "commit 没有进入源文件哈希"
            t0 = time.monotonic()
            fail_task = asyncio.create_task(server.fail_job(job_id, "probe"))
            completed, _pending = await asyncio.wait({fail_task}, timeout=5.0)
            elapsed = time.monotonic() - t0
            assert fail_task in completed, (
                f"fail_job 在哈希进行中超过 5 秒仍未完成（elapsed={elapsed:.3f}s）"
            )
            assert fail_task.exception() is None, (
                f"fail_job 在哈希进行中异常退出：{fail_task.exception()!r}"
            )
            assert elapsed < 5.0
            assert not finished.is_set(), "哈希已结束，无法证明 fail_job 没有排在整文件 SHA-256 后面"
            second_commit = await commit_task
            assert second_commit.status_code == 202, second_commit.text


def test_expired_upload_deletes_source_and_drops_reserve(tmp_path):
    """过期未完成上传必须删除源文件，且不再计入 16 GiB 声明预留。"""
    payload = b"expire-and-release"
    with HttpStore(tmp_path / "data") as store:
        record = store.create_upload(
            size_bytes=len(payload),
            sha256=sha256(payload).hexdigest(),
            options={
                "model": None,
                "language": None,
                "context": None,
                "seg_duration": 15.0,
                "seg_overlap": 2.0,
            },
            token="token-a",
            create_key="key-a",
        )
        store.append_bytes(record.upload_id, "token-a", 0, payload)
        source = tmp_path / "data" / "sources" / f"{record.upload_id}.bin"
        assert source.exists()
        assert store._reserved_source_bytes() == len(payload)
        store.conn.execute(
            "UPDATE uploads SET expires_at=? WHERE upload_id=?",
            (time.time() - 1, record.upload_id),
        )
        with pytest.raises(HttpStoreError) as info:
            store.get_upload(record.upload_id, "token-a")
        assert info.value.status == 410
        assert info.value.code == "upload_expired"
        assert not source.exists()
        assert store._reserved_source_bytes() == 0
        rows = store.conn.execute(
            "SELECT state FROM uploads WHERE upload_id=?",
            (record.upload_id,),
        ).fetchall()
        assert rows[0]["state"] == "EXPIRED"
