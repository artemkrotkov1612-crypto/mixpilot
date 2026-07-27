"""Реестр стилей и планирование 3 вариантов с учётом чипов-модификаторов.

Стиль задаёт базовые StyleParams и три «характера» варианта:
Классика / Акцент по пожеланию / Смелый. Чипы двигают параметры (офлайн,
без LLM); свободный текст подключит M4.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from .base import StyleParams

# Слаг стиля -> человеческое имя (для UI/логов, НЕ имена моделей).
STYLE_NAMES = {
    "slowed": "Slowed",
    "bass_boosted": "Bass Boosted",
    "phonk": "Phonk",
    "club": "Club",
    "house": "House",
    "auto": "AI сам решит",
}

# Реализованные в M3 стили; остальные добавит M4.
IMPLEMENTED = {"slowed", "bass_boosted"}


def resolve_style(style: str | None) -> str:
    if not style or style not in IMPLEMENTED:
        return "slowed" if style in (None, "auto", "slowed") else "bass_boosted"
    return style


def _base_params(style: str) -> StyleParams:
    if style == "bass_boosted":
        return StyleParams(
            tempo_factor=1.0, pitch_semitones=0.0,
            gain_db={"bass": 3.0},
            bass_shelf_db=6.0, bass_drive_db=6.0, kick_boost_db=3.0,
            sub_db=3.0, comp_threshold_db=-16.0, comp_ratio=2.5,
            target_loudness="club", ceiling_db=-1.0,
        )
    # slowed
    return StyleParams(
        tempo_factor=0.86, pitch_semitones=-1.0,
        gain_db={"vocals": -1.0},
        vocal_reverb=0.22, warmth_db=-2.5, sub_db=1.5,
        comp_threshold_db=-18.0, comp_ratio=2.0,
        target_loudness="stream", ceiling_db=-1.0,
    )


# Три характера варианта: (суффикс имени, описание, функция-модификатор base->params).
def _variants_for(style: str) -> list[tuple[str, str, callable]]:
    if style == "bass_boosted":
        return [
            ("Классика стиля", "Ровный мощный бас и чёткий кик",
             lambda p: p),
            ("Плавный акцент", "Бас глубже, верх мягче — акцент на вокал",
             lambda p: replace(p, bass_shelf_db=p.bass_shelf_db + 1.5, warmth_db=-2.0,
                               gain_db={**p.gain_db, "vocals": 1.0})),
            ("Смелый вариант", "Максимальный суб и сатурация — для клуба",
             lambda p: replace(p, bass_shelf_db=p.bass_shelf_db + 3.0, bass_drive_db=p.bass_drive_db + 3.0,
                               sub_db=p.sub_db + 2.0, kick_boost_db=p.kick_boost_db + 2.0)),
        ]
    return [
        ("Классика стиля", "Замедление и лёгкая атмосфера",
         lambda p: p),
        ("Плавная версия", "Мягче, больше воздуха на вокале",
         lambda p: replace(p, tempo_factor=0.88, vocal_reverb=p.vocal_reverb + 0.1, warmth_db=-3.5)),
        ("Смелый вариант", "Сильнее замедление и ниже тон",
         lambda p: replace(p, tempo_factor=0.80, pitch_semitones=p.pitch_semitones - 1.5,
                           vocal_reverb=p.vocal_reverb + 0.06)),
    ]


def _apply_chips(p: StyleParams, chips: list[str]) -> StyleParams:
    """Карточки-модификаторы двигают параметры (работают офлайн, без облака)."""
    chips = set(chips or [])
    g = dict(p.gain_db)
    changes: dict = {}
    if "Мощный бас" in chips:
        changes["bass_shelf_db"] = p.bass_shelf_db + 4.0
        changes["bass_drive_db"] = max(p.bass_drive_db, 4.0)
        changes["sub_db"] = p.sub_db + 2.0
    if "Быстрее" in chips:
        changes["tempo_factor"] = min(p.tempo_factor + 0.08, 1.15)
    if "Медленнее" in chips:
        changes["tempo_factor"] = max(p.tempo_factor - 0.08, 0.7)
    if "Эмоциональный вокал" in chips:
        g["vocals"] = g.get("vocals", 0.0) + 1.5
    if "Атмосферно" in chips:
        changes["vocal_reverb"] = min(p.vocal_reverb + 0.15, 0.6)
    if "Мрачно" in chips:
        changes["pitch_semitones"] = p.pitch_semitones - 1.0
        changes["warmth_db"] = min(p.warmth_db, 0.0) - 2.0
    if "Энергично" in chips:
        changes["air_db"] = p.air_db + 2.0
        changes["comp_ratio"] = p.comp_ratio + 0.5
    changes["gain_db"] = g
    return replace(p, **changes)


def plan_variants(style: str, chips: list[str] | None = None) -> list[dict]:
    """3 варианта: [{idx, title_ru, description_ru, params}]."""
    style = resolve_style(style)
    base = _apply_chips(_base_params(style), chips or [])
    out = []
    for idx, (suffix, desc, mod) in enumerate(_variants_for(style)):
        params = mod(deepcopy(base))
        out.append({
            "idx": idx,
            "title_ru": f"Вариант {chr(ord('A') + idx)} — {suffix}",
            "description_ru": desc,
            "params": params,
        })
    return out
