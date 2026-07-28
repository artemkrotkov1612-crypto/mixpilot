"""Настройки (whitelist-ключи) и сведения о хранилище."""

import json
import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from .. import config, db
from ..errors import AppError

router = APIRouter(tags=["settings"])

DEFAULTS: dict[str, object] = {
    "quality_mode": "fast",        # fast | max
    "cloud_enabled": True,         # понимание свободного текста через Claude API
    "learning_enabled": True,      # профиль вкуса
    "results_dir": "",             # пусто = renders внутри хранилища
}


@router.get("/settings")
def get_settings() -> dict:
    values = dict(DEFAULTS)
    with db.connect() as conn:
        rows = conn.execute("SELECT key, value_json FROM settings WHERE user_id=?", (db.LOCAL_USER,)).fetchall()
    for row in rows:
        if row["key"] in values:
            values[row["key"]] = json.loads(row["value_json"])
    return values


class PutBody(BaseModel):
    key: str
    value: object


@router.put("/settings")
def put_setting(body: PutBody) -> dict:
    if body.key not in DEFAULTS:
        raise AppError("E_BAD_REQUEST", f"неизвестный ключ настройки: {body.key}")
    if body.key == "quality_mode" and body.value not in ("fast", "max"):
        raise AppError("E_BAD_REQUEST", "quality_mode: fast или max")
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(user_id,key,value_json) VALUES(?,?,?)",
            (db.LOCAL_USER, body.key, json.dumps(body.value, ensure_ascii=False)),
        )
    return get_settings()


def _dir_size(path: Path) -> int:
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue
    return total


@router.get("/cloud")
def cloud() -> dict:
    """Готовность облачного понимания текста (ключ наружу не отдаём)."""
    from ..llm.provider import cloud_status

    return cloud_status()


@router.get("/storage")
def storage() -> dict:
    base = config.data_dir()
    usage = shutil.disk_usage(base if base.exists() else Path.home())
    return {
        "data_dir": str(base),
        "disk_total_gb": round(usage.total / 1024**3, 1),
        "disk_free_gb": round(usage.free / 1024**3, 1),
        "media_mb": round(_dir_size(base / "media") / 1024**2, 1),
        "cache_mb": round(_dir_size(base / "cache") / 1024**2, 1),
        "renders_mb": round(_dir_size(base / "renders") / 1024**2, 1),
        "models_mb": round(_dir_size(base / "models") / 1024**2, 1),
        "voice_mb": round(_dir_size(base / "voice") / 1024**2, 1),
        "tmp_mb": round(_dir_size(base / "tmp") / 1024**2, 1),
    }


# Что разрешено чистить. Оригиналы песен и записи голоса не трогаем никогда:
# первые пользователь загрузил сам, вторые нельзя восстановить (ТЗ §20).
CLEANABLE = {
    "cache": ("cache", "Разбор песен и дорожки", "Пересчитается при следующей генерации"),
    "tmp": ("tmp", "Временные файлы", "Мусор от прошлых запусков"),
    "models": ("models", "Веса моделей", "Скачаются заново при первом использовании"),
}


@router.get("/storage/cleanup")
def cleanup_options() -> dict:
    base = config.data_dir()
    items = []
    for key, (sub, title, note) in CLEANABLE.items():
        items.append({
            "key": key, "title_ru": title, "note_ru": note,
            "size_mb": round(_dir_size(base / sub) / 1024**2, 1),
        })
    return {"items": items}


class CleanupBody(BaseModel):
    keys: list[str]


@router.post("/storage/cleanup")
def cleanup(body: CleanupBody) -> dict:
    unknown = [k for k in body.keys if k not in CLEANABLE]
    if unknown:
        raise AppError("E_BAD_REQUEST", f"нельзя чистить: {', '.join(unknown)}")
    base = config.data_dir()
    freed = 0
    for key in body.keys:
        sub = CLEANABLE[key][0]
        freed += _dir_size(base / sub)
        shutil.rmtree(base / sub, ignore_errors=True)
    config.ensure_dirs()
    if "cache" in body.keys:
        # Записи о дорожках указывают на удалённые файлы — иначе воркер решит,
        # что стемы уже посчитаны, и упадёт на чтении. Разбор темпа и структуры
        # при этом оставляем: он лежит в самой базе и файлов не требует.
        with db.connect() as conn:
            conn.execute("DELETE FROM stems_cache")
    return {"freed_mb": round(freed / 1024**2, 1), **storage()}


@router.get("/taste")
def taste_profile() -> dict:
    from .. import taste

    return taste.get_profile()


@router.delete("/taste")
def taste_reset() -> dict:
    from .. import taste

    return taste.reset()
