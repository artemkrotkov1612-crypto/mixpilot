"""Импорт аудиофайла: hash → копия в хранилище → метаданные → пики.

Исходный файл пользователя только читается — никогда не изменяется
и не удаляется (требование §20 спецификации).
"""

import hashlib
import shutil
from pathlib import Path

from .. import config, db
from ..errors import AppError
from . import ffmpeg, waveform

HASH_PREFIX_LEN = 16
MAX_IMPORT_BYTES = 2 * 1024**3  # здравый предел: 2 ГБ


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_meta(path: Path) -> dict:
    info = ffmpeg.probe(str(path))
    streams = info.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise AppError("E_DECODE", "в файле нет аудиодорожки", status=422)
    fmt = info.get("format", {})
    duration = float(fmt.get("duration") or audio.get("duration") or 0)
    if duration <= 0:
        raise AppError("E_DECODE", "не удалось определить длительность", status=422)
    tags = {str(k).lower(): v for k, v in (fmt.get("tags") or {}).items()}
    return {
        "duration_s": round(duration, 3),
        "sample_rate": int(audio.get("sample_rate") or 0) or None,
        "format": fmt.get("format_name", "").split(",")[0] or None,
        "title": (tags.get("title") or "").strip() or None,
        "artist": (tags.get("artist") or "").strip() or None,
    }


def import_file(src: str) -> dict:
    """Возвращает трек (dict строки tracks) + служебное поле duplicate."""
    src_path = Path(src)
    if not src_path.is_file():
        raise AppError("E_FILE_ACCESS", f"файл не найден: {src}", status=404)
    ext = src_path.suffix.lower()
    if ext not in config.ALLOWED_IMPORT_EXTS:
        raise AppError("E_DECODE", f"формат {ext or '(без расширения)'} не поддерживается", status=422)
    size = src_path.stat().st_size
    if size == 0:
        raise AppError("E_DECODE", "файл пустой", status=422)
    if size > MAX_IMPORT_BYTES:
        raise AppError("E_TOO_LONG", "файл больше 2 ГБ", status=422)

    content_hash = _sha256(src_path)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM tracks WHERE content_hash=?", (content_hash,)).fetchone()
    if row is not None:
        return {**dict(row), "duplicate": True}

    meta = _probe_meta(src_path)
    hash16 = content_hash[:HASH_PREFIX_LEN]
    media_name = f"{hash16}{ext}"
    dest = config.originals_dir() / media_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.tmp_dir() / f"import-{hash16}{ext}"
    shutil.copyfile(src_path, tmp)  # копия через tmp: не оставляем битых файлов в originals
    tmp.replace(dest)

    try:
        waveform.generate(str(dest), hash16, meta["duration_s"])
    except AppError:
        dest.unlink(missing_ok=True)
        raise

    track = {
        "id": db.new_id(),
        "user_id": db.LOCAL_USER,
        "title": meta["title"] or src_path.stem,
        "artist": meta["artist"],
        "duration_s": meta["duration_s"],
        "sample_rate": meta["sample_rate"],
        "format": meta["format"],
        "src_path": str(src_path),
        "media_path": media_name,
        "content_hash": content_hash,
        "added_at": db.now_iso(),
        "is_favorite": 0,
        "origin": "import",
    }
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO tracks(id,user_id,title,artist,duration_s,sample_rate,format,
                                  src_path,media_path,content_hash,added_at,is_favorite,origin)
               VALUES(:id,:user_id,:title,:artist,:duration_s,:sample_rate,:format,
                      :src_path,:media_path,:content_hash,:added_at,:is_favorite,:origin)""",
            track,
        )
    return {**track, "duplicate": False}


def delete_track(track_id: str) -> None:
    """Удаляет копию и кеш; исходник пользователя не трогаем."""
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
        if row is None:
            raise AppError("E_NOT_FOUND", "трек не найден", status=404)
        conn.execute("DELETE FROM tracks WHERE id=?", (track_id,))
    (config.originals_dir() / row["media_path"]).unlink(missing_ok=True)
    waveform.peaks_path(row["content_hash"][:HASH_PREFIX_LEN]).unlink(missing_ok=True)
