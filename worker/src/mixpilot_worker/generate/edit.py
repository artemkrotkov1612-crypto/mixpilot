"""Job 'apply_edit': пересборка варианта из кеша стемов с новыми параметрами.

Быстро: анализ и стемы уже в кеше (M1/M2), пересчитывается только рендер
одного варианта mixkit'ом. Новый вариант не затирает исходный (история версий).
"""

import json

import numpy as np
import soundfile as sf

from .. import config, db
from ..errors import AppError, not_found
from ..jobs.runner import JobContext, register
from ..llm import edit_dsl
from ..stems.separator import get_stems
from ..styles import base as style_base
from .pipeline import _load_stems_audio, _render_dir, waveform_peaks

SR = style_base.SR


def _source_track_id(project_id: str) -> str:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT track_id FROM project_tracks WHERE project_id=? AND role='source' "
            "ORDER BY position LIMIT 1",
            (project_id,),
        ).fetchone()
    if row is None:
        raise AppError("E_BAD_REQUEST", "в проекте нет исходной песни", status=422)
    return row["track_id"]


@register("apply_edit")
def run_apply_edit(payload: dict, ctx: JobContext) -> dict:
    parent_variant_id = payload["variant_id"]
    ops = payload.get("ops", [])

    with db.connect() as conn:
        parent = conn.execute(
            "SELECT * FROM generation_variants WHERE id=?", (parent_variant_id,)
        ).fetchone()
        if parent is None:
            raise not_found("вариант не найден")
        gen = conn.execute(
            "SELECT * FROM generations WHERE id=?", (parent["generation_id"],)
        ).fetchone()
    generation_id = gen["id"]
    quality = gen["quality_mode"]

    base_params = style_base.StyleParams.from_dict(json.loads(parent["params_json"]))
    new_params = edit_dsl.apply_ops(base_params, edit_dsl.validate_ops(ops))

    track_id = _source_track_id(gen["project_id"])
    ctx.report("stems", 0.1, human="Готовим дорожки…")
    stems = _load_stems_audio(get_stems(track_id, quality, ctx))

    ctx.report("build", 0.4, human="Применяем изменения…")
    audio = style_base.render(stems, new_params, sr=SR, progress=lambda f: ctx.report("build", 0.4 + 0.5 * f))

    # Следующий idx в этой генерации.
    with db.connect() as conn:
        max_idx = conn.execute(
            "SELECT COALESCE(MAX(idx), -1) AS m FROM generation_variants WHERE generation_id=?",
            (generation_id,),
        ).fetchone()["m"]
    new_idx = int(max_idx) + 1

    render_dir = _render_dir(generation_id)
    wav_path = render_dir / f"variant_{new_idx}.wav"
    sf.write(str(wav_path), audio, SR, subtype="PCM_16")  # см. pipeline.py
    peaks_path = render_dir / f"variant_{new_idx}.peaks.json"
    peaks_path.write_text(json.dumps(waveform_peaks(audio)), encoding="utf-8")

    title = f"Вариант {chr(ord('A') + new_idx)} — с изменениями"
    # Если правку сформулировали словами, показываем формулировку модели.
    desc = (payload.get("summary_ru") or "").strip() or _describe_ops(ops)
    variant_id = db.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO generation_variants
               (id,generation_id,idx,title_ru,description_ru,render_wav,render_peaks,
                params_json,parent_variant_id,rating)
               VALUES(?,?,?,?,?,?,?,?,?,0)""",
            (variant_id, generation_id, new_idx, title, desc,
             wav_path.relative_to(config.data_dir()).as_posix(),
             peaks_path.relative_to(config.data_dir()).as_posix(),
             json.dumps(new_params.to_dict(), ensure_ascii=False), parent_variant_id),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now_iso(), gen["project_id"]))
    ctx.report("done", 1.0, human="Готово!")
    return {"variant_id": variant_id, "idx": new_idx, "title_ru": title, "description_ru": desc}


_OP_LABELS = {
    "bass": lambda o: "бас мощнее" if o.get("amount", 0) > 0 else "меньше баса",
    "tempo": lambda o: "быстрее" if o.get("delta", 0) > 0 else "медленнее",
    "gain": lambda o: f"{'громче' if o.get('db', 0) > 0 else 'тише'} {_ru_target(o.get('target'))}",
    "energy": lambda o: "мощнее припев",
    "reverb": lambda o: "больше атмосферы",
    "air": lambda o: "ярче",
    "mood": lambda o: "мрачнее" if o.get("name") == "dark" else "энергичнее",
    "intro_shorter": lambda o: "короче вступление",
    "pitch": lambda o: "ниже тон" if o.get("semitones", 0) < 0 else "выше тон",
}


def _ru_target(target: str | None) -> str:
    return {"vocals": "голос", "drums": "барабаны", "bass": "бас", "other": "музыку"}.get(target or "", "")


def _describe_ops(ops: list[dict]) -> str:
    parts = []
    for op in ops or []:
        fn = _OP_LABELS.get(op.get("op"))
        if fn:
            parts.append(fn(op))
    return ", ".join(dict.fromkeys(parts)) or "изменения применены"
