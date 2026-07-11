"""Библиотека треков: импорт, список, пики, избранное, удаление."""

from fastapi import APIRouter
from pydantic import BaseModel

from .. import db
from ..errors import AppError, not_found
from ..media import import_ as media_import
from ..media import waveform

router = APIRouter(prefix="/library", tags=["library"])

SORTS = {
    "added": "added_at DESC",
    "title": "title COLLATE NOCASE ASC",
    "duration": "duration_s DESC",
}


class ImportBody(BaseModel):
    path: str


@router.post("/import")
def import_track(body: ImportBody) -> dict:
    # Синхронно: hash+копия+пики занимают секунды. С M2 маршрутизируется в очередь.
    return media_import.import_file(body.path)


@router.get("/tracks")
def list_tracks(q: str = "", sort: str = "added", favorite: bool = False,
                limit: int = 200, offset: int = 0) -> dict:
    order = SORTS.get(sort)
    if order is None:
        raise AppError("E_BAD_REQUEST", f"неизвестная сортировка: {sort}")
    where, params = ["user_id=?"], [db.LOCAL_USER]
    if q.strip():
        needle = q.strip().casefold()
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append(
            r"(casefold(title) LIKE ? ESCAPE '\' OR casefold(artist) LIKE ? ESCAPE '\')"
        )
        like = f"%{escaped}%"
        params += [like, like]
    if favorite:
        where.append("is_favorite=1")
    params += [min(limit, 500), max(offset, 0)]
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM tracks WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM tracks WHERE user_id=?", (db.LOCAL_USER,)).fetchone()[0]
    return {"tracks": [dict(r) for r in rows], "total": total}


@router.get("/tracks/{track_id}")
def get_track(track_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if row is None:
        raise not_found("трек не найден")
    return dict(row)


@router.get("/tracks/{track_id}/peaks")
def get_peaks(track_id: str) -> dict:
    track = get_track(track_id)
    hash16 = track["content_hash"][: media_import.HASH_PREFIX_LEN]
    doc = waveform.load(hash16)
    if doc is None:  # кеш могли почистить — пересчитываем
        from .. import config

        media_path = config.originals_dir() / track["media_path"]
        if not media_path.exists():
            raise not_found("аудиофайл трека отсутствует в хранилище")
        doc = waveform.generate(str(media_path), hash16, track["duration_s"])
    return doc


class PatchTrackBody(BaseModel):
    is_favorite: bool | None = None
    title: str | None = None


@router.patch("/tracks/{track_id}")
def patch_track(track_id: str, body: PatchTrackBody) -> dict:
    sets, params = [], []
    if body.is_favorite is not None:
        sets.append("is_favorite=?")
        params.append(int(body.is_favorite))
    if body.title is not None and body.title.strip():
        sets.append("title=?")
        params.append(body.title.strip())
    if not sets:
        raise AppError("E_BAD_REQUEST", "нет полей для обновления")
    params.append(track_id)
    with db.connect() as conn:
        cur = conn.execute(f"UPDATE tracks SET {', '.join(sets)} WHERE id=?", params)
        if cur.rowcount == 0:
            raise not_found("трек не найден")
    return get_track(track_id)


@router.delete("/tracks/{track_id}")
def delete_track(track_id: str) -> dict:
    media_import.delete_track(track_id)
    return {"deleted": track_id}
