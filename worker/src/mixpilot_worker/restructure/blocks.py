"""Пересборка трека из смысловых блоков с равномощными кроссфейдами.

Швы кладём на границы секций (они уже привязаны к downbeat'ам в analysis),
кроссфейд гасит щелчки. Это не нейрогенерация — перестановка/повтор/укорочение
существующих кусков (ремикс v1, см. MODELS.md).
"""

import numpy as np

from ..mixkit import SR

DEFAULT_XFADE_MS = 40.0


def _equal_power_fade(n: int) -> tuple[np.ndarray, np.ndarray]:
    t = np.linspace(0, np.pi / 2, n, dtype=np.float32)
    return np.cos(t), np.sin(t)  # fade-out, fade-in; сумма энергии постоянна


def slice_segment(audio: np.ndarray, start_s: float, end_s: float, sr: int = SR) -> np.ndarray:
    a = max(0, int(start_s * sr))
    b = min(audio.shape[0], int(end_s * sr))
    if b <= a:
        return np.zeros((0, audio.shape[1] if audio.ndim > 1 else 1), dtype=np.float32)
    return np.asarray(audio[a:b], dtype=np.float32)


def concat_crossfade(pieces: list[np.ndarray], xfade_ms: float = DEFAULT_XFADE_MS, sr: int = SR) -> np.ndarray:
    """Склеивает куски (n, каналы) с равномощным кроссфейдом на стыках."""
    pieces = [p for p in pieces if p.shape[0] > 0]
    if not pieces:
        return np.zeros((0, 2), dtype=np.float32)
    channels = pieces[0].shape[1] if pieces[0].ndim > 1 else 1
    xf = int(xfade_ms * 0.001 * sr)

    out = pieces[0].astype(np.float32)
    for nxt in pieces[1:]:
        nxt = nxt.astype(np.float32)
        n = min(xf, out.shape[0], nxt.shape[0])
        if n <= 0:
            out = np.concatenate([out, nxt], axis=0)
            continue
        fade_out, fade_in = _equal_power_fade(n)
        tail = out[-n:] * fade_out[:, None]
        head = nxt[:n] * fade_in[:, None]
        out = np.concatenate([out[:-n], tail + head, nxt[n:]], axis=0)
    return out.astype(np.float32)


def sections_by_label(sections: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for s in sections:
        grouped.setdefault(s["label"], []).append(s)
    return grouped


def build_arrangement(audio: np.ndarray, sections: list[dict], order: list[str],
                      xfade_ms: float = DEFAULT_XFADE_MS, sr: int = SR) -> np.ndarray:
    """Собирает трек по списку id секций (order). Неизвестные id пропускаются."""
    by_id = {s["id"]: s for s in sections}
    pieces = [slice_segment(audio, by_id[sid]["start_s"], by_id[sid]["end_s"], sr)
              for sid in order if sid in by_id]
    return concat_crossfade(pieces, xfade_ms, sr)
