"""Анализ на синтетике: клик-трек, аккорд, чередование секций (без ffmpeg/GPU)."""

import numpy as np
import pytest

librosa = pytest.importorskip("librosa", reason="librosa ещё не установлена")

from mixpilot_worker.analysis import key as key_mod
from mixpilot_worker.analysis import structure as structure_mod
from mixpilot_worker.analysis import tempo as tempo_mod

SR = 22050


def _click_track(bpm: float, seconds: float) -> np.ndarray:
    y = np.zeros(int(SR * seconds), dtype=np.float32)
    step = int(SR * 60 / bpm)
    click = (np.random.default_rng(7).standard_normal(256) * np.linspace(1, 0, 256)).astype(np.float32)
    for start in range(0, len(y) - 300, step):
        y[start:start + 256] += click
    return y * 0.8


def _tone(freqs: list[float], seconds: float, amp: float = 0.2) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    y = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    return (amp * y / len(freqs)).astype(np.float32)


def test_tempo_click_track():
    y = _click_track(120, 20)
    res = tempo_mod.analyze(y, SR)
    assert 115 <= res["bpm"] <= 125, res["bpm"]
    assert abs(len(res["beats"]) - 40) <= 4
    assert len(res["downbeats"]) >= len(res["beats"]) // 4 - 1
    # downbeats — подмножество битов с шагом 4
    assert res["downbeats"][0] in res["beats"]


def test_fold_bpm():
    assert tempo_mod.fold_bpm(60) == 120
    assert tempo_mod.fold_bpm(200) == 100
    assert tempo_mod.fold_bpm(128) == 128


def test_key_major_chord():
    # До-мажорное трезвучие с октавой: C-E-G-C
    y = _tone([261.63, 329.63, 392.0, 523.25], 8)
    res = key_mod.analyze(y, SR)
    # Относительная пара C major / A minor — допустимая неоднозначность метода
    assert (res["key_root"], res["key_mode"]) in {("C", "major"), ("A", "minor")}, res
    assert 0 <= res["key_conf"] <= 1


def test_structure_alternating_sections():
    quiet = _tone([220.0], 20, amp=0.08)
    loud = _tone([220.0, 277.18, 329.63, 440.0], 20, amp=0.5)
    noise = (np.random.default_rng(3).standard_normal(len(loud)) * 0.08).astype(np.float32)
    y = np.concatenate([quiet, loud + noise, quiet, loud + noise])

    duration = len(y) / SR
    beats = [round(t, 4) for t in np.arange(0, duration, 0.5)]
    downbeats = beats[::4]
    sections = structure_mod.analyze(y, SR, downbeats, beats)

    assert len(sections) >= 2
    assert sections[0]["start_s"] == 0.0
    assert abs(sections[-1]["end_s"] - duration) < 0.05
    for prev, cur in zip(sections, sections[1:]):
        assert abs(prev["end_s"] - cur["start_s"]) < 1e-6  # непрерывное покрытие
        assert cur["start_s"] in downbeats  # границы по downbeat'ам
    assert all(s["label"] in structure_mod.LABELS for s in sections)
    assert all(0 <= s["energy"] <= 1 for s in sections)
    # есть и тихие, и громкие блоки
    energies = [s["energy"] for s in sections]
    assert max(energies) - min(energies) > 0.2
