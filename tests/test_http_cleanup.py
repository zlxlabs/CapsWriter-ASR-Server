# coding: utf-8
"""HTTP 终态源清理：真实 listener、I/O worker、runner 与隔离 TCP 客户端。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import queue
import shutil
import signal
import sqlite3
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from core.server import http_file_runner as runner_module
from core.server import http_server as server_module
from core.server.http_server import HttpServer
from core.server.http_store import (
    SOURCE_RETENTION_SECONDS,
    UPLOAD_EXPIRED,
    HttpStore,
    HttpStoreError,
)
from core.server.schema import Result

pytest.importorskip("aiohttp", reason="HTTP 入口测试需要 aiohttp==3.14.3")


class _StubApp:
    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.state = SimpleNamespace(
            tasks={},
            active_http_jobs=[],
            queue_in=queue.Queue(),
        )


async def _wait_until(predicate, message: str, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    assert predicate(), message


def _read_db(data_dir: Path, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(f"file:{data_dir / 'http.sqlite3'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _stored_job(store: HttpStore, payload: bytes, key: str, state: str, terminal_at: float):
    from hashlib import sha256

    upload = store.create_upload(
        size_bytes=len(payload),
        sha256=sha256(payload).hexdigest(),
        options={},
        token=f"token-{key}",
        create_key=key,
    )
    store.append_bytes(upload.upload_id, f"token-{key}", 0, payload)
    job = store.commit_upload(upload.upload_id, f"token-{key}")
    if state == "DONE":
        text = key
        store.record_result(job.job_id, {
            "task_id": job.job_id,
            "type": "file",
            "socket_id": "",
            "owner_kind": "http",
            "duration": 1.0,
            "time_start": 1.0,
            "time_submit": 2.0,
            "time_complete": 3.0,
            "text": text,
            "text_accu": text,
            "tokens": list(text),
            "timestamps": [float(index) for index in range(len(text))],
            "is_final": True,
        })
    elif state == "FAILED":
        store.fail_job(job.job_id, "decode_failed")
    elif state == "RUNNING":
        assert store.mark_running(job.job_id)
    elif state != "QUEUED":
        raise AssertionError(state)
    store.conn.execute(
        "UPDATE jobs SET terminal_at=? WHERE job_id=?", (terminal_at, job.job_id)
    )
    return job.job_id, upload.upload_id, store._source_path(
        store.conn.execute(
            "SELECT source_name FROM uploads WHERE upload_id=?", (upload.upload_id,)
        ).fetchone()["source_name"]
    )


def _stored_partial(store: HttpStore, key: str, token: str, content: bytes, expired=False):
    from hashlib import sha256

    payload = content + b"-unconfirmed-tail"
    upload = store.create_upload(
        size_bytes=len(payload),
        sha256=sha256(payload).hexdigest(),
        options={},
        token=token,
        create_key=key,
    )
    store.append_bytes(upload.upload_id, token, 0, content)
    if expired:
        store.conn.execute(
            "UPDATE uploads SET expires_at=? WHERE upload_id=?",
            (time.time() - 1, upload.upload_id),
        )
    return upload, store._source_path(
        store.conn.execute(
            "SELECT source_name FROM uploads WHERE upload_id=?", (upload.upload_id,)
        ).fetchone()["source_name"]
    )


def _complete_upload(store: HttpStore, key: str, token: str, payload: bytes):
    upload = store.create_upload(
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        options={},
        token=token,
        create_key=key,
    )
    store.append_bytes(upload.upload_id, token, 0, payload)
    return upload.upload_id


def test_store_cleanup_uses_terminal_boundary_and_keeps_every_other_source(tmp_path):
    anchor = time.time() + 0.1
    cutoff = anchor - SOURCE_RETENTION_SECONDS
    store = HttpStore(tmp_path / "data", inference_ready=lambda: True).open()
    try:
        exact_done = _stored_job(store, b"exact-done", "exact-done", "DONE", cutoff)
        older_failed = _stored_job(store, b"older-failed", "older-failed", "FAILED", cutoff - 1)
        newer_done = _stored_job(store, b"newer-done", "newer-done", "DONE", cutoff + 0.5)
        old_created = _stored_job(store, b"old-created", "old-created", "DONE", cutoff + 0.5)
        active_done = _stored_job(store, b"active-done", "active-done", "DONE", cutoff - 10)
        running = _stored_job(store, b"running", "running", "RUNNING", cutoff - 10)
        queued = _stored_job(store, b"queued", "queued", "QUEUED", cutoff - 10)
        missing_terminal = _stored_job(
            store, b"missing-terminal", "missing-terminal", "FAILED", cutoff - 10
        )
        store.conn.execute(
            "UPDATE jobs SET created_at=? WHERE job_id=?",
            (anchor - 20 * 365 * 24 * 3600, old_created[0]),
        )
        store.conn.execute(
            "UPDATE jobs SET terminal_at=NULL WHERE job_id=?", (missing_terminal[0],)
        )
        missing_source = _stored_job(
            store, b"already-gone", "already-gone", "DONE", cutoff - 10
        )
        missing_source[2].unlink()

        partial_upload = store.create_upload(
            size_bytes=20,
            sha256="0" * 64,
            options={},
            token="token-partial-upload",
            create_key="partial-upload",
        )
        store.append_bytes(partial_upload.upload_id, "token-partial-upload", 0, b"partial")
        expired_partial = store.create_upload(
            size_bytes=20,
            sha256="1" * 64,
            options={},
            token="token-expired-partial",
            create_key="expired-partial",
        )
        store.append_bytes(expired_partial.upload_id, "token-expired-partial", 0, b"partial")
        store.conn.execute(
            "UPDATE uploads SET expires_at=? WHERE upload_id=?",
            (anchor - 1, expired_partial.upload_id),
        )
        junk = store.sources_dir / "junk.bin"
        junk.write_bytes(b"unregistered")
        before_reserved = store._reserved_source_bytes()
        before_counts = store.stats()
        before_result_count = store.conn.execute(
            "SELECT COUNT(*) FROM results"
        ).fetchone()[0]
        expected_result = store.get_result(exact_done[0], "token-exact-done")

        store.cleanup_terminal_sources({active_done[0]}, now=anchor)
        store.cleanup_terminal_sources({active_done[0]}, now=anchor)

        assert not exact_done[2].exists()
        assert not older_failed[2].exists()
        assert not missing_source[2].exists()
        for _job_id, _upload_id, path in (
            newer_done,
            old_created,
            active_done,
            running,
            queued,
            missing_terminal,
        ):
            assert path.exists()
        assert store._source_path(
            store.conn.execute(
                "SELECT source_name FROM uploads WHERE upload_id=?",
                (partial_upload.upload_id,),
            ).fetchone()["source_name"]
        ).read_bytes() == b"partial"
        expired_row = store.conn.execute(
            "SELECT state FROM uploads WHERE upload_id=?", (expired_partial.upload_id,)
        ).fetchone()
        assert expired_row["state"] == UPLOAD_EXPIRED
        assert store._source_path(
            store.conn.execute(
                "SELECT source_name FROM uploads WHERE upload_id=?",
                (expired_partial.upload_id,),
            ).fetchone()["source_name"]
        ).read_bytes() == b"partial"
        assert junk.read_bytes() == b"unregistered"
        assert store.get_result(exact_done[0], "token-exact-done") == expected_result
        assert store.job_record(exact_done[0], "token-exact-done").source_available is False
        assert store.job_record(older_failed[0], "token-older-failed").source_available is False
        with pytest.raises(HttpStoreError) as failed_result:
            store.get_result(older_failed[0], "token-older-failed")
        assert failed_result.value.code == "job_failed"
        assert failed_result.value.error_code == "decode_failed"
        assert store.stats() == before_counts
        assert store.conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == before_result_count
        assert store._reserved_source_bytes() == (
            before_reserved - len(b"exact-done") - len(b"older-failed")
        )
    finally:
        store.close()


async def _create_job(client: httpx.AsyncClient, base_url: str, payload: bytes):
    token = "cleanup-test-token"
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "cleanup-test-key",
    }
    created = await client.post(
        f"{base_url}/v1/uploads",
        headers=headers,
        json={"size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
    )
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload_id"]
    patched = await client.patch(
        f"{base_url}/v1/uploads/{upload_id}",
        headers={**headers, "Upload-Offset": "0"},
        content=payload,
    )
    assert patched.status_code == 204
    assert patched.headers["Upload-Offset"] == str(len(payload))
    committed = await client.post(
        f"{base_url}/v1/uploads/{upload_id}/commit",
        headers=headers,
        content=b"",
    )
    assert committed.status_code == 202, committed.text
    return token, headers, created.json(), committed.json()


@pytest.mark.asyncio
async def test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result(
    tmp_path, monkeypatch
):
    """终态落库后 decoder.close 阻塞期间保留源；释放 runner 后由周期任务删除。"""
    monkeypatch.setattr(server_module, "SOURCE_CLEANUP_INTERVAL_SECONDS", 0.02, raising=False)
    app = _StubApp()
    server = HttpServer(app, "127.0.0.1", 0, tmp_path / "httpdata").prepare()
    close_started = asyncio.Event()
    release_close = asyncio.Event()
    decoder_payload = b"\x00\x00\x80\x3f" * 4

    class _Decoder:
        def __init__(self, _path):
            self.samples_emitted = 0

        async def start(self):
            return self

        async def pcm_chunks(self):
            self.samples_emitted += len(decoder_payload) // 4
            yield decoder_payload

        async def finish(self):
            return None

        def kill(self):
            return None

        async def close(self):
            close_started.set()
            await release_close.wait()

    monkeypatch.setattr(runner_module, "ffmpeg_path", lambda: "/test/ffmpeg")
    monkeypatch.setattr(runner_module, "FileSourceDecoder", _Decoder)
    runner = runner_module.HttpFileRunner(app.state, server)
    server.attach_runner(runner)
    app.state.http_result_sink = runner.result_sink
    serve_task = asyncio.create_task(server.serve())
    source_path = None
    headers = None
    job_id = None
    try:
        await _wait_until(lambda: server._bound_port is not None, "HTTP listener 未启动")
        base_url = f"http://127.0.0.1:{server._bound_port}"
        payload = b"registered-source-bytes"
        source_bytes = payload
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5) as client:
            _token, headers, created, committed = await _create_job(client, base_url, payload)
            upload_id = created["upload_id"]
            job_id = committed["job_id"]
            source_path = server.data_dir / "sources" / f"{upload_id}.bin"
            assert source_path.read_bytes() == source_bytes

            failed_payload = b"failed-source-bytes"
            failed_job_id, _failed_upload_id, failed_source = server._worker.run_sync(
                _stored_job,
                server._store,
                failed_payload,
                "periodic-failed",
                "FAILED",
                time.time() - 7 * 24 * 3600 - 1,
            )
            recent_job_id, _recent_upload_id, recent_source = server._worker.run_sync(
                _stored_job,
                server._store,
                b"old-created-terminal-new",
                "old-created-terminal-new",
                "DONE",
                time.time() - 6 * 24 * 3600,
            )
            server._worker.run_sync(
                lambda: server._store.conn.execute(
                    "UPDATE jobs SET created_at=? WHERE job_id=?",
                    (time.time() - 20 * 365 * 24 * 3600, recent_job_id),
                )
            )
            queued_job_id, _queued_upload_id, queued_source = server._worker.run_sync(
                _stored_job,
                server._store,
                b"nonterminal-source",
                "nonterminal-source",
                "QUEUED",
                time.time() - 8 * 24 * 3600,
            )
            server._worker.run_sync(
                lambda: server._store.conn.execute(
                    "UPDATE jobs SET terminal_at=NULL WHERE job_id=?", (queued_job_id,)
                )
            )
            partial_live, partial_live_source = server._worker.run_sync(
                _stored_partial,
                server._store,
                "periodic-partial-live",
                "periodic-partial-live-token",
                b"live-partial-prefix",
            )
            partial_expired, partial_expired_source = server._worker.run_sync(
                _stored_partial,
                server._store,
                "periodic-partial-expired",
                "periodic-partial-expired-token",
                b"expired-partial-prefix",
                True,
            )
            junk_source = server._store.sources_dir / "junk.bin"
            junk_source.write_bytes(b"unregistered-source")

            submitted = await asyncio.wait_for(
                asyncio.to_thread(app.state.queue_in.get, True, 5), timeout=5
            )
            assert submitted.task_id == job_id
            assert submitted.owner_kind == "http"
            assert submitted.socket_id == ""
            assert submitted.data == decoder_payload
            text = "清理后仍可领取"
            expected_result = {
                "task_id": job_id,
                "type": "file",
                "socket_id": "",
                "owner_kind": "http",
                "is_final": True,
                "duration": 1.25,
                "time_start": 10.0,
                "time_submit": 20.0,
                "time_complete": 30.0,
                "text": text,
                "text_accu": text,
                "tokens": list(text),
                "timestamps": [float(index) / 10 for index in range(len(text))],
            }
            result = Result(
                task_id=job_id,
                socket_id="",
                type="file",
                duration=1.25,
                time_start=10.0,
                time_submit=20.0,
                time_complete=30.0,
                text=text,
                text_accu=text,
                tokens=list(text),
                timestamps=[float(index) / 10 for index in range(len(text))],
                is_final=True,
                owner_kind="http",
            )
            await app.state.http_result_sink(result)
            await asyncio.wait_for(close_started.wait(), timeout=5)
            assert job_id in runner.active_jobs
            row = _read_db(
                server.data_dir,
                "SELECT state, terminal_at FROM jobs WHERE job_id=?",
                (job_id,),
            )[0]
            assert row["state"] == "DONE" and row["terminal_at"] is not None
            terminal_at = time.time() - 7 * 24 * 3600 - 1
            server._worker.run_sync(
                lambda: server._store.conn.execute(
                    "UPDATE jobs SET terminal_at=? WHERE job_id=?",
                    (terminal_at, job_id),
                )
            )
            # 真实 SQLite 终态已进入七天之外；清理仍须受 runner 的持有引用保护。
            row = _read_db(
                server.data_dir,
                "SELECT state, terminal_at FROM jobs WHERE job_id=?",
                (job_id,),
            )[0]
            assert row["state"] == "DONE" and row["terminal_at"] == terminal_at
            await asyncio.sleep(0.12)
            assert source_path.exists(), "周期清理在 decoder.close 释放前删除了仍被 runner 引用的源"
            assert job_id in runner.active_jobs
            await _wait_until(lambda: not failed_source.exists(), "周期任务未清理过期 FAILED 源")
            reserved_before_release = server._worker.run_sync(
                server._store._reserved_source_bytes
            )

            release_close.set()
            await asyncio.wait_for(runner._jobs[job_id], timeout=5)
            await _wait_until(
                lambda: not source_path.exists(),
                "runner 释放引用后的下一轮周期清理没有删除已到期源",
            )
            await _wait_until(
                lambda: not failed_source.exists(),
                "周期清理没有删除七天以上的 FAILED 源",
            )
            assert recent_source.exists(), "created_at 很旧不能替代新鲜 terminal_at"
            assert queued_source.exists(), "非终态 Job 不能成为清理候选"
            assert partial_live_source.read_bytes() == b"live-partial-prefix"
            assert partial_expired_source.read_bytes() == b"expired-partial-prefix"
            assert junk_source.read_bytes() == b"unregistered-source"
            expired_row = _read_db(
                server.data_dir,
                "SELECT state FROM uploads WHERE upload_id=?",
                (partial_expired.upload_id,),
            )[0]
            assert expired_row["state"] == UPLOAD_EXPIRED
            assert server._worker.run_sync(
                server._store._reserved_source_bytes
            ) == reserved_before_release - len(payload)
            assert _read_db(
                server.data_dir,
                "SELECT state, error_code, terminal_at FROM jobs WHERE job_id=?",
                (job_id,),
            )[0]["state"] == "DONE"
            assert _read_db(
                server.data_dir,
                "SELECT COUNT(*) AS n FROM results WHERE job_id=?",
                (job_id,),
            )[0]["n"] == 1
            fetched = await client.get(f"{base_url}/v1/jobs/{job_id}", headers=headers)
            assert fetched.status_code == 200
            assert fetched.json()["source_available"] is False
            assert fetched.json()["result_available"] is True
            result_response = await client.get(
                f"{base_url}/v1/jobs/{job_id}/result", headers=headers
            )
            assert result_response.status_code == 200
            assert result_response.json() == expected_result
            stored_result_bytes = _read_db(
                server.data_dir,
                "SELECT payload FROM results WHERE job_id=?",
                (job_id,),
            )[0]["payload"].encode("utf-8")
            assert stored_result_bytes == json.dumps(
                expected_result, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            failed_job = await client.get(
                f"{base_url}/v1/jobs/{failed_job_id}",
                headers={"Authorization": "Bearer token-periodic-failed"},
            )
            assert failed_job.status_code == 200
            assert failed_job.json()["state"] == "FAILED"
            assert failed_job.json()["error_code"] == "decode_failed"
            assert failed_job.json()["source_available"] is False
            failed_result = await client.get(
                f"{base_url}/v1/jobs/{failed_job_id}/result",
                headers={"Authorization": "Bearer token-periodic-failed"},
            )
            assert failed_result.status_code == 409
            assert failed_result.json()["code"] == "job_failed"
            assert failed_result.json()["error_code"] == "decode_failed"
            job_count_before_replay = _read_db(
                server.data_dir, "SELECT COUNT(*) AS n FROM jobs"
            )[0]["n"]
            replayed_create = await client.post(
                f"{base_url}/v1/uploads",
                headers=headers,
                json={"size_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
            )
            assert replayed_create.status_code == 200
            assert replayed_create.json()["upload_id"] == upload_id
            replayed_commit = await client.post(
                f"{base_url}/v1/uploads/{upload_id}/commit",
                headers=headers,
                content=b"",
            )
            assert replayed_commit.status_code == 200
            assert replayed_commit.json()["job_id"] == job_id
            assert _read_db(
                server.data_dir, "SELECT COUNT(*) AS n FROM jobs"
            )[0]["n"] == job_count_before_replay
            expired_upload = await client.get(
                f"{base_url}/v1/uploads/{partial_expired.upload_id}",
                headers={"Authorization": "Bearer periodic-partial-expired-token"},
            )
            assert expired_upload.status_code == 410
            assert expired_upload.json()["code"] == "upload_expired"
            await asyncio.sleep(0.08)
            assert server.fatal is None
    finally:
        release_close.set()
        server._fatal_event.set()
        await asyncio.gather(serve_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_upload_io_and_cleanup_share_one_worker_five_times(tmp_path):
    """append、commit、终态提交各重复五轮，均先完成真实 I/O 再执行排队 cleanup。"""
    server = HttpServer(_StubApp(), "127.0.0.1", 0, tmp_path / "httpdata").prepare()
    server.inference_available = True
    store = server._store
    worker = server._worker
    original_cleanup = store.cleanup_terminal_sources

    async def race(operation_name, args, candidate_source, label, after=None, extra_sources=()):
        operation = getattr(store, operation_name)
        started = threading.Event()
        release = threading.Event()
        cleanup_started = threading.Event()
        active_io = [0]
        active_lock = threading.Lock()

        def blocked_operation(*operation_args):
            with active_lock:
                active_io[0] += 1
            started.set()
            if not release.wait(5):
                raise TimeoutError(f"测试未释放被屏障阻塞的 {label}")
            try:
                result = operation(*operation_args)
                if after is not None:
                    after()
                return result
            finally:
                with active_lock:
                    active_io[0] -= 1

        def observed_cleanup(active_job_ids, now=None):
            with active_lock:
                assert active_io[0] == 0, f"cleanup 与 {label} 的实际 I/O 重叠"
            cleanup_started.set()
            return original_cleanup(active_job_ids, now)

        setattr(store, operation_name, blocked_operation)
        store.cleanup_terminal_sources = observed_cleanup
        operation_task = asyncio.create_task(
            worker.run(getattr(store, operation_name), *args)
        )
        try:
            await asyncio.wait_for(asyncio.to_thread(started.wait, 5), 5)
            cleanup_task = asyncio.create_task(
                worker.run(store.cleanup_terminal_sources, ())
            )
            await _wait_until(
                lambda: len(worker._pending) == 2,
                f"{label} 后的 cleanup 未排入 worker mailbox",
            )
            assert not operation_task.done()
            assert not cleanup_task.done()
            assert not cleanup_started.is_set()
            assert candidate_source.exists()
            release.set()
            result, _ = await asyncio.gather(operation_task, cleanup_task)
            assert cleanup_started.is_set()
            assert not candidate_source.exists()
            for path in extra_sources:
                assert not path.exists()
            await _wait_until(lambda: not worker._pending, f"{label} future 未释放")
            return result
        finally:
            release.set()
            setattr(store, operation_name, operation)
            store.cleanup_terminal_sources = original_cleanup

    try:
        for index in range(5):
            terminal_at = time.time() - SOURCE_RETENTION_SECONDS - 1
            _job_id, _upload_id, append_candidate = worker.run_sync(
                _stored_job, store, f"append-terminal-{index}".encode(),
                f"append-terminal-{index}", "DONE", terminal_at,
            )
            content = f"confirmed-prefix-{index}".encode()
            upload, partial_source = worker.run_sync(
                _stored_partial,
                store,
                f"upload-{index}",
                f"token-upload-{index}",
                content[:5],
            )
            offset = await race(
                "append_bytes",
                (upload.upload_id, f"token-upload-{index}", 5, content[5:]),
                append_candidate,
                f"append 第 {index + 1} 轮",
            )
            assert offset == len(content)
            assert partial_source.read_bytes() == content
            confirmed = worker.run_sync(
                lambda upload_id=upload.upload_id: store.conn.execute(
                    "SELECT confirmed_offset FROM uploads WHERE upload_id=?",
                    (upload_id,),
                ).fetchone()["confirmed_offset"]
            )
            assert confirmed == len(content)

            commit_candidate = worker.run_sync(
                _stored_job, store, f"commit-terminal-{index}".encode(),
                f"commit-terminal-{index}", "DONE", terminal_at,
            )
            commit_payload = f"commit-payload-{index}".encode()
            commit_upload_id = worker.run_sync(
                _complete_upload,
                store,
                f"commit-upload-{index}",
                f"token-commit-{index}",
                commit_payload,
            )
            committed = await race(
                "commit_upload",
                (commit_upload_id, f"token-commit-{index}"),
                commit_candidate[2],
                f"commit 第 {index + 1} 轮",
            )
            assert committed.state == "QUEUED"
            worker.run_sync(store.fail_job, committed.job_id, "probe-complete")

            terminal_candidate = worker.run_sync(
                _stored_job, store, f"record-terminal-{index}".encode(),
                f"record-terminal-{index}", "DONE", terminal_at,
            )
            terminal_payload = f"terminal-result-{index}"
            terminal_upload_id = worker.run_sync(
                _complete_upload,
                store,
                f"record-upload-{index}",
                f"token-record-{index}",
                terminal_payload.encode(),
            )
            terminal_job = worker.run_sync(
                store.commit_upload, terminal_upload_id, f"token-record-{index}"
            )
            assert worker.run_sync(store.mark_running, terminal_job.job_id)
            worker.run_sync(
                lambda: store.conn.execute(
                    "UPDATE jobs SET terminal_at=NULL WHERE job_id=?",
                    (terminal_job.job_id,),
                )
            )
            result = {
                "task_id": terminal_job.job_id,
                "type": "file",
                "socket_id": "",
                "owner_kind": "http",
                "duration": 1.0,
                "time_start": 1.0,
                "time_submit": 2.0,
                "time_complete": 3.0,
                "text": terminal_payload,
                "text_accu": terminal_payload,
                "tokens": list(terminal_payload),
                "timestamps": [float(i) for i in range(len(terminal_payload))],
                "is_final": True,
            }
            _terminal_job_id, _terminal_upload_id, terminal_source = worker.run_sync(
                lambda: (
                    terminal_job.job_id,
                    terminal_upload_id,
                    store._source_path(
                        store.conn.execute(
                            "SELECT source_name FROM uploads WHERE upload_id=?",
                            (terminal_upload_id,),
                        ).fetchone()["source_name"]
                    ),
                )
            )
            await race(
                "record_result",
                (terminal_job.job_id, result),
                terminal_candidate[2],
                f"terminal write 第 {index + 1} 轮",
                after=lambda job_id=terminal_job.job_id, cutoff=terminal_at: store.conn.execute(
                    "UPDATE jobs SET terminal_at=? WHERE job_id=?", (cutoff, job_id)
                ),
                extra_sources=(terminal_source,),
            )
            assert worker.run_sync(
                store.get_result, terminal_job.job_id, f"token-record-{index}"
            )["text"] == terminal_payload
    finally:
        store.cleanup_terminal_sources = original_cleanup
        await server.stop()


@pytest.mark.asyncio
async def test_cleanup_storage_failure_uses_fatal_serve_chain(tmp_path, monkeypatch):
    """已登记源 unlink 的 PermissionError 必须让 serve 失败并保留源与元数据。"""
    from core.server import http_store as store_module

    monkeypatch.setattr(server_module, "SOURCE_CLEANUP_INTERVAL_SECONDS", 0.01, raising=False)
    server = HttpServer(_StubApp(), "127.0.0.1", 0, tmp_path / "httpdata").prepare()
    server.inference_available = True
    _job_id, upload_id, source = server._worker.run_sync(
        _stored_job,
        server._store,
        b"permission-failure-source",
        "permission-failure",
        "DONE",
        time.time() - SOURCE_RETENTION_SECONDS - 1,
    )
    original_unlink = store_module.os.unlink

    def denied(path, *args, **kwargs):
        if Path(path) == source:
            raise PermissionError("injected source unlink denial")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(store_module.os, "unlink", denied)
    serve_task = asyncio.create_task(server.serve())
    with pytest.raises(PermissionError, match="injected source unlink denial"):
        await asyncio.wait_for(serve_task, 5)
    assert isinstance(server.fatal, PermissionError)
    assert source.exists()
    assert _read_db(
        server.data_dir,
        "SELECT state FROM uploads WHERE upload_id=?",
        (upload_id,),
    )[0]["state"] == "COMMITTED"
    assert server._worker is None


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_cleanup_io(tmp_path, monkeypatch):
    """停机先关清理生产者，真实 worker 操作完成后才关闭 store 与 executor。"""
    monkeypatch.setattr(server_module, "SOURCE_CLEANUP_INTERVAL_SECONDS", 3600, raising=False)
    server = HttpServer(_StubApp(), "127.0.0.1", 0, tmp_path / "httpdata").prepare()
    worker = server._worker
    original_cleanup = server._store.cleanup_terminal_sources
    io_started = threading.Event()
    release_io = threading.Event()
    io_finished = threading.Event()

    def blocked_cleanup(active_job_ids, now=None):
        io_started.set()
        if not release_io.wait(5):
            raise TimeoutError("测试未释放被屏障阻塞的 cleanup")
        result = original_cleanup(active_job_ids, now)
        io_finished.set()
        return result

    monkeypatch.setattr(server._store, "cleanup_terminal_sources", blocked_cleanup)
    serve_task = asyncio.create_task(server.serve())
    try:
        await asyncio.wait_for(asyncio.to_thread(io_started.wait, 5), 5)
        server._fatal_event.set()
        await asyncio.sleep(0.03)
        assert not serve_task.done(), "shutdown 越过仍在运行的 cleanup I/O"
        assert server._worker is worker and not worker._closed
        release_io.set()
        await asyncio.wait_for(serve_task, 5)
        assert io_finished.is_set()
        assert server._source_cleanup_task is None
        assert server._worker is None and server._store is None
        await _wait_until(lambda: not worker._pending, "shutdown 丢失或遗留了 I/O future")
        assert worker._closed
        assert server.fatal is None
    finally:
        release_io.set()
        if not serve_task.done():
            server._fatal_event.set()
            await asyncio.gather(serve_task, return_exceptions=True)


# ---------------------------------------------------------------- 进程边界探针

# 真实进程边界探针（tests/fixtures/http_fatal_exit_probe.py）在**自有进程**里跑
# 生产 CapsWriterServer：真实 SocketManager / HttpServer / HttpFileRunner /
# multiprocessing 识别子进程 / Manager / ffmpeg / SQLite，只有 ASR 引擎与权重
# 初始化按卡面 stub。探针与本测试的边界是「一个真实进程的退出与资源回收」，
# 因此下面所有 PID、cgroup、源字节都取自探针进程与 /proc，不在本进程里推断。

PROBE_MODULE = "tests.fixtures.http_fatal_exit_probe"
PROBE_READY_TIMEOUT = 120.0
PROBE_EXIT_TIMEOUT = 30.0
REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _systemd_usable() -> bool:
    """真实消费环境判定：本机 user systemd 能否拉起并观察一个瞬态 unit。"""
    import subprocess

    try:
        probe = subprocess.run(
            ["systemd-run", "--user", "--quiet", "--wait", "--collect",
             "--service-type=exec", "/bin/true"],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def _probe_env(workdir: Path, mode: str) -> dict:
    """只白名单传探针真正需要的环境变量，不整体继承测试环境。"""
    http_dir = workdir / "httpdata"
    if mode == "http_init_failure":
        # 父路径是普通文件：真实 mkdir 在装配期失败，不是被测代码里的假分支
        blocked = workdir / "blocked"
        blocked.write_bytes(b"not-a-directory")
        http_dir = blocked / "httpdata"
    return {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONUNBUFFERED": "1",
        "CW_ADDR": "127.0.0.1",
        "CW_PORT": str(_free_port()),
        "CW_PROBE_MODE": mode,
        "CW_PROBE_LOG": str(workdir / "probe-process.log"),
        "CW_PROBE_WAV": str(workdir / "probe.wav"),
        "CW_PROBE_REPORT": str(workdir / "probe-report.jsonl"),
        "CW_PROBE_DENIAL_LOG": str(workdir / "probe-denial.jsonl"),
        **({} if mode == "ws_only" else {
            "CW_HTTP_PORT": str(_free_port()),
            "CW_HTTP_DATA_DIR": str(http_dir),
        }),
    }


class ProbeRun:
    """探针进程句柄。

    回收只按自己拿到的句柄走：naked 走自己 setsid 出来的进程组，systemd 走自己
    起的那个 unit 名。绝不按名字通配，也绝不碰父进程或别的进程组。
    """

    def __init__(self, workdir: Path, mode: str, launcher: str):
        self.workdir = workdir
        self.mode = mode
        self.launcher = launcher
        self.env = _probe_env(workdir, mode)
        self.report_path = Path(self.env["CW_PROBE_REPORT"])
        self.log_path = workdir / "probe.log"
        self.process_log_path = Path(self.env["CW_PROBE_LOG"])
        self.exit_code = None
        self.control_group = None
        self._process = None
        self._log = None
        self._unit = None

    # ---- 启动 ----

    async def start(self) -> None:
        import subprocess

        argv = [sys.executable, "-m", PROBE_MODULE]
        if self.launcher == "systemd":
            import uuid

            self._unit = f"cw-http-fatal-{os.getpid()}-{uuid.uuid4().hex[:8]}"
            argv = [
                "systemd-run", "--user", f"--unit={self._unit}", "--wait",
                "--service-type=exec",
                "--property=KillMode=control-group",
                "--property=TimeoutStopSec=15",
                f"--working-directory={REPO_ROOT}",
            ]
            argv += [f"--setenv={key}={value}" for key, value in self.env.items()]
            argv += [sys.executable, "-m", PROBE_MODULE]
            self._log = open(self.log_path, "wb")
            self._process = subprocess.Popen(
                argv, cwd=REPO_ROOT, stdout=self._log,
                stderr=subprocess.STDOUT,
            )
            # `systemd-run --wait` 返回时 unit 已被回收，且它的退出码就是被测行为。
            # 先单独确认 unit 真的被创建出来（LoadState=loaded），才能把后续
            # 看到的退出码当作 unit 的退出码而不是 systemd-run 自己的失败。
            await self._wait_unit_loaded()
        else:
            env = dict(os.environ)
            env.update(self.env)
            self._log = open(self.log_path, "wb")
            self._process = subprocess.Popen(
                argv, cwd=REPO_ROOT, env=env, stdout=self._log,
                stderr=subprocess.STDOUT, start_new_session=True,
            )

    # ---- 观察 ----

    def reports(self) -> list:
        if not self.report_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.report_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    async def wait_report(self, phase: str, timeout: float = PROBE_READY_TIMEOUT):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            for report in self.reports():
                if report.get("phase") == phase:
                    if self.launcher == "systemd" and self.control_group is None:
                        self.control_group = self._unit_properties().get(
                            "ControlGroup"
                        ) or None
                    return report
            if self.launcher == "systemd":
                await asyncio.to_thread(self._assert_unit_alive)
            elif self._process.poll() is not None and not self.reports():
                raise AssertionError(
                    f"探针在产出 {phase} 报告前就退出了，exitcode="
                    f"{self._process.returncode}：{self.log_tail()}"
                )
            await asyncio.sleep(0.05)
        raise AssertionError(
            f"探针 {PROBE_MODULE} 在 {timeout}s 内没有产出 {phase} 报告：{self.log_tail()}"
        )

    async def wait_exit(self, timeout: float = PROBE_EXIT_TIMEOUT) -> int:
        # systemd 启动器用 `systemd-run --wait`：它的退出码就是 unit 主进程的退出码，
        # 不依赖已被回收的 transient unit 对象。
        try:
            self.exit_code = await asyncio.to_thread(self._process.wait, timeout)
        except Exception as exc:
            state = (
                await asyncio.to_thread(self._unit_properties)
                if self.launcher == "systemd"
                else f"pid={self._process.pid} alive={_pid_alive(self._process.pid)}"
            )
            raise AssertionError(
                f"探针主进程在 {timeout}s 内没有退出（{state}）；"
                f"探针日志：{self.log_tail()}"
            ) from exc
        return self.exit_code

    async def wait_log(self, marker: str, timeout: float = 15.0) -> str:
        """等真实日志里出现白名单标记。

        journald 是异步落盘：unit 已经退出时那一行未必立刻可读。这里只是等它
        到达，不会把「没有出现」当成通过。
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        tail = ""
        while loop.time() < deadline:
            tail = await asyncio.to_thread(self.log_tail)
            if marker in tail:
                return tail
            await asyncio.sleep(0.1)
        return tail

    def denial_records(self) -> list:
        path = Path(self.env["CW_PROBE_DENIAL_LOG"])
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def cgroup_pids(self) -> list:
        """unit cgroup 里剩下的 PID；unit 尚未起来过则返回空列表。"""
        if not self.control_group:
            return []
        procs = Path("/sys/fs/cgroup") / self.control_group.lstrip("/") / "cgroup.procs"
        if not procs.exists():
            return []
        return [int(line) for line in procs.read_text().split() if line.strip()]

    def log_tail(self, limit: int = 3000) -> str:
        chunks = []
        if self.launcher == "systemd":
            import subprocess

            probe = subprocess.run(
                ["journalctl", "--user", "-u", self._unit, "-n", "60",
                 "--no-pager", "--output=cat"],
                capture_output=True, timeout=30,
            )
            chunks.append(probe.stdout.decode("utf-8", errors="replace"))
        for path in (self.process_log_path, self.log_path):
            if path.exists():
                chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        # 探针自己的进程日志与 systemd-run 输出合并后再过滤；
        # 已被回收的 transient unit 不作为唯一证据源。
        return _whitelisted_log("".join(chunks))[-limit:]

    # ---- 回收（只碰自己的 unit / 自己的进程组） ----

    async def cleanup(self) -> None:
        """只回收本探针自己创建的 unit / 进程组。"""
        import subprocess

        try:
            if self.launcher == "systemd" and self._unit is not None:
                for verb in ("stop", "reset-failed"):
                    subprocess.run(
                        ["systemctl", "--user", verb, self._unit],
                        capture_output=True, timeout=30,
                    )
            elif self._process is not None:
                try:
                    os.killpg(self._process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.to_thread(self._process.wait, 10)
        finally:
            if getattr(self, "_log", None) is not None:
                self._log.close()
                self._log = None

    async def _wait_unit_loaded(self, timeout: float = 20.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            properties = await asyncio.to_thread(self._unit_properties)
            if properties.get("LoadState") == "loaded":
                return
            await asyncio.sleep(0.05)
        raise AssertionError(
            f"systemd-run 没能创建 unit {self._unit}：{self._unit_properties()}；"
            f"systemd-run 输出：{self.log_tail()}"
        )

    def _unit_properties(self) -> dict:
        import subprocess

        probe = subprocess.run(
            ["systemctl", "--user", "show", self._unit,
             "-p", "LoadState", "-p", "ActiveState", "-p", "ExecMainStatus",
             "-p", "ControlGroup"],
            capture_output=True, timeout=30,
        )
        properties = {}
        for line in probe.stdout.decode("utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key:
                properties[key] = value
        return properties

    def _assert_unit_alive(self) -> None:
        properties = self._unit_properties()
        if properties.get("LoadState") != "loaded":
            return  # unit 尚未入队，show 到的只是默认值
        if properties.get("ActiveState") in {"failed", "inactive"}:
            raise AssertionError(
                f"systemd unit {self._unit} 在产出报告前结束：{properties}；"
                f"探针日志：{self.log_tail()}"
            )


def _whitelisted_log(text: str) -> str:
    """只留本卡需要的白名单日志行；不回显环境变量、凭据或原始响应体。"""
    keep = (
        "PROBE=", "HTTP 未知 operation 失败", "listener 将停止",
        "HTTP 文件任务 listener", "开始清理服务端资源", "服务端资源清理完成",
        "正在终止识别子进程", "识别子进程已拉起", "HTTP 文件任务结果已持久化",
        "HTTP 文件任务失败", "HTTP 存储初始化失败", "再见",
        "Finished with result", "Main processes terminated",
    )
    return "".join(
        line + "\n" for line in text.splitlines()
        if any(marker in line for marker in keep)
    )


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return Path(f"/proc/{int(pid)}").exists()


async def _wait_gone(pids, timeout: float = 15.0) -> list:
    """等到这些真实 PID 从 /proc 消失；超时就把还活着的 PID 原样报出来。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    alive = list(pids)
    while loop.time() < deadline and alive:
        alive = [pid for pid in alive if _pid_alive(pid)]
        if alive:
            await asyncio.sleep(0.05)
    return alive


PROBE_LAUNCHERS = [
    pytest.param(
        "naked", id="naked-shell",
        marks=pytest.mark.skipif(
            shutil.which("ffmpeg") is None,
            reason="真实解码链需要本机 ffmpeg",
        ),
    ),
    pytest.param(
        "systemd", id="systemd-unit",
        marks=pytest.mark.skipif(
            shutil.which("ffmpeg") is None or not _systemd_usable(),
            reason="需要本机 ffmpeg 与可用的 user systemd（真实消费环境）",
        ),
    ),
]


def _probe_session(run: "ProbeRun", phase: str | None):
    """启动探针 → 等指定阶段报告 → 等进程退出；无论成败都只回收自己的 unit/进程组。"""
    import asyncio

    async def scenario():
        await run.start()
        try:
            report = await run.wait_report(phase) if phase else None
            return report, await run.wait_exit()
        finally:
            await run.cleanup()

    return asyncio.run(scenario())


@pytest.mark.parametrize("launcher", PROBE_LAUNCHERS)
def test_fatal_cleanup_exits_process_and_reaps_children(tmp_path, launcher):
    """运行中 cleanup fatal：进程必须真的非零退出，识别子进程/Manager 必须被回收。

    红（修复前）：具体 unlink PermissionError 之后 HTTP/WS 监听已关，但主进程与
    识别子进程留在自己 unit 的 cgroup 里不退出，监督看不到退出也就无从重启。
    """
    import asyncio

    workdir = tmp_path / "fatal"
    workdir.mkdir()
    run = ProbeRun(workdir, "fatal", launcher)
    pre, code = _probe_session(run, "pre_fatal")

    assert run.denial_records(), (
        "周期清理没有命中被注入 PermissionError 的那条具体源；"
        f"探针日志：{run.log_tail()}"
    )
    assert code != 0, (
        "fatal 之后进程必须以非零状态真正退出，监督才能触发重启；"
        f"实际 exitcode={code}；探针日志：{run.log_tail()}"
    )
    # 识别子进程与共享 Manager 必须随进程一起消失（不是被 leave 在后台）
    leftover = asyncio.run(_wait_gone([pre["worker_pid"], pre["manager_pid"]]))
    assert leftover == [], f"fatal 之后这些子进程仍然存活：{leftover}"
    assert run.cgroup_pids() == [], (
        f"unit cgroup 里仍残留进程：{run.cgroup_pids()}；探针日志：{run.log_tail()}"
    )
    # 磁盘事实：源字节、Job 终态、结果 payload 与上传元数据都必须原样保留
    data_dir = Path(run.env["CW_HTTP_DATA_DIR"])
    source = data_dir / "sources" / (
        run.denial_records()[0]["path"].rsplit("/", 1)[-1]
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == pre["source"]["sha256"]
    assert source.stat().st_size == pre["source"]["bytes"] == pre["uploaded_bytes"]
    rows = _read_db(
        data_dir,
        "SELECT j.state, j.terminal_at, u.state AS upload_state,"
        " (SELECT payload FROM results WHERE job_id=j.job_id) AS payload"
        " FROM jobs j JOIN uploads u ON u.upload_id=j.upload_id"
        " WHERE j.job_id=?",
        (pre["job_id"],),
    )
    assert len(rows) == 1
    row = rows[0]
    assert (row["state"], row["upload_state"]) == ("DONE", "COMMITTED")
    assert hashlib.sha256(str(row["payload"]).encode("utf-8")).hexdigest() == (
        pre["result_sha256"]
    )
    assert json.loads(row["payload"]) == pre["result_payload"]
    assert pre["job_state"] == "DONE"
    assert pre["uploaded_sha256"] == pre["source"]["sha256"]
    assert pre["source"]["exists"], "PermissionError 不得删除已登记源"
    assert pre["released_runner_jobs"] == [], (
        "老化之前 runner 必须已经释放该 Job 的终态引用，否则清理不该命中它"
    )
    # 监听必须已停：进程退出后端口不再接受连接
    assert _port_refused(pre["http_port"])
    assert _port_refused(pre["ws_port"])
    fatal_report = [
        entry for entry in run.reports() if entry.get("phase") == "post_fatal"
    ]
    assert fatal_report, (
        "没有观察到 listener 监督链上的具体 unlink PermissionError；"
        f"探针日志：{run.log_tail()}"
    )
    assert (fatal_report[0]["fatal_type"], fatal_report[0]["fatal_message"]) == (
        "PermissionError", "injected source unlink denial",
    )
    assert fatal_report[0]["source"]["sha256"] == pre["source"]["sha256"]
    fatal_log = asyncio.run(run.wait_log("HTTP 未知 operation 失败"))
    assert "HTTP 未知 operation 失败" in fatal_log, (
        f"日志里没有 listener 监督链的 fatal 记录：{fatal_log}"
    )


def _port_refused(port: int) -> bool:
    import socket

    with socket.socket() as probe:
        probe.settimeout(2)
        return probe.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize("launcher", PROBE_LAUNCHERS)
def test_normal_sigterm_still_exits_zero(tmp_path, launcher):
    """主动 stop 的既有语义不回归：正常 SIGTERM 仍以 0 退出并回收子进程。"""
    import asyncio

    workdir = tmp_path / "sigterm"
    workdir.mkdir()
    run = ProbeRun(workdir, "sigterm", launcher)
    ready, code = _probe_session(run, "ready")

    assert code == 0, f"正常 SIGTERM 必须 0 退出，实际 {code}：{run.log_tail()}"
    assert ready["worker_pid"] and ready["manager_pid"]
    leftover = asyncio.run(_wait_gone([ready["worker_pid"], ready["manager_pid"]]))
    assert leftover == [], f"主动 stop 后这些子进程仍然存活：{leftover}"


@pytest.mark.parametrize("launcher", PROBE_LAUNCHERS)
def test_http_startup_failure_exits_nonzero_without_hanging_worker(tmp_path, launcher):
    """HTTP 显式启用但装配失败：同一条 root，启动期也不得把 worker 挂在后台。"""
    import asyncio

    workdir = tmp_path / "startup"
    workdir.mkdir()
    run = ProbeRun(workdir, "http_init_failure", launcher)
    _report, code = _probe_session(run, None)

    assert code != 0, f"HTTP 初始化失败必须非零退出，实际 {code}：{run.log_tail()}"
    startup_log = asyncio.run(run.wait_log("HTTP 存储初始化失败"))
    assert "HTTP 存储初始化失败" in startup_log, (
        f"日志里没有真实装配失败记录：{startup_log}"
    )
    assert run.cgroup_pids() == [], (
        f"unit cgroup 里仍残留进程：{run.cgroup_pids()}"
    )


@pytest.mark.parametrize("launcher", PROBE_LAUNCHERS)
def test_http_disabled_keeps_default_websocket_lifecycle(tmp_path, launcher):
    """HTTP disabled：不装配 listener，默认 WS 生命周期与主动 stop 语义不变。"""
    import asyncio

    workdir = tmp_path / "wsonly"
    workdir.mkdir()
    run = ProbeRun(workdir, "ws_only", launcher)
    ready, code = _probe_session(run, "ready")

    assert ready["http_server_is_none"], "未提供 CW_HTTP_PORT 时不得装配 HTTP listener"
    assert code == 0, f"HTTP disabled 下 SIGTERM 必须 0 退出，实际 {code}：{run.log_tail()}"
    leftover = asyncio.run(_wait_gone([ready["worker_pid"], ready["manager_pid"]]))
    assert leftover == [], f"HTTP disabled 收尾后这些子进程仍然存活：{leftover}"
