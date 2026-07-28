"""Голос: мастер записи, профиль и проверка качества.

Записи и профиль остаются на компьютере — в облако не уходят (ТЗ §20).
"""

import numpy as np
from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..errors import AppError
from ..media import ffmpeg
from ..mixkit import SR
from ..voice import profile as voice_profile
from ..voice import quality, steps

router = APIRouter(prefix="/voice", tags=["voice"])

MAX_CLIP_BYTES = 40 * 1024 * 1024  # ~10 минут записи с запасом


@router.get("/steps")
def get_steps() -> dict:
    return {
        "steps": steps.STEPS,
        "total_clips": steps.TOTAL_CLIPS,
        "estimate_minutes": steps.estimate_minutes(),
    }


class CreateBody(BaseModel):
    name: str = "Мой голос"


@router.post("/profiles")
def create_profile(body: CreateBody | None = None) -> dict:
    return voice_profile.create_profile((body.name if body else None) or "Мой голос")


@router.get("/profiles")
def list_profiles() -> dict:
    return {"profiles": voice_profile.list_profiles(), "active": voice_profile.active_profile()}


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str) -> dict:
    return voice_profile.get_profile(profile_id)


@router.post("/profiles/{profile_id}/clip")
async def upload_clip(profile_id: str, request: Request, step: int = 0, idx: int = 0) -> dict:
    """Принимает запись как есть (браузер шлёт webm/opus) и оценивает качество."""
    voice_profile.get_profile(profile_id)  # 404, если профиля нет
    data = await request.body()
    if not data:
        raise AppError("E_BAD_REQUEST", "пустая запись", status=422)
    if len(data) > MAX_CLIP_BYTES:
        raise AppError("E_TOO_LONG", "запись слишком большая", status=413)

    raw = ffmpeg.decode_bytes_mono(data, SR)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return voice_profile.save_clip(profile_id, step, idx, audio, SR)


@router.post("/profiles/{profile_id}/finish")
def finish_profile(profile_id: str) -> dict:
    """Собирает эталон голоса из лучших фрагментов."""
    return voice_profile.build_reference(profile_id)


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str) -> dict:
    voice_profile.delete_profile(profile_id)
    return {"deleted": profile_id}


@router.post("/noise-check")
async def noise_check(request: Request) -> dict:
    """Шумомер до начала записи: насколько тихо в комнате."""
    data = await request.body()
    if not data:
        raise AppError("E_BAD_REQUEST", "пустая запись", status=422)
    raw = ffmpeg.decode_bytes_mono(data, SR)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return quality.measure_noise_floor(audio, SR)
