# coding: utf-8
"""HTTP 段超时只终结 HTTP Job，不牵连并行 WS 任务。"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pytest
import websockets

from core.protocol import AudioMessage
from tests.harness.server import ManagedHttpServerHarness
from tests.test_http_file_runner import make_container


pytest.importorskip("aiohttp", reason="未安装 aiohttp==3.14.3；HTTP 文件入口默认关闭")


async def _submit_file(base_url: str, source: Path, recovery: Path):
    from capswriter_asr import submit_file_http

    return await submit_file_http(
        source, base_url, resume_path=recovery, chunk_bytes=64 * 1024,
        seg_duration=5.0, seg_overlap=1.0,
    )


def _raw_frame(task_id: str, payload: bytes, *, final: bool = False) -> str:
    return AudioMessage(
        task_id=task_id,
        source="mic",
        data=base64.b64encode(payload).decode("ascii"),
        is_final=final,
        time_start=time.time(),
        seg_duration=5.0,
        seg_overlap=0.0,
    ).to_json()


def _health(ws_url: str) -> dict:
    url = ws_url.replace("ws://", "http://", 1) + "/health"
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read())


async def _wait_for_health(ws_url: str, expected: int, timeout: float = 10.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    last = None
    while asyncio.get_running_loop().time() < deadline:
        last = await asyncio.to_thread(_health, ws_url)
        if last["active_tasks"] == expected:
            return last
        await asyncio.sleep(0.02)
    raise AssertionError(f"/health active_tasks 未变成 {expected}：{last}")


async def _wait_http_failed(harness, job_id: str, timeout: float = 15.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    last = None
    while asyncio.get_running_loop().time() < deadline:
        rows = harness.read_db(
            "SELECT state, error_code FROM jobs WHERE job_id=?", (job_id,)
        )
        last = dict(rows[0]) if rows else None
        if last and last["state"] == "FAILED":
            return last
        await asyncio.sleep(0.02)
    raise AssertionError(f"HTTP Job 未落库 FAILED：{last}")


@pytest.mark.asyncio
async def test_http_segment_timeout_does_not_fail_active_ws_or_exit_service(tmp_path):
    """单个 HTTP 推理段超时不应将另一个活动 WS 任务置为 internal。"""
    source = make_container(tmp_path, "slow.mp3", seconds=12.0)
    recovery = tmp_path / "resume.json"
    harness = await ManagedHttpServerHarness.start(
        data_dir=tmp_path / "httpdata",
        options={
            "supports_timestamps": True,
            "result_text": "正文",
            "result_tokens": ["正", "文"],
            "result_timestamps": [0.1, 0.2],
            "delay_on_call": 1,
            "delay_seconds": 5.0,
        },
        env={"CW_SEGMENT_TIMEOUT": "2"},
        enable_ws=True,
    )
    try:
        handle = await _submit_file(harness.base_url, source, recovery)
        deadline = asyncio.get_running_loop().time() + 20
        while len(harness.calls) < 1:
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError(f"假引擎未开始 HTTP 推理：{list(harness.calls)!r}")
            await asyncio.sleep(0.02)

        task_id = "ws-survives-http-timeout"
        samples = np.zeros(16000, dtype="<f4").tobytes()
        async with websockets.connect(
            harness.ws_url, max_size=None, ping_interval=None
        ) as client:
            await client.send(_raw_frame(task_id, samples))
            before = await _wait_for_health(harness.ws_url, 2)
            assert before["worker_alive"] is True

            failed = await _wait_http_failed(harness, handle.job_id)
            assert failed == {"state": "FAILED", "error_code": "inference_timeout"}

            # 基线实现会在上述 FAILED 落库后把 WS 置为 internal 并退出主进程；
            # 修复后 HTTP 终态不影响该 WS 接收连接和活动名额。
            await asyncio.sleep(0.2)
            assert client.state.name == "OPEN", "HTTP 段超时关闭了并行 WS 连接"
            assert harness.process.is_alive(), (
                f"HTTP 段超时令服务主进程退出（exitcode={harness.process.exitcode}）"
            )
            after = await _wait_for_health(harness.ws_url, 1)
            assert after["worker_alive"] is True
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(client.recv(), timeout=0.2)

            # 假引擎的 5 秒慢调用结束后，同一 WS 任务仍可提交 final 并获得成功结果。
            await asyncio.sleep(3.5)
            await client.send(_raw_frame(task_id, b"", final=True))
            messages = []
            while True:
                message = json.loads(await asyncio.wait_for(client.recv(), timeout=10))
                messages.append(message)
                if message.get("is_final") or message.get("type") == "error":
                    break
            assert not any(message.get("type") == "error" for message in messages), messages
            assert messages[-1]["task_id"] == task_id
            assert messages[-1]["is_final"] is True
            assert harness.process.is_alive(), (
                f"WS 后续推理后服务进程退出（exitcode={harness.process.exitcode}）"
            )
    finally:
        await harness.cleanup()
