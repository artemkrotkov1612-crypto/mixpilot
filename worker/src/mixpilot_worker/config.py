"""Пути данных и внешние бинарники.

Все функции читают окружение в момент вызова (не при импорте) — тесты
подменяют MIXPILOT_DATA_DIR через monkeypatch до старта приложения.
"""

import os
import shutil
from pathlib import Path

APP_NAME = "MixPilot"

# Подкаталоги хранилища (ТЗ §6).
_SUBDIRS = (
    "db",
    "media/originals",
    "cache/peaks",
    "cache/decode",
    "cache/analysis",
    "cache/stems",
    "renders",
    "voice/datasets",
    "voice/models",
    "models",
    "logs",
    "tmp",
)

ALLOWED_IMPORT_EXTS = {
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif",
}


def data_dir() -> Path:
    env = os.environ.get("MIXPILOT_DATA_DIR")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / APP_NAME


def ensure_dirs() -> None:
    for sub in _SUBDIRS:
        (data_dir() / sub).mkdir(parents=True, exist_ok=True)


def db_path() -> Path:
    return data_dir() / "db" / "mixpilot.sqlite3"


def originals_dir() -> Path:
    return data_dir() / "media" / "originals"


def peaks_dir() -> Path:
    return data_dir() / "cache" / "peaks"


def logs_dir() -> Path:
    return data_dir() / "logs"


def tmp_dir() -> Path:
    return data_dir() / "tmp"


def _ffmpeg_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("MIXPILOT_FFMPEG_DIR")
    if env:
        roots.append(Path(env))
    roots.append(Path("C:/TheIceBoys/TOOLS/ffmpeg/bin"))  # dev-воркспейс
    return roots


def resolve_ffmpeg() -> tuple[str | None, str | None]:
    """(ffmpeg, ffprobe) — абсолютные пути или имена из PATH; None, если не найдены."""
    for root in _ffmpeg_roots():
        ff, fp = root / "ffmpeg.exe", root / "ffprobe.exe"
        if ff.exists() and fp.exists():
            return str(ff), str(fp)
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ff and fp:
        return ff, fp
    return None, None
