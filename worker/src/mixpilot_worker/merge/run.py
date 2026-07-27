"""Job 'merge': соединение нескольких песен.

Ключевое требование ТЗ: не загружать все дорожки всех треков сразу.
Обрабатываем по одному треку — анализ, стемы, вырезаем нужные куски,
освобождаем память — и только потом собираем результат.
"""

import json

import numpy as np
import soundfile as sf

from .. import config, db
from ..analysis.run import get_analysis, run_analyze
from ..errors import AppError, not_found
from ..jobs.runner import JobContext, register
from ..mixkit import SR, dynamics, loudness, mixdown
from ..restructure.blocks import concat_crossfade, slice_segment
from ..stems.separator import get_stems
from ..styles import base as style_base
from ..styles.registry import STYLE_NAMES, plan_variants, resolve_style
from ..timepitch import stretcher
from . import compat, strategies
from ..generate.pipeline import _render_dir, waveform_peaks

# Сколько треков считаем «много» — предупреждаем о времени обработки.
MANY_TRACKS = 4


def _track_rows(project_id: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT t.* FROM project_tracks pt JOIN tracks t ON t.id = pt.track_id
               WHERE pt.project_id=? AND pt.role='source' ORDER BY pt.position, t.added_at""",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _ensure_analysis(track_id: str, ctx: JobContext) -> dict:
    existing = get_analysis(track_id)
    if existing is not None:
        return existing
    run_analyze({"track_id": track_id}, ctx)
    result = get_analysis(track_id)
    if result is None:
        raise AppError("E_INTERNAL", "анализ не сохранился", status=500)
    return result


def _load_stem_mix(paths: dict[str, str], which: str) -> np.ndarray:
    """Читаем только нужные дорожки: вокал или инструментал (без вокала)."""
    names = ("vocals",) if which == "vocals" else ("drums", "bass", "other")
    parts = []
    for name in names:
        audio, _sr = sf.read(paths[name], dtype="float32", always_2d=True)
        parts.append(audio)
    return mixdown.mix(parts)


def _prepare_pieces(track_row: dict, analysis: dict, plan_track: dict, plan: dict,
                    ctx: JobContext, quality: str) -> dict:
    """Куски одного трека, уже подтянутые к якорю. Стемы после этого освобождаются."""
    track_id = track_row["id"]
    idx = plan_track["index"]

    needs_vocals = any(layer["track_index"] == idx for layer in plan.get("layers", []))
    needs_instrumental = any(
        p["track_index"] == idx and p.get("stem") == "instrumental" for p in plan["sequence"]
    )
    needs_full = any(
        p["track_index"] == idx and p.get("stem") is None for p in plan["sequence"]
    )

    audio_cache: dict[str, np.ndarray] = {}
    if needs_vocals or needs_instrumental:
        stem_paths = get_stems(track_id, quality, ctx)
        if needs_vocals:
            audio_cache["vocals"] = _load_stem_mix(stem_paths, "vocals")
        if needs_instrumental:
            audio_cache["instrumental"] = _load_stem_mix(stem_paths, "instrumental")
    if needs_full:
        media = config.originals_dir() / track_row["media_path"]
        full, _sr = sf.read(str(media), dtype="float32", always_2d=True)
        audio_cache["full"] = mixdown.to_stereo(full)

    def cut(source_key: str, start_s: float, end_s: float) -> np.ndarray:
        piece = slice_segment(audio_cache[source_key], start_s, end_s, SR)
        if piece.shape[0] == 0:
            return piece
        return stretcher.stretch(piece, SR, plan_track["tempo_factor"], plan_track["pitch_semitones"])

    result: dict = {"sequence": {}, "layers": []}
    for order, piece in enumerate(plan["sequence"]):
        if piece["track_index"] != idx:
            continue
        key = "instrumental" if piece.get("stem") == "instrumental" else "full"
        result["sequence"][order] = cut(key, piece["start_s"], piece["end_s"])
    for layer in plan.get("layers", []):
        if layer["track_index"] != idx:
            continue
        result["layers"].append({
            "stem": layer["stem"],
            "pieces": [cut("vocals", p["start_s"], p["end_s"]) for p in layer["pieces"]],
        })

    audio_cache.clear()  # освобождаем стемы до перехода к следующему треку
    return result


def _assemble(plan: dict, prepared: dict[int, dict]) -> np.ndarray:
    """Собираем основу по порядку и накладываем слои (вокал)."""
    ordered = []
    for order, piece in enumerate(plan["sequence"]):
        chunk = prepared.get(piece["track_index"], {}).get("sequence", {}).get(order)
        if chunk is not None and chunk.shape[0] > 0:
            ordered.append(chunk)
    base = concat_crossfade(ordered, xfade_ms=plan.get("xfade_ms", 400), sr=SR)
    if base.shape[0] == 0:
        raise AppError("E_INTERNAL", "не удалось собрать основу", status=500)

    # Слои: вокал раскладываем по основе от начала, куски идут подряд.
    for track_prepared in prepared.values():
        for layer in track_prepared.get("layers", []):
            vocal = concat_crossfade(layer["pieces"], xfade_ms=200, sr=SR)
            if vocal.shape[0] == 0:
                continue
            if vocal.shape[0] > base.shape[0]:
                vocal = vocal[: base.shape[0]]
            padded = np.zeros_like(base)
            padded[: vocal.shape[0]] = vocal
            # Лёгкий дакинг музыки, чтобы голос читался.
            base = base * 0.82 + padded * 1.0
    return base.astype(np.float32)


@register("merge")
def run_merge(payload: dict, ctx: JobContext) -> dict:
    generation_id = payload["generation_id"]
    with db.connect() as conn:
        gen = conn.execute("SELECT * FROM generations WHERE id=?", (generation_id,)).fetchone()
        if gen is None:
            raise not_found("генерация не найдена")
    request = json.loads(gen["request_json"])
    quality = gen["quality_mode"]

    tracks = _track_rows(gen["project_id"])
    if len(tracks) < 2:
        raise AppError("E_BAD_REQUEST", "нужно хотя бы две песни", status=422,
                       message_ru="Добавьте хотя бы две песни")

    # 1. Анализ каждого трека (по очереди) и план совместимости.
    ctx.report("analyze", 0.05, human="Слушаем песни…")
    analyses = []
    for i, track in enumerate(tracks):
        ctx.report("analyze", 0.05 + 0.15 * i / len(tracks),
                   human=f"Слушаем песню {i + 1} из {len(tracks)}…")
        analysis = _ensure_analysis(track["id"], ctx)
        analyses.append({
            "track_id": track["id"],
            "title": track["title"],
            "duration_s": track["duration_s"],
            **{k: analysis.get(k) for k in ("bpm", "key_root", "key_mode", "sections")},
        })

    ctx.report("plan", 0.22, human="Подбираем темп и тональность…")
    compat_plan = compat.build_plan(analyses)
    plan = strategies.build(
        request.get("strategy"),
        analyses,
        vocal_from=int(request.get("vocal_from", 0) or 0),
        music_from=int(request.get("music_from", 1) or 1),
    )

    # 2. Куски треков — по одному треку за раз, память освобождается сразу.
    prepared: dict[int, dict] = {}
    used = sorted({p["track_index"] for p in plan["sequence"]} |
                  {layer["track_index"] for layer in plan.get("layers", [])})
    for n, idx in enumerate(used):
        ctx.check_cancelled()
        ctx.report("stems", 0.25 + 0.4 * n / max(len(used), 1),
                   human=f"Готовим песню {n + 1} из {len(used)}…")
        prepared[idx] = _prepare_pieces(
            tracks[idx], analyses[idx], compat_plan["tracks"][idx], plan, ctx, quality
        )

    ctx.report("build", 0.7, human="Собираем варианты…")
    merged = _assemble(plan, prepared)
    prepared.clear()

    # 3. Три варианта: сырой микс + два стилевых характера поверх него.
    style = resolve_style(request.get("style"), {"bpm": compat_plan.get("anchor_bpm")})
    variant_specs = plan_variants(style, request.get("chips", []))
    stems_like = {"other": merged}

    render_dir = _render_dir(generation_id)
    results = []
    for i, spec in enumerate(variant_specs):
        ctx.check_cancelled()
        ctx.report("build", 0.72 + 0.22 * i / len(variant_specs),
                   human=f"Собираем вариант {i + 1} из {len(variant_specs)}…")
        params = spec["params"]
        if i == 0:
            # Первый вариант — честное соединение без стилевой окраски.
            audio = dynamics.limiter(
                loudness.normalize_lufs(merged, loudness.TARGET_LUFS["stream"]), ceiling_db=-1.0
            )
            title = "Вариант A — Как есть"
            desc = plan["description_ru"]
        else:
            audio = style_base.render(stems_like, params, sr=SR)
            title = f"Вариант {chr(ord('A') + i)} — {STYLE_NAMES.get(style, style)}"
            desc = spec["description_ru"]

        wav_path = render_dir / f"variant_{i}.wav"
        sf.write(str(wav_path), audio, SR, subtype="PCM_16")
        peaks_path = render_dir / f"variant_{i}.peaks.json"
        peaks_path.write_text(json.dumps(waveform_peaks(audio)), encoding="utf-8")

        variant_id = db.new_id()
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO generation_variants
                   (id,generation_id,idx,title_ru,description_ru,render_wav,render_peaks,params_json,rating)
                   VALUES(?,?,?,?,?,?,?,?,0)""",
                (variant_id, generation_id, i, title, desc,
                 wav_path.relative_to(config.data_dir()).as_posix(),
                 peaks_path.relative_to(config.data_dir()).as_posix(),
                 json.dumps(params.to_dict(), ensure_ascii=False)),
            )
        results.append({"id": variant_id, "idx": i, "title_ru": title, "description_ru": desc})

    plan_summary = {
        "style": style,
        "style_name": plan["strategy_name"],
        "strategy": plan["strategy"],
        "chips": request.get("chips", []),
        "warnings": compat_plan["warnings"],
        "anchor_title": analyses[compat_plan["anchor"]]["title"],
    }
    with db.connect() as conn:
        conn.execute(
            "UPDATE generations SET status='ready', plan_json=?, finished_at=? WHERE id=?",
            (json.dumps(plan_summary, ensure_ascii=False), db.now_iso(), generation_id),
        )
        conn.execute("UPDATE projects SET status='ready', updated_at=? WHERE id=?",
                     (db.now_iso(), gen["project_id"]))

    ctx.report("done", 1.0, human="Готово!")
    return {"generation_id": generation_id, "variants": results,
            "strategy": plan["strategy_name"], "warnings": compat_plan["warnings"]}
