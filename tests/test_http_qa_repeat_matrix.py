# coding: utf-8
"""同一隔离服务上的并发／取消／重启五轮矩阵。

循环单元、同服务身份与双消费者契约见
``docs/sessions/261003-http-completion/m6-repeat-matrix-design.md``。
12 组普通 suite 仍以其来源表覆盖一次；本模块不把那 12 组再跑五遍。
假引擎只锁边界，不是 ASR 质量。
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

REPEAT_COUNT = 5
REQUIRED_PHASES = ("concurrency", "cancel_io", "restart", "legacy_ws")
ARTIFACT_ENV = "M6_REPEAT_MATRIX_ARTIFACT_DIR"
TRACE_NAME = "trace.json"
SCHEMA_VERSION = 1
_CREDENTIAL_ASSIGN = re.compile(r"(api[_-]?key|token|secret|password)=", re.I)
_IPV4 = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")


def required_phases() -> tuple[str, ...]:
    """相位轴的机械来源：调用方必须迭代本函数返回值，禁止另写一份人工清单。"""
    return REQUIRED_PHASES


def resolve_artifact_dir(tmp_path: Path | None = None) -> Path:
    """CI / 裸环境必须显式设置 ARTIFACT_ENV 并读同一路径；普通 pytest 默认 tmp_path。"""
    raw = os.environ.get(ARTIFACT_ENV)
    if raw:
        path = Path(raw)
        if not path.is_dir():
            raise AssertionError(f"{ARTIFACT_ENV} 必须是已存在目录")
        return path
    if tmp_path is not None:
        return Path(tmp_path)
    raise AssertionError(
        f"{ARTIFACT_ENV} 未设置，且调用方未提供 tmp_path"
    )


def _json_contains_absolute_path(value: Any) -> bool:
    """拒绝 JSON 值里的绝对路径，源码不写宿主机目录字面量。"""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("/") or (
            len(stripped) >= 3 and stripped[1] == ":" and stripped[0].isalpha()
        ):
            return True
        return False
    if isinstance(value, dict):
        return any(_json_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_json_contains_absolute_path(item) for item in value)
    return False


def consume_repeat_matrix_trace(path: Path) -> dict[str, Any]:
    """独立消费者：读持久文件实际字节，缺轮次／缺相位／自贴标签都必须 AssertionError。

    FileNotFoundError 会转成 AssertionError，避免「文件不存在」冒充行为红验。
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise AssertionError("五轮矩阵工件不存在: trace.json") from exc
    if not raw:
        raise AssertionError("五轮矩阵工件为空")
    decoded = raw.decode("utf-8", errors="replace")
    if _CREDENTIAL_ASSIGN.search(decoded) or _IPV4.search(decoded):
        raise AssertionError("工件含凭据赋值或 IP")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"工件不是合法 JSON: {exc}") from exc
    if _json_contains_absolute_path(payload):
        raise AssertionError("工件含绝对路径")
    if not isinstance(payload, dict):
        raise AssertionError("工件根必须是 object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise AssertionError("schema_version 必须为 1")
    if payload.get("skips") != []:
        raise AssertionError("具名五轮入口禁止 skip")
    if not payload.get("source_runtime"):
        raise AssertionError("缺少 source_runtime")
    sha = payload.get("source_sha")
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise AssertionError("source_sha 必须是 40 位小写 hex")
    roles = payload.get("producer_roles")
    if not isinstance(roles, list) or not roles or not all(isinstance(r, str) and r for r in roles):
        raise AssertionError("producer_roles 必须是非空角色名列表")
    rounds = payload.get("rounds")
    if not isinstance(rounds, list) or len(rounds) != REPEAT_COUNT:
        raise AssertionError(f"rounds 必须恰好 {REPEAT_COUNT} 条，实际={len(rounds) if isinstance(rounds, list) else type(rounds)}")
    seen: set[int] = set()
    job_ids: set[str] = set()
    prev_ffmpeg_offset = -1
    for index, round_row in enumerate(rounds, start=1):
        if not isinstance(round_row, dict):
            raise AssertionError(f"round[{index}] 必须是 object")
        round_id = round_row.get("round")
        if round_id != index:
            raise AssertionError(f"round 字段必须按 1..{REPEAT_COUNT} 顺序，index={index} 得到 {round_id!r}")
        if round_id in seen:
            raise AssertionError("round 编号重复")
        seen.add(round_id)
        if round_row.get("pass") is not True:
            raise AssertionError(f"round {round_id} pass 不为 true")
        if round_row.get("data_dir_role") != "persistent-httpdata":
            raise AssertionError("同服务身份必须记角色 persistent-httpdata")
        phases = round_row.get("phases")
        if not isinstance(phases, dict):
            raise AssertionError(f"round {round_id} 缺少 phases")
        missing = [name for name in required_phases() if name not in phases]
        if missing:
            raise AssertionError(f"round {round_id} 缺少相位 {missing}")
        extra = [name for name in phases if name not in required_phases()]
        if extra:
            raise AssertionError(f"round {round_id} 含未知相位 {extra}")
        for name in required_phases():
            phase = phases[name]
            if not isinstance(phase, dict) or phase.get("pass") is not True:
                raise AssertionError(f"round {round_id} 相位 {name} 未通过")
            evidence_id = phase.get("round_job_id")
            if not isinstance(evidence_id, str) or f"r{round_id}" not in evidence_id:
                raise AssertionError(
                    f"round {round_id} 相位 {name} 的 round_job_id 必须含本轮 r{{n}}，"
                    "禁止借旧事件贴标签"
                )
            if evidence_id in job_ids:
                raise AssertionError(f"round_job_id 跨轮或跨相位重复: {evidence_id}")
            job_ids.add(evidence_id)
            phase_roles = phase.get("producer_roles")
            if not isinstance(phase_roles, list) or not phase_roles:
                raise AssertionError(f"round {round_id} 相位 {name} 缺少 producer_roles")
        _assert_concurrency_evidence(round_id, phases["concurrency"])
        _assert_cancel_evidence(round_id, phases["cancel_io"])
        _assert_restart_evidence(round_id, phases["restart"])
        _assert_ws_evidence(round_id, phases["legacy_ws"])
        _assert_ffmpeg_round(round_id, round_row, prev_ffmpeg_offset)
        prev_ffmpeg_offset = int(round_row["ffmpeg_log_offset"])
    if seen != set(range(1, REPEAT_COUNT + 1)):
        raise AssertionError(f"rounds 未覆盖 1..{REPEAT_COUNT}: {seen}")
    return payload


def _assert_concurrency_evidence(round_id: int, phase: dict) -> None:
    if phase.get("http_owner_kind") != "http":
        raise AssertionError(f"round {round_id} 缺少 HTTP owner 证据")
    if phase.get("ws_owner_kind") != "ws":
        raise AssertionError(f"round {round_id} 缺少 WS owner 证据")
    if phase.get("idle_socket_http_done") is not True:
        raise AssertionError(f"round {round_id} 空 socket 未证明 HTTP DONE")
    if phase.get("ws_disconnected") is not True:
        raise AssertionError(f"round {round_id} 未证明断连 WS")
    if int(phase.get("http_task_count") or 0) < 1 or int(phase.get("ws_task_count") or 0) < 1:
        raise AssertionError(f"round {round_id} worker 未同时收到 HTTP 与 WS Task")
    if phase.get("http_source_bytes_match") is not True:
        raise AssertionError(f"round {round_id} 未证明源文件与落盘字节一致")
    if phase.get("pcm_segment_oracle_ok") is not True:
        raise AssertionError(f"round {round_id} 未证明每段 PCM 对独立 ffmpeg oracle")


def _assert_cancel_evidence(round_id: int, phase: dict) -> None:
    from core.server.http_store import IO_MAILBOX

    for order in ("cancel_first", "io_first"):
        row = phase.get(order)
        if not isinstance(row, dict):
            raise AssertionError(f"round {round_id} 缺少 {order} 证据")
        if int(row.get("confirmed_offset") or -1) < 1:
            raise AssertionError(f"round {round_id} {order} 未记录 confirmed_offset")
        if int(row.get("disk_bytes") or -1) < 1:
            raise AssertionError(f"round {round_id} {order} 未记录磁盘字节")
        pending = row.get("pending_at_cancel")
        mailbox = row.get("mailbox_at_cancel")
        held = row.get("slot_held_before_release")
        if order == "cancel_first":
            if held is not True:
                raise AssertionError(f"round {round_id} cancel_first 取消时槽位必须仍占用")
            if int(pending if pending is not None else -1) != 1:
                raise AssertionError(f"round {round_id} cancel_first pending 必须为 1，实际={pending!r}")
            if int(mailbox if mailbox is not None else -1) != IO_MAILBOX - 1:
                raise AssertionError(
                    f"round {round_id} cancel_first mailbox 必须为 {IO_MAILBOX - 1}，实际={mailbox!r}"
                )
        else:
            if held is not False:
                raise AssertionError(f"round {round_id} io_first I/O 完成后槽位必须已归还")
            if int(pending if pending is not None else -1) != 0:
                raise AssertionError(f"round {round_id} io_first pending 必须为 0，实际={pending!r}")
            if int(mailbox if mailbox is not None else -1) != IO_MAILBOX:
                raise AssertionError(
                    f"round {round_id} io_first mailbox 必须为 {IO_MAILBOX}，实际={mailbox!r}"
                )


def _assert_restart_evidence(round_id: int, phase: dict) -> None:
    old = phase.get("pid_old")
    new = phase.get("pid_new")
    if not isinstance(old, int) or not isinstance(new, int) or old <= 0 or new <= 0:
        raise AssertionError(f"round {round_id} 重启 PID 无效")
    if old == new:
        raise AssertionError(f"round {round_id} 重启后 PID 未更换")
    if phase.get("known_empty_received") is not True:
        raise AssertionError(f"round {round_id} 重启后未用 known-empty 证明无自动重跑")
    if phase.get("done_replay") is not True:
        raise AssertionError(f"round {round_id} 未证明 DONE 新连接回放")
    if int(phase.get("prefix_offset") or 0) <= 0:
        raise AssertionError(f"round {round_id} 缺少已确认 prefix offset")
    if int(phase.get("suffix_offset") or 0) <= int(phase.get("prefix_offset") or 0):
        raise AssertionError(f"round {round_id} 未显式补 suffix")
    if phase.get("result_payload_equal") is not True:
        raise AssertionError(f"round {round_id} 重启前后 GET /result 全 payload 必须相等")
    engine_calls = phase.get("engine_calls_after_restart")
    if not isinstance(engine_calls, int) or engine_calls != 0:
        raise AssertionError(f"round {round_id} 重启后不得自动识别")


def _assert_ws_evidence(round_id: int, phase: dict) -> None:
    if phase.get("ws_final") is not True:
        raise AssertionError(f"round {round_id} 重启后 WS 未收到 is_final")
    if not phase.get("ws_task_id"):
        raise AssertionError(f"round {round_id} 缺少 WS task_id")
    if phase.get("ws_on_restarted_instance") is not True:
        raise AssertionError(f"round {round_id} WS 必须连在仍存活的重启后实例上")


def _assert_ffmpeg_round(round_id: int, round_row: dict, prev_offset: int) -> None:
    offset = round_row.get("ffmpeg_log_offset")
    count = round_row.get("ffmpeg_start_count")
    if not isinstance(offset, int) or offset < 0:
        raise AssertionError(f"round {round_id} 缺少本轮 ffmpeg 日志偏移")
    if prev_offset >= 0 and offset <= prev_offset:
        raise AssertionError(
            f"round {round_id} ffmpeg_log_offset={offset} 必须大于前轮 {prev_offset}，禁止借用累计日志"
        )
    if not isinstance(count, int) or count < 1:
        raise AssertionError(f"round {round_id} 本轮必须有新的 ffmpeg start，实际={count!r}")
    if round_row.get("ffmpeg_argv_real") is not True:
        raise AssertionError(f"round {round_id} 未证明本轮 ffmpeg argv/env 来自真实 shim")


def _require_runtime() -> None:
    if shutil.which("ffmpeg") is None:
        raise AssertionError(
            "测试环境缺少 ffmpeg：具名五轮矩阵必须失败而不是 skip"
        )
    try:
        import aiohttp  # noqa: F401
    except ImportError as exc:
        raise AssertionError(
            "未安装 aiohttp：具名五轮矩阵必须失败而不是 skip"
        ) from exc


def _write_fault_marker(directory: Path, note: str) -> None:
    (directory / "FAULT_INJECTION_REACHED").write_text(note, encoding="utf-8")


def _minimal_phase(round_id: int, name: str, **fields: Any) -> dict[str, Any]:
    body = {
        "pass": True,
        "round_job_id": f"r{round_id}-{name}",
        "producer_roles": ["fixture"],
    }
    body.update(fields)
    return body


def _complete_round(round_id: int) -> dict[str, Any]:
    return {
        "round": round_id,
        "pass": True,
        "data_dir_role": "persistent-httpdata",
        "ffmpeg_start_count": 1,
        "ffmpeg_log_offset": (round_id - 1) * 2,
        "ffmpeg_argv_real": True,
        "phases": {
            "concurrency": _minimal_phase(
                round_id, "concurrency",
                http_owner_kind="http", ws_owner_kind="ws",
                idle_socket_http_done=True, ws_disconnected=True,
                http_task_count=1, ws_task_count=1,
                http_source_bytes_match=True, pcm_segment_oracle_ok=True,
            ),
            "cancel_io": _minimal_phase(
                round_id, "cancel_io",
                cancel_first={
                    "confirmed_offset": 4, "disk_bytes": 4,
                    "slot_held_before_release": True,
                    "pending_at_cancel": 1, "mailbox_at_cancel": 31,
                },
                io_first={
                    "confirmed_offset": 4, "disk_bytes": 4,
                    "slot_held_before_release": False,
                    "pending_at_cancel": 0, "mailbox_at_cancel": 32,
                },
            ),
            "restart": _minimal_phase(
                round_id, "restart",
                pid_old=1000 + round_id, pid_new=2000 + round_id,
                known_empty_received=True, done_replay=True,
                prefix_offset=2, suffix_offset=4,
                result_payload_equal=True, engine_calls_after_restart=0,
            ),
            "legacy_ws": _minimal_phase(
                round_id, "legacy_ws",
                ws_final=True, ws_task_id=f"ws-r{round_id}",
                ws_on_restarted_instance=True,
            ),
        },
    }


def _envelope(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "skips": [],
        "source_runtime": "pytest-fixture",
        "source_sha": "a" * 40,
        "producer_roles": ["fixture"],
        "rounds": rounds,
    }


def test_trace_consumer_rejects_missing_round_five(tmp_path):
    """反例：只有 1..4 轮。注入标记证明本断言被执行到。"""
    path = tmp_path / TRACE_NAME
    path.write_bytes(json.dumps(_envelope([_complete_round(n) for n in range(1, 5)])).encode("utf-8"))
    _write_fault_marker(tmp_path, "missing-round-five")
    marker = (tmp_path / "FAULT_INJECTION_REACHED").read_text(encoding="utf-8")
    assert marker == "missing-round-five"
    with pytest.raises(AssertionError, match="rounds 必须恰好 5"):
        consume_repeat_matrix_trace(path)


def test_trace_consumer_rejects_missing_cancel_or_restart_phase(tmp_path):
    """反例：第 5 轮抽掉 cancel_io 或 restart，消费者必须拒。"""
    _write_fault_marker(tmp_path, "missing-phase")
    assert (tmp_path / "FAULT_INJECTION_REACHED").read_text(encoding="utf-8") == "missing-phase"
    for dropped in ("cancel_io", "restart"):
        rounds = [_complete_round(n) for n in range(1, 6)]
        del rounds[4]["phases"][dropped]
        path = tmp_path / f"drop-{dropped}.json"
        path.write_bytes(json.dumps(_envelope(rounds)).encode("utf-8"))
        with pytest.raises(AssertionError, match="缺少相位"):
            consume_repeat_matrix_trace(path)


def test_trace_consumer_rejects_relabeled_round_without_unique_job(tmp_path):
    """反例：把同一轮证据复制五份只改 round 号，round_job_id 不含对应 r{n}。"""
    clone = _complete_round(1)
    rounds = []
    for n in range(1, 6):
        row = json.loads(json.dumps(clone))
        row["round"] = n
        rounds.append(row)
    path = tmp_path / TRACE_NAME
    path.write_bytes(json.dumps(_envelope(rounds)).encode("utf-8"))
    with pytest.raises(AssertionError, match="r\\{n\\}|round_job_id"):
        consume_repeat_matrix_trace(path)


def test_trace_consumer_rejects_missing_file(tmp_path):
    with pytest.raises(AssertionError, match="五轮矩阵工件不存在"):
        consume_repeat_matrix_trace(tmp_path / TRACE_NAME)


def test_trace_consumer_accepts_complete_five_rounds(tmp_path):
    path = tmp_path / TRACE_NAME
    path.write_bytes(json.dumps(_envelope([_complete_round(n) for n in range(1, 6)])).encode("utf-8"))
    payload = consume_repeat_matrix_trace(path)
    assert [row["round"] for row in payload["rounds"]] == list(range(1, 6))


def test_trace_consumer_rejects_io_first_slot_still_held(tmp_path):
    """反例：io-first 仍写 slot_held=true，与真实 mailbox 归还相反。"""
    rounds = [_complete_round(n) for n in range(1, 6)]
    rounds[2]["phases"]["cancel_io"]["io_first"]["slot_held_before_release"] = True
    path = tmp_path / TRACE_NAME
    path.write_bytes(json.dumps(_envelope(rounds)).encode("utf-8"))
    _write_fault_marker(tmp_path, "io-first-slot-held")
    assert (tmp_path / "FAULT_INJECTION_REACHED").read_text(encoding="utf-8") == "io-first-slot-held"
    with pytest.raises(AssertionError, match="io_first I/O 完成后槽位必须已归还"):
        consume_repeat_matrix_trace(path)


def test_trace_consumer_rejects_ws_not_on_restarted_instance(tmp_path):
    rounds = [_complete_round(n) for n in range(1, 6)]
    rounds[4]["phases"]["legacy_ws"]["ws_on_restarted_instance"] = False
    path = tmp_path / TRACE_NAME
    path.write_bytes(json.dumps(_envelope(rounds)).encode("utf-8"))
    with pytest.raises(AssertionError, match="仍存活的重启后实例"):
        consume_repeat_matrix_trace(path)


def test_trace_consumer_rejects_reused_ffmpeg_log_offset(tmp_path):
    rounds = [_complete_round(n) for n in range(1, 6)]
    rounds[3]["ffmpeg_log_offset"] = rounds[2]["ffmpeg_log_offset"]
    path = tmp_path / TRACE_NAME
    path.write_bytes(json.dumps(_envelope(rounds)).encode("utf-8"))
    with pytest.raises(AssertionError, match="禁止借用累计日志"):
        consume_repeat_matrix_trace(path)


def test_trace_consumer_rejects_unequal_done_payload(tmp_path):
    rounds = [_complete_round(n) for n in range(1, 6)]
    rounds[1]["phases"]["restart"]["result_payload_equal"] = False
    path = tmp_path / TRACE_NAME
    path.write_bytes(json.dumps(_envelope(rounds)).encode("utf-8"))
    with pytest.raises(AssertionError, match="全 payload 必须相等"):
        consume_repeat_matrix_trace(path)


@pytest.mark.asyncio
async def test_legacy_ws_fails_if_restarted_instance_has_no_ws(tmp_path):
    """关闭重启后实例的 WS listener：必须 AssertionError，不是缺 fixture。"""
    from tests.harness.server import ManagedHttpServerHarness
    from tests.test_http_file_runner import FAKE_ENGINE

    harness = await ManagedHttpServerHarness.start(
        data_dir=tmp_path / "httpdata", options=FAKE_ENGINE, enable_ws=False,
    )
    try:
        with pytest.raises(AssertionError, match="未暴露真实 WS"):
            await _phase_legacy_ws(harness, 1)
    finally:
        await harness.stop()
        await harness.cleanup()


def _source_sha() -> str:
    import subprocess

    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=str(Path(__file__).resolve().parents[1]),
        text=True,
    ).strip()
    if len(sha) != 40:
        raise AssertionError("git rev-parse HEAD 未返回 40 位 SHA")
    return sha


