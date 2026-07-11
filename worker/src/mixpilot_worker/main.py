"""Точка входа worker: /health, /meta, /shutdown.

Модули пайплайнов (media, analysis, stems, …) подключаются в M1+
согласно 01_DOCS/TZ.md проекта PRJ-2026-005.
"""

import os
import platform
import threading
import time

from fastapi import FastAPI

from . import __version__

app = FastAPI(title="MixPilot Worker", version=__version__)

_started_at = time.monotonic()


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
