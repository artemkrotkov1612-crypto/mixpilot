"""Названия для трека: облако придумывает, офлайн-шаблоны страхуют.

В облако уходит только текст (название исходника, стиль, темп) — аудио не
покидает компьютер. Без интернета и без ключа кнопка обязана работать:
названия тогда собираются из шаблонов по стилю и настроению.
"""

from __future__ import annotations

import logging
import random

from ..errors import AppError
from ..llm import prompts
from ..llm.json_extract import JsonExtractError, extract_json_object
from ..llm.provider import get_provider

log = logging.getLogger("mixpilot.artwork")

# Запасные названия: по стилю — свой словарь настроений.
FALLBACK = {
    "slowed": ["Ночной ход", "Замедленно", "Тихий этаж", "Полусон", "Долгий вечер"],
    "bass_boosted": ["Низкий фронт", "Глубина", "Подвал", "Толчок", "Волна снизу"],
    "phonk": ["Дым", "Трасса 3 ночи", "Тёмный салон", "Сигнал", "Хищник"],
    "club": ["Первый ряд", "До утра", "Свет в потолок", "Пульс", "Танцпол"],
    "house": ["Тёплый вечер", "Лёгкий шаг", "Летний этаж", "Открытая крыша", "Ровный ритм"],
}
GENERIC = ["Новая версия", "Свежий взгляд", "Другая сторона", "Второй дубль", "Иначе"]


def _fallback_titles(source_title: str, style: str) -> list[str]:
    pool = list(FALLBACK.get(style, GENERIC))
    random.shuffle(pool)
    titles = pool[:4]
    if source_title:
        # Понятная привязка к исходнику — чтобы список не выглядел случайным.
        titles.insert(0, f"{source_title.strip()} — {_style_word(style)}")
    return titles[:5]


def _style_word(style: str) -> str:
    return {
        "slowed": "замедленная версия",
        "bass_boosted": "версия с мощным басом",
        "phonk": "phonk-версия",
        "club": "клубная версия",
        "house": "house-версия",
    }.get(style, "новая версия")


def _user_prompt(source_title: str, style_name: str, bpm: float | None, mood: str) -> str:
    lines = ["Придумай названия для ремикса."]
    if source_title:
        lines.append(f"Исходная песня: «{source_title}»")
    if style_name:
        lines.append(f"Стиль: {style_name}")
    if bpm:
        lines.append(f"Темп: {round(bpm)} BPM")
    if mood:
        lines.append(f"Настроение: {mood}")
    lines.append("Названия — на русском языке.")
    return "\n".join(lines)


def suggest_titles(source_title: str = "", style: str = "", style_name: str = "",
                   bpm: float | None = None, mood: str = "") -> dict:
    """Пять названий. Всегда возвращает результат — офлайн просто без облака."""
    try:
        provider = get_provider()
        answer = provider.complete(
            prompts.COVER_SYSTEM, _user_prompt(source_title, style_name or style, bpm, mood)
        )
        doc = extract_json_object(answer)
        titles = [str(t).strip() for t in (doc.get("titles") or []) if str(t).strip()]
        titles = [t for t in titles if len(t) <= 60][:5]
        if titles:
            return {"titles": titles, "source": "cloud",
                    "cover_idea_ru": str(doc.get("cover_idea_ru") or "").strip()}
        log.info("облако не дало названий — берём шаблоны")
    except (AppError, JsonExtractError) as exc:
        log.info("названия офлайн: %s", type(exc).__name__)

    return {"titles": _fallback_titles(source_title, style), "source": "local", "cover_idea_ru": ""}
