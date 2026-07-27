"""Темп/тональность через ffmpeg rubberband на синтетике (длительность и питч)."""

import numpy as np
import pytest

from mixpilot_worker import config
from mixpilot_worker.mixkit import SR
from mixpilot_worker.timepitch import stretcher


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MIXPILOT_DATA_DIR", str(tmp_path / "data"))
    config.ensure_dirs()
    if not config.resolve_ffmpeg()[0]:
        pytest.skip("ffmpeg недоступен")


def _sine(freq, seconds=2.0):
    t = np.arange(int(SR * seconds)) / SR
    mono = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def _dominant_freq(audio):
    mono = audio[:, 0]
    spec = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1 / SR)
    return float(freqs[np.argmax(spec)])


def test_clamps():
    assert stretcher.clamp_tempo(0.1) == 0.5
    assert stretcher.clamp_tempo(9) == 2.0
    assert stretcher.clamp_semitones(-20) == -6.0


def test_slower_tempo_lengthens_without_pitch_change():
    x = _sine(440, seconds=2.0)
    y = stretcher.stretch(x, SR, tempo_factor=0.8)
    # 0.8x темпа -> длиннее примерно на 1/0.8.
    assert 1.15 < len(y) / len(x) < 1.32
    assert abs(_dominant_freq(y) - 440) < 15  # высота не изменилась


def test_pitch_shift_up_preserves_length():
    x = _sine(300, seconds=2.0)
    y = stretcher.stretch(x, SR, semitones=6)  # +6 = максимум guard'а
    assert abs(len(y) - len(x)) < SR * 0.1
    expected = 300 * 2 ** (6 / 12)  # ~424 Гц
    assert abs(_dominant_freq(y) - expected) < 25


def test_pitch_is_clamped_to_guard():
    # Запрос +12 обрезается guard'ом до +6 — высота не выше +6 полутонов.
    x = _sine(300, seconds=2.0)
    y = stretcher.stretch(x, SR, semitones=12)
    assert abs(_dominant_freq(y) - 300 * 2 ** (6 / 12)) < 25


def test_noop_returns_input():
    x = _sine(200, seconds=1.0)
    y = stretcher.stretch(x, SR, tempo_factor=1.0, semitones=0.0)
    assert np.array_equal(x, y)
