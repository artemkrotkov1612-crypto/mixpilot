"""Конверсия голоса: адаптер поверх seed-vc.

Бизнес-код зовёт convert_voice() и не знает, какая модель внутри —
её можно заменить, не трогая пайплайны (ТЗ §5, адаптеры моделей).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

from .. import config, gpu
from ..errors import AppError

log = logging.getLogger("mixpilot.voice")

# Модель тяжёлая: держим одну на процесс, выгружаем после блока задач.
_wrapper = None
_compat_applied = False


def _apply_compat() -> None:
    """Совместимость BigVGAN со свежим huggingface_hub.

    BigVGAN написан под старый hub, который передавал `proxies` и
    `resume_download`; в hub 1.x их больше нет, и загрузка падает с
    TypeError. Понизить hub нельзя — от него зависит transformers 5.
    """
    global _compat_applied
    if _compat_applied:
        return
    try:
        from seed_vc.modules.bigvgan import bigvgan

        original = bigvgan.BigVGAN._from_pretrained.__func__

        def patched(cls, **kwargs):
            kwargs.setdefault("proxies", None)
            kwargs.setdefault("resume_download", None)
            return original(cls, **kwargs)

        bigvgan.BigVGAN._from_pretrained = classmethod(patched)
        log.info("bigvgan compat applied")
    except Exception:  # noqa: BLE001 — совместимость не должна ронять импорт
        log.warning("не удалось применить совместимость bigvgan", exc_info=True)
    _redirect_seed_vc_cache()
    _compat_applied = True


def _redirect_seed_vc_cache() -> None:
    """Веса seed-vc — в хранилище приложения, а не в текущей папке.

    seed_vc.hf_utils жёстко передаёт `cache_dir="./checkpoints"`, то есть
    пишет туда, откуда запущен процесс. У установленного приложения это
    может быть Program Files — папка только для чтения, и голос молча не
    заработает. Плюс HF_HOME такой аргумент не перебивает.
    """
    try:
        from huggingface_hub import hf_hub_download
        from seed_vc import hf_utils

        cache = str(config.data_dir() / "models" / "seed-vc")

        def load(repo_id, model_filename="pytorch_model.bin", config_filename=None):
            model_path = hf_hub_download(repo_id=repo_id, filename=model_filename, cache_dir=cache)
            if config_filename is None:
                return model_path
            return model_path, hf_hub_download(
                repo_id=repo_id, filename=config_filename, cache_dir=cache
            )

        hf_utils.load_custom_model_from_hf = load
        # app_vc импортирует функцию по имени — подменяем и там, если он уже загружен.
        for name in ("seed_vc.app_vc", "seed_vc.seed_vc_wrapper"):
            module = sys.modules.get(name)
            if module is not None and hasattr(module, "load_custom_model_from_hf"):
                module.load_custom_model_from_hf = load
        log.info("seed-vc cache -> %s", cache)
    except Exception:  # noqa: BLE001 — совместимость не должна ронять импорт
        log.warning("не удалось перенаправить кеш seed-vc", exc_info=True)


def _hf_home() -> str:
    """Веса моделей — в хранилище приложения, а не в профиле пользователя."""
    path = config.data_dir() / "models" / "hf"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _get_wrapper():
    global _wrapper
    if _wrapper is not None:
        return _wrapper
    os.environ.setdefault("HF_HOME", _hf_home())
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    _apply_compat()
    try:
        from seed_vc.seed_vc_wrapper import SeedVCWrapper

        _wrapper = SeedVCWrapper()
    except Exception as exc:  # noqa: BLE001 — граница внешней модели
        raise AppError(
            "E_MODEL_MISSING", f"{type(exc).__name__}: {exc}"[:400], status=500,
            message_ru="Не удалось загрузить голосовой компонент — проверьте подключение к интернету",
        ) from exc
    return _wrapper


def unload() -> None:
    """Освобождаем VRAM после работы с голосом."""
    global _wrapper
    _wrapper = None


def _write_temp(audio: np.ndarray, sr: int, name: str) -> str:
    tmp = config.tmp_dir()
    tmp.mkdir(parents=True, exist_ok=True)
    path = tempfile.NamedTemporaryFile(suffix=f"-{name}.wav", dir=str(tmp), delete=False).name
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    sf.write(path, np.asarray(mono, dtype=np.float32), sr, subtype="PCM_16")
    return path


def _unwrap_result(result) -> np.ndarray:
    """Достаём аудио из ответа seed-vc.

    convert_voice — генератор: при stream_output=False он ничего не yield-ит,
    а возвращает массив через `return`, то есть в StopIteration.value.
    """
    if hasattr(result, "__next__"):
        last_yield = None
        try:
            while True:
                last_yield = next(result)
        except StopIteration as stop:
            result = stop.value if stop.value is not None else last_yield

    if isinstance(result, np.ndarray):
        return result
    if isinstance(result, tuple):
        for part in reversed(result):
            if isinstance(part, np.ndarray):
                return part
    raise AppError("E_INTERNAL", f"неожиданный формат результата: {type(result)}", status=500)


def convert_voice(
    source: np.ndarray,
    source_sr: int,
    reference_path: str,
    *,
    quality: str = "fast",
    pitch_shift: int = 0,
    singing: bool = True,
) -> tuple[np.ndarray, int]:
    """Перекладывает исполнение source на голос из reference_path.

    singing=True сохраняет мелодию — обязательно для каверов.
    Возвращает (моно float32, частота дискретизации).
    """
    if not os.path.exists(reference_path):
        raise AppError("E_BAD_REQUEST", "нет эталона голоса", status=422,
                       message_ru="Сначала создайте свой голос")

    src_path = _write_temp(source, source_sr, "source")
    # Больше шагов — чище звук, но дольше; «Максимум» заметно лучше на пении.
    steps_count = 25 if quality == "max" else 10

    try:
        with gpu.gpu_session("seed-vc"):
            wrapper = _get_wrapper()
            result = wrapper.convert_voice(
                source=src_path,
                target=reference_path,
                diffusion_steps=steps_count,
                f0_condition=singing,
                auto_f0_adjust=True,
                pitch_shift=pitch_shift,
                stream_output=False,
            )
            audio = _unwrap_result(result)
            # seed-vc отдаёт 44.1 кГц в режиме пения (f0) и 22.05 кГц иначе.
            rate = 44100 if singing else 22050
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        if gpu.is_oom(exc):
            raise AppError("E_VRAM", str(exc)[:300], status=507) from exc
        raise AppError("E_INTERNAL", f"конверсия голоса: {type(exc).__name__}: {exc}"[:400],
                       status=500) from exc
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    # Модель иногда отдаёт int16-подобный масштаб — нормализуем к float32 [-1, 1].
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 1.5:
        audio = audio / 32768.0
    return audio, int(rate)
