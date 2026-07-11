"""Коды ошибок и единый формат ответа: {"error": {code, message_ru, detail}} (ТЗ §11)."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("mixpilot")

# Базовые русские тексты (UX_UI.md §6.2); detail — для «Скопировать для поддержки».
MESSAGES_RU = {
    "E_VRAM": "Не хватило видеопамяти. Попробуйте режим «Быстро» или закройте тяжёлые программы",
    "E_DISK_SPACE": "Мало места на диске",
    "E_DECODE": "Не удалось прочитать файл — возможно, он повреждён или в редком формате",
    "E_TOO_LONG": "Трек слишком длинный — обработка может занять очень долго",
    "E_MODEL_MISSING": "Нужен звуковой компонент — скачайте его в настройках",
    "E_NET_CLOUD": "Нет соединения — свободный текст временно недоступен",
    "E_CANCELLED": "Отменено. Черновик сохранён",
    "E_WORKER_DOWN": "Звуковой движок перезапускается",
    "E_DSL": "Не понял команду — уточните формулировку",
    "E_LLM_KEY": "Добавьте API-ключ в Настройках → Облако",
    "E_AUDIO_DEVICE": "Микрофон занят или недоступен",
    "E_NOT_FOUND": "Не найдено — возможно, элемент уже удалён",
    "E_BAD_REQUEST": "Некорректный запрос",
    "E_FILE_ACCESS": "Нет доступа к файлу — проверьте, что он существует и не занят другой программой",
    "E_INTERNAL": "Внутренняя ошибка. Подробности сохранены в журнале",
}


class AppError(Exception):
    def __init__(self, code: str, detail: str = "", status: int = 400, message_ru: str | None = None):
        self.code = code
        self.detail = detail
        self.status = status
        self.message_ru = message_ru or MESSAGES_RU.get(code, code)
        super().__init__(f"{code}: {detail}")

    def to_body(self) -> dict:
        return {"error": {"code": self.code, "message_ru": self.message_ru, "detail": self.detail}}


def not_found(detail: str = "") -> AppError:
    return AppError("E_NOT_FOUND", detail, status=404)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_req: Request, exc: AppError):
        return JSONResponse(exc.to_body(), status_code=exc.status)

    @app.exception_handler(Exception)
    async def _unhandled(_req: Request, exc: Exception):
        log.exception("unhandled error")
        body = AppError("E_INTERNAL", detail=f"{type(exc).__name__}: {exc}", status=500).to_body()
        return JSONResponse(body, status_code=500)
