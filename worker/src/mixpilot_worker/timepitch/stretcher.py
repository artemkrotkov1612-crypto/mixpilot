"""Темп и тональность через ffmpeg-фильтр rubberband (высокое качество, отд. процесс).

Rubber Band — GPL; вызывается как фильтр ffmpeg отдельным процессом, код worker'а
не заражается (для SaaS — коммерческая лицензия или Signalsmith, см. MODELS.md).
Guard ±25% темпа: экстремальные значения портят звук (ТЗ §20, риски).
"""

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import config
from ..errors import AppError

_CREATE_NO_WINDOW = 0x08000000

TEMPO_MIN, TEMPO_MAX = 0.5, 2.0
SEMITONES_MIN, SEMITONES_MAX = -6.0, 6.0


def clamp_tempo(factor: float) -> float:
    return float(np.clip(factor, TEMPO_MIN, TEMPO_MAX))


def clamp_semitones(semitones: float) -> float:
    return float(np.clip(semitones, SEMITONES_MIN, SEMITONES_MAX))


def stretch(audio: np.ndarray, sr: int, tempo_factor: float = 1.0, semitones: float = 0.0) -> np.ndarray:
    """Меняет темп (tempo_factor<1 — медленнее) и высоту (полутоны). Форма (n, каналы)."""
    tempo_factor = clamp_tempo(tempo_factor)
    semitones = clamp_semitones(semitones)
    if abs(tempo_factor - 1.0) < 1e-3 and abs(semitones) < 1e-3:
        return np.asarray(audio, dtype=np.float32)

    ffmpeg, _fp = config.resolve_ffmpeg()
    if not ffmpeg:
        raise AppError("E_INTERNAL", "ffmpeg недоступен для rubberband", status=500)

    pitch_scale = float(2 ** (semitones / 12.0))
    with tempfile.TemporaryDirectory(dir=config.tmp_dir()) as td:
        src = Path(td) / "in.wav"
        dst = Path(td) / "out.wav"
        sf.write(str(src), np.asarray(audio, dtype=np.float32), sr, subtype="FLOAT")
        # tempo в ffmpeg rubberband — множитель длительности НАоборот: tempo=0.85 -> медленнее.
        # pitchq НЕ задаём: это int-опция (дефолт «quality»), строка ломает сдвиг высоты.
        flt = f"rubberband=tempo={tempo_factor:.5f}:pitch={pitch_scale:.5f}"
        proc = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(src), "-af", flt, "-c:a", "pcm_f32le", str(dst)],
            capture_output=True, creationflags=_CREATE_NO_WINDOW, timeout=600,
        )
        if proc.returncode != 0:
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-2:]
            raise AppError("E_INTERNAL", f"rubberband: {' | '.join(tail)}", status=500)
        out, _sr = sf.read(str(dst), dtype="float32", always_2d=True)
    return out
