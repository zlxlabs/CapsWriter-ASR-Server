# coding: utf-8
"""标点 / ITN 失败必须上抛，任务以 inference_failed 结束，不以成功结果交付。"""
from queue import Queue
from types import SimpleNamespace

import numpy as np

from config_server import ServerConfig
from core.server.engines.base import EngineCapabilities
from core.server.schema import Task
from core.server.state import WorkerState
from core.server.worker.task_handler import TaskHandler


def _audio(samples=1600):
    return np.zeros(samples, dtype=np.float32).tobytes()


def _task(task_id="punct-fail"):
    return Task(
        "file",
        _audio(),
        0.0,
        0.0,
        task_id,
        "socket",
        True,
        0.0,
        0.0,
        language="chinese",
        owner_kind="ws",
    )


class _Recognizer:
    def __init__(self, text, tokens, timestamps):
        self.text = text
        self.tokens = list(tokens)
        self.timestamps = list(timestamps)
        self.capabilities = [EngineCapabilities.ASR, EngineCapabilities.TIMESTAMPS]

    def create_stream(self):
        return _Stream(self)

    def decode_stream(self, stream, **kwargs):
        return None


class _Stream:
    def __init__(self, recognizer):
        self.result = SimpleNamespace(
            text=recognizer.text,
            tokens=list(recognizer.tokens),
            timestamps=list(recognizer.timestamps),
        )

    def accept_waveform(self, sample_rate, samples):
        self.sample_rate = sample_rate
        self.samples = samples


class _RaisingPunc:
    def punctuate(self, text):
        raise RuntimeError("synthetic punctuation failure")


def _run_handler(punc_model, monkeypatch):
    monkeypatch.setattr(ServerConfig, "format_num", False)
    monkeypatch.setattr(ServerConfig, "format_spell", False)
    monkeypatch.setattr(ServerConfig, "gpu_boost_enabled", False)
    handler = TaskHandler(Queue(), Queue(), ["socket"], WorkerState())
    handler.set_engine(
        _Recognizer("明天见", ["明", "天", "见"], [0.1, 0.2, 0.3]),
        punc_model=punc_model,
    )
    handler.handle_audio_task(_task())
    return handler.queue_out.get_nowait()


def test_punctuation_failure_fails_task_with_inference_failed(monkeypatch):
    result = _run_handler(_RaisingPunc(), monkeypatch)
    assert result.error_code == "inference_failed"
    assert result.is_final is False
    assert result.text == ""


def test_itn_failure_fails_task_with_inference_failed(monkeypatch):
    def boom(text):
        raise RuntimeError("synthetic ITN failure")

    monkeypatch.setattr(ServerConfig, "format_num", True)
    monkeypatch.setattr(ServerConfig, "format_spell", False)
    monkeypatch.setattr(ServerConfig, "gpu_boost_enabled", False)
    monkeypatch.setattr(
        "core.server.formatter.text_formatter.chinese_to_num", boom
    )
    handler = TaskHandler(Queue(), Queue(), ["socket"], WorkerState())
    handler.set_engine(
        _Recognizer("明天见", ["明", "天", "见"], [0.1, 0.2, 0.3]),
        punc_model=None,
    )
    handler.handle_audio_task(_task("itn-fail"))
    result = handler.queue_out.get_nowait()
    assert result.error_code == "inference_failed"
    assert result.is_final is False
    assert result.text == ""
