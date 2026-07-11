"""Точка входа worker: системные эндпоинты + роутеры медиабазы (M1).

Очередь задач и пайплайны подключаются в M2+ согласно 01_DOCS/TZ.md.
"""

import logging
import os
import platform
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, config, db, log
from .errors import install_handlers
from .media import ffmpeg
from .routers import library, projects, settings

_started_at = time.monotonic()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    log.setup()
    db.init_db()
    # tmp чистится при старте: там только незавершённые операции прошлой сессии
    for leftover in config.tmp_dir().glob("*"):
        try:
            leftover.unlink()
        except OSError:
            pass
    logging.getLogger("mixpilot").info("worker started", extra={"ctx": {"data_dir": str(config.data_dir())}})
    yield


app = FastAPI(title="MixPilot Worker", version=__version__, lifespan=lifespan)

# Worker слушает только 127.0.0.1; origin'ы renderer'а — vite (dev) и file:// (prod, Origin: null).
# Токен-авторизация появится вместе с SaaS-режимом.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

install_handlers(app)
app.include_router(library.router)
app.include_router(projects.router)
app.include_router(settings.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/meta")
def meta() -> dict:
    return {
        "name": "mixpilot-worker",
        "version": __version__,
        "python": platform.python_version(),
        "pid": os.getpid(),
        "uptime_s": round(time.monotonic() - _started_at, 1),
        # GPU-детект появится в M2 вместе с torch — до этого честный null.
        "gpu": None,
        "ffmpeg": ffmpeg.available(),
        "data_dir": str(config.data_dir()),
    }


@app.post("/shutdown")
def shutdown() -> dict:
    """Грациозная остановка по запросу Electron main.

    Ответ уходит клиенту, после чего процесс завершается целиком —
    uvicorn на Windows не умеет мягкий self-stop без сигналов.
    """

    def _exit() -> None:
        time.sleep(0.2)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
    return {"status": "stopping"}
