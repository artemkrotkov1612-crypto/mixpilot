"""Достаём JSON-объект из ответа модели.

Посредники (в т.ч. cheapai.io) игнорируют structured output и заворачивают
JSON в markdown-фенсы, иногда с пояснением вокруг. Безопасный дефолт для
любого провайдера: снять фенсы и найти самый внешний сбалансированный объект
с учётом строк и экранирования.
"""

import json


class JsonExtractError(ValueError):
    pass


def _strip_fences(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    # ```json\n...\n``` либо ```\n...\n```
    first_newline = t.find("\n")
    if first_newline == -1:
        return t
    body = t[first_newline + 1 :]
    closing = body.rfind("```")
    return (body[:closing] if closing != -1 else body).strip()


def _outermost_object(text: str) -> str | None:
    """Первый сбалансированный {...}, игнорируя скобки внутри строк."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_object(text: str) -> dict:
    """Возвращает dict из ответа модели. Кидает JsonExtractError, если не вышло."""
    if not text or not text.strip():
        raise JsonExtractError("пустой ответ модели")

    candidates = []
    stripped = _strip_fences(text)
    candidates.append(stripped)
    outer = _outermost_object(stripped)
    if outer and outer != stripped:
        candidates.append(outer)
    # текст мог не начинаться с фенсов, но содержать объект внутри пояснения
    outer_raw = _outermost_object(text)
    if outer_raw:
        candidates.append(outer_raw)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise JsonExtractError(f"не нашёл JSON-объект в ответе: {text[:200]}")
