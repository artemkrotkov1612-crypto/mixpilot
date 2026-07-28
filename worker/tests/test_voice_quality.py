"""Оценка качества записи: вердикт должен быть понятным и правильным."""

import numpy as np
import pytest

from mixpilot_worker.voice import quality

SR = 44100


def speech(seconds=3.0, level=0.15, noise=0.0005, sr=SR):
    """Псевдоречь: тон с огибающей вроде слогов + слабый фон."""
    t = np.arange(int(sr * seconds)) / sr
    envelope = (np.sin(2 * np.pi * 3 * t) > -0.2).astype(np.float32)  # «слоги»
    tone = np.sin(2 * np.pi * 180 * t) * 0.6 + np.sin(2 * np.pi * 360 * t) * 0.4
    rng = np.random.default_rng(7)
    return ((tone * envelope * level) + rng.standard_normal(t.size) * noise).astype(np.float32)


def test_good_recording_is_great():
    verdict = quality.analyze(speech(), SR)
    assert verdict["level"] == "great", verdict
    assert verdict["accepted"] is True
    assert verdict["metrics"]["snr_db"] > 20


def test_clipped_recording_is_rejected():
    loud = np.clip(speech(level=3.0), -1.0, 1.0)
    verdict = quality.analyze(loud, SR)
    assert verdict["level"] == "retake"
    assert "громко" in verdict["reason_ru"].lower()


def test_too_quiet_is_rejected():
    verdict = quality.analyze(speech(level=0.008), SR)
    assert verdict["level"] == "retake"
    assert "тихо" in verdict["reason_ru"].lower()


def test_noisy_room_is_rejected():
    verdict = quality.analyze(speech(level=0.12, noise=0.06), SR)
    assert verdict["level"] == "retake"
    assert "шум" in verdict["reason_ru"].lower()


def sustained_note(seconds=6.0, level=0.15, sr=SR):
    """Длинная нота без пауз — шаги «протяжные гласные» и «длинные ноты»."""
    t = np.arange(int(sr * seconds)) / sr
    f0 = 220 * (1 + 0.01 * np.sin(2 * np.pi * 5 * t))  # лёгкое вибрато
    phase = 2 * np.pi * np.cumsum(f0) / sr
    tone = sum(np.sin(phase * k) / k for k in (1, 2, 3))
    return (tone * level).astype(np.float32)


def test_sustained_note_is_accepted():
    """Тянущаяся нота не должна отвергаться как «шумная»: пауз в ней нет,
    поэтому фон по ним измерить нельзя (поймано живым прогоном M6)."""
    verdict = quality.analyze(sustained_note(), SR)
    assert verdict["accepted"] is True, verdict
    assert verdict["metrics"]["has_pauses"] is False


def test_speech_has_pauses_detected():
    verdict = quality.analyze(speech(), SR)
    assert verdict["metrics"]["has_pauses"] is True


def test_noisy_sustained_note_still_checks_level():
    """Даже без пауз слишком тихая запись отклоняется."""
    verdict = quality.analyze(sustained_note(level=0.008), SR)
    assert verdict["level"] == "retake"


def test_silence_is_rejected():
    verdict = quality.analyze(np.zeros(SR * 2, dtype=np.float32), SR)
    assert verdict["level"] == "retake"
    assert verdict["accepted"] is False


def test_slight_noise_is_acceptable():
    verdict = quality.analyze(speech(level=0.12, noise=0.004), SR)
    assert verdict["level"] in ("ok", "great")
    assert verdict["accepted"] is True


def test_verdict_has_human_fields():
    verdict = quality.analyze(speech(), SR)
    assert verdict["label_ru"] in ("Отлично", "Нормально", "Перезапишите")
    assert verdict["reason_ru"]
    assert verdict["duration_s"] > 0


# --- шумомер комнаты ---

def test_quiet_room():
    rng = np.random.default_rng(1)
    res = quality.measure_noise_floor((rng.standard_normal(SR * 2) * 0.0006).astype(np.float32), SR)
    assert res["level"] == "great" and res["accepted"] is True


def test_noisy_room():
    rng = np.random.default_rng(2)
    res = quality.measure_noise_floor((rng.standard_normal(SR * 2) * 0.08).astype(np.float32), SR)
    assert res["level"] == "retake" and res["accepted"] is False
    assert "окно" in res["reason_ru"]


# --- подготовка датасета ---

def test_trim_silence_removes_edges():
    body = speech(seconds=2.0)
    padded = np.concatenate([np.zeros(SR, dtype=np.float32), body, np.zeros(SR, dtype=np.float32)])
    trimmed = quality.trim_silence(padded, SR)
    assert trimmed.size < padded.size
    assert trimmed.size >= body.size * 0.8  # саму речь не срезали


def test_trim_keeps_all_silence_input():
    silent = np.zeros(SR, dtype=np.float32)
    assert quality.trim_silence(silent, SR).size == silent.size


def test_normalize_peak():
    quiet = speech(level=0.02)
    normalized = quality.normalize_peak(quiet, target_db=-3.0)
    peak_db = 20 * np.log10(float(np.abs(normalized).max()))
    assert peak_db == pytest.approx(-3.0, abs=0.2)


def test_normalize_silence_is_safe():
    silent = np.zeros(1000, dtype=np.float32)
    assert not np.any(np.isnan(quality.normalize_peak(silent)))
