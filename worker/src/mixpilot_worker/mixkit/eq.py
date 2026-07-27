"""Биквад-эквалайзер (формулы RBJ Audio EQ Cookbook)."""

import numpy as np
from scipy.signal import sosfilt

from . import SR


def _biquad_sos(b0, b1, b2, a0, a1, a2) -> np.ndarray:
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


def low_shelf(freq: float, gain_db: float, q: float = 0.707, sr: int = SR) -> np.ndarray:
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * freq / sr
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / (2 * q)
    two_sqrt_a_alpha = 2 * np.sqrt(a) * alpha
    b0 = a * ((a + 1) - (a - 1) * cos_w0 + two_sqrt_a_alpha)
    b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
    b2 = a * ((a + 1) - (a - 1) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1) + (a - 1) * cos_w0 + two_sqrt_a_alpha
    a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
    a2 = (a + 1) + (a - 1) * cos_w0 - two_sqrt_a_alpha
    return _biquad_sos(b0, b1, b2, a0, a1, a2)


def high_shelf(freq: float, gain_db: float, q: float = 0.707, sr: int = SR) -> np.ndarray:
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * freq / sr
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / (2 * q)
    two_sqrt_a_alpha = 2 * np.sqrt(a) * alpha
    b0 = a * ((a + 1) + (a - 1) * cos_w0 + two_sqrt_a_alpha)
    b1 = -2 * a * ((a - 1) + (a + 1) * cos_w0)
    b2 = a * ((a + 1) + (a - 1) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1) - (a - 1) * cos_w0 + two_sqrt_a_alpha
    a1 = 2 * ((a - 1) - (a + 1) * cos_w0)
    a2 = (a + 1) - (a - 1) * cos_w0 - two_sqrt_a_alpha
    return _biquad_sos(b0, b1, b2, a0, a1, a2)


def peaking(freq: float, gain_db: float, q: float = 1.0, sr: int = SR) -> np.ndarray:
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * freq / sr
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / (2 * q)
    b0 = 1 + alpha * a
    b1 = -2 * cos_w0
    b2 = 1 - alpha * a
    a0 = 1 + alpha / a
    a1 = -2 * cos_w0
    a2 = 1 - alpha / a
    return _biquad_sos(b0, b1, b2, a0, a1, a2)


def high_pass(freq: float, q: float = 0.707, sr: int = SR) -> np.ndarray:
    w0 = 2 * np.pi * freq / sr
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / (2 * q)
    b0 = (1 + cos_w0) / 2
    b1 = -(1 + cos_w0)
    b2 = (1 + cos_w0) / 2
    a0 = 1 + alpha
    a1 = -2 * cos_w0
    a2 = 1 - alpha
    return _biquad_sos(b0, b1, b2, a0, a1, a2)


def apply(audio: np.ndarray, sos_list: list[np.ndarray]) -> np.ndarray:
    """Последовательно применяет биквады по каждому каналу (zero-phase не нужен — минимизируем задержку)."""
    if not sos_list:
        return audio
    sos = np.vstack(sos_list)
    x = np.ascontiguousarray(audio, dtype=np.float64)
    if x.ndim == 1:
        y = sosfilt(sos, x)
    else:
        y = np.empty_like(x)
        for ch in range(x.shape[1]):
            y[:, ch] = sosfilt(sos, x[:, ch])
    return y.astype(np.float32)
