"""Смоук-тесты HTTP-поверхности worker.

Внимание: /shutdown здесь не вызываем — он завершает процесс pytest.
"""

from fastapi.testclient import TestClient

from mixpilot_worker import __version__
from mixpilot_worker.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta() -> None:
    response = client.get("/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "mixpilot-worker"
    assert body["version"] == __version__
    assert body["pid"] > 0
    assert "python" in body
    # Имя видеокарты появляется только после того, как что-то подтянуло torch:
    # до первой тяжёлой задачи здесь None. Проверяем контракт поля, а не
    # порядок импортов — иначе тест ломается от соседнего теста в прогоне.
    assert body["gpu"] is None or isinstance(body["gpu"], str) and body["gpu"]
