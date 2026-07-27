"""Сатурация: мягкое насыщение (tanh) для «толщины» баса и клея микса."""

import numpy as np


def saturate(audio: np.ndarray, drive_db: float = 6.0, mix: float = 0.5) -> np.ndarray:
    """tanh-сатурация с компенсацией уровня. mix=0..1 — доля обработанного сигнала."""
    x = np.asarray(audio, dtype=np.float32)
    drive = 10 ** (drive_db / 20)
    if drive <= 1e-6:
        return x
    wet = np.tanh(x * drive) / np.tanh(drive) if drive > 0 else x
    mix = float(np.clip(mix, 0.0, 1.0))
    return ((1 - mix) * x + mix * wet).astype(np.float32)
