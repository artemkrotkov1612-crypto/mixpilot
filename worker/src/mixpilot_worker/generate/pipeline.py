"""Пайплайн ремикса (job 'generate'): decode → analysis → stems → 3 варианта.

Тяжёлые стадии кешируются M1/M2 (decode.wav, analysis, stems) — повторная
генерация и правки не пересчитывают их. Рендер вариантов — на CPU (mixkit).
"""

import json
import logging

import numpy as np
import soundfile as sf

from .. import config, db, taste
from ..analysis.run import get_analysis, run_analyze
from ..errors import AppError, not_found
from ..jobs.runner import JobContext, register
from ..media import waveform
from ..stems.separator import get_stems
from ..styles import base as style_base
from ..styles.registry import STYLE_NAMES, plan_variants, resolve_style

SR = style_base.SR
log = logging.getLogger("mixpilot.generate")

# Русские подписи блоков для контекста модели (аудио не отправляем — только метки).
SECTION_RU = {
    "intro": "вступление", "verse": "куплет", "chorus": "припев",
    "bridge": "проигрыш", "drop": "дроп", "outro": "финал",
}


def _llm_context(analysis: dict | None) -> dict:
    """Минимальный текстовый контекст для модели: темп и названия блоков."""
    if not analysis:
        return {}
    sections = analysis.get("sections") or []
    return {
        "bpm": analysis.get("bpm"),
        "sections": [SECTION_RU.get(s.get("label", ""), s.get("label", "")) for s in sections][:12],
    }


def _load_stems_audio(stem_paths: dict[str, str]) -> dict[str, np.ndarray]:
    out = {}
    for name, path in stem_paths.items():
        audio, _sr = sf.read(path, dtype="float32", always_2d=True)
        out[name] = audio
    return out


def _render_dir(generation_id: str):
    d = config.data_dir() / "renders" / generation_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _analysis_for(track_id: str, ctx: JobContext) -> dict:
    existing = get_analysis(track_id)
    if existing is not None:
        return existing
    # Синхронно внутри этой же задачи (analysis-джоб не плодим).
    run_analyze({"track_id": track_id}, ctx)
    result = get_analysis(track_id)
    if result is None:
        raise AppError("E_INTERNAL", "анализ не сохранился", status=500)
    return result


