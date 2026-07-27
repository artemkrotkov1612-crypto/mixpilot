"""Совместимость треков: темп и тональность.

Две песни звучат вместе, только если совпадает темп и не спорят тональности.
Здесь считаем, насколько каждый трек нужно подтянуть к якорному, и честно
предупреждаем, если сведение потребует слишком сильной правки.
"""

from __future__ import annotations

import math

from ..analysis.key import NOTE_NAMES
from ..timepitch.stretcher import TEMPO_MAX, TEMPO_MIN

# Мягкие пределы: за ними звук заметно портится (ТЗ §20, риски).
MAX_COMFORT_STRETCH = 0.15   # ±15% темпа — незаметно
MAX_PITCH_SHIFT = 3.0        # больше 3 полутонов — уже слышно


def tempo_factor(source_bpm: float, target_bpm: float) -> float:
    """Множитель темпа source -> target с учётом half/double-time.

    Трек на 72 BPM и трек на 140 BPM совместимы: 72 играется «в два раза
    быстрее». Выбираем вариант с наименьшим растяжением.
    """
    if source_bpm <= 0 or target_bpm <= 0:
        return 1.0
    best = 1.0
    best_cost = math.inf
    for multiple in (0.25, 0.5, 1.0, 2.0, 4.0):
        factor = (target_bpm * multiple) / source_bpm
        if not (TEMPO_MIN <= factor <= TEMPO_MAX):
            continue
        cost = abs(math.log(factor))
        if cost < best_cost:
            best, best_cost = factor, cost
    return round(best, 4)


def _pitch_class(root: str | None) -> int | None:
    if not root:
        return None
    try:
        return NOTE_NAMES.index(root)
    except ValueError:
        return None


def key_shift(source: dict, target: dict) -> float:
    """На сколько полутонов сдвинуть source, чтобы попасть в тональность target.

    Параллельные тональности (A minor и C major) считаем совпадающими:
    сравниваем по относительному мажору.
    """
    src_pc = _pitch_class(source.get("key_root"))
    dst_pc = _pitch_class(target.get("key_root"))
    if src_pc is None or dst_pc is None:
        return 0.0
    # Приводим минор к относительному мажору (+3 полутона).
    if source.get("key_mode") == "minor":
        src_pc = (src_pc + 3) % 12
    if target.get("key_mode") == "minor":
        dst_pc = (dst_pc + 3) % 12

    diff = (dst_pc - src_pc) % 12
    if diff > 6:
        diff -= 12  # ближе вниз
    return float(diff)


def choose_anchor(tracks: list[dict]) -> int:
    """Индекс якорного трека: к нему подтягиваются остальные.

    Берём тот, при котором суммарное растяжение остальных минимально —
    так меньше всего страдает звук.
    """
    if not tracks:
        return 0
    best_idx, best_cost = 0, math.inf
    for i, anchor in enumerate(tracks):
        anchor_bpm = float(anchor.get("bpm") or 0)
        if anchor_bpm <= 0:
            continue
        cost = 0.0
        for j, other in enumerate(tracks):
            if i == j:
                continue
            factor = tempo_factor(float(other.get("bpm") or 0), anchor_bpm)
            cost += abs(math.log(factor)) if factor > 0 else 1.0
        if cost < best_cost:
            best_idx, best_cost = i, cost
    return best_idx


def build_plan(tracks: list[dict]) -> dict:
    """План сведения: якорь, правки на каждый трек и понятные предупреждения.

    tracks — список анализов: {track_id, title, bpm, key_root, key_mode, ...}
    """
    if not tracks:
        return {"anchor": 0, "tracks": [], "warnings": []}

    anchor_idx = choose_anchor(tracks)
    anchor = tracks[anchor_idx]
    anchor_bpm = float(anchor.get("bpm") or 0)

    plan_tracks: list[dict] = []
    warnings: list[str] = []
    for i, track in enumerate(tracks):
        factor = 1.0 if i == anchor_idx else tempo_factor(float(track.get("bpm") or 0), anchor_bpm)
        shift = 0.0 if i == anchor_idx else key_shift(track, anchor)

        title = track.get("title") or f"трек {i + 1}"
        if abs(math.log(factor)) > math.log(1 + MAX_COMFORT_STRETCH):
            percent = round((factor - 1) * 100)
            warnings.append(
                f"«{title}» пришлось {'ускорить' if percent > 0 else 'замедлить'} "
                f"на {abs(percent)}% — темп заметно отличается"
            )
        if abs(shift) > MAX_PITCH_SHIFT:
            warnings.append(f"«{title}» в далёкой тональности — оставили как есть, чтобы не портить звук")
            shift = 0.0

        plan_tracks.append({
            "index": i,
            "track_id": track.get("track_id"),
            "title": title,
            "is_anchor": i == anchor_idx,
            "tempo_factor": factor,
            "pitch_semitones": shift,
            "bpm": track.get("bpm"),
        })

    return {
        "anchor": anchor_idx,
        "anchor_bpm": anchor_bpm,
        "anchor_key": f"{anchor.get('key_root') or '?'} {anchor.get('key_mode') or ''}".strip(),
        "tracks": plan_tracks,
        "warnings": warnings,
    }
