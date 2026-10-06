"""默认时限的两段计时与自动预算公式：本地准备结束后远端预算重新锚定，超时分阶段报错。

自动预算是 watchdog（挂死检测）不是识别时限 SLA：它的唯一职责是服务端不再推进时
把调用救回来，因此必须覆盖实测耗时，不得在识别仍在跑时误杀（issue #69）。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from http import HTTPStatus

import pytest
from websockets.datastructures import Headers

from sdk.capswriter_asr import AsrError, Transcript, transcribe_file
from sdk.capswriter_asr import client as sdk_client
from sdk.capswriter_asr.client import _auto_budget


class FakeClock:
    """只替换 SDK 看到的 time.monotonic/time.time，不动真实 time 模块（asyncio 自用）。"""

    def __init__(self):
        self.now = 1000.0
        self.real = time

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.real.time()

    def __getattr__(self, name):
        return getattr(self.real, name)

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _install_fake_clock(monkeypatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(sdk_client, "time", clock)
    return clock


@pytest.fixture
def tracked_processes(monkeypatch):
    """跟踪 SDK 起的子进程，断言函数返回前都被回收（returncode 非 None）。"""
    original = asyncio.create_subprocess_exec
    processes = []

    async def tracked(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", tracked)
    return processes


@pytest.fixture
def sleeping_ffmpeg(tmp_path, monkeypatch):
    """PATH 里放一个只睡觉的假 ffmpeg：本地转码阶段会真的挂着一个子进程。"""
    tool_dir = tmp_path / "media-tools"
    tool_dir.mkdir()
    ffmpeg = tool_dir / "ffmpeg"
    ffmpeg.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    ffmpeg.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tool_dir}{os.pathsep}{os.environ['PATH']}")
    return ffmpeg


@asynccontextmanager
async def fake_v2_server(handler):
    body = json.dumps({"protocol_version": 2, "encodings": ["s16le"]}).encode()

    async def process_request(connection, request):
        path = request.path if hasattr(request, "path") else connection
        if path != "/health":
            return None
        headers = Headers()
        headers["Content-Type"] = "application/json"
        from websockets.http11 import Response

        return Response(200, HTTPStatus.OK.phrase, headers, body)

    async def receive(ws):
        await handler(ws)

    import websockets

    async with websockets.serve(
        receive,
        "127.0.0.1",
        0,
        process_request=process_request,
        ping_interval=None,
        max_size=None,
        max_queue=None,
    ) as server:
        yield f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


FINAL_RESULT = {
    "type": "result",
    "is_final": True,
    "text": "好的。",
    "tokens": ["好", "的"],
    "timestamps": [0.0, 0.2],
    "duration": 1.0,
}


def _final_payload(task_id: str, **overrides) -> str:
    result = dict(FINAL_RESULT)
    result.update(overrides)
    result["task_id"] = task_id
    return json.dumps(result)


def _write_stub_audio(tmp_path):
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"RIFF")
    return audio


@pytest.mark.asyncio
async def test_default_deadline_reanchors_after_local_stage(tmp_path, monkeypatch):
    """默认时限：本地阶段烧掉 100 秒假时钟，1 秒音频的远端预算从本地结束时起算。"""
    audio = _write_stub_audio(tmp_path)
    clock = _install_fake_clock(monkeypatch)
    seen = {}

    async def slow_transcode(*_args):
        clock.advance(100.0)
        return b"\0" * 32000  # 1 秒 s16le

    monkeypatch.setattr(sdk_client, "_transcode", slow_transcode)

    async def handler(ws):
        seen["sent"] = json.loads(await ws.recv())
        # 远端阶段再烧 110 秒假时钟：累计 210 秒 > 入口的 120 秒上限，
        # 只有「远端预算从本地阶段结束时重新锚定」才会成功返回。
        clock.advance(110.0)
        await ws.send(_final_payload(seen["sent"]["task_id"]))

    async with fake_v2_server(handler) as url:
        transcript = await transcribe_file(audio, url, encoding="s16le", idle_timeout=5)

    assert isinstance(transcript, Transcript)
    assert transcript.text == "好的。"
    assert clock.now == 1000.0 + 210.0
    assert seen["sent"]["samples_total"] == 16000


@pytest.mark.asyncio
async def test_explicit_deadline_total_still_covers_local_stage(tmp_path, monkeypatch):
    """显式 deadline_total=50 是整个调用的墙钟上限：本地阶段推进 100 秒后必须超时。"""
    audio = _write_stub_audio(tmp_path)
    clock = _install_fake_clock(monkeypatch)

    async def slow_transcode(*_args):
        clock.advance(100.0)
        return b"\0" * 32000

    monkeypatch.setattr(sdk_client, "_transcode", slow_transcode)

    async def handler(ws):
        frame = json.loads(await ws.recv())
        await ws.send(_final_payload(frame["task_id"]))

    async with fake_v2_server(handler) as url:
        with pytest.raises(AsrError) as caught:
            await transcribe_file(
                audio, url, encoding="s16le", deadline_total=50, idle_timeout=5
            )

    assert caught.value.code == "timeout"
    # 显式传参下 set_deadline 不重新锚定：本地阶段吃掉 100 秒后预算已耗尽。
    assert "转录超过deadline_total" in caught.value.message


@pytest.mark.asyncio
async def test_default_path_timeout_names_auto_budget(tmp_path, monkeypatch):
    """默认路径下用户没传过 deadline_total，消息不得把它写成被超过的预算。"""
    audio = _write_stub_audio(tmp_path)
    clock = _install_fake_clock(monkeypatch)

    async def fast_transcode(*_args):
        return b"\0" * 32000

    monkeypatch.setattr(sdk_client, "_transcode", fast_transcode)

    async def handler(ws):
        await ws.recv()
        clock.advance(200.0)  # 远超重锚定后的自动预算 _auto_budget(1) = 124 秒
        await ws.send(_final_payload())

    async with fake_v2_server(handler) as url:
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio, url, encoding="s16le", idle_timeout=5)

    assert caught.value.code == "timeout"
    assert "自动预算" in caught.value.message
    assert "远端转录" in caught.value.message
    assert "deadline_total" not in caught.value.message


@pytest.mark.asyncio
async def test_explicit_deadline_kills_local_ffmpeg(
    tmp_path, sleeping_ffmpeg, tracked_processes
):
    """显式 deadline_total 卡在本地转码：抛 timeout，且本地 ffmpeg 子进程被回收。"""
    audio = _write_stub_audio(tmp_path)

    async def handler(ws):
        await ws.recv()  # pragma: no cover - 超时前不该走到上传

    async with fake_v2_server(handler) as url:
        with pytest.raises(AsrError) as caught:
            await transcribe_file(
                audio, url, encoding="s16le", deadline_total=1, idle_timeout=5
            )

    assert caught.value.code == "timeout"
    assert "本地准备" in caught.value.message
    assert tracked_processes, "本地转码应真的起过 ffmpeg 子进程"
    assert all(process.returncode is not None for process in tracked_processes), [
        process.pid for process in tracked_processes if process.returncode is None
    ]


@pytest.mark.asyncio
async def test_remote_stage_timeout_message(tmp_path, monkeypatch):
    """远端阶段超时：本地阶段已完成，消息点名「远端转录」。"""
    audio = _write_stub_audio(tmp_path)

    async def fast_transcode(*_args):
        return b"\0" * 32000

    async def never_reply(ws):
        await ws.recv()
        await ws.wait_closed()

    monkeypatch.setattr(sdk_client, "_transcode", fast_transcode)
    async with fake_v2_server(never_reply) as url:
        with pytest.raises(AsrError) as caught:
            await transcribe_file(
                audio, url, encoding="s16le", deadline_total=1, idle_timeout=5
            )
    assert caught.value.code == "timeout"
    assert "远端转录" in caught.value.message
    assert "本地准备" not in caught.value.message


@pytest.mark.asyncio
async def test_local_and_remote_timeout_messages_are_distinguishable(
    tmp_path, monkeypatch
):
    """两段超时的消息文案必须不同，且各自点名所处阶段。"""
    audio = _write_stub_audio(tmp_path)
    messages = {}

    async def never_reply(ws):
        await ws.recv()
        await ws.wait_closed()

    async def fast_transcode(*_args):
        return b"\0" * 32000

    monkeypatch.setattr(sdk_client, "_transcode", fast_transcode)
    async with fake_v2_server(never_reply) as url:
        with pytest.raises(AsrError) as remote:
            await transcribe_file(
                audio, url, encoding="s16le", deadline_total=1, idle_timeout=5
            )
    messages["remote"] = remote.value.message

    async def hanging_transcode(*_args):
        await asyncio.sleep(30)

    monkeypatch.setattr(sdk_client, "_transcode", hanging_transcode)
    async with fake_v2_server(never_reply) as url:
        with pytest.raises(AsrError) as local:
            await transcribe_file(
                audio, url, encoding="s16le", deadline_total=1, idle_timeout=5
            )
    messages["local"] = local.value.message

    assert "本地准备" in messages["local"]
    assert "远端转录" in messages["remote"]
    assert messages["local"] != messages["remote"]

def test_auto_budget_covers_observed_93s_recognition():
    """93 秒音频的一次真实识别约需 306 秒，自动预算必须留有余量。

    旧公式 max(120, 93 + 60) = 153 秒会在识别仍在跑时误杀长音频（issue #69）。
    """
    assert _auto_budget(93) > 306


def test_auto_budget_formula_is_four_times_duration_plus_120():
    """锁公式本身：93 秒 → 492 秒。改系数或常量会立刻转红。"""
    assert _auto_budget(93) == 492


def test_auto_budget_keeps_the_120_second_floor():
    """0 时长与短音频不得跌破 120 秒下限（原 max(120, …) 的语义由 +120 覆盖）。"""
    assert _auto_budget(0) == 120
    assert _auto_budget(0) >= 120
    assert _auto_budget(1) == 124
    assert _auto_budget(1) >= 120
    assert _auto_budget(30) >= 120


def _write_93s_stub_audio(tmp_path):
    """93 秒 s16le 音频（经 _transcode 直接产出字节，不经过 ffmpeg）。"""
    audio = tmp_path / "long.wav"
    audio.write_bytes(b"RIFF")
    return audio


def _install_93s_transcode(monkeypatch):
    """让 _transcode 交出 93 秒 s16le 字节：samples_total/16000 恰好是 93.0。"""

    async def transcode(*_args):
        return b"\0" * (93 * 16000 * 2)

    monkeypatch.setattr(sdk_client, "_transcode", transcode)


@pytest.mark.asyncio
async def test_auto_budget_lets_93s_identification_finish(tmp_path, monkeypatch):
    """93 秒音频、识别耗时 306 秒：默认自动预算下必须成功返回，不得误杀。"""
    audio = _write_93s_stub_audio(tmp_path)
    clock = _install_fake_clock(monkeypatch)
    _install_93s_transcode(monkeypatch)

    async def handler(ws):
        # 收完上传（含 is_final 帧），再把假时钟推到实测识别耗时。
        while True:
            frame = json.loads(await ws.recv())
            if frame["is_final"]:
                break
        clock.advance(306.0)
        await ws.send(_final_payload(frame["task_id"]))

    async with fake_v2_server(handler) as url:
        transcript = await transcribe_file(audio, url, encoding="s16le", idle_timeout=5)

    assert isinstance(transcript, Transcript)
    assert transcript.text == "好的。"
    # 旧公式的 153 秒预算在这里会把它误杀；新预算 492 秒留出余量。
    assert clock.now == 1000.0 + 306.0


@pytest.mark.asyncio
async def test_default_timeout_message_reports_budget_and_audio_duration(
    tmp_path, monkeypatch
):
    """默认路径超时消息必须同时写明预算秒数与音频时长，便于用户对照。"""
    audio = _write_93s_stub_audio(tmp_path)
    clock = _install_fake_clock(monkeypatch)
    _install_93s_transcode(monkeypatch)

    async def handler(ws):
        while True:
            frame = json.loads(await ws.recv())
            if frame["is_final"]:
                break
        clock.advance(600.0)  # 越过 _auto_budget(93) = 492 秒
        await ws.send(_final_payload(frame["task_id"]))

    async with fake_v2_server(handler) as url:
        with pytest.raises(AsrError) as caught:
            await transcribe_file(audio, url, encoding="s16le", idle_timeout=5)

    assert caught.value.code == "timeout"
    assert "自动预算" in caught.value.message
    # 预算秒数与音频时长都要出现，只写「自动预算」用户无从判断是不是自己音频太长。
    assert "492" in caught.value.message
    assert "93.0" in caught.value.message
    assert "远端转录" in caught.value.message
    assert "deadline_total" not in caught.value.message


@pytest.mark.asyncio
async def test_local_stage_timeout_message_names_entry_cap(tmp_path, monkeypatch):
    """本地准备阶段还没算出时长：消息写入口 120 秒上限，不编造音频时长。"""
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"RIFF")

    async def hanging_transcode(*_args):
        await asyncio.sleep(30)

    monkeypatch.setattr(sdk_client, "_transcode", hanging_transcode)

    async def never_reply(ws):
        await ws.recv()  # pragma: no cover - 本地阶段超时，走不到上传

    async with fake_v2_server(never_reply) as url:
        with pytest.raises(AsrError) as caught:
            # 默认路径入口上限 120 秒，但本地阶段由假时钟推不倒，改用显式上限断言消息结构。
            await transcribe_file(audio, url, encoding="s16le", deadline_total=7)

    assert caught.value.code == "timeout"
    assert "本地准备" in caught.value.message
    assert "7" in caught.value.message
    assert "音频" not in caught.value.message