@register("generate")
def run_generate(payload: dict, ctx: JobContext) -> dict:
    generation_id = payload["generation_id"]
    with db.connect() as conn:
        gen = conn.execute("SELECT * FROM generations WHERE id=?", (generation_id,)).fetchone()
        if gen is None:
            raise not_found("генерация не найдена")
        project = conn.execute("SELECT * FROM projects WHERE id=?", (gen["project_id"],)).fetchone()
        src = conn.execute(
            "SELECT t.* FROM project_tracks pt JOIN tracks t ON t.id=pt.track_id "
            "WHERE pt.project_id=? AND pt.role='source' ORDER BY pt.position LIMIT 1",
            (gen["project_id"],),
        ).fetchone()
    if src is None:
        raise AppError("E_BAD_REQUEST", "в проекте нет исходной песни", status=422)

    request = json.loads(gen["request_json"])
    quality = gen["quality_mode"]
    chips = request.get("chips", [])
    track_id = src["id"]

    ctx.report("analyze", 0.05, human="Слушаем трек…")
    analysis = _analysis_for(track_id, ctx)

    # Свободный текст (если облако включено) может задать стиль и правки.
    text = (request.get("text") or "").strip()
    text_ops: list[dict] = []
    text_summary = ""
    style_from_text = ""
    if text:
        try:
            from ..llm.understand import text_to_plan

            ctx.report("plan", 0.3, human="Читаем ваши пожелания…")
            plan = text_to_plan(text, _llm_context(analysis))
            style_from_text = plan.get("style") or ""
            text_ops = plan.get("ops") or []
            text_summary = plan.get("summary_ru") or ""
        except AppError as exc:
            # Облако недоступно или не поняло — стили и карточки работают всегда.
            log.info("свободный текст пропущен: %s", exc.code)

    style = resolve_style(style_from_text or request.get("style"), analysis)

    ctx.report("stems", 0.2, human="Разделяем на дорожки…")
    stem_paths = get_stems(track_id, quality, ctx)
    stems = _load_stems_audio(stem_paths)

    ctx.report("plan", 0.42, human="Придумываем варианты…")
    variants = plan_variants(style, chips)
    # Вкус подмешиваем до пожеланий словами: прямая просьба всегда главнее.
    taste_summary = taste.apply_to_variants(variants)
    if text_ops:
        # Пожелания словами применяются поверх каждого варианта.
        from ..llm.edit_dsl import apply_ops

        for v in variants:
            v["params"] = apply_ops(v["params"], text_ops)
        if text_summary:
            variants[1]["description_ru"] = f"{variants[1]['description_ru']} · {text_summary}"

    render_dir = _render_dir(generation_id)
    results = []
    n = len(variants)
    for i, v in enumerate(variants):
        ctx.check_cancelled()
        span_lo = 0.45 + 0.5 * i / n
        span_hi = 0.45 + 0.5 * (i + 1) / n
        ctx.report("build", span_lo, human=f"Собираем вариант {i + 1} из {n}…")

        def prog(frac, lo=span_lo, hi=span_hi):
            ctx.report("build", lo + (hi - lo) * frac, human=f"Собираем вариант {i + 1} из {n}…")

        audio = style_base.render(stems, v["params"], sr=SR, progress=prog)
        wav_path = render_dir / f"variant_{v['idx']}.wav"
        # PCM_16: рендер нужен только для прослушивания и экспорта (мастер уже
        # ограничен -1 dBTP), а float32 занимал бы вдвое больше места на диске.
        sf.write(str(wav_path), audio, SR, subtype="PCM_16")
        peaks = waveform_peaks(audio)
        peaks_path = render_dir / f"variant_{v['idx']}.peaks.json"
        peaks_path.write_text(json.dumps(peaks), encoding="utf-8")

        variant_id = db.new_id()
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO generation_variants
                   (id,generation_id,idx,title_ru,description_ru,render_wav,render_peaks,params_json,rating)
                   VALUES(?,?,?,?,?,?,?,?,0)""",
                # as_posix(): прямые слеши нужны протоколу media:// в Electron
                (variant_id, generation_id, v["idx"], v["title_ru"], v["description_ru"],
                 wav_path.relative_to(config.data_dir()).as_posix(),
                 peaks_path.relative_to(config.data_dir()).as_posix(),
                 json.dumps(v["params"].to_dict(), ensure_ascii=False)),
            )
        results.append({"id": variant_id, "idx": v["idx"], "title_ru": v["title_ru"],
                        "description_ru": v["description_ru"]})

    plan_summary = {
        "style": style,
        "style_name": STYLE_NAMES.get(style, style),
        "chips": chips,
        "text_summary_ru": text_summary,
        "taste_ru": taste_summary,
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
            "style_name": STYLE_NAMES.get(style, style)}


def waveform_peaks(audio: np.ndarray, buckets: int = waveform.BUCKETS) -> dict:
    mono = np.abs(audio).max(axis=1) if audio.ndim > 1 else np.abs(audio)
    if mono.size == 0:
        return {"version": 1, "buckets": buckets, "duration_s": 0.0, "peaks": [0.0] * buckets}
    pad = (-mono.size) % buckets
    padded = np.pad(mono, (0, pad))
    peaks = padded.reshape(buckets, -1).max(axis=1)
    return {
        "version": 1,
        "buckets": buckets,
        "duration_s": round(len(mono) / SR, 3),
        "peaks": [round(float(v), 3) for v in np.clip(peaks, 0.0, 1.0)],
    }
