"""Свободный текст → операции Edit DSL.

Цепочка: провайдер → извлечение JSON из фенсов → строгая валидация нашим
валидатором. Модель не может «придумать» операцию: всё, что не описано в
edit_dsl, отсекается до применения к звуку.
"""

import logging

from ..errors import AppError
from . import prompts
from .edit_dsl import DslError, validate_ops
from .json_extract import JsonExtractError, extract_json_object
from .provider import get_provider

log = logging.getLogger("mixpilot.llm")


def _clean_ops(raw: object) -> list[dict]:
    """Оставляем только объекты-операции; строки/мусор от посредника отбрасываем."""
    if not isinstance(raw, list):
        return []
    return [op for op in raw if isinstance(op, dict) and "op" in op]


def text_to_ops(text: str, context: dict | None = None) -> dict:
    """{"ops": [...], "summary_ru": "..."} — уже провалидированные операции."""
    if not text or not text.strip():
        raise AppError("E_BAD_REQUEST", "пустой запрос", status=422)

    provider = get_provider()
    answer = provider.complete(
        prompts.EDIT_SYSTEM,
        prompts.edit_user_prompt(text, context or {}),
    )
    try:
        doc = extract_json_object(answer)
    except JsonExtractError as exc:
        log.warning("llm вернул неразбираемый ответ", extra={"ctx": {"detail": str(exc)[:200]}})
        raise AppError("E_DSL", str(exc), status=422,
                       message_ru="Не удалось разобрать ответ — попробуйте сформулировать иначе") from exc

    ops = _clean_ops(doc.get("ops"))
    if not ops:
        raise AppError("E_DSL", f"модель не выделила операций: {doc}", status=422,
                       message_ru=f"Не понял «{text.strip()[:60]}» — уточните формулировку")
    try:
        ops = validate_ops(ops)
    except DslError as exc:
        raise AppError("E_DSL", exc.message, status=422,
                       message_ru="Не понял часть пожелания — уточните формулировку") from exc

    summary = str(doc.get("summary_ru") or "").strip()
    return {"ops": ops, "summary_ru": summary}


def text_to_plan(text: str, context: dict | None = None) -> dict:
    """Свободный текст на этапе создания: {"style": ..., "ops": [...], "summary_ru": ...}."""
    from ..styles.registry import IMPLEMENTED

    provider = get_provider()
    answer = provider.complete(
        prompts.PLAN_SYSTEM,
        prompts.edit_user_prompt(text, context or {}),
    )
    try:
        doc = extract_json_object(answer)
    except JsonExtractError as exc:
        raise AppError("E_DSL", str(exc), status=422,
                       message_ru="Не удалось разобрать ответ — попробуйте иначе") from exc

    style = str(doc.get("style") or "").strip().lower()
    if style not in IMPLEMENTED:
        style = ""  # выберем сами по анализу трека
    ops = _clean_ops(doc.get("ops"))
    try:
        ops = validate_ops(ops) if ops else []
    except DslError:
        ops = []  # стиль важнее: неудачные правки просто отбрасываем
    return {"style": style, "ops": ops, "summary_ru": str(doc.get("summary_ru") or "").strip()}