def _dump_trace(path: Path, payload: dict) -> None:
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(encoded)
    tmp.replace(path)


async def _wait_until(predicate, what: str, timeout: float = 30.0):
    import asyncio

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError(f"等待「{what}」超时 ({timeout}s)")
        await asyncio.sleep(0.005)


def _decoded_pcm_bytes(path: Path) -> bytes:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AssertionError("测试环境缺少 ffmpeg：具名五轮矩阵必须失败而不是 skip")
    process = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
         "-i", str(path), "-ar", "16000", "-ac", "1", "-f", "f32le", "pipe:1"],
        check=True, capture_output=True,
    )
    pcm = process.stdout
    if not pcm or len(pcm) % 4 != 0:
        raise AssertionError("独立 ffmpeg oracle 未产出 16k mono f32")
    return pcm


def _assert_pcm_segments_match_oracle(segments: list[dict], reference: bytes) -> None:
    from hashlib import sha256

    expected_samples = len(reference) // 4
    cursor = 0
    assert segments and segments[-1].get("is_final") is True
    for index, item in enumerate(segments):
        start = round(item["offset"] * 16000)
        assert start == cursor, (item["offset"], cursor)
        expected = reference[start * 4:(start + item["samples"]) * 4]
        assert len(expected) == item["data_bytes"]
        assert expected != b"\x00" * len(expected)
        assert sha256(expected).hexdigest() == item["data_sha256"]
        if item["is_final"]:
            assert start + item["samples"] == expected_samples
        else:
            overlap_samples = round(item["overlap"] * 16000)
            assert 0 < overlap_samples < item["samples"]
            cursor = start + item["samples"] - overlap_samples


