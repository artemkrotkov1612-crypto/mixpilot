"""Точка входа worker: системные эндпоинты + роутеры медиабазы (M1).

Очередь задач и пайплайны подключаются в M2+ согласно 01_DOCS/TZ.md.
"""

import asyncio
import logging
import os
import platform
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import __version__, config, db, gpu, log
from .errors import install_handlers
from .media import ffmpeg
from .routers import generations, library, processing, projects, settings

# Регистрация job-хендлеров (side effect декораторов @register).
from .analysis import run as _analysis_jobs  # noqa: F401
from .stems import separator as _stems_jobs  # noqa: F401
from .generate import pipeline as _generate_jobs  # noqa: F401
from .generate import edit as _edit_jobs  # noqa: F401
from .merge import run as _merge_jobs  # noqa: F401
from .jobs.progress import hub
from .jobs.runner import runner
from .jobs import queue as jobs_queue

_started_at = time.monotonic()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    log.setup()
    db.init_db()
    # Веса torch-моделей (demucs и др.) живут в нашем хранилище.
    os.environ.setdefault("TORCH_HOME", str(config.data_dir() / "models"))
    # tmp чистится при старте: там только незавершённые операции прошлой сессии
    for leftover in config.tmp_dir().glob("*"):
        try:
            leftover.unlink()
        except OSError:
            pass
    resumed = jobs_queue.reset_running_to_queued()
    hub.bind_loop(asyncio.get_running_loop())
    runner.start()
    logging.getLogger("mixpilot").info(
        "worker started",
        extra={"ctx": {"data_dir": str(config.data_dir()), "resumed_jobs": resumed}},
    )
    yield
    await runner.stop()


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
app.include_router(processing.router)
app.include_router(generations.router)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # ping-и клиента; сервер только шлёт события
    except WebSocketDisconnect:
        hub.disconnect(ws)


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
        # Имя GPU появляется после первой тяжёлой задачи (torch лениво).
        "gpu": gpu.gpu_name(),
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
