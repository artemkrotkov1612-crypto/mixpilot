"""Адаптер текстовой модели: бизнес-код не знает, кто именно отвечает.

В облако уходит ТОЛЬКО текст (пожелания, названия блоков, темп, стиль).
Аудио, голос и файлы не покидают компьютер — см. 01_DOCS/TZ.md §12.
"""

from __future__ import annotations

import logging
from typing import Protocol

from .. import config
from ..errors import AppError

log = logging.getLogger("mixpilot.llm")

# Разумные потолки: правки короткие, тексты песен длиннее.
MAX_TOKENS_SMALL = 700
MAX_TOKENS_TEXT = 1500


class TextProvider(Protocol):
    def complete(self, system: str, user: str, *, quality: bool = False, max_tokens: int = MAX_TOKENS_SMALL) -> str:
        """Возвращает текст ответа модели."""


class ClaudeProvider:
    """Официальный SDK anthropic; base_url позволяет работать через посредника."""

    def __init__(self, cfg: dict):
        self._cfg = cfg

    def complete(self, system: str, user: str, *, quality: bool = False, max_tokens: int = MAX_TOKENS_SMALL) -> str:
        import anthropic

        kwargs: dict = {"api_key": self._cfg["api_key"]}
        if self._cfg.get("base_url"):
            kwargs["base_url"] = self._cfg["base_url"]
        client = anthropic.Anthropic(**kwargs)

        # Датированный ID обязателен: у посредников алиасы не резолвятся.
        model = self._cfg["model_quality"] if quality else self._cfg["model_fast"]
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # noqa: BLE001 — граница внешнего сервиса
            raise _translate_error(exc) from exc

        parts = [block.text for block in message.content if getattr(block, "type", "") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise AppError("E_NET_CLOUD", "модель вернула пустой ответ", status=502)
        log.info(
            "llm ok",
            extra={"ctx": {"model": model, "in": message.usage.input_tokens, "out": message.usage.output_tokens}},
        )
        return text


def _translate_error(exc: Exception) -> AppError:
    name = type(exc).__name__
    detail = f"{name}: {exc}"[:500]
    if "Authentication" in name or "PermissionDenied" in name:
        return AppError("E_LLM_KEY", detail, status=401)
    if "NotFound" in name:
        return AppError(
            "E_LLM_KEY",
            f"модель недоступна у провайдера (нужен ID с датой). {detail}",
            status=404,
            message_ru="Выбранная модель недоступна у вашего провайдера ключа",
        )
    if "RateLimit" in name:
        return AppError("E_NET_CLOUD", detail, status=429,
                        message_ru="Провайдер ограничил частоту запросов — попробуйте через минуту")
    return AppError("E_NET_CLOUD", detail, status=502)


def cloud_status() -> dict:
    """Готовность облака для UI: без раскрытия самого ключа."""
    from ..routers.settings import get_settings

    cfg = config.load_llm_config()
    has_key = bool(cfg.get("api_key"))
    enabled = bool(get_settings().get("cloud_enabled", True))
    return {
        "enabled": enabled,
        "has_key": has_key,
        "ready": enabled and has_key,
        "base_url": cfg.get("base_url") or "api.anthropic.com",
        "key_hint": f"…{cfg['api_key'][-4:]}" if has_key else "",
    }


def get_provider() -> TextProvider:
    """Провайдер или понятная ошибка, если облако выключено/нет ключа."""
    status = cloud_status()
    if not status["enabled"]:
        raise AppError("E_NET_CLOUD", "облако выключено в настройках", status=409,
                       message_ru="Понимание текста выключено в настройках — работают карточки")
    if not status["has_key"]:
        raise AppError("E_LLM_KEY", "не задан ключ", status=401)
    return ClaudeProvider(config.load_llm_config())
