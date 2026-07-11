"""Demucs v4 через demucs.api: GPU-сессия, прогресс, OOM-даунгрейд сегмента.

Веса скачиваются самим demucs при первом использовании в TORCH_HOME
(наше хранилище models/), см. lifespan в main.py.
"""

import logging
from pathlib import Path

from .. import gpu
from ..errors import AppError
from ..jobs.runner import JobCancelled, JobContext

log = logging.getLogger("mixpilot.stems")

# Попытки: сегмент по умолчанию модели → укороченный при нехватке VRAM.
SEGMENT_ATTEMPTS: tuple[int | None, ...] = (None, 4)


def _progress_callback(ctx: JobContext):
    def cb(info: dict) -> None:
        # Отмена проверяется прямо в цикле инференса demucs.
        if ctx.cancel_event.is_set():
            raise JobCancelled()
        try:
            models = max(int(info.get("models", 1)), 1)
            model_idx = int(info.get("model_idx_in_bag", 0))
            length = max(int(info.get("audio_length", 1)), 1)
            offset = int(info.get("segment_offset", 0))
            state_bonus = 1.0 if info.get("state") == "end" else 0.0
            inner = min((offset + state_bonus) / length, 1.0)
            pct = 0.1 + 0.8 * (model_idx + inner) / models
            ctx.report("separate", pct)
        except JobCancelled:
            raise
        except Exception:  # прогресс не должен ронять инференс
            pass

    return cb


def separate(src_path: str, out_dir: Path, model_name: str, ctx: JobContext) -> dict[str, Path]:
    import soundfile as sf
    import torch
    from demucs.api import Separator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        log.warning("CUDA недоступна — разделение на CPU будет в разы медленнее")

    ctx.report("load", 0.02)
    last_oom: Exception | None = None
    for attempt, segment in enumerate(SEGMENT_ATTEMPTS):
        try:
            with gpu.gpu_session("demucs"):
                kwargs: dict = {"model": model_name, "device": device,
                                "callback": _progress_callback(ctx)}
                if segment is not None:
                    kwargs["segment"] = segment
                separator = Separator(**kwargs)
                ctx.report("separate", 0.1)
                _origin, stems = separator.separate_audio_file(Path(src_path))
                samplerate = separator.samplerate

                ctx.report("save", 0.92)
                paths: dict[str, Path] = {}
                for name, tensor in stems.items():
                    path = out_dir / f"{name}.wav"
                    sf.write(str(path), tensor.cpu().numpy().T, samplerate, subtype="FLOAT")
                    paths[name] = path
                return paths
        except JobCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 — анализируем на OOM
            if gpu.is_oom(exc):
                last_oom = exc
                log.warning("VRAM OOM на попытке %d (segment=%s) — даунгрейд", attempt + 1, segment)
                continue
            raise AppError("E_INTERNAL", f"demucs: {type(exc).__name__}: {exc}", status=500) from exc

    raise AppError("E_VRAM", f"не хватило видеопамяти даже с segment=4: {last_oom}", status=507)
