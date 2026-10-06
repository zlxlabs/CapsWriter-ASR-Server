"""#93 解码子进程中止顺序与时长越线回归。"""
from __future__ import annotations

import asyncio
import base64
import functools
import logging
import multiprocessing
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import websockets

from core.protocol import AudioMessage
from core.server.connection import ws_recv as ws_recv_module
from core.server.connection.audio_decoder import AudioDecoder
from core.server.connection.ws_recv import ws_recv
from core.server.connection.ws_send import ws_send
from core.server.http_file_runner import FileSourceDecoder
from tests.harness.client import collect_terminal
from tests.harness.server import ObservedTaskQueue
from tests.harness.worker import run_fake_worker


ISOLATED_TIMEOUT_SECONDS = 15.0
ISOLATED_WS_ROUNDS_TIMEOUT_SECONDS = 45.0


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
    raise AssertionError(
        f"ffmpeg stdout 未形成真实背压：paused={reader._paused} "
        f"buffered={_stream_buffered(reader)} limit={limit}"
    )


def _ffmpeg_pids() -> set[int]:
    pids = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = Path(f"/proc/{entry.name}/comm").read_text().strip()
        except OSError:
            continue
        if comm == "ffmpeg":
            pids.add(int(entry.name))
    return pids


def _live_group_pids(pgid: int) -> list[int]:
    """列出该进程组内仍活着的 pid；僵尸不计，它不占文件描述符、挂不住管道。"""
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry.name}/stat").read_text()
        except OSError:
            continue
        # comm 里可能带空格和右括号，只能从最后一个 ")" 之后开始切
        fields = stat[stat.rindex(")") + 2:].split()
        if fields[0] != "Z" and int(fields[2]) == pgid:
            pids.append(int(entry.name))
    return sorted(pids)


def _kill_group(pgid: int, timeout: float = 5.0) -> list[int]:
    """SIGKILL 整个隔离子进程组；返回杀完仍存活的 pid。

    等的是内核把被 SIGKILL 的成员摘掉，不是等它自己正常退出。
    """
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return []
    deadline = time.monotonic() + timeout
    while True:
        leftover = _live_group_pids(pgid)
        if not leftover or time.monotonic() >= deadline:
            return leftover
        time.sleep(0.02)


def _isolated_child(kind: str, args: tuple, conn) -> None:
    os.setsid()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_isolated_scenario(kind, args))
        conn.send(("ok", result))
    except BaseException as exc:
        try:
            conn.send(("err", f"{type(exc).__name__}: {exc}"))
        except Exception:
            pass
        os._exit(1)
    os._exit(0)


def _run_isolated(kind: str, args: tuple, timeout: float = ISOLATED_TIMEOUT_SECONDS):
    """在独立进程组跑场景；子进程一停就回收整个组，通过路径也不留孤儿进程。

    孤儿会继承 pytest 的 stdout/stderr 管道写端，CI 里 `pytest | cat` 拿不到 EOF，
    步骤就在汇总行之后一直挂着。
    """
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    before = _ffmpeg_pids()
    proc = ctx.Process(target=_isolated_child, args=(kind, args, child_conn))
    proc.start()
    child_conn.close()
    try:
        proc.join(timeout)
        if proc.is_alive():
            raise AssertionError(
                f"expected isolated {kind} to finish in {timeout:g}s, "
                f"actual hung pid={proc.pid} "
                f"leftover_ffmpeg={sorted(_ffmpeg_pids() - before)}"
            )
        if not parent_conn.poll(0.2):
            raise AssertionError(
                f"expected isolated {kind} result pipe, actual exitcode={proc.exitcode}"
            )
        status, payload = parent_conn.recv()
        if status != "ok":
            raise AssertionError(f"isolated {kind} failed: {payload}")
        return payload
    finally:
        leftover_group_pids = _kill_group(proc.pid)
        if leftover_group_pids:
            raise AssertionError(
                f"expected isolated {kind} to leave no live process, "
                f"actual pgid={proc.pid} leftover_group_pids={leftover_group_pids}"
            )


async def _isolated_scenario(kind: str, args: tuple):
    if kind == "cancel":
        return await _scenario_cancel(*args)
    if kind == "finish_cancel":
        return await _scenario_finish_cancel(*args)
    if kind == "ws":
        return await _scenario_ws(*args)
    raise AssertionError(f"unknown isolated kind {kind}")


async def _scenario_cancel(encoding: str, payload: bytes) -> None:
    decoder = AudioDecoder(encoding)
    await decoder.feed(b"")
    process = decoder.process
    feed_task = asyncio.create_task(decoder.feed(payload))
    started = time.monotonic()
    await _wait_for_backpressure(process)
    await decoder.cancel()
    elapsed = time.monotonic() - started
    if elapsed >= 2:
        raise AssertionError(f"expected cancel() in <2s, actual {elapsed:.3f}s")
    if process.returncode is None:
        raise AssertionError("expected ffmpeg reaped, actual returncode=None")
    if not process.stdout.at_eof() or not process.stderr.at_eof():
        raise AssertionError("expected stdout/stderr EOF after cancel")
    if not feed_task.done():
        feed_task.cancel()
        await asyncio.gather(feed_task, return_exceptions=True)


