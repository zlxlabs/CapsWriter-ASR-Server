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
_UNSAFE_IN_TRACE = re.compile(
    r"(/home/|/Users/|\\\\Users\\\\)|"
    r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b|"
    r"(api[_-]?key|token|secret|password)=",
    re.I,
)


def required_phases() -> tuple[str, ...]:
    """相位轴的机械来源：调用方必须迭代本函数返回值，禁止另写一份人工清单。"""
    return REQUIRED_PHASES


def resolve_artifact_dir() -> Path:
    raw = os.environ.get(ARTIFACT_ENV)
    if not raw:
        raise AssertionError(
            f"调用方必须设置 {ARTIFACT_ENV} 为已存在目录，禁止测试自报路径"
        )
    path = Path(raw)
    if not path.is_dir():
        raise AssertionError(f"{ARTIFACT_ENV} 必须是已存在目录")
    return path


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
    unsafe = _UNSAFE_IN_TRACE.search(raw.decode("utf-8", errors="replace"))
    if unsafe:
        raise AssertionError("工件含宿主机路径、IP 或凭据字段")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"工件不是合法 JSON: {exc}") from exc
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


def _assert_cancel_evidence(round_id: int, phase: dict) -> None:
    for order in ("cancel_first", "io_first"):
        row = phase.get(order)
        if not isinstance(row, dict):
            raise AssertionError(f"round {round_id} 缺少 {order} 证据")
        if int(row.get("confirmed_offset") or -1) < 1:
            raise AssertionError(f"round {round_id} {order} 未记录 confirmed_offset")
        if int(row.get("disk_bytes") or -1) < 1:
            raise AssertionError(f"round {round_id} {order} 未记录磁盘字节")
        if row.get("slot_held_before_release") is not True:
            raise AssertionError(f"round {round_id} {order} 未证明槽位在 write 完成前占用")


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


def _assert_ws_evidence(round_id: int, phase: dict) -> None:
    if phase.get("ws_final") is not True:
        raise AssertionError(f"round {round_id} 重启后 WS 未收到 is_final")
    if not phase.get("ws_task_id"):
        raise AssertionError(f"round {round_id} 缺少 WS task_id")


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
        "phases": {
            "concurrency": _minimal_phase(
                round_id, "concurrency",
                http_owner_kind="http", ws_owner_kind="ws",
                idle_socket_http_done=True, ws_disconnected=True,
                http_task_count=1, ws_task_count=1,
            ),
            "cancel_io": _minimal_phase(
                round_id, "cancel_io",
                cancel_first={
                    "confirmed_offset": 4, "disk_bytes": 4,
                    "slot_held_before_release": True,
                },
                io_first={
                    "confirmed_offset": 4, "disk_bytes": 4,
                    "slot_held_before_release": True,
                },
            ),
            "restart": _minimal_phase(
                round_id, "restart",
                pid_old=1000 + round_id, pid_new=2000 + round_id,
                known_empty_received=True, done_replay=True,
                prefix_offset=2, suffix_offset=4,
            ),
            "legacy_ws": _minimal_phase(
                round_id, "legacy_ws",
                ws_final=True, ws_task_id=f"ws-r{round_id}",
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


@pytest.mark.asyncio
async def test_five_round_same_service_concurrency_cancel_restart_ws(tmp_path):
    """具名入口：同 data_dir 五轮完整相位。本提交是不完整生产者，必须红。"""
    artifact_dir = resolve_artifact_dir()
    _write_fault_marker(artifact_dir, "stub-producer-incomplete")
    _require_runtime()
    consume_repeat_matrix_trace(artifact_dir / TRACE_NAME)
