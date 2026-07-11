"""GPU-дисциплина: один жилец VRAM, уборка после себя (ТЗ §5).

torch импортируется лениво — /health и /meta не должны платить 3-5 секунд
за его загрузку. Слот GPU обеспечивает очередь; лок здесь — страховка.
"""

import gc
import logging
import sys
import threading
from contextlib import contextmanager

log = logging.getLogger("mixpilot.gpu")

_lock = threading.Lock()


@contextmanager
def gpu_session(tag: str = ""):
    with _lock:
        try:
            yield
        finally:
            _cleanup(tag)


def _cleanup(tag: str) -> None:
    try:
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # уборка не должна ронять пайплайн
        log.warning("cuda empty_cache failed", exc_info=True)
    gc.collect()


def gpu_name() -> str | None:
    """Имя GPU, если torch уже загружен (не форсируем импорт ради /meta)."""
    torch = sys.modules.get("torch")
    if torch is None:
        return None
    try:
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        return None
    return None


def is_oom(exc: BaseException) -> bool:
    torch = sys.modules.get("torch")
    if torch is not None and isinstance(exc, torch.cuda.OutOfMemoryError):
        return True
    return "out of memory" in str(exc).lower()