async def _scenario_finish_cancel(payload: bytes) -> None:
    decoder = AudioDecoder("flac")
    await decoder.feed(b"")
    process = decoder.process
    feed_task = asyncio.create_task(decoder.feed(payload))
    await _wait_for_backpressure(process)
    finish_task = asyncio.create_task(decoder.finish())
    await asyncio.sleep(0)
    finish_task.cancel()
    try:
        await finish_task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("expected CancelledError from finish(), actual returned")
    if process.returncode is None:
        raise AssertionError("expected ffmpeg reaped, actual returncode=None")
    if not feed_task.done():
        feed_task.cancel()
        await asyncio.gather(feed_task, return_exceptions=True)


def _compressed_frame(task_id: str, payload: bytes, encoding: str, *,
                      final: bool, samples_total: int) -> str:
    return AudioMessage(
        task_id=task_id, source="mic",
        data=base64.b64encode(payload).decode("ascii"), is_final=final,
        time_start=time.time(), seg_duration=5.0, seg_overlap=0.0,
        encoding=encoding, samples_total=samples_total if final else None,
    ).to_json()


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


async def _run_ws_client(url, payload, encoding, samples_total, *, final_only, decoder_class):
    task_id = f"cw93-{encoding}-{uuid.uuid4()}"
    decoder_class.instances.clear()
    started = time.monotonic()
    async with websockets.connect(
        url, max_size=None, ping_interval=None, close_timeout=0.1
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
        messages, closed = await collect_terminal(client, task_id=task_id, timeout=5)
        await asyncio.gather(sender, return_exceptions=True)
        elapsed = time.monotonic() - started
        error = next(message for message in messages if message.get("type") == "error")
        if error["code"] != "audio_too_long":
            raise AssertionError(f"expected code=audio_too_long, actual {error}")
        if elapsed > 5:
            raise AssertionError(f"expected error in ≤5s, actual {elapsed:.3f}s")
        if not closed:
            try:
                await asyncio.wait_for(client.recv(), timeout=2)
            except (websockets.ConnectionClosed, TimeoutError):
                pass
    if not decoder_class.instances:
        raise AssertionError("expected TrackingDecoder instance")
    decoder = decoder_class.instances[-1]
    if not decoder.backpressure_observed:
        raise AssertionError("expected real stdout backpressure before audio_too_long")
    if decoder.process.returncode is None:
        raise AssertionError("expected ffmpeg reaped, actual returncode=None")
    return elapsed


async def _scenario_ws(encoding, payload, samples_total, final_only, rounds):
    decoder_class = _tracking_decoder_class(ws_recv_module.AudioDecoder)
    ws_recv_module.AudioDecoder = decoder_class
    ws_recv_module.Config.seg_cut_snap = False
    ws_recv_module.Config.upload_idle_seconds = 120.0
    os.environ["CW_MAX_TASK_SECONDS"] = "5"
    manager = multiprocessing.Manager()
    sockets_id = manager.list()
    calls = manager.list()
    observed = manager.list()
    queue_in = multiprocessing.Queue()
    queue_out = multiprocessing.Queue()
    worker = multiprocessing.Process(
        target=run_fake_worker,
        args=(queue_in, queue_out, sockets_id, {}, calls),
        daemon=True,
    )
    worker.start()
    app = SimpleNamespace(state=SimpleNamespace(
        queue_in=ObservedTaskQueue(queue_in, observed),
        queue_out=queue_out, sockets={}, sockets_id=sockets_id,
    ))
    server = await websockets.serve(
        functools.partial(ws_recv, app=app),
        "127.0.0.1", 0, max_size=None, ping_interval=None,
    )
    sender = asyncio.create_task(ws_send(app))
    url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    elapsed = []
    try:
        for _ in range(rounds):
            elapsed.append(await _run_ws_client(
                url, payload, encoding, samples_total,
                final_only=final_only, decoder_class=decoder_class,
            ))
        return elapsed
    finally:
        server.close()
        worker.kill()
        worker.join(5)
        if not sender.done():
            sender.cancel()
        manager.shutdown()


@pytest.mark.parametrize("encoding", ["flac", "ogg_opus"])
def test_cancel_drains_backpressured_ffmpeg_pipes(long_compressed_audio, encoding):
    _, encoded = long_compressed_audio
    _run_isolated("cancel", (encoding, encoded[encoding]))


def test_external_finish_cancellation_propagates(long_compressed_audio):
    _, encoded = long_compressed_audio
    _run_isolated("finish_cancel", (encoded["flac"],))


@pytest.mark.asyncio
async def test_http_decoder_close_drains_backpressured_ffmpeg_pipes(
    tmp_path: Path, long_compressed_audio, caplog
):
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
        if process.returncode is None:
            process.kill()
        await asyncio.gather(process.stdout.read(), process.stderr.read())
        await process.wait()


@pytest.mark.parametrize("encoding", ["flac", "ogg_opus"])
def test_ws_compressed_audio_too_long_is_delivered_with_backpressure(
    long_compressed_audio, encoding
):
    samples, encoded = long_compressed_audio
    elapsed = _run_isolated(
        "ws",
        (encoding, encoded[encoding], int(samples.size), False, 5),
        ISOLATED_WS_ROUNDS_TIMEOUT_SECONDS,
    )
    assert all(item <= 5 for item in elapsed), elapsed
    for round_number, item in enumerate(elapsed, start=1):
        print(
            f"cw93_e2e_latency encoding={encoding} round={round_number} "
            f"elapsed_s={item:.6f}",
            flush=True,
        )


@pytest.mark.parametrize("encoding", ["flac", "ogg_opus"])
def test_ws_final_frame_audio_too_long_observes_decoder_failure(
    long_compressed_audio, encoding
):
    samples, encoded = long_compressed_audio
    _run_isolated(
        "ws",
        (encoding, encoded[encoding], int(samples.size), True, 1),
    )