def _ws_tone(seconds: float):
    import numpy as np

    rate = 16000
    count = round(seconds * rate)
    t = np.arange(count, dtype=np.float64) / rate
    return (0.2 * np.sin(2 * np.pi * 220 * t) * np.sin(2 * np.pi * 0.7 * t)).astype("<f4")


def _ws_frame(samples, task_id: str, *, is_final: bool) -> str:
    import base64
    from core.protocol import AudioMessage

    return AudioMessage(
        data=base64.b64encode(samples.astype("<f4", copy=False).tobytes()).decode("ascii"),
        is_final=is_final, task_id=task_id, source="mic", time_start=0.0,
        seg_duration=5.0, seg_overlap=0.0, context="", language="auto",
    ).to_json()


async def _start_ws(state):
    import functools
    from types import SimpleNamespace

    import websockets
    from core.server.connection.ws_recv import ws_recv

    server = await websockets.serve(
        functools.partial(ws_recv, app=SimpleNamespace(state=state)),
        "127.0.0.1", 0, max_size=None, ping_interval=None,
    )
    return server, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


async def _find_http_handler_task(path: str):
    import asyncio

    deadline = asyncio.get_running_loop().time() + 5
    while asyncio.get_running_loop().time() < deadline:
        for task in asyncio.all_tasks():
            if task is asyncio.current_task() or task.done():
                continue
            coro = task.get_coro()
            while coro is not None:
                frame = getattr(coro, "cr_frame", None)
                if frame is not None:
                    request = frame.f_locals.get("request")
                    if frame.f_code.co_name == "wrapped" and request is not None and request.path == path:
                        return task
                coro = getattr(coro, "cr_await", None)
        await asyncio.sleep(0.005)
    raise AssertionError(f"没有找到真实 aiohttp handler task：{path}")


