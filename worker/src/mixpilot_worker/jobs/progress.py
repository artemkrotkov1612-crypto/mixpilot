"""WebSocket-хаб прогресса: события job.progress / job.done / job.error.

emit() потокобезопасен — хендлеры задач работают в executor-потоках.
"""

import asyncio
import logging

from fastapi import WebSocket

log = logging.getLogger("mixpilot.ws")

# Человеческие статусы (UX_UI.md §6.1); ключ: "<kind>.<stage>".
STAGES_RU: dict[str, str] = {
    "analyze.decode": "Слушаем трек…",
    "analyze.tempo": "Считаем темп и тональность…",
    "analyze.key": "Считаем темп и тональность…",
    "analyze.structure": "Ищем куплеты и припевы…",
    "analyze.save": "Запоминаем…",
    "stems.load": "Готовим модель… (при первом запуске скачается компонент)",
    "stems.separate": "Разделяем на дорожки…",
    "stems.save": "Сохраняем дорожки…",
    "generate.analyze": "Слушаем трек…",
    "generate.stems": "Разделяем на дорожки…",
    "generate.plan": "Придумываем варианты…",
    "generate.build": "Собираем варианты…",
    "generate.done": "Готово!",
    "merge.analyze": "Слушаем песни…",
    "merge.plan": "Подбираем темп и тональность…",
    "merge.stems": "Готовим дорожки песен…",
    "merge.build": "Собираем варианты…",
    "merge.done": "Готово!",
    "voice_cover.stems": "Отделяем голос от музыки…",
    "voice_cover.convert": "Поём вашим голосом…",
    "voice_cover.mix": "Сводим с музыкой…",
    "voice_cover.done": "Готово!",
    "apply_edit.stems": "Готовим дорожки…",
    "apply_edit.build": "Применяем изменения…",
    "apply_edit.done": "Готово!",
}


def human_ru(kind: str, stage: str) -> str:
    return STAGES_RU.get(f"{kind}.{stage}", "Обрабатываем…")


class ProgressHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def _broadcast(self, payload: dict) -> None:
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def emit(self, payload: dict) -> None:
        """Из любого потока: доставка best-effort (UI переспросит REST'ом)."""
        loop = self._loop
        if loop is None or not self._clients:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)
        except RuntimeError:
            log.debug("emit after loop shutdown")


hub = ProgressHub()
