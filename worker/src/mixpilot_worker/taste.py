"""Профиль вкуса: учимся на выборе пользователя и объясняем это словами.

Сигнал берём не из абсолютных значений («ему нравится бас +4 дБ»), а из
сравнения выбранного варианта с его соседями по той же генерации. Иначе
профиль выучил бы стиль: в Slowed все три варианта медленные, и любой лайк
выглядел бы как «любит медленное».

Наружу профиль отдаётся человеческими фразами (ТЗ §22: пользователю не
показываем технические параметры) и всегда может быть выключен и стёрт.
"""

from __future__ import annotations

import json
import logging

from . import db
from .styles.base import StyleParams

log = logging.getLogger("mixpilot.taste")

# Оси вкуса — то, что человек реально слышит. Значение каждой считаем в
# условных «децибелах», чтобы разброс осей был сопоставим.
AXES = ("bass", "vocal", "space", "tempo", "bright")

AXIS_RU = {
    "bass": ("более мощный низ", "более лёгкий низ"),
    "vocal": ("голос погромче", "голос потише"),
    "space": ("больше атмосферы и эха", "суше и ближе, без эха"),
    "tempo": ("помедленнее", "побыстрее"),
    "bright": ("ярче и звонче", "мягче и теплее"),
}

# Насколько сильная разница между вариантами считается «полным» предпочтением.
AXIS_SCALE = 3.0
# Меньше этого — не мнение, а случайность: молчим и ничего не подкручиваем.
MIN_EVENTS = 3
MIN_BIAS = 0.25
# Сколько последних событий учитываем: вкус меняется, старое не должно давить.
WINDOW = 60


def axes_of(params: StyleParams) -> dict[str, float]:
    """Технические параметры → пять слышимых осей."""
    return {
        "bass": params.bass_shelf_db + params.sub_db
                + 0.5 * params.kick_boost_db + 0.5 * params.bass_drive_db,
        "vocal": float(params.gain_db.get("vocals", 0.0)),
        "space": params.vocal_reverb * 10.0,
        # Замедление ощущается сильнее, чем выглядит: 0.9 темпа — это заметно.
        "tempo": (1.0 - params.tempo_factor) * 20.0,
        "bright": params.air_db - params.warmth_db,
    }


def _delta_vs_siblings(conn, variant_id: str) -> dict[str, float] | None:
    """Чем выбранный вариант отличается от соседей той же генерации."""
    row = conn.execute(
        "SELECT generation_id, params_json FROM generation_variants WHERE id=?", (variant_id,)
    ).fetchone()
    if row is None:
        return None
    siblings = conn.execute(
        "SELECT id, params_json FROM generation_variants WHERE generation_id=?",
        (row["generation_id"],),
    ).fetchall()
    if len(siblings) < 2:
        # Сравнивать не с чем — вариант единственный, предпочтение не выражено.
        return None

    mine = axes_of(StyleParams.from_dict(json.loads(row["params_json"])))
    others = [
        axes_of(StyleParams.from_dict(json.loads(s["params_json"])))
        for s in siblings if s["id"] != variant_id
    ]
    return {a: mine[a] - sum(o[a] for o in others) / len(others) for a in AXES}


def record_choice(conn, variant_id: str, rating: int) -> None:
    """Событие вкуса: лайк, дизлайк или «этот вариант я забрал».

    Пишем сразу разницу с соседями, а не ссылку на вариант: варианты можно
    удалить, а выученное предпочтение должно пережить уборку.
    """
    if rating == 0:
        # Оценку сняли — забываем и мнение.
        conn.execute(
            "DELETE FROM taste_events WHERE user_id=? AND json_extract(payload_json,'$.variant_id')=?",
            (db.LOCAL_USER, variant_id),
        )
        _rebuild(conn)
        return
    delta = _delta_vs_siblings(conn, variant_id)
    if delta is None:
        return
    kind = "like" if rating > 0 else "dislike"
    # Одно мнение на вариант: повторный клик по 👍 (или смена оценки на
    # противоположную) заменяет прежнее событие, а не добавляет ещё одно.
    # Иначе пятикратный тык по одной карточке перекосил бы весь профиль.
    conn.execute(
        "DELETE FROM taste_events WHERE user_id=? AND json_extract(payload_json,'$.variant_id')=?",
        (db.LOCAL_USER, variant_id),
    )
    conn.execute(
        "INSERT INTO taste_events(id,user_id,kind,payload_json,created_at) VALUES(?,?,?,?,?)",
        (db.new_id(), db.LOCAL_USER, kind,
         json.dumps({"variant_id": variant_id, "delta": delta}, ensure_ascii=False),
         db.now_iso()),
    )
    _rebuild(conn)