async def _wait_for_worker_pending(worker, expected: int) -> None:
    import asyncio

    deadline = asyncio.get_running_loop().time() + 5
    while len(worker._pending) != expected and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.005)
    assert len(worker._pending) == expected


def _tasks(harness, task_id: str) -> list[dict]:
    return [
        entry for entry in harness.received
        if entry.get("event") == "task" and entry.get("task_id") == task_id
    ]


async def _phase_concurrency(harness, source: Path, round_id: int, tmp_path: Path) -> dict:
    import asyncio
    import json

    import websockets

    from tests.test_http_file_runner import submit, wait_terminal

    samples = _ws_tone(6.0)
    ws_server, ws_url = await _start_ws(harness.state)
    recovery = tmp_path / f"r{round_id}-http-done.json"
    try:
        idle = await websockets.connect(ws_url, max_size=None, ping_interval=None)
        handle = await submit(harness, source, recovery, seg_duration=5.0, seg_overlap=1.0)
        assert (await wait_terminal(harness, recovery)).state == "DONE"
        assert idle.state.name == "OPEN"
        await idle.close()

        live = await websockets.connect(ws_url, max_size=None, ping_interval=None)
        messages: list[dict] = []

        async def reader():
            try:
                async for raw in live:
                    messages.append(json.loads(raw))
            except websockets.ConnectionClosed:
                pass

        reader_task = asyncio.create_task(reader())
        ws_id = f"ws-live-r{round_id}"
        chunk = round(0.4 * 16000)
        finished = asyncio.Event()

        async def streamer():
            for start in range(0, len(samples), chunk):
                await live.send(_ws_frame(samples[start:start + chunk], ws_id, is_final=False))
                await asyncio.sleep(0.05)
            await live.send(_ws_frame(samples[len(samples):], ws_id, is_final=True))
            finished.set()

        stream_task = asyncio.create_task(streamer())
        await _wait_until(lambda: len(_tasks(harness, ws_id)) >= 1, "worker 收到 WS 段")
        recovery_b = tmp_path / f"r{round_id}-http-live.json"
        handle_b = await submit(harness, source, recovery_b, seg_duration=5.0, seg_overlap=1.0)
        both_seen = False
        http_seen = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 30
        while loop.time() < deadline:
            keys = set(harness.state.tasks)
            if ("http", handle_b.job_id, handle_b.job_id) in keys:
                http_seen = True
                if any(key[0] == "ws" for key in keys):
                    both_seen = True
                    break
            elif http_seen:
                break
            await asyncio.sleep(0.005)
        assert both_seen, f"没有观察到 WS 与 HTTP 同时在场: {harness.state.tasks!r}"
        assert (await wait_terminal(harness, recovery_b)).state == "DONE"
        await asyncio.wait_for(finished.wait(), timeout=30)
        await asyncio.wait_for(stream_task, timeout=30)
        await _wait_until(
            lambda: any(item.get("is_final") and item.get("task_id") == ws_id for item in messages),
            "WS 客户端收到 is_final",
        )
        ws_records = _tasks(harness, ws_id)
        http_records = [
            entry for entry in harness.received
            if entry.get("event") == "task" and entry.get("owner_kind") == "http"
            and entry.get("task_id") == handle_b.job_id
        ]
        assert ws_records and http_records
        assert all(item["owner_kind"] == "ws" and item["socket_id"] for item in ws_records)
        assert all(item["owner_kind"] == "http" and item["socket_id"] == "" for item in http_records)
        assert messages and {item["task_id"] for item in messages} == {ws_id}
        finals = [item for item in messages if item.get("is_final")]
        assert len(finals) == 1

        dropped = await websockets.connect(ws_url, max_size=None, ping_interval=None)
        drop_id = f"ws-drop-r{round_id}"

        async def drop_streamer():
            for start in range(0, len(samples), chunk):
                await dropped.send(_ws_frame(samples[start:start + chunk], drop_id, is_final=False))
                await asyncio.sleep(0.05)

        drop_task = asyncio.create_task(drop_streamer())
        await _wait_until(lambda: len(_tasks(harness, drop_id)) >= 1, "worker 收到将被断开的 WS")
        await dropped.close()
        drop_task.cancel()
        await asyncio.gather(drop_task, return_exceptions=True)
        await _wait_until(
            lambda: all(key[2] != drop_id for key in harness.state.tasks),
            "断连 WS 从 state.tasks 移除",
        )
        settled = len(_tasks(harness, drop_id))
        await asyncio.sleep(0.2)
        assert len(_tasks(harness, drop_id)) == settled
        reader_task.cancel()
        await asyncio.gather(reader_task, return_exceptions=True)
        await live.close()
        source_bytes = source.read_bytes()
        row = harness.read_db(
            "SELECT source_name FROM uploads WHERE job_id=?", (handle.job_id,),
        )[0]
        disk = (harness.data_dir / "sources" / row["source_name"]).read_bytes()
        assert disk == source_bytes and disk
        http_segments = [
            entry for entry in harness.received
            if entry.get("event") == "task" and entry.get("owner_kind") == "http"
            and entry.get("task_id") == handle_b.job_id
        ]
        _assert_pcm_segments_match_oracle(http_segments, _decoded_pcm_bytes(source))
        return {
            "pass": True,
            "round_job_id": f"r{round_id}-concurrency-{handle.job_id[:8]}",
            "producer_roles": ["http-sdk", "ws-frame", "recording-worker"],
            "http_owner_kind": "http",
            "ws_owner_kind": "ws",
            "idle_socket_http_done": True,
            "ws_disconnected": True,
            "http_task_count": len(http_records),
            "ws_task_count": len(ws_records),
            "http_source_bytes": len(disk),
            "http_source_bytes_match": True,
            "pcm_segment_oracle_ok": True,
            "engine_calls": len(list(harness.calls)),
            "recovery": str(recovery.name),
            "_recovery_path": recovery,
            "_done_job": handle.job_id,
        }
    finally:
        ws_server.close()
        await ws_server.wait_closed()


