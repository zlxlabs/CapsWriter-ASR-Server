# coding: utf-8
"""合成 PCM 经过分段与假识别合并后，时间戳和结果时长不得越过输入边界。"""
from types import SimpleNamespace

import numpy as np
import pytest

from core.server.engines.base import EngineCapabilities
from core.server.schema import Task
from core.server.segmenter import PcmSegmenter
from core.server.state import WorkerState
from core.server.worker.pipeline import TaskPipeline


SAMPLE_RATE, INPUT_SECONDS = 16_000, 600
NOMINAL_CUT, SNAPPED_CUT, OVERLAP = 30.0, 30.12, 1.0


class _SilenceFinder:
    """确认合成 PCM 的静音切点存在，再返回帧对齐切点。"""

    def __init__(self):
        self.calls = 0

    def find(self, chunks, lo, hi, nominal):
        samples = np.frombuffer(chunks, dtype="<f4")
        cut_sample = round(SNAPPED_CUT * SAMPLE_RATE)
        assert lo <= SNAPPED_CUT <= hi
        assert np.all(samples[cut_sample - 16 : cut_sample + 16] == 0)
        self.calls += 1
        return SNAPPED_CUT, True


class _FakeStream:
    def __init__(self):
        self.result = SimpleNamespace(text="", tokens=[], timestamps=[])

    def accept_waveform(self, sample_rate, samples):
        self.sample_rate, self.samples = sample_rate, samples


class _FakeRecognizer:
    capabilities = [EngineCapabilities.ASR, EngineCapabilities.TIMESTAMPS]

    def __init__(self):
        self.calls = 0

    def create_stream(self):
        return _FakeStream()

    def decode_stream(self, stream, **kwargs):
        duration = len(stream.samples) / stream.sample_rate
        tokens = [chr(0x4E00 + self.calls * 3 + i) for i in range(3)]
        stream.result = SimpleNamespace(
            text="".join(tokens), tokens=tokens,
            timestamps=[0.1, duration / 2, duration - 0.05],
        )
        self.calls += 1


@pytest.mark.asyncio
async def test_global_timestamps_and_result_duration_stay_within_pcm_duration():
    pcm = np.full(INPUT_SECONDS * SAMPLE_RATE, 0.25, dtype="<f4")
    cut_samples, silence_half_width = round(SNAPPED_CUT * SAMPLE_RATE), round(0.1 * SAMPLE_RATE)
    for boundary in range(cut_samples, len(pcm), cut_samples):
        pcm[boundary - silence_half_width : boundary + silence_half_width] = 0
    pcm_bytes, input_duration = pcm.tobytes(), len(pcm) / SAMPLE_RATE

    finder = _SilenceFinder()
    segmenter = PcmSegmenter()
    segmenter.configure(
        cut_finder=finder, engine_segment_limit=80.0, cut_snap=True,
        search_before=5.0, search_after=1.0, max_cut=31.0,
    )
    segmenter.append(pcm_bytes)
    segments = await segmenter.drain_ready(
        source="file", nominal=NOMINAL_CUT, overlap=OVERLAP, is_final=True,
    )
    segments.append(segmenter.final_segment(OVERLAP))

    recognizer = _FakeRecognizer()
    pipeline = TaskPipeline(recognizer, state=WorkerState())
    pipeline.formatter = SimpleNamespace(format=lambda text: text)
    for segment in segments:
        task = Task(
            "file", segment.data, segment.offset, segment.overlap,
            "timestamp-bounds", "socket", segment.is_final, 0.0, 0.0,
            language="chinese",
        )
        result = pipeline.process(task)

    timestamps = result.timestamps
    assert (
        recognizer.calls > 1 and finder.calls > 1 and timestamps
        and all(timestamp <= input_duration for timestamp in timestamps)
        and all(a <= b for a, b in zip(timestamps, timestamps[1:]))
    )
    assert abs(result.duration - input_duration) <= 1 / SAMPLE_RATE
