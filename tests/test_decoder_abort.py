"""#93 解码子进程中止顺序与时长越线回归。"""
from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import numpy as np
import pytest
import websockets

from core.protocol import AudioMessage
from core.server.connection import audio_decoder as audio_decoder_module
from core.server.connection import ws_recv as ws_recv_module
from core.server.connection.audio_decoder import AudioDecoder
from core.server.http_file_runner import FileSourceDecoder
from tests.harness.client import collect_terminal


def _encode_audio(samples: np.ndarray, codec: str, output_format: str) -> bytes:
    if shutil.which("ffmpeg") is None:
        pytest.fail("本测试需要真实 ffmpeg")
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "f32le", "-ar", "16000", "-ac", "1", "-i", "pipe:0",
            "-c:a", codec, "-f", output_format, "pipe:1",
        ],
        input=samples.astype("<f4", copy=False).tobytes(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


@pytest.fixture(scope="module")
def long_compressed_audio() -> tuple[np.ndarray, dict[str, bytes]]:
    samples = np.random.default_rng(93).uniform(
        -0.8, 0.8, 60 * 16000
    ).astype("<f4")
    return samples, {
        "flac": _encode_audio(samples, "flac", "flac"),
        "ogg_opus": _encode_audio(samples, "libopus", "ogg"),
    }


def _stream_buffered(reader) -> int:
    return len(reader._buffer)


async def _wait_for_backpressure(process, timeout: float = 5.0) -> None:
    reader = process.stdout
    limit = reader._limit
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        buffered = _stream_buffered(reader)
        if reader._paused and buffered > 2 * limit:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"ffmpeg stdout 未形成真实背压：paused={reader._paused} buffered={_stream_buffered(reader)} limit={limit}")


async def _force_reap(process, tasks=()) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*(task for task in tasks if task is not None), return_exceptions=True)
    if process.returncode is None:
        process.kill()
    await asyncio.gather(process.stdout.read(), process.stderr.read())
    await process.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["flac", "ogg_opus"])
async def test_cancel_drains_backpressured_ffmpeg_pipes(
    long_compressed_audio, encoding
):
    _, encoded = long_compressed_audio
    decoder = AudioDecoder(encoding)
    await decoder.feed(b"")
    process = decoder.process
    feed_task = asyncio.create_task(decoder.feed(encoded[encoding]))
    started = time.monotonic()
    try:
        await _wait_for_backpressure(process)
        await asyncio.wait_for(decoder.cancel(), timeout=2)
        assert time.monotonic() - started < 2
        assert process.returncode is not None
        assert process.stdout.at_eof()
        assert process.stderr.at_eof()
    finally:
        if not feed_task.done():
            feed_task.cancel()
        await asyncio.gather(feed_task, return_exceptions=True)
        await _force_reap(
            process,
            (decoder._writer_task, decoder._reader_task, decoder._stderr_task),
        )


@pytest.mark.asyncio
async def test_external_finish_cancellation_propagates(long_compressed_audio):
    _, encoded = long_compressed_audio
    decoder = AudioDecoder("flac")
    await decoder.feed(b"")
    process = decoder.process
    feed_task = asyncio.create_task(decoder.feed(encoded["flac"]))
    try:
        await _wait_for_backpressure(process)
        finish_task = asyncio.create_task(decoder.finish())
        await asyncio.sleep(0)
        finish_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await finish_task
        assert process.returncode is not None
    finally:
        if not feed_task.done():
            feed_task.cancel()
        await asyncio.gather(feed_task, return_exceptions=True)
        await _force_reap(
            process,
            (decoder._writer_task, decoder._reader_task, decoder._stderr_task),
        )


@pytest.mark.asyncio
async def test_http_decoder_close_drains_backpressured_ffmpeg_pipes(tmp_path: Path, long_compressed_audio, caplog):
    _, encoded = long_compressed_audio
    source = tmp_path / "long.flac"
    source.write_bytes(encoded["flac"])
    decoder = await FileSourceDecoder(source).start()
    chunks = decoder.pcm_chunks()
    process = decoder.process
    await anext(chunks)
    try:
        await _wait_for_backpressure(process)
        with caplog.at_level(logging.ERROR):
            await asyncio.wait_for(decoder.close(), timeout=2)
        assert process.returncode is not None
        assert process.stdout.at_eof()
        assert process.stderr.at_eof()
        assert not any("kill 后仍未退出" in record.getMessage() for record in caplog.records)
    finally:
        await chunks.aclose()
        await _force_reap(process, (decoder._stderr_task,))


def _compressed_frame(task_id: str, payload: bytes, encoding: str, *,
                      final: bool, samples_total: int) -> str:
    return AudioMessage(
        task_id=task_id, source="mic",
        data=base64.b64encode(payload).decode("ascii"), is_final=final,
        time_start=time.time(), seg_duration=5.0, seg_overlap=0.0,
        encoding=encoding, samples_total=samples_total if final else None,
    ).to_json()


