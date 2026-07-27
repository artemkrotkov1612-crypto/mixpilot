"""Edit DSL: маппинг чипов, валидация, клампы, применение к параметрам."""

import pytest

from mixpilot_worker.llm import edit_dsl
from mixpilot_worker.styles.base import StyleParams


def test_chips_to_ops():
    ops = edit_dsl.chips_to_ops(["Больше баса", "Быстрее", "неизвестный чип"])
    kinds = [o["op"] for o in ops]
    assert "bass" in kinds and "tempo" in kinds
    assert len(ops) == 2  # неизвестный чип отброшен


def test_validate_rejects_unknown():
    with pytest.raises(edit_dsl.DslError):
        edit_dsl.validate_ops([{"op": "hack_the_planet"}])
    with pytest.raises(edit_dsl.DslError):
        edit_dsl.validate_ops([{"op": "gain", "target": "guitar", "db": 3}])
    with pytest.raises(edit_dsl.DslError):
        edit_dsl.validate_ops("not a list")


def test_apply_bass_and_tempo():
    p = StyleParams(bass_shelf_db=2.0, tempo_factor=0.9)
    out = edit_dsl.apply_ops(p, [{"op": "bass", "amount": 1}, {"op": "tempo", "delta": 0.06}])
    assert out.bass_shelf_db > p.bass_shelf_db
    assert out.tempo_factor > 0.9
    # исходные параметры не мутированы
    assert p.bass_shelf_db == 2.0 and p.tempo_factor == 0.9


def test_apply_gain_accumulates_and_clamps():
    p = StyleParams(gain_db={"vocals": 10.0})
    out = edit_dsl.apply_ops(p, [{"op": "gain", "target": "vocals", "db": 6}])
    assert out.gain_db["vocals"] == 12.0  # клампится к +12


def test_tempo_clamped():
    p = StyleParams(tempo_factor=1.5)
    out = edit_dsl.apply_ops(p, [{"op": "tempo", "delta": 1.0}])
    assert out.tempo_factor <= edit_dsl.TEMPO_MAX


def test_roundtrip_serialization():
    p = StyleParams(bass_shelf_db=6.0, gain_db={"bass": 3.0}, tempo_factor=0.86)
    restored = StyleParams.from_dict(p.to_dict())
    assert restored == p
    # from_dict игнорирует посторонние ключи
    noisy = StyleParams.from_dict({**p.to_dict(), "garbage": 123})
    assert noisy == p
