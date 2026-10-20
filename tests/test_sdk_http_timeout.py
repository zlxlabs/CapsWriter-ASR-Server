"""HTTP SDK 请求超时的用户可见契约。"""
from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "sdk"))

from capswriter_asr import AsrError, submit_file_http  # noqa: E402
import capswriter_asr.http_client as sdk_http_client  # noqa: E402


@asynccontextmanager
async def _http_server(commit_delay: float):
    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while line := await reader.readline():
            method, target, _version = line.decode("ascii").rstrip("\r\n").split(" ", 2)
            headers: dict[str, str] = {}
            while line := await reader.readline():
                if line in (b"\r\n", b"\n"):
                    break
                key, value = line.decode("iso-8859-1").rstrip("\r\n").split(":", 1)
                headers[key.lower()] = value.strip()
            await reader.readexactly(int(headers.get("content-length", "0")))

            if method == "POST" and target == "/v1/uploads":
                status = 201
                payload = {
                    "upload_id": "upload-timeout",
                    "state": "UPLOADING",
                    "size_bytes": 4,
                    "confirmed_offset": 0,
                    "expires_at": "2026-10-20T00:00:00Z",
                }
            elif method == "PATCH" and target == "/v1/uploads/upload-timeout":
                status = 204
                payload = None
            elif method == "POST" and target == "/v1/uploads/upload-timeout/commit":
                await asyncio.sleep(commit_delay)
                status = 202
                payload = {"job_id": "job-after-slow-commit", "state": "QUEUED"}
            else:
                raise AssertionError((method, target))

            body = b"" if payload is None else json.dumps(payload).encode("utf-8")
            response_headers = {
                "Content-Length": str(len(body)),
                "Connection": "close",
            }
            if payload is not None:
                response_headers["Content-Type"] = "application/json"
            if status == 204:
                response_headers["Upload-Offset"] = "4"
            writer.write(
                f"HTTP/1.1 {status} test\r\n".encode("ascii")
                + b"".join(
                    f"{key}: {value}\r\n".encode("ascii")
                    for key, value in response_headers.items()
                )
                + b"\r\n"
                + body
            )
            writer.close()
            await writer.wait_closed()
            return

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_submit_file_http_returns_job_after_seven_second_commit(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"data")

    async with _http_server(commit_delay=7) as base_url:
        handle = await submit_file_http(
            source,
            base_url,
            resume_path=tmp_path / "resume.json",
            chunk_bytes=4,
        )

    assert handle.job_id == "job-after-slow-commit"
    assert handle.state == "QUEUED"


@pytest.mark.asyncio
async def test_submit_file_http_constructs_bounded_client_and_commit_timeouts(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.bin"
    source.write_bytes(b"data")
    created_clients = []
    commit_timeouts = []
    original_async_client = httpx.AsyncClient

    def track_async_client(*args, **kwargs):
        client = original_async_client(*args, **kwargs)
        created_clients.append(client)
        original_request = client.request

        async def track_request(method, url, *request_args, **request_kwargs):
            if str(url).endswith("/commit"):
                commit_timeouts.append(request_kwargs.get("timeout"))
            return await original_request(method, url, *request_args, **request_kwargs)

        client.request = track_request
        return client

    monkeypatch.setattr(sdk_http_client.httpx, "AsyncClient", track_async_client)
    async with _http_server(commit_delay=0) as base_url:
        handle = await submit_file_http(
            source,
            base_url,
            resume_path=tmp_path / "resume.json",
            chunk_bytes=4,
        )

    assert handle.job_id == "job-after-slow-commit"
    assert len(created_clients) == 1
    client_timeout = created_clients[0].timeout
    assert (client_timeout.connect, client_timeout.read, client_timeout.write, client_timeout.pool) == (
        30.0,
        30.0,
        30.0,
        30.0,
    )
    assert len(commit_timeouts) == 1
    commit_timeout = commit_timeouts[0]
    assert isinstance(commit_timeout, httpx.Timeout)
    assert (commit_timeout.connect, commit_timeout.read, commit_timeout.write, commit_timeout.pool) == (
        30.0,
        600.0,
        30.0,
        30.0,
    )
