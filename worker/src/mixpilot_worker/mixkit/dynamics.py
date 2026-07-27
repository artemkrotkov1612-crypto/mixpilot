"""Динамическая обработка: компрессор и брикуолл-лимитер (true-peak-осведомлённый)."""

import numpy as np

from . import SR
from ._kernels import comp_gain, limiter_gain


def _db_to_lin(db: float) -> float:
    return float(10 ** (db / 20))


def _mono_env(audio: np.ndarray) -> np.ndarray:
    return np.abs(audio).max(axis=1) if audio.ndim > 1 else np.abs(audio)


def compressor(
    audio: np.ndarray,
    threshold_db: float = -18.0,
    ratio: float = 3.0,
    attack_ms: float = 10.0,
    release_ms: float = 120.0,
    makeup_db: float | None = None,
    sr: int = SR,
) -> np.ndarray:
    """Пиковый компрессор с огибающей по громкому каналу. Общий гейн на оба канала."""
    x = np.asarray(audio, dtype=np.float32)
    env = _mono_env(x)
    env_db = (20 * np.log10(env + 1e-9)).astype(np.float32)

    att = float(np.exp(-1.0 / (attack_ms * 0.001 * sr)))
    rel = float(np.exp(-1.0 / (release_ms * 0.001 * sr)))
    smoothed = comp_gain(env_db, float(threshold_db), float(ratio), att, rel)

    gain = np.power(10.0, smoothed / 20.0).astype(np.float32)
    if makeup_db is None:
        # Авто-makeup: примерно компенсируем срез на пороге.
        makeup_db = -threshold_db * (1.0 / ratio - 1.0) * 0.5
    gain *= _db_to_lin(makeup_db)

    return (x * gain[:, None] if x.ndim > 1 else x * gain).astype(np.float32)


def limiter(
    audio: np.ndarray,
    ceiling_db: float = -1.0,
    lookahead_ms: float = 2.0,
    release_ms: float = 60.0,
    sr: int = SR,
) -> np.ndarray:
    """Lookahead brickwall-лимитер: гейн ведём по будущему пику, релиз сглаживаем."""
    x = np.asarray(audio, dtype=np.float32)
    ceiling = _db_to_lin(ceiling_db)
    env = _mono_env(x)

    la = max(1, int(lookahead_ms * 0.001 * sr))
    # «Будущий» пик = скользящий максимум вперёд на окно lookahead (векторно).
    padded = np.concatenate([env, np.zeros(la, dtype=env.dtype)])
    fut = np.copy(env)
    for shift in range(1, la + 1):
        fut = np.maximum(fut, padded[shift:shift + len(env)])

    rel = float(np.exp(-1.0 / (release_ms * 0.001 * sr)))
    gain = limiter_gain(fut.astype(np.float32), float(ceiling), rel)

    y = x * gain[:, None] if x.ndim > 1 else x * gain
    return np.clip(y, -ceiling, ceiling).astype(np.float32)
