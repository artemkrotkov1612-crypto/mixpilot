"""Громкость: измерение LUFS (pyloudnorm) и нормализация к цели."""

import numpy as np
import pyloudnorm as pyln

from . import SR

# Целевые уровни по стилям (ТЗ §10): клуб громче, стрим тише.
TARGET_LUFS = {"stream": -11.0, "club": -8.5}


def measure_lufs(audio: np.ndarray, sr: int = SR) -> float:
    meter = pyln.Meter(sr)
    data = audio if audio.ndim > 1 else audio[:, None]
    try:
        return float(meter.integrated_loudness(data.astype(np.float64)))
    except Exception:
        return -70.0


def normalize_lufs(audio: np.ndarray, target_lufs: float = -11.0, max_gain_db: float = 24.0, sr: int = SR) -> np.ndarray:
    """Приводит интегральную громкость к target. Гейн ограничен, чтобы не раскачивать тишину/шум."""
    x = np.asarray(audio, dtype=np.float32)
    current = measure_lufs(x, sr)
    if current <= -70.0:  # практически тишина — не трогаем
        return x
    gain_db = float(np.clip(target_lufs - current, -max_gain_db, max_gain_db))
    return (x * (10 ** (gain_db / 20))).astype(np.float32)


def peak_db(audio: np.ndarray) -> float:
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    return 20 * np.log10(peak + 1e-12)