async def _assert_closed(websocket) -> None:
    try:
        await asyncio.wait_for(websocket.recv(), timeout=20)
    except websockets.ConnectionClosed:
        return
    raise AssertionError("audio_too_long 错误帧后连接未关闭")


def _tracking_decoder_class(real_decoder):
    class TrackingDecoder(real_decoder):
        instances = []

        def __init__(self, decoder_encoding):
            super().__init__(decoder_encoding)
            self.backpressure_observed = False
            type(self).instances.append(self)

        async def _wait_for_backpressure(self):
            reader = self.process.stdout
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if reader._paused and _stream_buffered(reader) > 2 * reader._limit:
                    self.backpressure_observed = True
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("消费侧停止取许可后 stdout 未形成真实背压")

        async def pcm_chunks(self):
            async for pcm in super().pcm_chunks():
                if self.samples_emitted > 5 * 16000 and not self.backpressure_observed:
                    await self._wait_for_backpressure()
                yield pcm

        async def cancel(self):
            if self.process is not None:
                reader = self.process.stdout
                self.backpressure_observed |= (
                    reader._paused and _stream_buffered(reader) > 2 * reader._limit
                )
            await super().cancel()

    return TrackingDecoder


async def _run_ws_audio_too_long(
    fake_asr_server, payload: bytes, encoding: str, samples_total: int, *,
    final_only: bool, decoder_class,
) -> tuple[float, object]:
    task_id = f"cw93-{encoding}-{uuid.uuid4()}"
    decoder_class.instances.clear()
    started = time.monotonic()
    async with websockets.connect(
        fake_asr_server.url, max_size=None, ping_interval=None
    ) as client:
        async def send_stream() -> None:
            if final_only:
                await client.send(_compressed_frame(
                    task_id, payload, encoding, final=True, samples_total=samples_total
                ))
                return
            chunk_size = 64 * 1024
            for offset in range(0, len(payload), chunk_size):
                await client.send(_compressed_frame(
                    task_id, payload[offset:offset + chunk_size], encoding,
                    final=False, samples_total=samples_total,
                ))
            await client.send(_compressed_frame(
                task_id, b"", encoding, final=True, samples_total=samples_total
            ))

        sender = asyncio.create_task(send_stream())
        messages, closed = await collect_terminal(
            client, task_id=task_id, timeout=5
        )
        await asyncio.gather(sender, return_exceptions=True)
        elapsed = time.monotonic() - started
        error = next(message for message in messages if message.get("type") == "error")
        assert error["code"] == "audio_too_long", error
        assert elapsed <= 5
        if not closed:
            await _assert_closed(client)
    assert decoder_class.instances
    decoder = decoder_class.instances[-1]
    assert decoder.backpressure_observed
    assert decoder.process.returncode is not None
    return elapsed, decoder


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["flac", "ogg_opus"])
async def test_ws_compressed_audio_too_long_is_delivered_with_backpressure(
    fake_asr_server, long_compressed_audio, monkeypatch, caplog, encoding
):
    samples, encoded = long_compressed_audio
    monkeypatch.setenv("CW_MAX_TASK_SECONDS", "5")
    monkeypatch.setattr(ws_recv_module.Config, "upload_idle_seconds", 120.0)
    real_decoder = ws_recv_module.AudioDecoder
    TrackingDecoder = _tracking_decoder_class(real_decoder)
    monkeypatch.setattr(ws_recv_module, "AudioDecoder", TrackingDecoder)
    with caplog.at_level(logging.INFO):
        for round_number in range(1, 6):
            result, _ = await _run_ws_audio_too_long(
                fake_asr_server,
                encoded[encoding],
                encoding,
                samples.size,
                final_only=False,
                decoder_class=TrackingDecoder,
            )
            print(
                f"cw93_e2e_latency encoding={encoding} round={round_number} "
                f"elapsed_s={result:.6f}",
                flush=True,
            )
    assert any(
        f"code=audio_too_long" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["flac", "ogg_opus"])
async def test_ws_final_frame_audio_too_long_observes_decoder_failure(
    fake_asr_server, long_compressed_audio, monkeypatch, encoding
):
    samples, encoded = long_compressed_audio
    monkeypatch.setenv("CW_MAX_TASK_SECONDS", "5")
    monkeypatch.setattr(ws_recv_module.Config, "upload_idle_seconds", 120.0)
    real_decoder = ws_recv_module.AudioDecoder
    TrackingDecoder = _tracking_decoder_class(real_decoder)
    monkeypatch.setattr(ws_recv_module, "AudioDecoder", TrackingDecoder)
    await _run_ws_audio_too_long(
        fake_asr_server,
        encoded[encoding],
        encoding,
        samples.size,
        final_only=True,
        decoder_class=TrackingDecoder,
    )


def test_decoder_abort_has_no_stale_cancel_timeout_constant():
    assert not hasattr(audio_decoder_module, "_CANCEL_TIMEOUT_SECONDS")