async def _phase_cancel(harness, round_id: int) -> dict:
    import asyncio
    import threading
    from hashlib import sha256

    import httpx
    from core.server.http_store import IO_MAILBOX

    server = harness.http_server
    evidence = {}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
        for order in ("cancel-first", "io-first"):
            payload = bytes((65 + round_id, 75 + round_id, 85 + round_id, 95 + round_id))
            key = f"r{round_id}-{order}"
            created = await client.post(
                harness.base_url + "/v1/uploads",
                headers={"Authorization": f"Bearer {key}", "Idempotency-Key": key},
                json={"size_bytes": len(payload), "sha256": sha256(payload).hexdigest(), "options": {}},
            )
            assert created.status_code == 201, created.text
            upload_id = created.json()["upload_id"]
            route_path = f"/v1/uploads/{upload_id}"
            patch_headers = {
                "Authorization": f"Bearer {key}", "Content-Length": "2",
                "Upload-Offset": "0", "Content-Type": "application/octet-stream",
            }
            io_started = threading.Event()
            io_release = threading.Event()
            io_finished = asyncio.Event()
            route_release = asyncio.Event()
            original_append = server._store.append_bytes
            original_run = server._worker.run

            def pause_before_io(upload, capability, offset, data):
                io_started.set()
                if not io_release.wait(5):
                    raise RuntimeError("test I/O barrier timed out")
                return original_append(upload, capability, offset, data)

            async def pause_after_io(func, *args, **kwargs):
                result = await original_run(func, *args, **kwargs)
                if func is original_append and args[0] == upload_id and args[2] == 0:
                    io_finished.set()
                    await route_release.wait()
                return result

            if order == "cancel-first":
                server._store.append_bytes = pause_before_io
            else:
                server._worker.run = pause_after_io
            first_request = asyncio.create_task(client.patch(
                harness.base_url + route_path, headers=patch_headers, content=payload[:2]))
            try:
                if order == "cancel-first":
                    assert await asyncio.to_thread(io_started.wait, 5)
                else:
                    await asyncio.wait_for(io_finished.wait(), timeout=5)
                handler = await _find_http_handler_task(route_path)
                handler.cancel()
                cancelled = await asyncio.gather(handler, return_exceptions=True)
                assert isinstance(cancelled[0], asyncio.CancelledError)
                pending_after = 1 if order == "cancel-first" else 0
                await _wait_for_worker_pending(server._worker, pending_after)
                mailbox_at_cancel = server._worker._mailbox._value
                expected_mailbox = IO_MAILBOX - 1 if order == "cancel-first" else IO_MAILBOX
                assert mailbox_at_cancel == expected_mailbox
                slot_held = mailbox_at_cancel < IO_MAILBOX
                try:
                    await asyncio.wait_for(first_request, timeout=5)
                except httpx.HTTPError:
                    pass
                source_path = server.data_dir / "sources" / f"{upload_id}.bin"
                if order == "cancel-first":
                    row = harness.read_db(
                        "SELECT confirmed_offset FROM uploads WHERE upload_id=?", (upload_id,),
                    )[0]
                    assert row["confirmed_offset"] == 0
                    assert source_path.read_bytes() == b""
                    get_request = asyncio.create_task(client.get(
                        harness.base_url + route_path, headers={"Authorization": f"Bearer {key}"}))
                    stale = asyncio.create_task(client.patch(
                        harness.base_url + route_path,
                        headers={**patch_headers, "Upload-Offset": "0"}, content=payload[:2]))
                    await _wait_for_worker_pending(server._worker, 3)
                    io_release.set()
                    get_result, patch_result = await asyncio.gather(get_request, stale)
                    assert get_result.status_code == 200
                    assert get_result.json()["confirmed_offset"] == 2
                    assert patch_result.status_code == 409
                    await _wait_for_worker_pending(server._worker, 0)
                    server._store.append_bytes = original_append
                    resumed = await client.patch(
                        harness.base_url + route_path,
                        headers={**patch_headers, "Upload-Offset": "2"}, content=payload[2:])
                    assert resumed.status_code == 204
                else:
                    row = harness.read_db(
                        "SELECT confirmed_offset FROM uploads WHERE upload_id=?", (upload_id,),
                    )[0]
                    assert row["confirmed_offset"] == 2
                    assert source_path.read_bytes() == payload[:2]
                    route_release.set()
                    server._worker.run = original_run
                    get_result, patch_result = await asyncio.gather(
                        client.get(harness.base_url + route_path,
                                   headers={"Authorization": f"Bearer {key}"}),
                        client.patch(harness.base_url + route_path,
                                     headers={**patch_headers, "Upload-Offset": "2"},
                                     content=payload[2:]),
                    )
                    assert get_result.status_code == 200
                    assert patch_result.status_code == 204
                final = harness.read_db(
                    "SELECT confirmed_offset FROM uploads WHERE upload_id=?", (upload_id,),
                )[0]
                disk = source_path.read_bytes()
                assert final["confirmed_offset"] == 4 and disk == payload
                await _wait_for_worker_pending(server._worker, 0)
                assert server._worker._mailbox._value == IO_MAILBOX
                field = "cancel_first" if order == "cancel-first" else "io_first"
                evidence[field] = {
                    "confirmed_offset": 4,
                    "disk_bytes": len(disk),
                    "slot_held_before_release": slot_held,
                    "pending_at_cancel": pending_after,
                    "mailbox_at_cancel": mailbox_at_cancel,
                }
            finally:
                io_release.set()
                route_release.set()
                server._store.append_bytes = original_append
                server._worker.run = original_run
    return {
        "pass": True,
        "round_job_id": f"r{round_id}-cancel_io",
        "producer_roles": ["http-handler-cancel", "io-thread-barrier"],
        **evidence,
    }


