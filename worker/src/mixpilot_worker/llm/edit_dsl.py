"""Edit DSL v1: правки как операции над параметрами варианта (ТЗ §8).

Чипы UI мапятся в те же операции без облака (работают офлайн). Свободный
текст → DSL через Claude подключит M4; здесь — валидатор и применение.
"""

from __future__ import annotations

from dataclasses import replace

from ..styles.base import StyleParams

# Диапазоны-клампы (защита от абсурдных значений).
TEMPO_MIN, TEMPO_MAX = 0.6, 1.6
PITCH_MIN, PITCH_MAX = -6.0, 6.0
GAIN_TARGETS = {"vocals", "drums", "bass", "other"}

# Чип UI -> список операций DSL.
CHIP_OPS: dict[str, list[dict]] = {
    "Больше баса": [{"op": "bass", "amount": 1}],
    "Меньше баса": [{"op": "bass", "amount": -1}],
    "Громче голос": [{"op": "gain", "target": "vocals", "db": 2}],
    "Тише голос": [{"op": "gain", "target": "vocals", "db": -2}],
    "Быстрее": [{"op": "tempo", "delta": 0.06}],
    "Медленнее": [{"op": "tempo", "delta": -0.06}],
    "Мощнее припев": [{"op": "energy", "amount": 1}],
    "Короче вступление": [{"op": "intro_shorter"}],
    "Больше атмосферы": [{"op": "reverb", "amount": 1}],
    "Ярче": [{"op": "air", "db": 2}],
    "Мрачнее": [{"op": "mood", "name": "dark"}],
}


class DslError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def chips_to_ops(chips: list[str]) -> list[dict]:
    ops: list[dict] = []
    for chip in chips or []:
        if chip in CHIP_OPS:
            ops.extend(CHIP_OPS[chip])
    return ops


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def validate_ops(ops: list[dict]) -> list[dict]:
    """Пропускает только известные операции с корректными полями."""
    if not isinstance(ops, list):
        raise DslError("ops должен быть списком")
    clean: list[dict] = []
    for op in ops:
        if not isinstance(op, dict) or "op" not in op:
            raise DslError("операция без поля op")
        kind = op["op"]
        if kind == "gain" and op.get("target") not in GAIN_TARGETS:
            raise DslError(f"gain: неизвестный target {op.get('target')}")
        if kind not in _KNOWN_OPS:
            raise DslError(f"неизвестная операция: {kind}")
        clean.append(op)
    return clean


def apply_ops(params: StyleParams, ops: list[dict]) -> StyleParams:
    """Применяет операции к копии параметров. Неизвестные — уже отсеяны validate_ops."""
    p = params
    gain = dict(p.gain_db)
    for op in ops:
        kind = op["op"]
        if kind == "tempo":
            delta = float(op.get("delta", 0.0))
            factor = float(op["factor"]) if "factor" in op else p.tempo_factor + delta
            p = replace(p, tempo_factor=_clamp(factor, TEMPO_MIN, TEMPO_MAX))
        elif kind == "pitch":
            semis = float(op.get("semitones", 0.0))
            p = replace(p, pitch_semitones=_clamp(p.pitch_semitones + semis, PITCH_MIN, PITCH_MAX))
        elif kind == "gain":
            tgt = op["target"]
            gain[tgt] = _clamp(gain.get(tgt, 0.0) + float(op.get("db", 0.0)), -12.0, 12.0)
        elif kind == "bass":
            amt = float(op.get("amount", 0.0))
            p = replace(p, bass_shelf_db=_clamp(p.bass_shelf_db + 3.0 * amt, -6.0, 18.0),
                        sub_db=_clamp(p.sub_db + 1.5 * amt, -6.0, 12.0),
                        bass_drive_db=_clamp(p.bass_drive_db + 2.0 * max(amt, 0), 0.0, 14.0))
        elif kind == "energy":
            amt = float(op.get("amount", 0.0))
            p = replace(p, comp_ratio=_clamp(p.comp_ratio + 0.5 * amt, 1.0, 6.0),
                        air_db=_clamp(p.air_db + 1.5 * amt, -6.0, 8.0))
        elif kind == "reverb":
            amt = float(op.get("amount", 0.0))
            p = replace(p, vocal_reverb=_clamp(p.vocal_reverb + 0.12 * amt, 0.0, 0.7))
        elif kind == "air":
            p = replace(p, air_db=_clamp(p.air_db + float(op.get("db", 0.0)), -6.0, 8.0))
        elif kind == "mood":
            if op.get("name") == "dark":
                p = replace(p, pitch_semitones=_clamp(p.pitch_semitones - 1.0, PITCH_MIN, PITCH_MAX),
                            warmth_db=_clamp(min(p.warmth_db, 0.0) - 2.0, -8.0, 0.0))
            elif op.get("name") == "energetic":
                p = replace(p, air_db=_clamp(p.air_db + 2.0, -6.0, 8.0))
        elif kind == "intro_shorter":
            pass  # структурная правка обрабатывается на уровне пайплайна (M4-структура)
    return replace(p, gain_db=gain)


_KNOWN_OPS = {"tempo", "pitch", "gain", "bass", "energy", "reverb", "air", "mood", "intro_shorter"}
