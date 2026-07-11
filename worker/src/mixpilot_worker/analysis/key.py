"""Тональность: средняя хрома + профили Крумхансл-Шмуклера."""

import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denom) if denom > 0 else 0.0


def analyze(y: np.ndarray, sr: int) -> dict:
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    scores: list[tuple[float, str, str]] = []
    for root in range(12):
        rolled = np.roll(chroma, -root)
        scores.append((_corr(rolled, _MAJOR), NOTE_NAMES[root], "major"))
        scores.append((_corr(rolled, _MINOR), NOTE_NAMES[root], "minor"))
    scores.sort(reverse=True)
    (best, root, mode), (second, *_rest) = scores[0], scores[1]
    conf = max(0.0, min(1.0, (best - second) * 4)) if best > 0 else 0.0
    return {"key_root": root, "key_mode": mode, "key_conf": round(conf, 2)}