def _rebuild(conn) -> dict:
    """Пересчёт профиля по последним событиям."""
    rows = conn.execute(
        "SELECT kind, payload_json FROM taste_events WHERE user_id=? "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        (db.LOCAL_USER, WINDOW),
    ).fetchall()

    sums = {a: 0.0 for a in AXES}
    used = 0
    for row in rows:
        payload = json.loads(row["payload_json"])
        delta = payload.get("delta")
        if not isinstance(delta, dict):
            continue  # событие старого формата — без разницы с соседями
        sign = 1.0 if row["kind"] == "like" else -1.0
        for axis in AXES:
            sums[axis] += sign * float(delta.get(axis, 0.0))
        used += 1

    bias = {a: 0.0 for a in AXES}
    if used:
        for axis in AXES:
            raw = sums[axis] / used / AXIS_SCALE
            bias[axis] = round(max(-1.0, min(1.0, raw)), 3)

    profile = {"bias": bias, "events": used}
    conn.execute(
        "INSERT INTO taste_profile(user_id,profile_json,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET profile_json=excluded.profile_json, "
        "updated_at=excluded.updated_at",
        (db.LOCAL_USER, json.dumps(profile, ensure_ascii=False), db.now_iso()),
    )
    return profile


def _stored(conn) -> dict:
    row = conn.execute(
        "SELECT profile_json FROM taste_profile WHERE user_id=?", (db.LOCAL_USER,)
    ).fetchone()
    if row is None:
        return {"bias": {a: 0.0 for a in AXES}, "events": 0}
    data = json.loads(row["profile_json"] or "{}")
    bias = data.get("bias") or {}
    return {"bias": {a: float(bias.get(a, 0.0)) for a in AXES}, "events": int(data.get("events", 0))}


def is_enabled() -> bool:
    from .routers.settings import get_settings

    return bool(get_settings().get("learning_enabled", True))


def get_profile() -> dict:
    """Профиль для экрана настроек: числа наружу не показываем, только слова."""
    with db.connect() as conn:
        profile = _stored(conn)
    active = profile["events"] >= MIN_EVENTS
    likes = []
    if active:
        for axis, value in sorted(profile["bias"].items(), key=lambda kv: -abs(kv[1])):
            if abs(value) >= MIN_BIAS:
                likes.append(AXIS_RU[axis][0 if value > 0 else 1])
    return {
        "enabled": is_enabled(),
        "events": profile["events"],
        "active": active and bool(likes),
        "likes_ru": likes,
        "summary_ru": _summary_ru(profile["events"], likes),
        "bias": profile["bias"],  # для отладки и тестов, в интерфейсе не показывается
    }


def _summary_ru(events: int, likes: list[str]) -> str:
    if events < MIN_EVENTS:
        left = MIN_EVENTS - events
        return f"Пока присматриваюсь — оцените ещё {left} вариант{'' if left == 1 else 'а'}"
    if not likes:
        return "Пока не вижу устойчивых предпочтений — оценивайте варианты дальше"
    return "Вам обычно нравится: " + ", ".join(likes)


def reset() -> dict:
    """Забыть всё выученное — по кнопке в настройках."""
    with db.connect() as conn:
        conn.execute("DELETE FROM taste_events WHERE user_id=?", (db.LOCAL_USER,))
        conn.execute("DELETE FROM taste_profile WHERE user_id=?", (db.LOCAL_USER,))
    return get_profile()


# Насколько сильно профиль двигает параметры при полном (|bias|=1) предпочтении.
# Держим малым: профиль подстраивает, а не подменяет выбранный стиль.
NUDGE = {
    "bass": {"bass_shelf_db": 2.0, "sub_db": 1.0},
    "vocal": {"gain_db.vocals": 1.5},
    "space": {"vocal_reverb": 0.15},
    "tempo": {"tempo_factor": -0.03},
    "bright": {"air_db": 1.5},
}


def apply_bias(params: StyleParams, bias: dict[str, float]) -> StyleParams:
    """Подкручиваем параметры варианта под вкус — мягко и в пределах разумного."""
    for axis, fields in NUDGE.items():
        value = bias.get(axis, 0.0)
        if abs(value) < MIN_BIAS:
            continue
        for field, amount in fields.items():
            shift = amount * value
            if field == "gain_db.vocals":
                gains = dict(params.gain_db)
                gains["vocals"] = gains.get("vocals", 0.0) + shift
                params.gain_db = gains
            elif field == "vocal_reverb":
                params.vocal_reverb = max(0.0, min(1.0, params.vocal_reverb + shift))
            elif field == "tempo_factor":
                params.tempo_factor = max(0.75, min(1.25, params.tempo_factor + shift))
            else:
                setattr(params, field, getattr(params, field) + shift)
    return params


def apply_to_variants(variants: list[dict]) -> str:
    """Подмешивает вкус в план генерации. Возвращает фразу для истории плана."""
    if not is_enabled():
        return ""
    with db.connect() as conn:
        profile = _stored(conn)
    if profile["events"] < MIN_EVENTS:
        return ""
    bias = profile["bias"]
    if all(abs(v) < MIN_BIAS for v in bias.values()):
        return ""
    for v in variants:
        apply_bias(v["params"], bias)
    likes = [AXIS_RU[a][0 if bias[a] > 0 else 1] for a in AXES if abs(bias[a]) >= MIN_BIAS]
    return "с учётом ваших предпочтений: " + ", ".join(likes)