async def _phase_restart(tmp_path: Path, data_dir: Path, recovery: Path, source: Path,
                         round_id: int, ffmpeg_shim: Path):
    import signal
    from hashlib import sha256

    import httpx
    from tests.harness.server import ManagedHttpServerHarness
    from tests.test_http_file_runner import FAKE_ENGINE, raw_get, raw_job, submit, wait_state

    stalled = dict(FAKE_ENGINE, delay_on_call=1, delay_seconds=60.0)
    prefix = bytes((1 + round_id, 2 + round_id, 3 + round_id, 4 + round_id))
    prefix_key = f"r{round_id}-restart-prefix"
    first = await ManagedHttpServerHarness.start(
        data_dir=data_dir, options=stalled, ffmpeg_shim=str(ffmpeg_shim),
    )
    running_recovery = tmp_path / f"r{round_id}-running.json"
    try:
        done = await raw_job(first, recovery)
        assert done["state"] == "DONE"
        replay_resp = await raw_get(first, recovery, "/result")
        assert replay_resp.status_code == 200, replay_resp.text
        replay = replay_resp.json()
        assert replay.get("is_final") is True
        assert replay.get("task_id") == json.loads(recovery.read_text(encoding="utf-8"))["job_id"]
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
            created = await client.post(
                first.base_url + "/v1/uploads",
                headers={"Authorization": f"Bearer {prefix_key}", "Idempotency-Key": prefix_key},
                json={"size_bytes": len(prefix), "sha256": sha256(prefix).hexdigest(), "options": {}},
            )
            assert created.status_code == 201, created.text
            upload_id = created.json()["upload_id"]
            patched = await client.patch(
                first.base_url + f"/v1/uploads/{upload_id}",
                headers={
                    "Authorization": f"Bearer {prefix_key}", "Content-Length": "2",
                    "Upload-Offset": "0", "Content-Type": "application/octet-stream",
                },
                content=prefix[:2],
            )
            assert patched.status_code == 204
            assert patched.headers["Upload-Offset"] == "2"
        await submit(first, source, running_recovery, seg_duration=5.0, seg_overlap=1.0)
        assert (await wait_state(first, running_recovery, "RUNNING")).state == "RUNNING"
        pid_old = first.process.pid
        await first.terminate(signal.SIGTERM, timeout=20)
    finally:
        await first.cleanup()
    assert first.exitcode == 0, first.stderr_tail()

    second = await ManagedHttpServerHarness.start(
        data_dir=data_dir, options=FAKE_ENGINE, ffmpeg_shim=str(ffmpeg_shim),
        enable_ws=True,
    )
    try:
        pid_new = second.process.pid
        assert pid_new != pid_old
        assert second.process.is_alive()
        assert second.ws_url, "重启后实例必须暴露真实 ws_recv 端口"
        assert list(second.received) == [], f"重启后不得自动重跑: {list(second.received)!r}"
        engine_calls_after_restart = len(list(second.calls))
        assert engine_calls_after_restart == 0
        running = await raw_job(second, running_recovery)
        assert running["state"] == "FAILED"
        assert running["error_code"] == "server_restarted"
        done_again = await raw_job(second, recovery)
        assert done_again["state"] == "DONE"
        replay_again = await raw_get(second, recovery, "/result")
        assert replay_again.status_code == 200, replay_again.text
        assert replay_again.json() == replay
        row = second.read_db(
            "SELECT confirmed_offset, source_name FROM uploads WHERE upload_id=?",
            (upload_id,),
        )[0]
        assert row["confirmed_offset"] == 2
        disk = (second.data_dir / "sources" / row["source_name"]).read_bytes()
        assert disk == prefix[:2]
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
            stale = await client.patch(
                second.base_url + f"/v1/uploads/{upload_id}",
                headers={
                    "Authorization": f"Bearer {prefix_key}", "Content-Length": "2",
                    "Upload-Offset": "0", "Content-Type": "application/octet-stream",
                },
                content=prefix[:2],
            )
            assert stale.status_code == 409
            suffix = await client.patch(
                second.base_url + f"/v1/uploads/{upload_id}",
                headers={
                    "Authorization": f"Bearer {prefix_key}", "Content-Length": "2",
                    "Upload-Offset": "2", "Content-Type": "application/octet-stream",
                },
                content=prefix[2:],
            )
            assert suffix.status_code == 204
            assert suffix.headers["Upload-Offset"] == "4"
        row2 = second.read_db(
            "SELECT confirmed_offset FROM uploads WHERE upload_id=?", (upload_id,),
        )[0]
        assert row2["confirmed_offset"] == 4
        disk2 = (second.data_dir / "sources" / row["source_name"]).read_bytes()
        assert disk2 == prefix
        evidence = {
            "pass": True,
            "round_job_id": f"r{round_id}-restart-{pid_old}-{pid_new}",
            "producer_roles": ["managed-http-subprocess", "http-sdk"],
            "pid_old": pid_old,
            "pid_new": pid_new,
            "known_empty_received": True,
            "done_replay": True,
            "result_payload_equal": True,
            "engine_calls_after_restart": engine_calls_after_restart,
            "prefix_offset": 2,
            "suffix_offset": 4,
        }
    except BaseException:
        await second.stop()
        await second.cleanup()
        raise
    return evidence, second


