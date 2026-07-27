"""Пересборка блоков: длина кроссфейда, равномощность, сборка по order."""

import numpy as np

from mixpilot_worker.mixkit import SR
from mixpilot_worker.restructure import blocks


def _tone(freq, seconds, amp=0.5):
    t = np.arange(int(SR * seconds)) / SR
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def test_crossfade_length_and_no_click():
    a = _tone(220, 0.5)
    b = _tone(440, 0.5)
    xfade_ms = 40
    out = blocks.concat_crossfade([a, b], xfade_ms=xfade_ms)
    xf = int(xfade_ms * 0.001 * SR)
    # длина = сумма минус перекрытие
    assert abs(out.shape[0] - (a.shape[0] + b.shape[0] - xf)) <= 1
    # нет резкого скачка на стыке (макс разность соседних сэмплов ограничена)
    diff = np.abs(np.diff(out[:, 0]))
    assert diff.max() < 0.2


def test_equal_power_preserves_energy_on_uncorrelated():
    # Равномощный кроссфейд сохраняет RMS для НЕкоррелированных сигналов (случай музыки).
    rng = np.random.default_rng(1)
    a = (rng.standard_normal((int(SR * 0.4), 2)) * 0.2).astype(np.float32)
    b = (rng.standard_normal((int(SR * 0.4), 2)) * 0.2).astype(np.float32)
    out = blocks.concat_crossfade([a, b], xfade_ms=50)
    xf = int(50 * 0.001 * SR)
    seam = out[a.shape[0] - xf : a.shape[0]]
    # RMS в зоне шва близок к RMS исходных кусков (±15%) — без провала и всплеска.
    assert 0.85 < np.sqrt((seam**2).mean()) / 0.2 < 1.15


def test_coherent_crossfade_bounded():
    # Идентичные сигналы дают когерентный +3 дБ в центре шва — но не «взрыв».
    a = _tone(300, 0.4)
    out = blocks.concat_crossfade([a, a], xfade_ms=50)
    assert np.abs(out).max() < 0.8  # исходная амплитуда 0.5, всплеск ограничен


def test_build_arrangement_by_order():
    audio = np.concatenate([_tone(200, 1.0), _tone(400, 1.0), _tone(800, 1.0)], axis=0)
    sections = [
        {"id": "intro1", "label": "intro", "start_s": 0.0, "end_s": 1.0},
        {"id": "chorus1", "label": "chorus", "start_s": 1.0, "end_s": 2.0},
        {"id": "outro1", "label": "outro", "start_s": 2.0, "end_s": 3.0},
    ]
    # повтор припева + пропуск неизвестного id
    out = blocks.build_arrangement(audio, sections, ["chorus1", "chorus1", "intro1", "zzz"])
    assert out.shape[0] > 0
    assert out.shape[1] == 2


def test_empty_pieces():
    assert blocks.concat_crossfade([]).shape[0] == 0
    audio = _tone(200, 1.0)
    sections = [{"id": "a", "label": "intro", "start_s": 0.0, "end_s": 1.0}]
    assert blocks.build_arrangement(audio, sections, ["nonexistent"]).shape[0] == 0
