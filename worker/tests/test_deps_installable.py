"""Зависимости должны ставиться на машине без инструментов разработчика.

Проверка появилась после реального блокера: demucs был подключён как
git-зависимость, и на чистой Windows первый запуск падал с «Git executable
not found» — движок не устанавливался вообще ни у кого, кроме разработчика.
На машине разработчика это невидимо: Git там есть всегда.
"""

import re
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parent.parent
LOCK = WORKER / "uv.lock"


@pytest.fixture(scope="module")
def lock_text() -> str:
    if not LOCK.exists():
        pytest.skip("uv.lock недоступен")
    return LOCK.read_text(encoding="utf-8")


def test_no_git_dependencies(lock_text):
    """git-источник требует Git у пользователя — установщик его не несёт."""
    git_sources = re.findall(r'name = "([^"]+)"\nversion = [^\n]+\nsource = \{ git', lock_text)
    assert not git_sources, (
        "git-зависимости ставятся только там, где установлен Git: "
        f"{', '.join(git_sources)}. Соберите колесо (scripts\\build-demucs-wheel.cmd "
        "как образец) и укажите его в [tool.uv.sources]."
    )


def test_demucs_comes_from_local_wheel(lock_text):
    """Нужен коммит с demucs.api, но принести его должен установщик, а не Git."""
    entry = re.search(r'name = "demucs"\nversion = ([^\n]+)\nsource = \{ ([^}]+)\}', lock_text)
    assert entry, "demucs пропал из блокировки"
    source = entry.group(2)
    assert "path = " in source and ".whl" in source, f"demucs берётся не из колеса: {source}"


def test_wheel_file_is_present():
    wheels = WORKER / "wheels"
    assert wheels.is_dir(), "нет папки worker/wheels"
    found = list(wheels.glob("demucs-*.whl"))
    assert found, "нет колеса demucs — соберите scripts\\build-demucs-wheel.cmd"
    assert found[0].stat().st_size > 10_000, "колесо подозрительно маленькое"


def test_demucs_api_is_importable():
    """Ради этого и нужен нестабильный коммит: в 4.0.1 с PyPI api нет."""
    demucs_api = pytest.importorskip("demucs.api")
    assert hasattr(demucs_api, "Separator")


def test_demucs_model_configs_shipped():
    """Колесо должно нести описания моделей — без них разделение не запустится."""
    demucs = pytest.importorskip("demucs")
    remote = Path(demucs.__file__).parent / "remote"
    assert (remote / "htdemucs.yaml").exists(), "в колесе нет описаний моделей demucs"