async def _phase_legacy_ws(harness, round_id: int) -> dict:
    import asyncio
    import json

    import websockets

    assert harness.process.is_alive(), "重启后实例在 WS 相位必须仍存活"
    ws_url = harness.ws_url
    if not ws_url:
        raise AssertionError("重启后实例未暴露真实 WS listener，禁止另起 stub")
    samples = _ws_tone(2.0)
    ws_id = f"ws-after-r{round_id}"
    conn = await websockets.connect(ws_url, max_size=None, ping_interval=None)
    messages: list[dict] = []

    async def reader():
        try:
            async for raw in conn:
                messages.append(json.loads(raw))
        except websockets.ConnectionClosed:
            pass

    reader_task = asyncio.create_task(reader())
    chunk = round(0.5 * 16000)
    for start in range(0, len(samples), chunk):
        await conn.send(_ws_frame(samples[start:start + chunk], ws_id, is_final=False))
    await conn.send(_ws_frame(samples[len(samples):], ws_id, is_final=True))
    await _wait_until(
        lambda: any(item.get("is_final") and item.get("task_id") == ws_id for item in messages),
        "重启后同实例 WS 收到 is_final",
    )
    finals = [item for item in messages if item.get("is_final") and item.get("task_id") == ws_id]
    assert len(finals) == 1
    for field in ("task_id", "is_final"):
        assert field in finals[0]
    assert _tasks(harness, ws_id)
    assert harness.process.is_alive()
    reader_task.cancel()
    await asyncio.gather(reader_task, return_exceptions=True)
    await conn.close()
    return {
        "pass": True,
        "round_job_id": f"r{round_id}-legacy_ws",
        "producer_roles": ["ws-frame", "recording-worker", "restarted-managed-http"],
        "ws_final": True,
        "ws_task_id": ws_id,
        "ws_on_restarted_instance": True,
    }


