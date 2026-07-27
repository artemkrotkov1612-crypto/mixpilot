"""Пять способов соединить песни.

Каждая стратегия — план: какие куски каких треков взять и как их
склеить. Сам звук собирает pipeline; здесь только «режиссура», чтобы
логику можно было проверить тестами без аудио.
"""

from __future__ import annotations

STRATEGIES = {
    "auto": "AI сам решит",
    "smooth": "Плавное соединение",
    "club": "Клубный mashup",
    "best_parts": "Лучшие моменты",
    "vocal_instr": "Вокал одной + музыка другой",
}

# Сколько секунд брать из блока, если он слишком длинный.
MAX_PIECE_S = 40.0
MIN_PIECE_S = 6.0


def resolve_strategy(strategy: str | None, track_count: int) -> str:
    """'auto' выбирает по числу треков: две песни — наложение вокала, больше — лучшие моменты."""
    if strategy in STRATEGIES and strategy != "auto":
        return strategy
    return "vocal_instr" if track_count == 2 else "best_parts"


def _sections(track: dict) -> list[dict]:
    return track.get("sections") or []


def _pick(sections: list[dict], labels: tuple[str, ...], limit: int) -> list[dict]:
    """Блоки нужных типов, самые энергичные первыми."""
    chosen = [s for s in sections if s.get("label") in labels]
    chosen.sort(key=lambda s: -float(s.get("energy", 0)))
    return chosen[:limit]


def _clip(section: dict) -> dict:
    """Ограничиваем длину куска, чтобы mashup не превратился в плейлист."""
    start = float(section["start_s"])
    end = float(section["end_s"])
    if end - start > MAX_PIECE_S:
        end = start + MAX_PIECE_S
    return {"start_s": round(start, 3), "end_s": round(end, 3), "label": section.get("label", "")}


def _fallback_piece(track: dict) -> dict:
    """Если структура не определилась — берём кусок из середины трека."""
    duration = float(track.get("duration_s") or 0) or MAX_PIECE_S
    start = max(0.0, duration * 0.25)
    return {"start_s": round(start, 3), "end_s": round(min(start + MAX_PIECE_S, duration), 3), "label": ""}


def plan_smooth(tracks: list[dict]) -> dict:
    """Песни целиком одна за другой с кроссфейдом по фразе."""
    pieces = []
    for i, track in enumerate(tracks):
        sections = _sections(track)
        if sections:
            # Берём от первого куплета до конца — вступления второй песни ни к чему.
            start = sections[0]["start_s"] if i == 0 else next(
                (s["start_s"] for s in sections if s.get("label") != "intro"), sections[0]["start_s"]
            )
            end = sections[-1]["end_s"]
            piece = {"start_s": round(float(start), 3), "end_s": round(float(end), 3), "label": "полностью"}
        else:
            piece = _fallback_piece(track)
        pieces.append({"track_index": i, **piece})
    return {
        "layers": [],
        "sequence": pieces,
        "xfade_ms": 2000,  # длинный кроссфейд: переход должен быть незаметным
        "description_ru": "Песни переходят одна в другую плавно",
    }


def plan_club(tracks: list[dict]) -> dict:
    """Чередование припевов с коротким жёстким переходом — как в клубе."""
    pieces = []
    per_track = max(1, 4 // max(len(tracks), 1))
    for i, track in enumerate(tracks):
        sections = _sections(track)
        picked = _pick(sections, ("chorus", "drop"), per_track) or _pick(sections, ("verse",), per_track)
        if not picked:
            pieces.append({"track_index": i, **_fallback_piece(track)})
            continue
        for section in picked:
            pieces.append({"track_index": i, **_clip(section)})
    # Чередуем треки, а не идём подряд: A-припев, B-припев, A-припев…
    interleaved: list[dict] = []
    by_track: dict[int, list[dict]] = {}
    for p in pieces:
        by_track.setdefault(p["track_index"], []).append(p)
    while any(by_track.values()):
        for idx in sorted(by_track):
            if by_track[idx]:
                interleaved.append(by_track[idx].pop(0))
    return {
        "layers": [],
        "sequence": interleaved,
        "xfade_ms": 120,  # короткий стык на долю — «клубный» переход
        "description_ru": "Припевы чередуются с резкими переходами",
    }


def plan_best_parts(tracks: list[dict]) -> dict:
    """Самые сильные моменты каждой песни в порядке нарастания энергии."""
    pieces = []
    per_track = 2 if len(tracks) <= 3 else 1
    for i, track in enumerate(tracks):
        sections = _sections(track)
        picked = _pick(sections, ("chorus", "drop", "verse", "bridge"), per_track)
        if not picked:
            pieces.append({"track_index": i, "energy": 0.5, **_fallback_piece(track)})
            continue
        for section in picked:
            pieces.append({"track_index": i, "energy": float(section.get("energy", 0.5)), **_clip(section)})
    pieces.sort(key=lambda p: p.get("energy", 0.5))  # от спокойного к мощному
    for p in pieces:
        p.pop("energy", None)
    return {
        "layers": [],
        "sequence": pieces,
        "xfade_ms": 400,
        "description_ru": "Лучшие моменты, от спокойного к мощному",
    }


def plan_vocal_instr(tracks: list[dict], vocal_from: int = 0, music_from: int = 1) -> dict:
    """Вокал одной песни поверх музыки другой — классический mashup."""
    vocal_from = min(max(vocal_from, 0), len(tracks) - 1)
    music_from = min(max(music_from, 0), len(tracks) - 1)
    if vocal_from == music_from:
        music_from = (vocal_from + 1) % max(len(tracks), 1)

    music = tracks[music_from]
    sections = _sections(music)
    if sections:
        base = {"start_s": round(float(sections[0]["start_s"]), 3),
                "end_s": round(float(sections[-1]["end_s"]), 3), "label": "музыка"}
    else:
        base = _fallback_piece(music)

    vocal = tracks[vocal_from]
    vocal_sections = _pick(_sections(vocal), ("chorus", "verse", "drop"), 4)
    vocal_pieces = [_clip(s) for s in vocal_sections] or [_fallback_piece(vocal)]

    return {
        # layers: слои поверх основы (вокал), sequence: сама основа
        "layers": [{"track_index": vocal_from, "stem": "vocals", "pieces": vocal_pieces}],
        "sequence": [{"track_index": music_from, "stem": "instrumental", **base}],
        "xfade_ms": 300,
        "description_ru": f"Голос из «{vocal.get('title', '1-й песни')}» поверх музыки «{music.get('title', '2-й')}»",
    }


def build(strategy: str, tracks: list[dict], *, vocal_from: int = 0, music_from: int = 1) -> dict:
    """План соединения: {layers, sequence, xfade_ms, description_ru, strategy}."""
    resolved = resolve_strategy(strategy, len(tracks))
    if resolved == "smooth":
        plan = plan_smooth(tracks)
    elif resolved == "club":
        plan = plan_club(tracks)
    elif resolved == "vocal_instr":
        plan = plan_vocal_instr(tracks, vocal_from, music_from)
    else:
        plan = plan_best_parts(tracks)
    plan["strategy"] = resolved
    plan["strategy_name"] = STRATEGIES[resolved]
    # Отбрасываем слишком короткие огрызки — они звучат как случайный обрыв.
    plan["sequence"] = [p for p in plan["sequence"] if p["end_s"] - p["start_s"] >= MIN_PIECE_S] or plan["sequence"][:1]
    return plan
