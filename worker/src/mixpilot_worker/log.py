"""JSON-логи в файл + краткий вывод в консоль. Ротация: 7 суточных файлов.

Стандартный logging вместо structlog — меньше зависимостей, формат тот же
(однострочный JSON на запись). Содержимое пользовательских текстов не пишем.
"""

import datetime as dt
import json
import logging
from pathlib import Path

from . import config

KEEP_DAYS = 7


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            entry.update(extra)
        return json.dumps(entry, ensure_ascii=False)


def _cleanup(dir_: Path) -> None:
    cutoff = dt.date.today() - dt.timedelta(days=KEEP_DAYS)
    for f in dir_.glob("worker-*.jsonl"):
        try:
            day = dt.date.fromisoformat(f.stem.removeprefix("worker-"))
            if day < cutoff:
                f.unlink(missing_ok=True)
        except ValueError:
            continue


def setup() -> None:
    logs = config.logs_dir()
    logs.mkdir(parents=True, exist_ok=True)
    _cleanup(logs)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Повторная инициализация (тесты) — не плодим хендлеры.
    root.handlers = [h for h in root.handlers if not getattr(h, "_mixpilot", False)]

    file_h = logging.FileHandler(logs / f"worker-{dt.date.today().isoformat()}.jsonl", encoding="utf-8")
    file_h.setFormatter(JsonFormatter())
    file_h._mixpilot = True  # type: ignore[attr-defined]
    root.addHandler(file_h)

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    console._mixpilot = True  # type: ignore[attr-defined]
    root.addHandler(console)
