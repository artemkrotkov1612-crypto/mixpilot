"""Ревербератор Шрёдера (4 гребёнки + 2 allpass) — «воздух» для Slowed-вокала."""

import numpy as np

from . import SR
from ._kernels import allpass, comb

_COMB_MS = (29.7, 37.1, 41.1, 43.7)
_ALLPASS_MS = (5.0, 1.7)


def _mono_reverb(x: np.ndarray, sr: int, room: float, damp: float) -> np.ndarray:
    feedback = np.float32(0.7 + 0.28 * room)
    damp = np.float32(damp)
    acc = np.zeros_like(x)
    for ms in _COMB_MS:
        acc += comb(x, max(1, int(ms * 0.001 * sr)), feedback, damp)
    acc /= len(_COMB_MS)
    for ms in _ALLPASS_MS:
        acc = allpass(acc, max(1, int(ms * 0.001 * sr)), np.float32(0.5))
    return acc


def reverb(audio: np.ndarray, mix: float = 0.2, room: float = 0.6, damp: float = 0.4, sr: int = SR) -> np.ndarray:
    """Добавляет реверберацию. mix=0..1 — доля влажного сигнала."""
    x = np.ascontiguousarray(audio, dtype=np.float32)
    if mix <= 1e-4:
        return x
    if x.ndim == 1:
        wet = _mono_reverb(x, sr, room, damp)
    else:
        wet = np.stack(
            [_mono_reverb(np.ascontiguousarray(x[:, ch]), sr, room, damp) for ch in range(x.shape[1])],
            axis=1,
        )
    mix = float(np.clip(mix, 0.0, 1.0))
    return ((1 - mix) * x + mix * wet).astype(np.float32)
