"""Полный цикл мастера голоса через API: профиль → записи → эталон."""

import io
import wave

import numpy as np
import pytest

SR = 44100


def wav_bytes(audio: np.ndarray, sr: int = SR) -> bytes:
    """WAV в память — ровно то, что присылает интерфейс (ffmpeg читает любой формат)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def speech(seconds=3.0, level=0.15, noise=0.0005, sr=SR) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    envelope = (np.sin(2 * np.pi * 3 * t) > -0.2).astype(np.float32)
    tone = np.sin(2 * np.pi * 180 * t) * 0.6 + np.sin(2 * np.pi * 360 * t) * 0.4
    rng = np.random.default_rng(11)
    return ((tone * envelope * level) + rng.standard_normal(t.size) * noise).astype(np.float32)


@pytest.fixture()
def profile(client):
    if not _ffmpeg_ready():
        pytest.skip("ffmpeg недоступен")
    return client.post("/voice/profiles", json={"name": "Мой голос"}).json()


def _ffmpeg_ready() -> bool:
    from mixpilot_worker import config

    return bool(config.resolve_ffmpeg()[0])


def test_steps_are_described_for_human(client):
    data = client.get("/voice/steps").json()
    assert len(data["steps"]) == 8
    assert data["steps"][0]["kind"] == "noise"
    assert data["estimate_minutes"] > 0
    for step in data["steps"]:
        assert step["title_ru"] and step["instruction_ru"]


def test_create_and_get_profile(client, profile):
    assert profile["status"] == "recording"
    assert profile["recorded_clips"] == 0
    fetched = client.get(f"/voice/profiles/{profile['id']}").json()
    assert fetched["id"] == profile["id"]


def test_good_clip_is_saved(client, profile):
    res = client.post(
        f"/voice/profiles/{profile['id']}/clip",
        params={"step": 1, "idx": 0},
        content=wav_bytes(speech()),
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    assert res["saved"] is True
    assert res["quality"]["level"] in ("great", "ok")
    assert client.get(f"/voice/profiles/{profile['id']}").json()["recorded_clips"] == 1


def test_bad_clip_is_not_saved(client, profile):
    silence = np.zeros(int(SR * 2), dtype=np.float32)
    res = client.post(
        f"/voice/profiles/{profile['id']}/clip",
        params={"step": 1, "idx": 0},
        content=wav_bytes(silence),
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    assert res["saved"] is False
    assert res["quality"]["accepted"] is False
    # плохая запись не попала в датасет
    assert client.get(f"/voice/profiles/{profile['id']}").json()["recorded_clips"] == 0


def test_reretake_replaces_clip(client, profile):
    for _ in range(2):
        client.post(
            f"/voice/profiles/{profile['id']}/clip",
            params={"step": 1, "idx": 0},
            content=wav_bytes(speech()),
            headers={"Content-Type": "application/octet-stream"},
        )
    # перезапись того же фрагмента не создаёт дубликат
    assert client.get(f"/voice/profiles/{profile['id']}").json()["recorded_clips"] == 1


def test_noise_step_reports_room(client, profile):
    rng = np.random.default_rng(3)
    quiet = (rng.standard_normal(int(SR * 2)) * 0.0006).astype(np.float32)
    res = client.post(
        f"/voice/profiles/{profile['id']}/clip",
        params={"step": 0, "idx": 0},
        content=wav_bytes(quiet),
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    assert res["saved"] is False  # шумомер не часть датасета
    assert res["quality"]["level"] == "great"


def test_finish_builds_reference(client, profile):
    # записываем несколько фрагментов, включая «пение»
    for step, idx in [(1, 0), (1, 1), (2, 0), (5, 0), (7, 0)]:
        client.post(
            f"/voice/profiles/{profile['id']}/clip",
            params={"step": step, "idx": idx},
            content=wav_bytes(speech(seconds=4.0)),
            headers={"Content-Type": "application/octet-stream"},
        )
    res = client.post(f"/voice/profiles/{profile['id']}/finish").json()
    assert res["enough"] is True
    assert res["status"] == "ready"
    assert res["clips_used"] >= 3

    listing = client.get("/voice/profiles").json()
    assert listing["active"] is not None
    assert listing["active"]["id"] == profile["id"]


def test_finish_without_clips_is_rejected(client, profile):
    res = client.post(f"/voice/profiles/{profile['id']}/finish")
    assert res.status_code == 422
    assert "запишите" in res.json()["error"]["message_ru"].lower()


def test_delete_profile_removes_recordings(client, profile):
    from pathlib import Path

    client.post(
        f"/voice/profiles/{profile['id']}/clip",
        params={"step": 1, "idx": 0},
        content=wav_bytes(speech()),
        headers={"Content-Type": "application/octet-stream"},
    )
    from mixpilot_worker.voice.profile import profile_dir

    dataset = Path(profile_dir(profile["id"]))
    assert any(dataset.glob("*.wav"))

    client.delete(f"/voice/profiles/{profile['id']}")
    assert client.get(f"/voice/profiles/{profile['id']}").status_code == 404
    assert not dataset.exists() or not any(dataset.glob("*.wav"))
