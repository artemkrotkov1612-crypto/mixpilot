"""Сведение стемов и утилиты уровней."""

import numpy as np


def db_to_lin(db: float) -> float:
    return float(10 ** (db / 20))


def apply_gain(audio: np.ndarray, db: float) -> np.ndarray:
    if abs(db) < 1e-6:
        return np.asarray(audio, dtype=np.float32)
    return (np.asarray(audio, dtype=np.float32) * db_to_lin(db)).astype(np.float32)


def mix(stems: list[np.ndarray]) -> np.ndarray:
    """Суммирует стемы одинаковой формы (n, каналы)."""
    if not stems:
        raise ValueError("нет стемов для сведения")
    length = max(s.shape[0] for s in stems)
    channels = max(s.shape[1] if s.ndim > 1 else 1 for s in stems)
    acc = np.zeros((length, channels), dtype=np.float32)
    for s in stems:
        s2 = s if s.ndim > 1 else s[:, None]
        if s2.shape[1] == 1 and channels == 2:
            s2 = np.repeat(s2, 2, axis=1)
        acc[: s2.shape[0], : s2.shape[1]] += s2
    return acc


def to_stereo(audio: np.ndarray) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float32)
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    return x
