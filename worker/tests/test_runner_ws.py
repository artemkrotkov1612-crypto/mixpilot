"""Интеграция: runner исполняет задачи внутри lifespan, WS доставляет события."""

import json
import time

from mixpilot_worker.jobs import queue
from mixpilot_worker.jobs.runner import JobContext, register


@register("t_ok")
def _ok_handler(payload: dict, ctx: JobContext) -> dict:
    ctx.report("work", 0.5, human="Тестовая работа…")
    return {"echo": payload}


@register("t_slow")
def _slow_handler(payload: dict, ctx: JobContext) -> dict:
    for _ in range(200):  # ~10 c максимум; отмена придёт раньше
        ctx.check_cancelled()
        time.sleep(0.05)
    return {}


def _wait_status(client, job_id: str, statuses: set[str], timeout_s: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} не достиг {statuses}: {job}")


def test_runner_executes_and_ws_notifies(client):
    with client.websocket_connect("/ws") as ws:
        job = queue.enqueue("t_ok", {"hello": "мир"}, priority=10, gpu=False)
        events = []
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            msg = json.loads(json.dumps(ws.receive_json()))
            if msg.get("job_id") == job["id"]:
                events.append(msg)
                if msg["type"] in ("job.done", "job.error"):
                    break
        kinds = [e["type"] for e in events]
        assert kinds[-1] == "job.done", events
        done = events[-1]
        assert done["result"] == {"echo": {"hello": "мир"}}
        progress = [e for e in events if e["type"] == "job.progress"]
        assert any(e.get("human_ru") for e in progress)

    assert _wait_status(client, job["id"], {"done"})["progress"] == 1.0


def test_cancel_running_job(client):
    job = queue.enqueue("t_slow", {"n": 1}, priority=10, gpu=False)
    _wait_status(client, job["id"], {"running"})
    client.post(f"/jobs/{job['id']}/cancel")
    final = _wait_status(client, job["id"], {"cancelled"})
    assert final["status"] == "cancelled"


def test_jobs_listing(client):
    queue.enqueue("t_ok", {"n": "list"}, priority=10, gpu=False)
    res = client.get("/jobs", params={"limit": 10}).json()
    assert "jobs" in res and len(res["jobs"]) >= 1
