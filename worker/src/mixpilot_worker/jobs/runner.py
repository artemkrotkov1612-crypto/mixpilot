"""Исполнитель очереди: 1 GPU-слот + 2 CPU-слота, кооперативная отмена.

Хендлеры — синхронные функции (тяжёлые библиотеки), работают в executor;
прогресс возвращается через JobContext (троттлинг БД + WS-события).
"""

import asyncio
import logging
import threading
import time
from typing import Callable

from ..errors import AppError
from . import queue
from .progress import hub, human_ru

log = logging.getLogger("mixpilot.jobs")

CPU_SLOTS = 2
POLL_S = 0.25
DB_THROTTLE_S = 0.4


class JobCancelled(Exception):
    pass


class JobContext:
    def __init__(self, job_id: str, kind: str, cancel_event: threading.Event):
        self.job_id = job_id
        self.kind = kind
        self.cancel_event = cancel_event
        self._last_db_write = 0.0

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelled()

    def report(self, stage: str, pct: float, human: str | None = None) -> None:
        self.check_cancelled()
        now = time.monotonic()
        if now - self._last_db_write >= DB_THROTTLE_S:
            queue.update_progress(self.job_id, stage, pct)
            self._last_db_write = now
        hub.emit({
            "type": "job.progress",
            "job_id": self.job_id,
            "kind": self.kind,
            "stage": stage,
            "human_ru": human or human_ru(self.kind, stage),
            "pct": round(max(0.0, min(1.0, pct)), 3),
        })


Handler = Callable[[dict, JobContext], dict]
_HANDLERS: dict[str, Handler] = {}


def register(kind: str):
    def deco(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return deco


class Runner:
    def __init__(self) -> None:
        self._gpu_busy = False
        self._cpu_running = 0
        # _stop создаётся в start(): asyncio.Event привязывается к текущему loop,
        # а на каждый запуск worker'а (и каждый TestClient) — свой event loop.
        self._stop: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._stop = asyncio.Event()
        self._gpu_busy = False
        self._cpu_running = 0
        self._task = asyncio.create_task(self._loop(), name="jobs-runner")

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            await asyncio.wait([self._task], timeout=3)

    async def _loop(self) -> None:
        log.info("runner started")
        while not self._stop.is_set():
            job = None
            if not self._gpu_busy:
                job = queue.claim_next(gpu=True)
            if job is None and self._cpu_running < CPU_SLOTS:
                job = queue.claim_next(gpu=False)
            if job is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=POLL_S)
                except TimeoutError:
                    pass
                continue
            if job["gpu"]:
                self._gpu_busy = True
            else:
                self._cpu_running += 1
            asyncio.create_task(self._run(job))
        log.info("runner stopped")

    async def _run(self, job: dict) -> None:
        job_id, kind = job["id"], job["kind"]
        cancel_event = queue.cancel_event_for(job_id)
        ctx = JobContext(job_id, kind, cancel_event)
        handler = _HANDLERS.get(kind)
        try:
            if handler is None:
                raise AppError("E_INTERNAL", f"нет обработчика задачи '{kind}'", status=500)
            queue.set_status(job_id, "running", started=True)
            hub.emit({"type": "job.progress", "job_id": job_id, "kind": kind,
                      "stage": "start", "human_ru": human_ru(kind, "start"), "pct": 0.0})
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, handler, job["payload"], ctx)
            queue.set_status(job_id, "done")
            hub.emit({"type": "job.done", "job_id": job_id, "kind": kind, "result": result})
            log.info("job done", extra={"ctx": {"job": job_id, "kind": kind}})
        except JobCancelled:
            queue.set_status(job_id, "cancelled")
            hub.emit({"type": "job.error", "job_id": job_id, "kind": kind,
                      "code": "E_CANCELLED", "message_ru": "Отменено. Черновик сохранён"})
            log.info("job cancelled", extra={"ctx": {"job": job_id, "kind": kind}})
        except AppError as err:
            queue.set_status(job_id, "error", error_code=err.code, error_detail=err.detail)
            hub.emit({"type": "job.error", "job_id": job_id, "kind": kind,
                      "code": err.code, "message_ru": err.message_ru})
            log.warning("job failed: %s %s", err.code, err.detail,
                        extra={"ctx": {"job": job_id, "kind": kind}})
        except Exception as err:  # noqa: BLE001 — граница исполнителя
            queue.set_status(job_id, "error", error_code="E_INTERNAL",
                             error_detail=f"{type(err).__name__}: {err}")
            hub.emit({"type": "job.error", "job_id": job_id, "kind": kind,
                      "code": "E_INTERNAL", "message_ru": "Внутренняя ошибка. Подробности в журнале"})
            log.exception("job crashed", extra={"ctx": {"job": job_id, "kind": kind}})
        finally:
            queue.drop_cancel_event(job_id)
            if job["gpu"]:
                self._gpu_busy = False
            else:
                self._cpu_running -= 1


runner = Runner()
