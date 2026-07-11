"""Персистентная очередь на таблице jobs: приоритеты, дедупликация, ресюм.

Приоритеты (меньше — важнее): интерактив 10, анализ 20, стемы 40,
генерация 50, обучение голоса 90 (ТЗ §9).
"""

import json
import threading

from .. import db

PRIORITY = {"interactive": 10, "analyze": 20, "stems": 40, "generate": 50, "train": 90}

ACTIVE_STATUSES = ("queued", "running")

# Кооперативная отмена running-задач: job_id -> Event (живёт только в памяти процесса).
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()


def cancel_event_for(job_id: str) -> threading.Event:
    with _cancel_lock:
        return _cancel_events.setdefault(job_id, threading.Event())


def drop_cancel_event(job_id: str) -> None:
    with _cancel_lock:
        _cancel_events.pop(job_id, None)


def _row(job) -> dict:
    d = dict(job)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    d["gpu"] = bool(d["gpu"])
    return d


def enqueue(kind: str, payload: dict, priority: int, gpu: bool) -> dict:
    """Ставит задачу; идентичная активная задача не дублируется."""
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with db.connect() as conn:
        existing = conn.execute(
            "SELECT * FROM jobs WHERE kind=? AND payload_json=? AND status IN (?,?)",
            (kind, payload_json, *ACTIVE_STATUSES),
        ).fetchone()
        if existing is not None:
            return _row(existing)
        job = {
            "id": db.new_id(),
            "kind": kind,
            "payload_json": payload_json,
            "status": "queued",
            "priority": priority,
            "progress": 0.0,
            "stage": None,
            "error_code": None,
            "error_detail": None,
            "created_at": db.now_iso(),
            "started_at": None,
            "finished_at": None,
            "gpu": int(gpu),
        }
        conn.execute(
            """INSERT INTO jobs(id,kind,payload_json,status,priority,progress,stage,
                                error_code,error_detail,created_at,started_at,finished_at,gpu)
               VALUES(:id,:kind,:payload_json,:status,:priority,:progress,:stage,
                      :error_code,:error_detail,:created_at,:started_at,:finished_at,:gpu)""",
            job,
        )
        return _row(conn.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone())


def get_job(job_id: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _row(row) if row else None


def list_jobs(active_only: bool = False, limit: int = 50) -> list[dict]:
    where = "WHERE status IN ('queued','running')" if active_only else ""
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ?", (min(limit, 200),)
        ).fetchall()
    return [_row(r) for r in rows]


def claim_next(gpu: bool) -> dict | None:
    """Лучшая queued-задача нужной категории (клеймит один runner-цикл)."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' AND gpu=? "
            "ORDER BY priority ASC, created_at ASC LIMIT 1",
            (int(gpu),),
        ).fetchone()
    return _row(row) if row else None


def request_cancel(job_id: str) -> dict:
    from ..errors import not_found

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise not_found("задача не найдена")
        if row["status"] == "queued":
            conn.execute(
                "UPDATE jobs SET status='cancelled', finished_at=? WHERE id=?",
                (db.now_iso(), job_id),
            )
        elif row["status"] == "running":
            cancel_event_for(job_id).set()  # хендлер увидит на ближайшем чекпоинте
        updated = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _row(updated)


def set_status(job_id: str, status: str, *, error_code: str | None = None,
               error_detail: str | None = None, started: bool = False) -> None:
    sets = ["status=?"]
    params: list = [status]
    if started:
        sets.append("started_at=?")
        params.append(db.now_iso())
    if status in ("done", "error", "cancelled"):
        sets.append("finished_at=?")
        params.append(db.now_iso())
        sets.append("progress=?")
        params.append(1.0 if status == "done" else 0.0)
    if error_code is not None:
        sets += ["error_code=?", "error_detail=?"]
        params += [error_code, (error_detail or "")[:2000]]
    params.append(job_id)
    with db.connect() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", params)


def update_progress(job_id: str, stage: str, pct: float) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET stage=?, progress=? WHERE id=? AND status='running'",
            (stage, max(0.0, min(1.0, pct)), job_id),
        )


def reset_running_to_queued() -> int:
    """Ресюм при старте: подвисшие running возвращаем в очередь (стадии идемпотентны по кешу)."""
    with db.connect() as conn:
        cur = conn.execute("UPDATE jobs SET status='queued', stage=NULL WHERE status='running'")
        return cur.rowcount
