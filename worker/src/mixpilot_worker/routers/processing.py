"""Анализ, стемы и очередь задач: REST-поверхность (WS — в main)."""

from fastapi import APIRouter
from pydantic import BaseModel

from ..analysis.run import get_analysis
from ..errors import AppError, not_found
from ..jobs import queue
from ..stems.separator import stems_status

router = APIRouter(tags=["processing"])


class StartBody(BaseModel):
    quality: str = "fast"


@router.post("/analysis/{track_id}")
def start_analysis(track_id: str, _body: StartBody | None = None) -> dict:
    existing = get_analysis(track_id)
    if existing is not None:
        return {"status": "ready", "analysis": existing}
    job = queue.enqueue("analyze", {"track_id": track_id}, priority=queue.PRIORITY["analyze"], gpu=False)
    return {"status": "queued", "job": job}


@router.get("/analysis/{track_id}")
def read_analysis(track_id: str) -> dict:
    analysis = get_analysis(track_id)
    if analysis is None:
        raise not_found("анализ ещё не выполнялся")
    return analysis


@router.post("/stems/{track_id}")
def start_stems(track_id: str, body: StartBody | None = None) -> dict:
    quality = (body.quality if body else "fast")
    if quality not in ("fast", "max"):
        raise AppError("E_BAD_REQUEST", "quality: fast или max")
    if stems_status(track_id).get(quality):
        return {"status": "ready"}
    job = queue.enqueue(
        "stems", {"quality": quality, "track_id": track_id},
        priority=queue.PRIORITY["stems"], gpu=True,
    )
    return {"status": "queued", "job": job}


@router.get("/stems/{track_id}")
def read_stems_status(track_id: str) -> dict:
    return stems_status(track_id)


@router.get("/jobs")
def jobs_list(active: bool = False, limit: int = 50) -> dict:
    return {"jobs": queue.list_jobs(active_only=active, limit=limit)}


@router.get("/jobs/{job_id}")
def job_get(job_id: str) -> dict:
    job = queue.get_job(job_id)
    if job is None:
        raise not_found("задача не найдена")
    return job


@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str) -> dict:
    return queue.request_cancel(job_id)
