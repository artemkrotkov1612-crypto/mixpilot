"""DSP-математика mixkit на синтетике: спектр EQ, потолок лимитера, LUFS, реверб."""

import numpy as np
import pytest

from mixpilot_worker.mixkit import SR, dynamics, eq, loudness, reverb, saturate


def sine(freq: float, seconds: float = 1.0, amp: float = 0.3, stereo: bool = True) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono, mono], axis=1) if stereo else mono


def band_energy(audio: np.ndarray, freq: float) -> float:
    mono = audio[:, 0] if audio.ndim > 1 else audio
    spec = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1 / SR)
    idx = np.argmin(np.abs(freqs - freq))
    return float(spec[idx - 2 : idx + 3].sum())


def test_low_shelf_boosts_bass():
    x = sine(60) + sine(6000)
    y = eq.apply(x, [eq.low_shelf(120, gain_db=9)])
    # Бас усилен заметно, верх почти не тронут.
    assert band_energy(y, 60) > band_energy(x, 60) * 1.8
    assert 0.9 < band_energy(y, 6000) / band_energy(x, 6000) < 1.1


def test_high_pass_cuts_sub():
    x = sine(40) + sine(2000)
    y = eq.apply(x, [eq.high_pass(200)])
    assert band_energy(y, 40) < band_energy(x, 40) * 0.3
    assert band_energy(y, 2000) > band_energy(x, 2000) * 0.8


def test_limiter_respects_ceiling():
    loud = sine(220, amp=0.9) + sine(440, amp=0.7)  # заведомо >0 dBFS местами
    assert np.abs(loud).max() > 1.0
    y = dynamics.limiter(loud, ceiling_db=-1.0)
    ceiling = 10 ** (-1.0 / 20)
    assert np.abs(y).max() <= ceiling + 1e-4
    assert y.shape == loud.shape


def test_compressor_reduces_dynamic_range():
    quiet = sine(220, seconds=0.5, amp=0.05)
    loud = sine(220, seconds=0.5, amp=0.8)
    x = np.concatenate([quiet, loud])
    y = dynamics.compressor(x, threshold_db=-24, ratio=4, makeup_db=0)
    # Отношение громкой части к тихой уменьшается.
    r_in = np.abs(loud).max() / np.abs(quiet).max()
    r_out = np.abs(y[len(quiet):]).max() / np.abs(y[: len(quiet)]).max()
    assert r_out < r_in


def test_saturation_adds_harmonics_bounded():
    x = sine(100, amp=0.5)
    y = saturate.saturate(x, drive_db=12, mix=1.0)
    # Появляется 3-я гармоника, амплитуда остаётся ограниченной.
    assert band_energy(y, 300) > band_energy(x, 300) * 3
    assert np.abs(y).max() <= 1.01


def test_loudness_normalizes_to_target():
    x = sine(300, seconds=3, amp=0.1)
    y = loudness.normalize_lufs(x, target_lufs=-14.0)
    assert abs(loudness.measure_lufs(y) - (-14.0)) < 1.0


def test_reverb_adds_tail():
    # Импульс: после него сухой сигнал — тишина, влажный — хвост.
    x = np.zeros((SR, 2), dtype=np.float32)
    x[100] = 1.0
    y = reverb.reverb(x, mix=1.0)
    tail_energy = float(np.abs(y[SR // 2 :]).sum())
    assert tail_energy > 0.01
    assert y.shape == x.shape


def test_no_input_mutation():
    x = sine(440)
    x_copy = x.copy()
    dynamics.limiter(x)
    eq.apply(x, [eq.peaking(1000, 6)])
    saturate.saturate(x)
    assert np.array_equal(x, x_copy)
