"""Фикстуры: изолированное хранилище и синтетическое аудио (без чужих треков)."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mixpilot_worker import config


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient с MIXPILOT_DATA_DIR во временной папке (lifespan инициализирует БД)."""
    monkeypatch.setenv("MIXPILOT_DATA_DIR", str(tmp_path / "data"))
    from mixpilot_worker.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def ffmpeg_bin() -> str:
    ff, _probe = config.resolve_ffmpeg()
    if not ff:
        pytest.skip("ffmpeg недоступен — медиа-тесты пропущены")
    return ff


@pytest.fixture()
def sine_wav(tmp_path: Path, ffmpeg_bin: str) -> Path:
    """2-секундный синус 440 Гц, 44.1 кГц stereo — типовой «трек» для тестов."""
    out = tmp_path / "sine.wav"
    subprocess.run(
        [ffmpeg_bin, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-ar", "44100", "-ac", "2", str(out)],
        check=True, capture_output=True,
    )
    return out
