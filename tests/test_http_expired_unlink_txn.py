"""过期上传必须在写事务内复查状态并删除源文件。"""
from __future__ import annotations

import hashlib
import time

import pytest

from core.server.http_store import UPLOAD_COMMITTED, UPLOAD_EXPIRED, UPLOAD_UPLOADING, HttpStore


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
    source_path = store._source_path(row["source_name"])
    return upload.upload_id, row, source_path


def _expire(store: HttpStore, expiry_path: str, row, now: float) -> None:
    if expiry_path == "lazy":
        store._expire_if_due(row)
    else:
        store.cleanup_terminal_sources(set(), now=now)


@pytest.mark.parametrize("expiry_path", ["lazy", "cleanup"])
def test_expiry_rechecks_committed_state_before_unlink(tmp_path, expiry_path):
    store = HttpStore(tmp_path / expiry_path, inference_ready=lambda: True).open()
    try:
        upload_id, stale_row, source_path = _expired_upload(store, f"committed-{expiry_path}")
        now = time.time()
        real_connection = store.conn
        injected = False

        if expiry_path == "lazy":
            # Caller holds an earlier UPLOADING snapshot; a concurrent commit wins before expiry locks.
            real_connection.execute(
                "UPDATE uploads SET state=? WHERE upload_id=?",
                (UPLOAD_COMMITTED, upload_id),
            )
            injected = True
        else:
            class _Rows:
                def __init__(self, rows):
                    self.rows = rows

                def fetchall(self):
                    return self.rows

            class _CommitAfterExpiryScan:
                def execute(self, sql, parameters=()):
                    nonlocal injected
                    if sql.startswith(
                        "SELECT upload_id, source_name FROM uploads WHERE state=? AND expires_at <= ?"
                    ) and not injected:
                        rows = real_connection.execute(sql, parameters).fetchall()
                        real_connection.execute(
                            "UPDATE uploads SET state=? WHERE upload_id=?",
                            (UPLOAD_COMMITTED, upload_id),
                        )
                        injected = True
                        return _Rows(rows)
                    return real_connection.execute(sql, parameters)

                def __getattr__(self, name):
                    return getattr(real_connection, name)

            store._conn = _CommitAfterExpiryScan()

        _expire(store, expiry_path, stale_row, now)

        current = real_connection.execute(
            "SELECT state FROM uploads WHERE upload_id=?", (upload_id,)
        ).fetchone()
        assert injected
        assert current["state"] == UPLOAD_COMMITTED
        assert source_path.exists()
    finally:
        store.close()


@pytest.mark.parametrize("expiry_path", ["lazy", "cleanup"])
def test_unlink_failure_rolls_back_and_next_expiry_retries(tmp_path, monkeypatch, expiry_path):
    store = HttpStore(tmp_path / expiry_path, inference_ready=lambda: True).open()
    try:
        upload_id, stale_row, source_path = _expired_upload(store, f"retry-{expiry_path}")
        now = time.time()
        original_unlink = store._unlink_source

        def fail_unlink(_source_name):
            raise PermissionError("synthetic unlink failure")

        monkeypatch.setattr(store, "_unlink_source", fail_unlink)
        with pytest.raises(PermissionError, match="synthetic unlink failure"):
            _expire(store, expiry_path, stale_row, now)

        current = store.conn.execute(
            "SELECT state FROM uploads WHERE upload_id=?", (upload_id,)
        ).fetchone()
        assert current["state"] == UPLOAD_UPLOADING
        assert store.conn.in_transaction is False
        assert source_path.exists()

        monkeypatch.setattr(store, "_unlink_source", original_unlink)
        _expire(store, expiry_path, stale_row, now)
        current = store.conn.execute(
            "SELECT state FROM uploads WHERE upload_id=?", (upload_id,)
        ).fetchone()
        assert current["state"] == UPLOAD_EXPIRED
        assert not source_path.exists()
    finally:
        store.close()
