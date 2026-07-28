"""Веса голосовой модели должны лежать в хранилище приложения.

seed-vc жёстко пишет их в «./checkpoints» — рядом с рабочей папкой процесса.
У установленного приложения это Program Files (только чтение), а в разработке —
корень репозитория. Проверяем, что подмена работает и путь ведёт в данные.
"""

import sys
import types

import pytest

from mixpilot_worker import config
from mixpilot_worker.voice import convert


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Тесты не должны заглядывать в настоящее хранилище пользователя."""
    monkeypatch.setenv("MIXPILOT_DATA_DIR", str(tmp_path / "data"))


def _fake_seed_vc(monkeypatch):
    """Подставляем модули seed_vc: настоящие тянут torch и веса на гигабайты."""
    hf_utils = types.ModuleType("seed_vc.hf_utils")
    hf_utils.load_custom_model_from_hf = lambda *a, **kw: "./checkpoints/original"
    package = types.ModuleType("seed_vc")
    package.hf_utils = hf_utils
    monkeypatch.setitem(sys.modules, "seed_vc", package)
    monkeypatch.setitem(sys.modules, "seed_vc.hf_utils", hf_utils)
    return hf_utils


def _capture_downloads(monkeypatch) -> list[dict]:
    import huggingface_hub as hub

    calls: list[dict] = []

    def fake_download(repo_id, filename, cache_dir=None, **kw):
        calls.append({"repo_id": repo_id, "filename": filename, "cache_dir": cache_dir})
        return f"{cache_dir}/{filename}"

    monkeypatch.setattr(hub, "hf_hub_download", fake_download)
    return calls


def test_weights_go_to_app_storage(monkeypatch):
    hf_utils = _fake_seed_vc(monkeypatch)
    calls = _capture_downloads(monkeypatch)

    convert._redirect_seed_vc_cache()
    hf_utils.load_custom_model_from_hf("Plachta/Seed-VC", "model.pth")

    assert len(calls) == 1
    cache_dir = calls[0]["cache_dir"]
    assert str(config.data_dir()) in cache_dir
    assert "checkpoints" not in cache_dir


def test_config_file_uses_same_cache(monkeypatch):
    """Вариант с конфигом возвращает пару путей — оба в хранилище."""
    hf_utils = _fake_seed_vc(monkeypatch)
    calls = _capture_downloads(monkeypatch)

    convert._redirect_seed_vc_cache()
    model_path, config_path = hf_utils.load_custom_model_from_hf(
        "Plachta/Seed-VC", "model.pth", "config.yml"
    )

    assert len(calls) == 2
    assert calls[0]["cache_dir"] == calls[1]["cache_dir"]
    assert str(config.data_dir()) in model_path
    assert str(config.data_dir()) in config_path


def test_already_imported_modules_get_patched(monkeypatch):
    """app_vc берёт функцию по имени при импорте — если он уже загружен,
    замена в hf_utils его не касается, поэтому правим и его тоже."""
    _fake_seed_vc(monkeypatch)
    _capture_downloads(monkeypatch)
    app_vc = types.ModuleType("seed_vc.app_vc")
    app_vc.load_custom_model_from_hf = lambda *a, **kw: "./checkpoints/original"
    monkeypatch.setitem(sys.modules, "seed_vc.app_vc", app_vc)

    convert._redirect_seed_vc_cache()

    assert app_vc.load_custom_model_from_hf("Plachta/Seed-VC", "model.pth").startswith(
        str(config.data_dir())
    )


def test_missing_seed_vc_does_not_crash(monkeypatch):
    """Без установленного seed-vc импорт воркера обязан пережить подмену."""
    monkeypatch.setitem(sys.modules, "seed_vc", None)
    convert._redirect_seed_vc_cache()  # не должно бросить
