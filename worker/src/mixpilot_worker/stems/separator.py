"""Адаптер разделения стемов: кеш + выбор реализации по режиму качества.

Бизнес-код знает только get_stems(); имена моделей — деталь реализации
(ТЗ §5: адаптеры, реестр, никакой модели в бизнес-логике).
"""

from .. import config, db
from ..errors import AppError, not_found
from ..jobs.runner import JobContext, register

STEM_NAMES = ("vocals", "drums", "bass", "other")

# Реализации по режиму качества (сейчас обе — demucs с разными весами).
QUALITY_IMPL = {
    "fast": ("demucs", "htdemucs"),
    "max": ("demucs", "htdemucs_ft"),
}


def stems_dir(content_hash16: str, model: str):
    return config.data_dir() / "cache" / "stems" / content_hash16 / model


def _cached(track_id: str, model: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM stems_cache WHERE track_id=? AND model=?", (track_id, model)
        ).fetchone()
    if row is None:
        return None
    paths = {name: row[f"path_{name}"] for name in STEM_NAMES}
    if not all(p and config.data_dir().joinpath(p).exists() for p in paths.values()):
        return None
    return {name: str(config.data_dir() / p) for name, p in paths.items()}


def get_stems(track_id: str, quality: str, ctx: JobContext) -> dict:
    """Пути к 4 стемам (кеш или разделение). Ключи: vocals/drums/bass/other."""
    if quality not in QUALITY_IMPL:
        raise AppError("E_BAD_REQUEST", f"неизвестный режим качества: {quality}")
    impl, model = QUALITY_IMPL[quality]

    with db.connect() as conn:
        track = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if track is None:
        raise not_found("трек не найден")

    cached = _cached(track_id, model)
    if cached is not None:
        ctx.report("save", 0.98)
        return cached

    media_path = config.originals_dir() / track["media_path"]
    if not media_path.exists():
        raise AppError("E_FILE_ACCESS", "аудиофайл отсутствует в хранилище", status=404)

    hash16 = track["content_hash"][:16]
    out_dir = stems_dir(hash16, model)
    out_dir.mkdir(parents=True, exist_ok=True)

    if impl == "demucs":
        from . import demucs_impl

        paths = demucs_impl.separate(str(media_path), out_dir, model, ctx)
    else:  # pragma: no cover — реестр на будущее (RoFormer и т.п.)
        raise AppError("E_INTERNAL", f"неизвестная реализация: {impl}", status=500)

    rel = {name: str(paths[name].relative_to(config.data_dir())) for name in STEM_NAMES}
    with db.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO stems_cache
               (track_id,model,path_vocals,path_drums,path_bass,path_other,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (track_id, model, rel["vocals"], rel["drums"], rel["bass"], rel["other"], db.now_iso()),
        )
    return {name: str(paths[name]) for name in STEM_NAMES}


@register("stems")
def run_stems(payload: dict, ctx: JobContext) -> dict:
    paths = get_stems(payload["track_id"], payload.get("quality", "fast"), ctx)
    return {"track_id": payload["track_id"], "stems": paths}


def stems_status(track_id: str) -> dict:
    """Какие модели уже разделили этот трек (для UI/отладки)."""
    out = {}
    for quality, (_impl, model) in QUALITY_IMPL.items():
        out[quality] = _cached(track_id, model) is not None
    return out
