"""Запуск ffmpeg/ffprobe отдельными процессами (без питон-биндингов)."""

import json
import subprocess

from .. import config
from ..errors import AppError

_CREATE_NO_WINDOW = 0x08000000  # не мигать консолью на Windows


def available() -> bool:
    ff, fp = config.resolve_ffmpeg()
    return bool(ff and fp)


def _run(cmd: list[str], what: str) -> bytes:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            creationflags=_CREATE_NO_WINDOW,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise AppError("E_INTERNAL", f"ffmpeg не найден: {exc}", status=500) from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError("E_DECODE", f"{what}: таймаут обработки", status=422) from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise AppError("E_DECODE", f"{what}: {' | '.join(tail)}", status=422)
    return proc.stdout


def probe(path: str) -> dict:
    """Метаданные файла: формат, длительность, потоки, теги."""
    _ff, fprobe = config.resolve_ffmpeg()
    if not fprobe:
        raise AppError("E_INTERNAL", "ffprobe недоступен", status=500)
    out = _run(
        [fprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        "чтение метаданных",
    )
    try:
        return json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise AppError("E_DECODE", f"ffprobe вернул некорректный JSON: {exc}", status=422) from exc


def decode_pcm_mono(path: str, sample_rate: int) -> bytes:
    """Декодирование в raw PCM s16le mono для расчёта пиков."""
    ffmpeg, _fp = config.resolve_ffmpeg()
    if not ffmpeg:
        raise AppError("E_INTERNAL", "ffmpeg недоступен", status=500)
    return _run(
        [
            ffmpeg, "-v", "error",
            "-i", path,
            "-map", "a:0",
            "-ac", "1",
            "-ar", str(sample_rate),
            "-f", "s16le",
            "-",
        ],
        "декодирование аудио",
    )
