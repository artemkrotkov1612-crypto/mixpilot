"""Job 'voice_cover': песня зазвучит вашим голосом.

Вокал отделяется от музыки, переносится на голос из профиля и сводится
обратно. Три варианта отличаются обработкой голоса, а не самой моделью.
"""

import json

import numpy as np
import soundfile as sf

from .. import config, db
from ..errors import AppError, not_found
from ..jobs.runner import JobContext, register
from ..mixkit import SR, dynamics, eq, loudness, mixdown, reverb
from ..stems.separator import get_stems
from ..generate.pipeline import _render_dir, waveform_peaks
from . import convert as voice_convert
from . import profile as voice_profile

# Три характера обработки голоса — понятные на слух, без терминов.
VARIANTS = [
    {
        "title_ru": "Вариант A — Ближе к оригиналу",
        "description_ru": "Голос как есть, минимальная обработка",
        "vocal_gain_db": 0.0, "reverb": 0.0, "presence_db": 0.0, "comp": False,
    },
    {
        "title_ru": "Вариант B — Студийно",
        "description_ru": "Ровнее и разборчивее, как в студии",
        "vocal_gain_db": 1.0, "reverb": 0.08, "presence_db": 2.5, "comp": True,
    },
    {
        "title_ru": "Вариант C — С эффектами",
        "description_ru": "Атмосферный голос с эхом",
        "vocal_gain_db": 1.5, "reverb": 0.28, "presence_db": 3.5, "comp": True,
    },
]


def _resample_to(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Простое приведение частоты: линейная интерполяция достаточно точна для микса."""
    if src_sr == dst_sr or audio.size == 0:
        return audio
    ratio = dst_sr / src_sr
    target_len = int(round(audio.shape[0] * ratio))
    src_idx = np.linspace(0, audio.shape[0] - 1, target_len)
    if audio.ndim == 1:
        return np.interp(src_idx, np.arange(audio.shape[0]), audio).astype(np.float32)
    return np.stack(
        [np.interp(src_idx, np.arange(audio.shape[0]), audio[:, ch]) for ch in range(audio.shape[1])],
        axis=1,
    ).astype(np.float32)


def _shape_vocal(vocal: np.ndarray, spec: dict) -> np.ndarray:
    """Обработка голоса под выбранный характер варианта."""
    out = mixdown.to_stereo(vocal)
    sos = [eq.high_pass(85)]  # убираем гул ниже голоса
    if spec["presence_db"]:
        sos.append(eq.peaking(3200, spec["presence_db"], q=1.1))  # разборчивость
    out = eq.apply(out, sos)
    if spec["comp"]:
        out = dynamics.compressor(out, threshold_db=-20.0, ratio=3.0, attack_ms=8, release_ms=120)
    if spec["reverb"]:
        out = reverb.reverb(out, mix=spec["reverb"], room=0.55, damp=0.45)
    return mixdown.apply_gain(out, spec["vocal_gain_db"])


@register("voice_cover")
def run_voice_cover(payload: dict, ctx: JobContext) -> dict:
    generation_id = payload["generation_id"]
    with db.connect() as conn:
        gen = conn.execute("SELECT * FROM generations WHERE id=?", (generation_id,)).fetchone()
        if gen is None:
            raise not_found("генерация не найдена")
        src = conn.execute(
            "SELECT t.* FROM project_tracks pt JOIN tracks t ON t.id=pt.track_id "
            "WHERE pt.project_id=? AND pt.role='source' ORDER BY pt.position LIMIT 1",
            (gen["project_id"],),
        ).fetchone()
    if src is None:
        raise AppError("E_BAD_REQUEST", "нет исходной песни", status=422,
                       message_ru="Добавьте песню для кавера")

    request = json.loads(gen["request_json"])
    quality = gen["quality_mode"]

    profile = voice_profile.active_profile()
    if profile is None or not profile.get("model_path"):
        raise AppError("E_BAD_REQUEST", "нет готового профиля голоса", status=422,
                       message_ru="Сначала создайте свой голос — это займёт пару минут")

    ctx.report("stems", 0.08, human="Отделяем голос от музыки…")
    stem_paths = get_stems(src["id"], quality, ctx)
    vocals, v_sr = sf.read(stem_paths["vocals"], dtype="float32", always_2d=True)
    instrumental = mixdown.mix([
        sf.read(stem_paths[name], dtype="float32", always_2d=True)[0]
        for name in ("drums", "bass", "other")
    ])

    ctx.report("convert", 0.35, human="Поём вашим голосом… это самая долгая часть")
    mono_vocal = vocals.mean(axis=1)
    converted, out_sr = voice_convert.convert_voice(
        mono_vocal, v_sr, profile["model_path"],
        quality=quality,
        pitch_shift=int(request.get("pitch_shift", 0) or 0),
        singing=True,
    )
    voice_convert.unload()  # освобождаем VRAM до сведения

    ctx.report("mix", 0.75, human="Сводим с музыкой…")
    converted = _resample_to(converted, out_sr, SR)
    instrumental = _resample_to(instrumental, v_sr, SR)
    # Выравниваем длины: конверсия может дать чуть иную длительность.
    length = min(len(converted), len(instrumental)) or max(len(converted), len(instrumental))
    converted = converted[:length]
    instrumental = instrumental[:length]

    render_dir = _render_dir(generation_id)
    results = []
    for i, spec in enumerate(VARIANTS):
        ctx.check_cancelled()
        ctx.report("mix", 0.78 + 0.18 * i / len(VARIANTS),
                   human=f"Собираем вариант {i + 1} из {len(VARIANTS)}…")
        vocal_track = _shape_vocal(converted, spec)
        # Лёгкий дакинг музыки, чтобы голос читался.
        mixed = mixdown.mix([mixdown.apply_gain(instrumental, -1.5), vocal_track])
        mastered = dynamics.limiter(
            loudness.normalize_lufs(mixed, loudness.TARGET_LUFS["stream"]), ceiling_db=-1.0
        )

        wav_path = render_dir / f"variant_{i}.wav"
        sf.write(str(wav_path), mastered, SR, subtype="PCM_16")
        peaks_path = render_dir / f"variant_{i}.peaks.json"
        peaks_path.write_text(json.dumps(waveform_peaks(mastered)), encoding="utf-8")

        variant_id = db.new_id()
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO generation_variants
                   (id,generation_id,idx,title_ru,description_ru,render_wav,render_peaks,params_json,rating)
                   VALUES(?,?,?,?,?,?,?,?,0)""",
                (variant_id, generation_id, i, spec["title_ru"], spec["description_ru"],
                 wav_path.relative_to(config.data_dir()).as_posix(),
                 peaks_path.relative_to(config.data_dir()).as_posix(),
                 json.dumps(spec, ensure_ascii=False)),
            )
        results.append({"id": variant_id, "idx": i, "title_ru": spec["title_ru"]})

    plan_summary = {
        "style": "voice_cover",
        "style_name": "Кавер вашим голосом",
        "voice_profile": profile["name"],
        "chips": [],
    }
    with db.connect() as conn:
        conn.execute(
            "UPDATE generations SET status='ready', plan_json=?, finished_at=? WHERE id=?",
            (json.dumps(plan_summary, ensure_ascii=False), db.now_iso(), generation_id),
        )
        conn.execute("UPDATE projects SET status='ready', updated_at=? WHERE id=?",
                     (db.now_iso(), gen["project_id"]))

    ctx.report("done", 1.0, human="Готово!")
    return {"generation_id": generation_id, "variants": results}
