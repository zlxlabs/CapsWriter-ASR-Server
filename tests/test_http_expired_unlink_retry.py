"""过期上传源文件 unlink 失败时，状态保留以便之后重试。"""
from __future__ import annotations

import hashlib
import time

import pytest

from core.server.http_store import UPLOAD_EXPIRED, UPLOAD_UPLOADING, HttpStore


def _expired_upload(store: HttpStore, key: str):
    payload = b"partial-upload-source"
    token = f"token-{key}"
    upload = store.create_upload(
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        options={},
        token=token,
        create_key=key,
    )
    store.append_bytes(upload.upload_id, token, 0, payload)
    store.conn.execute(
        "UPDATE uploads SET expires_at=? WHERE upload_id=?",
        (time.time() - 1, upload.upload_id),
    )
    row = store.conn.execute(
        "SELECT * FROM uploads WHERE upload_id=?", (upload.upload_id,)
    ).fetchone()
    return upload.upload_id, row, store._source_path(
        store.conn.execute(
            "SELECT source_name FROM uploads WHERE upload_id=?", (upload.upload_id,)
        ).fetchone()["source_name"]
    ), len(payload)


def test_cleanup_retries_failed_expired_source_unlink_after_store_restart(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    store = HttpStore(data_dir, inference_ready=lambda: True).open()
    upload_id, _row, source_path, size_bytes = _expired_upload(store, "cleanup-retry")
    original_unlink = store._unlink_source
    calls = 0

    def fail_once(source_name):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("synthetic unlink failure")
        original_unlink(source_name)

    monkeypatch.setattr(store, "_unlink_source", fail_once)
    with pytest.raises(PermissionError, match="synthetic unlink failure"):
        store.cleanup_terminal_sources(set(), now=time.time())

    current = store.conn.execute(
        "SELECT state FROM uploads WHERE upload_id=?", (upload_id,)
    ).fetchone()
    assert current["state"] == UPLOAD_UPLOADING
    assert source_path.exists()
    assert store._reserved_source_bytes() == size_bytes

    store.close()
    store = HttpStore(data_dir, inference_ready=lambda: True).open()
    try:
        store.cleanup_terminal_sources(set(), now=time.time())
        current = store.conn.execute(
            "SELECT state FROM uploads WHERE upload_id=?", (upload_id,)
        ).fetchone()
        assert current["state"] == UPLOAD_EXPIRED
        assert not source_path.exists()
        assert store._reserved_source_bytes() == 0
    finally:
        store.close()


def test_expire_if_due_keeps_uploading_state_when_source_unlink_fails(tmp_path, monkeypatch):
    store = HttpStore(tmp_path / "data", inference_ready=lambda: True).open()
    try:
        upload_id, row, source_path, _size_bytes = _expired_upload(store, "lazy-expiry")

        def fail_unlink(_source_name):
            raise PermissionError("synthetic unlink failure")

        monkeypatch.setattr(store, "_unlink_source", fail_unlink)
        with pytest.raises(PermissionError, match="synthetic unlink failure"):
            store._expire_if_due(row)

        current = store.conn.execute(
            "SELECT state FROM uploads WHERE upload_id=?", (upload_id,)
        ).fetchone()
        assert current["state"] == UPLOAD_UPLOADING
        assert source_path.exists()
    finally:
        store.close()
