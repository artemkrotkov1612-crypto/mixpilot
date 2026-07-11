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
    }
