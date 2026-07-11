"""Юниты очереди: дедупликация, приоритеты, отмена, ресюм (без runner'а)."""

import pytest

from mixpilot_worker import config, db
from mixpilot_worker.jobs import queue


@pytest.fixture()
def data_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MIXPILOT_DATA_DIR", str(tmp_path / "data"))
    config.ensure_dirs()
    db.init_db()


def test_enqueue_dedupe(data_env):
    a = queue.enqueue("analyze", {"track_id": "t1"}, priority=20, gpu=False)
    b = queue.enqueue("analyze", {"track_id": "t1"}, priority=20, gpu=False)
    c = queue.enqueue("analyze", {"track_id": "t2"}, priority=20, gpu=False)
    assert a["id"] == b["id"]
    assert c["id"] != a["id"]
    assert a["status"] == "queued" and a["payload"] == {"track_id": "t1"}


def test_priority_order(data_env):
    low = queue.enqueue("generate", {"n": 1}, priority=50, gpu=True)
    high = queue.enqueue("stems", {"n": 2}, priority=40, gpu=True)
    cpu = queue.enqueue("analyze", {"n": 3}, priority=20, gpu=False)

    first_gpu = queue.claim_next(gpu=True)
    assert first_gpu["id"] == high["id"]
    first_cpu = queue.claim_next(gpu=False)
    assert first_cpu["id"] == cpu["id"]
    assert queue.get_job(low["id"])["status"] == "queued"


def test_cancel_queued_and_running(data_env):
    job = queue.enqueue("analyze", {"x": 1}, priority=20, gpu=False)
    cancelled = queue.request_cancel(job["id"])
    assert cancelled["status"] == "cancelled"

    running = queue.enqueue("analyze", {"x": 2}, priority=20, gpu=False)
    queue.set_status(running["id"], "running", started=True)
    after = queue.request_cancel(running["id"])
    assert after["status"] == "running"  # статус сменит сам хендлер
    assert queue.cancel_event_for(running["id"]).is_set()


def test_reset_running_to_queued(data_env):
    job = queue.enqueue("stems", {"y": 1}, priority=40, gpu=True)
    queue.set_status(job["id"], "running", started=True)
    assert queue.reset_running_to_queued() == 1
    assert queue.get_job(job["id"])["status"] == "queued"


def test_terminal_states(data_env):
    job = queue.enqueue("analyze", {"z": 1}, priority=20, gpu=False)
    queue.set_status(job["id"], "running", started=True)
    queue.update_progress(job["id"], "tempo", 0.4)
    mid = queue.get_job(job["id"])
    assert mid["stage"] == "tempo" and 0.39 < mid["progress"] < 0.41

    queue.set_status(job["id"], "error", error_code="E_VRAM", error_detail="oom")
    done = queue.get_job(job["id"])
    assert done["status"] == "error" and done["error_code"] == "E_VRAM"
    assert done["finished_at"] is not None
