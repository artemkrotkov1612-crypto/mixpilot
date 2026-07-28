"""Профиль голоса: приём клипов, датасет и эталон для конверсии.

Эталон — короткая склейка лучших фрагментов записи. Именно он подаётся
модели как «вот так звучит мой голос».
"""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from .. import config, db
from ..errors import AppError, not_found
from ..mixkit import SR
from . import quality, steps

# Эталон дольше 40 с не нужен: модель берёт из него тембр, а не содержание.
REFERENCE_MAX_S = 40.0
REFERENCE_MIN_S = 6.0


def profile_dir(profile_id: str):
    path = config.data_dir() / "voice" / "datasets" / profile_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def reference_path(profile_id: str):
    return config.data_dir() / "voice" / "models" / f"{profile_id}-reference.wav"


def create_profile(name: str = "Мой голос") -> dict:
    profile_id = db.new_id()
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO voice_profiles(id,user_id,name,status,dataset_dir,minutes_recorded,created_at)
               VALUES(?,?,?,?,?,0,?)""",
            (profile_id, db.LOCAL_USER, name, "recording", str(profile_dir(profile_id)), db.now_iso()),
        )
    return get_profile(profile_id)


def get_profile(profile_id: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM voice_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise not_found("профиль голоса не найден")
        clips = conn.execute(
            "SELECT step, idx, duration_s, quality_json, accepted FROM voice_clips WHERE profile_id=? ORDER BY step, idx",
            (profile_id,),
        ).fetchall()
    profile = dict(row)
    profile["quality"] = json.loads(profile.pop("quality_json") or "null")
    profile["clips"] = [
        {**dict(c), "quality": json.loads(c["quality_json"] or "null")} for c in clips
    ]
    profile["recorded_clips"] = sum(1 for c in profile["clips"] if c["accepted"])
    profile["total_clips"] = steps.TOTAL_CLIPS
    return profile


def list_profiles() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id FROM voice_profiles WHERE user_id=? ORDER BY created_at DESC", (db.LOCAL_USER,)
        ).fetchall()
    return [get_profile(r["id"]) for r in rows]


def active_profile() -> dict | None:
    """Готовый профиль для каверов — последний обученный."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM voice_profiles WHERE user_id=? AND status='ready' ORDER BY trained_at DESC LIMIT 1",
            (db.LOCAL_USER,),
        ).fetchone()
    return get_profile(row["id"]) if row else None


def save_clip(profile_id: str, step: int, idx: int, audio: np.ndarray, sr: int) -> dict:
    """Оценивает клип и сохраняет, если он годится. Плохой не портит датасет."""
    step_def = steps.get_step(step)
    if step_def is None:
        raise AppError("E_BAD_REQUEST", f"нет шага {step}", status=422)

    if step_def["kind"] == "noise":
        verdict = quality.measure_noise_floor(audio, sr)
        _touch(profile_id)
        return {"step": step, "idx": idx, "quality": verdict, "saved": False}

    verdict = quality.analyze(audio, sr)
    if not verdict["accepted"]:
        return {"step": step, "idx": idx, "quality": verdict, "saved": False}

    prepared = quality.normalize_peak(quality.trim_silence(audio, sr), target_db=-3.0)
    path = profile_dir(profile_id) / f"step{step:02d}_{idx:02d}.wav"
    sf.write(str(path), prepared, sr, subtype="PCM_16")

    duration = len(prepared) / sr
    with db.connect() as conn:
        conn.execute("DELETE FROM voice_clips WHERE profile_id=? AND step=? AND idx=?", (profile_id, step, idx))
        conn.execute(
            """INSERT INTO voice_clips(id,profile_id,step,idx,path,duration_s,quality_json,accepted)
               VALUES(?,?,?,?,?,?,?,1)""",
            (db.new_id(), profile_id, step, idx, str(path), duration,
             json.dumps(verdict, ensure_ascii=False)),
        )
    _touch(profile_id)
    return {"step": step, "idx": idx, "quality": verdict, "saved": True, "duration_s": round(duration, 2)}


def _touch(profile_id: str) -> None:
    with db.connect() as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(duration_s),0) AS s FROM voice_clips WHERE profile_id=? AND accepted=1",
            (profile_id,),
        ).fetchone()["s"]
        conn.execute("UPDATE voice_profiles SET minutes_recorded=? WHERE id=?",
                     (round(float(total) / 60, 2), profile_id))


def build_reference(profile_id: str) -> dict:
    """Собирает эталон голоса из лучших фрагментов записи.

    Приоритет — пение: для каверов важнее, как человек тянет ноты,
    чем как он читает текст.
    """
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM voice_clips WHERE profile_id=? AND accepted=1 ORDER BY step, idx",
            (profile_id,),
        ).fetchall()
    if not rows:
        raise AppError("E_BAD_REQUEST", "нет принятых записей", status=422,
                       message_ru="Сначала запишите хотя бы несколько фрагментов")

    def score(row) -> float:
        verdict = json.loads(row["quality_json"] or "{}")
        metrics = verdict.get("metrics", {})
        step_def = steps.get_step(row["step"]) or {}
        singing_bonus = 12.0 if step_def.get("kind") in steps.SINGING_KINDS else 0.0
        return float(metrics.get("snr_db", 0)) + singing_bonus

    ordered = sorted(rows, key=score, reverse=True)
    pieces: list[np.ndarray] = []
    total = 0.0
    for row in ordered:
        if total >= REFERENCE_MAX_S:
            break
        try:
            audio, sr = sf.read(row["path"], dtype="float32", always_2d=False)
        except (OSError, RuntimeError):
            continue
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        pieces.append(audio.astype(np.float32))
        total += len(audio) / sr

    if not pieces:
        raise AppError("E_INTERNAL", "не удалось прочитать записи", status=500)

    # Небольшая пауза между фрагментами, чтобы модель не слышала стыков.
    gap = np.zeros(int(0.15 * SR), dtype=np.float32)
    reference = np.concatenate([p for piece in pieces for p in (piece, gap)][:-1])
    reference = quality.normalize_peak(reference, target_db=-3.0)

    path = reference_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), reference, SR, subtype="PCM_16")

    duration = len(reference) / SR
    status = "ready" if duration >= REFERENCE_MIN_S else "recording"
    quality_summary = {
        "reference_s": round(duration, 1),
        "clips_used": len(pieces),
        "enough": duration >= REFERENCE_MIN_S,
    }
    with db.connect() as conn:
        conn.execute(
            "UPDATE voice_profiles SET status=?, model_path=?, quality_json=?, trained_at=? WHERE id=?",
            (status, str(path), json.dumps(quality_summary, ensure_ascii=False), db.now_iso(), profile_id),
        )
    return {**quality_summary, "status": status, "profile_id": profile_id}


def delete_profile(profile_id: str) -> None:
    """Удаляем профиль вместе с записями — голос приватен (ТЗ §20)."""
    import shutil

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM voice_profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise not_found("профиль голоса не найден")
        conn.execute("DELETE FROM voice_profiles WHERE id=?", (profile_id,))
    shutil.rmtree(profile_dir(profile_id), ignore_errors=True)
    reference_path(profile_id).unlink(missing_ok=True)
