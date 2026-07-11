"""Job 'analyze': декод → темп → тональность → структура → track_analysis."""

import json

import numpy as np

from .. import config, db
from ..errors import AppError, not_found
from ..jobs.runner import JobContext, register
from ..media import ffmpeg
from . import key as key_mod
from . import structure as structure_mod
from . import tempo as tempo_mod

ENGINE_VER = "m2.1"
ANALYSIS_SR = 22050
MAX_ANALYSIS_S = 20 * 60


def get_analysis(track_id: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM track_analysis WHERE track_id=?", (track_id,)).fetchone()
    if row is None or row["engine_ver"] != ENGINE_VER:
        return None
    d = dict(row)
    for field in ("beats_json", "downbeats_json", "sections_json"):
        d[field.removesuffix("_json")] = json.loads(d.pop(field) or "[]")
    return d


def _load_track(track_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    if row is None:
        raise not_found("трек не найден")
    return dict(row)


@register("analyze")
def run_analyze(payload: dict, ctx: JobContext) -> dict:
    track = _load_track(payload["track_id"])
    if track["duration_s"] > MAX_ANALYSIS_S:
        raise AppError("E_TOO_LONG", f"трек длиннее {MAX_ANALYSIS_S // 60} минут", status=422)
    media_path = config.originals_dir() / track["media_path"]
    if not media_path.exists():
        raise AppError("E_FILE_ACCESS", "аудиофайл отсутствует в хранилище", status=404)

    ctx.report("decode", 0.03)
    raw = ffmpeg.decode_pcm_mono(str(media_path), ANALYSIS_SR)
    y = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if y.size < ANALYSIS_SR:
        raise AppError("E_DECODE", "трек короче секунды", status=422)

    ctx.report("tempo", 0.2)
    t = tempo_mod.analyze(y, ANALYSIS_SR)

    ctx.report("key", 0.5)
    k = key_mod.analyze(y, ANALYSIS_SR)

    ctx.report("structure", 0.65)
    sections = structure_mod.analyze(y, ANALYSIS_SR, t["downbeats"], t["beats"])

    ctx.report("save", 0.95)
    with db.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO track_analysis
               (track_id,bpm,bpm_conf,key_root,key_mode,key_conf,
                beats_json,downbeats_json,sections_json,analyzed_at,engine_ver)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                track["id"], t["bpm"], t["bpm_conf"],
                k["key_root"], k["key_mode"], k["key_conf"],
                json.dumps(t["beats"]), json.dumps(t["downbeats"]),
                json.dumps(sections, ensure_ascii=False),
                db.now_iso(), ENGINE_VER,
            ),
        )
    return {
        "track_id": track["id"],
        "bpm": t["bpm"],
        "key_root": k["key_root"],
        "key_mode": k["key_mode"],
        "sections": sections,
    }
