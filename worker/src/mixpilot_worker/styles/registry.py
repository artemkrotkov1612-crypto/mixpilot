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

IMPLEMENTED = {"slowed", "bass_boosted", "phonk", "club", "house"}


def resolve_style(style: str | None, analysis: dict | None = None) -> str:
    """Слаг стиля. 'auto' и неизвестное выбираются по характеру трека."""
    if style in IMPLEMENTED:
        return style
    return auto_style(analysis)


def auto_style(analysis: dict | None) -> str:
    """«AI сам решит» без облака: по темпу и энергии трека.

    Быстрые треки уводим в клубную сторону, медленные — в Slowed;
    средний темп с плотным низом — Phonk, иначе Bass Boosted.
    """
    if not analysis:
        return "slowed"
    bpm = float(analysis.get("bpm") or 0)
    sections = analysis.get("sections") or []
    energy = max((float(s.get("energy", 0)) for s in sections), default=0.5)

    if bpm >= 124:
        return "house" if energy < 0.8 else "club"
    if bpm <= 95:
        return "slowed"
    return "phonk" if energy >= 0.7 else "bass_boosted"


def _base_params(style: str) -> StyleParams:
    if style == "phonk":
        # Медленнее и ниже, жирный сатурированный низ, приглушённый верх.
        return StyleParams(
            tempo_factor=0.92, pitch_semitones=-2.0,
            gain_db={"drums": 1.5, "bass": 2.5},
            bass_shelf_db=7.0, bass_drive_db=9.0, kick_boost_db=4.0,
            sub_db=2.5, warmth_db=-3.0, vocal_reverb=0.12,
            comp_threshold_db=-15.0, comp_ratio=3.0,
            target_loudness="club", ceiling_db=-1.0,
        )
    if style == "club":
        # Энергия и удар: быстрее, яркий верх, плотная компрессия.
        return StyleParams(
            tempo_factor=1.06, pitch_semitones=0.0,
            gain_db={"drums": 2.0, "bass": 1.5},
            bass_shelf_db=4.0, bass_drive_db=3.0, kick_boost_db=5.0,
            sub_db=2.0, air_db=3.0,
            comp_threshold_db=-14.0, comp_ratio=3.5,
            target_loudness="club", ceiling_db=-1.0,
        )
    if style == "house":
        # Ровный грув, мягче кик, воздух и лёгкая атмосфера на вокале.
        return StyleParams(
            tempo_factor=1.04, pitch_semitones=0.0,
            gain_db={"drums": 1.0, "other": 1.0},
            bass_shelf_db=3.0, bass_drive_db=2.0, kick_boost_db=2.5,
            sub_db=1.5, air_db=2.5, vocal_reverb=0.14,
            comp_threshold_db=-16.0, comp_ratio=2.5,
            target_loudness="club", ceiling_db=-1.0,
        )
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
    if style == "phonk":
        return [
            ("Классика стиля", "Тяжёлый низ и приглушённый верх",
             lambda p: p),
            ("Плавный акцент", "Мягче кач, вокал разборчивее",
             lambda p: replace(p, tempo_factor=0.95, bass_drive_db=p.bass_drive_db - 2.0,
                               gain_db={**p.gain_db, "vocals": 1.5})),
            ("Смелый вариант", "Ниже тон, гуще сатурация",
             lambda p: replace(p, pitch_semitones=p.pitch_semitones - 1.5,
                               bass_drive_db=p.bass_drive_db + 3.0, sub_db=p.sub_db + 2.0)),
        ]
    if style == "club":
        return [
            ("Классика стиля", "Энергичный бит и яркий верх",
             lambda p: p),
            ("Плавный акцент", "Ровнее динамика, акцент на вокал",
             lambda p: replace(p, comp_ratio=p.comp_ratio - 1.0, air_db=p.air_db - 1.0,
                               gain_db={**p.gain_db, "vocals": 1.5})),
            ("Смелый вариант", "Быстрее и мощнее — для танцпола",
             lambda p: replace(p, tempo_factor=min(p.tempo_factor + 0.05, 1.15),
                               kick_boost_db=p.kick_boost_db + 2.0, sub_db=p.sub_db + 1.5,
                               comp_ratio=p.comp_ratio + 0.5)),
        ]
    if style == "house":
        return [
            ("Классика стиля", "Ровный грув и лёгкий воздух",
             lambda p: p),
            ("Плавный акцент", "Глубже атмосфера, мягче верх",
             lambda p: replace(p, vocal_reverb=p.vocal_reverb + 0.12, air_db=p.air_db - 1.0,
                               warmth_db=-1.5)),
            ("Смелый вариант", "Плотнее бас и заметнее бит",
             lambda p: replace(p, bass_shelf_db=p.bass_shelf_db + 2.5, kick_boost_db=p.kick_boost_db + 2.0,
                               gain_db={**p.gain_db, "drums": p.gain_db.get("drums", 0.0) + 1.0})),
        ]
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
