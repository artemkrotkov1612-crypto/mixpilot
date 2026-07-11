"""Пики волны для UI: N корзин, максимум |амплитуды| в каждой, 0..1."""

import json
from pathlib import Path

import numpy as np

from .. import config
from . import ffmpeg

BUCKETS = 1000
DECODE_RATE = 8000  # для огибающей хватает низкой частоты — быстрее декод


def peaks_path(content_hash16: str) -> Path:
    return config.peaks_dir() / f"{content_hash16}.json"


def generate(media_path: str, content_hash16: str, duration_s: float) -> dict:
    raw = ffmpeg.decode_pcm_mono(media_path, DECODE_RATE)
    samples = np.frombuffer(raw, dtype=np.int16)
    if samples.size == 0:
        peaks = [0.0] * BUCKETS
    else:
        # Дополняем до кратности BUCKETS и берём max(|x|) по корзинам.
        # Значения честные (без нормализации) — плеер нормализует отображение сам.
        pad = (-samples.size) % BUCKETS
        padded = np.pad(np.abs(samples.astype(np.int32)), (0, pad))
        peaks_arr = padded.reshape(BUCKETS, -1).max(axis=1) / 32768.0
        peaks = [round(float(v), 3) for v in np.clip(peaks_arr, 0.0, 1.0)]

    doc = {"version": 1, "buckets": BUCKETS, "duration_s": round(duration_s, 3), "peaks": peaks}
    path = peaks_path(content_hash16)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return doc


def load(content_hash16: str) -> dict | None:
    path = peaks_path(content_hash16)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
