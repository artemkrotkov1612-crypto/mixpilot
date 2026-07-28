"""Название и обложка варианта (M7).

Названия предлагает облако, обложка рисуется локально из волны трека.
Обе части работают по отдельности: без интернета останутся шаблонные
названия и та же обложка.
"""

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import config, db, share
from ..artwork import cover as cover_render
from ..artwork import naming
from ..errors import AppError, not_found
from ..media.export import export_variant

router = APIRouter(tags=["artwork"])


def _variant_context(variant_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            """SELECT v.*, g.plan_json, g.project_id
               FROM generation_variants v JOIN generations g ON g.id = v.generation_id
               WHERE v.id=?""", (variant_id,)
        ).fetchone()
        if row is None:
            raise not_found("вариант не найден")
        src = conn.execute(
            "SELECT t.title FROM project_tracks pt JOIN tracks t ON t.id=pt.track_id "
            "WHERE pt.project_id=? AND pt.role='source' ORDER BY pt.position LIMIT 1",
            (row["project_id"],),
        ).fetchone()
        analysis = conn.execute(
            "SELECT a.bpm FROM project_tracks pt JOIN track_analysis a ON a.track_id=pt.track_id "
            "WHERE pt.project_id=? AND pt.role='source' LIMIT 1",
            (row["project_id"],),
        ).fetchone()

    plan = json.loads(row["plan_json"] or "{}")
    return {
        "row": row,
        "source_title": (src["title"] if src else "") or "",
        "style": plan.get("style", ""),
        "style_name": plan.get("style_name", ""),
        "bpm": analysis["bpm"] if analysis else None,
    }


@router.get("/variants/{variant_id}/titles")
def titles(variant_id: str) -> dict:
    """Пять вариантов названия. Работает и без облака."""
    ctx = _variant_context(variant_id)
    result = naming.suggest_titles(
        source_title=ctx["source_title"], style=ctx["style"],
        style_name=ctx["style_name"], bpm=ctx["bpm"],
        mood=ctx["row"]["description_ru"] or "",
    )
    result["cloud"] = result["source"] == "cloud"
    return result


class CoverBody(BaseModel):
    title: str


@router.post("/variants/{variant_id}/cover")
def make_cover(variant_id: str, body: CoverBody) -> dict:
    """Рисует обложку с выбранным названием и запоминает его за вариантом."""
    ctx = _variant_context(variant_id)
    row = ctx["row"]
    title = body.title.strip()[:80]

    peaks = []
    if row["render_peaks"]:
        peaks = cover_render.peaks_from_file(config.data_dir() / row["render_peaks"])

    out = config.data_dir() / "renders" / row["generation_id"] / f"variant_{row['idx']}.cover.png"
    subtitle = " · ".join(x for x in (ctx["style_name"], ctx["source_title"]) if x)[:60]
    cover_render.render_cover(title, subtitle, peaks, ctx["style"], out)

    rel = out.relative_to(config.data_dir()).as_posix()
    with db.connect() as conn:
        conn.execute("UPDATE generation_variants SET cover_path=?, custom_title=? WHERE id=?",
                     (rel, title or None, variant_id))
    return {"cover_path": rel, "title": title}


@router.post("/variants/{variant_id}/share")
def share_to_phone(variant_id: str) -> dict:
    """Временная ссылка в домашней сети + QR. Наружу, в интернет, ничего не уходит."""
    exported = export_variant(variant_id, "mp3")
    path = Path(exported["path"])
    try:
        link = share.publish(path, filename=path.name)
    except FileNotFoundError as exc:
        raise AppError("E_FILE_ACCESS", "экспортированный файл не найден", status=404) from exc
    link["cloud"] = False
    return link


@router.delete("/share")
def share_revoke() -> dict:
    return {"closed": share.revoke_all()}


@router.get("/share")
def share_status() -> dict:
    return {"active": share.active_links()}


@router.get("/variants/{variant_id}/cover.png")
def get_cover(variant_id: str):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT cover_path FROM generation_variants WHERE id=?", (variant_id,)
        ).fetchone()
    if row is None:
        raise not_found("вариант не найден")
    path = config.data_dir() / (row["cover_path"] or "")
    if not row["cover_path"] or not path.exists():
        raise not_found("обложка ещё не сделана")
    return FileResponse(path, media_type="image/png")
