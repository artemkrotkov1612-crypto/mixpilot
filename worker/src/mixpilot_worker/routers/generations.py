"""Генерации, варианты, правки, экспорт, оценки (ТЗ §7)."""

import json

from fastapi import APIRouter
from pydantic import BaseModel

from .. import config, db
from ..errors import AppError, not_found
from ..jobs import queue
from ..llm import edit_dsl
from ..media.export import export_variant

router = APIRouter(tags=["generations"])


def _variant_dict(row) -> dict:
    d = dict(row)
    d.pop("params_json", None)
    return d


def _variants_for(generation_id: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM generation_variants WHERE generation_id=? ORDER BY idx",
            (generation_id,),
        ).fetchall()
    return [_variant_dict(r) for r in rows]


class GenerateBody(BaseModel):
    project_id: str
    request: dict = {}


@router.post("/generations")
def create_generation(body: GenerateBody) -> dict:
    with db.connect() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=?", (body.project_id,)).fetchone()
        if project is None:
            raise not_found("проект не найден")
        src = conn.execute(
            "SELECT 1 FROM project_tracks WHERE project_id=? AND role='source' LIMIT 1",
            (body.project_id,),
        ).fetchone()
        if src is None:
            raise AppError("E_BAD_REQUEST", "сначала добавьте песню в проект", status=422)

        source_count = conn.execute(
            "SELECT COUNT(*) AS n FROM project_tracks WHERE project_id=? AND role='source'",
            (body.project_id,),
        ).fetchone()["n"]
        if project["mode"] == "merge" and source_count < 2:
            raise AppError("E_BAD_REQUEST", "нужно хотя бы две песни", status=422,
                           message_ru="Добавьте хотя бы две песни")

        quality = body.request.get("quality", "fast")
        if quality not in ("fast", "max"):
            quality = "fast"
        generation_id = db.new_id()
        conn.execute(
            """INSERT INTO generations(id,project_id,request_json,quality_mode,status,created_at)
               VALUES(?,?,?,?,'queued',?)""",
            (generation_id, body.project_id, json.dumps(body.request, ensure_ascii=False),
             quality, db.now_iso()),
        )
        conn.execute("UPDATE projects SET status='processing', updated_at=? WHERE id=?",
                     (db.now_iso(), body.project_id))

    kind = {"merge": "merge", "voice_cover": "voice_cover"}.get(project["mode"], "generate")
    job = queue.enqueue(kind, {"generation_id": generation_id},
                        priority=queue.PRIORITY["generate"], gpu=True)
    return {"generation_id": generation_id, "job": job}


@router.get("/generations/{generation_id}")
def get_generation(generation_id: str) -> dict:
    with db.connect() as conn:
        gen = conn.execute("SELECT * FROM generations WHERE id=?", (generation_id,)).fetchone()
    if gen is None:
        raise not_found("генерация не найдена")
    d = dict(gen)
    d["request"] = json.loads(d.pop("request_json") or "{}")
    d["plan"] = json.loads(d.pop("plan_json") or "null")
    d["variants"] = _variants_for(generation_id)
    return d


@router.get("/projects/{project_id}/generations")
def list_project_generations(project_id: str) -> dict:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM generations WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return {"generations": [get_generation(r["id"]) for r in rows]}


class EditBody(BaseModel):
    chips: list[str] = []
    ops: list[dict] | None = None
    text: str | None = None


def _edit_context(variant_id: str) -> dict:
    """Текстовый контекст для модели: стиль, темп, названия блоков. Без аудио."""
    from ..analysis.run import get_analysis
    from ..generate.pipeline import _llm_context

    with db.connect() as conn:
        row = conn.execute(
            """SELECT g.plan_json, pt.track_id FROM generation_variants v
               JOIN generations g ON g.id = v.generation_id
               LEFT JOIN project_tracks pt ON pt.project_id = g.project_id AND pt.role='source'
               WHERE v.id=? LIMIT 1""",
            (variant_id,),
        ).fetchone()
    if row is None:
        return {}
    ctx = {}
    plan = json.loads(row["plan_json"] or "null") or {}
    if plan.get("style_name"):
        ctx["style_name"] = plan["style_name"]
    if row["track_id"]:
        ctx.update(_llm_context(get_analysis(row["track_id"])))
    return ctx


@router.post("/variants/{variant_id}/edit")
def edit_variant(variant_id: str, body: EditBody) -> dict:
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM generation_variants WHERE id=?", (variant_id,)).fetchone() is None:
            raise not_found("вариант не найден")

    ops = list(body.ops) if body.ops else []
    ops += edit_dsl.chips_to_ops(body.chips)

    summary = ""
    text = (body.text or "").strip()
    if text:
        # Свободный текст -> операции через Claude (в облако уходит только текст).
        from ..llm.understand import text_to_ops

        understood = text_to_ops(text, _edit_context(variant_id))
        ops += understood["ops"]
        summary = understood["summary_ru"]

    try:
        ops = edit_dsl.validate_ops(ops)
    except edit_dsl.DslError as exc:
        raise AppError("E_DSL", exc.message, status=422) from exc
    if not ops:
        raise AppError("E_BAD_REQUEST", "не выбрано ни одного изменения", status=422)

    job = queue.enqueue("apply_edit", {"variant_id": variant_id, "ops": ops, "summary_ru": summary},
                        priority=queue.PRIORITY["interactive"], gpu=True)
    return {"job": job, "summary_ru": summary}


class FeedbackBody(BaseModel):
    rating: int  # 1 | -1 | 0


@router.post("/variants/{variant_id}/feedback")
def variant_feedback(variant_id: str, body: FeedbackBody) -> dict:
    rating = 1 if body.rating > 0 else (-1 if body.rating < 0 else 0)
    with db.connect() as conn:
        cur = conn.execute("UPDATE generation_variants SET rating=? WHERE id=?", (rating, variant_id))
        if cur.rowcount == 0:
            raise not_found("вариант не найден")
        conn.execute(
            "INSERT INTO taste_events(id,user_id,kind,payload_json,created_at) VALUES(?,?,?,?,?)",
            (db.new_id(), db.LOCAL_USER, "like" if rating > 0 else "dislike",
             json.dumps({"variant_id": variant_id}), db.now_iso()),
        )
    return {"rating": rating}


@router.get("/variants/{variant_id}/peaks")
def variant_peaks(variant_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT render_peaks FROM generation_variants WHERE id=?", (variant_id,)
        ).fetchone()
    if row is None:
        raise not_found("вариант не найден")
    peaks_path = config.data_dir() / (row["render_peaks"] or "")
    if not row["render_peaks"] or not peaks_path.exists():
        raise not_found("пики варианта отсутствуют")
    return json.loads(peaks_path.read_text(encoding="utf-8"))


class ExportBody(BaseModel):
    format: str
    dest_dir: str | None = None


@router.post("/variants/{variant_id}/export")
def export(variant_id: str, body: ExportBody) -> dict:
    return export_variant(variant_id, body.format, body.dest_dir)