@pytest.mark.asyncio
async def test_five_round_same_service_concurrency_cancel_restart_ws(tmp_path, monkeypatch):
    """具名入口：同一 persistent-httpdata 上机械循环五轮完整相位。"""
    import sys

    _require_runtime()
    artifact_dir = resolve_artifact_dir(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "sdk"))
    from tests.test_http_file_runner import (
        install_recording_ffmpeg, make_container, read_ffmpeg_invocations,
        running_runner_server,
    )

    ffmpeg_log = install_recording_ffmpeg(tmp_path, monkeypatch)
    source = make_container(tmp_path, "speech.mp3", seconds=8.0)
    shim = tmp_path / "ffmpeg-shim"
    data_dir = tmp_path / "httpdata"
    trace_path = artifact_dir / TRACE_NAME
    payload = {
        "schema_version": SCHEMA_VERSION,
        "skips": [],
        "source_runtime": f"python-{sys.version_info.major}.{sys.version_info.minor}",
        "source_sha": _source_sha(),
        "producer_roles": [
            "http-sdk", "ws-frame", "ffmpeg-shim", "recording-worker",
            "managed-http-subprocess", "io-thread-barrier",
        ],
        "rounds": [],
    }
    _dump_trace(trace_path, payload)
    for round_id in range(1, REPEAT_COUNT + 1):
        invocations_before = read_ffmpeg_invocations(ffmpeg_log) if ffmpeg_log.exists() else []
        log_offset = len(invocations_before)
        async with running_runner_server(tmp_path) as harness:
            assert harness.data_dir.resolve() == data_dir.resolve()
            concurrency = await _phase_concurrency(harness, source, round_id, tmp_path)
            cancel_io = await _phase_cancel(harness, round_id)
            recovery = concurrency.pop("_recovery_path")
            concurrency.pop("_done_job", None)
        restart, second = await _phase_restart(
            tmp_path, data_dir, recovery, source, round_id, shim,
        )
        try:
            assert second.process.is_alive()
            legacy_ws = await _phase_legacy_ws(second, round_id)
        finally:
            await second.stop()
            await second.cleanup()
        round_events = read_ffmpeg_invocations(ffmpeg_log)[log_offset:] if ffmpeg_log.exists() else []
        round_starts = [entry for entry in round_events if entry.get("event") == "start"]
        assert round_starts, f"round {round_id} 没有新的 ffmpeg start"
        for entry in round_starts:
            argv = entry.get("argv")
            assert isinstance(argv, list) and len(argv) >= 2
            assert entry.get("env_marker") == "runner-env-marker"
            assert isinstance(entry.get("path_head"), str) and entry["path_head"]
        payload["rounds"].append({
            "round": round_id,
            "pass": True,
            "data_dir_role": "persistent-httpdata",
            "ffmpeg_start_count": len(round_starts),
            "ffmpeg_log_offset": log_offset,
            "ffmpeg_argv_real": True,
            "phases": {
                "concurrency": concurrency,
                "cancel_io": cancel_io,
                "restart": restart,
                "legacy_ws": legacy_ws,
            },
        })
        _dump_trace(trace_path, payload)
    consume_repeat_matrix_trace(trace_path)
