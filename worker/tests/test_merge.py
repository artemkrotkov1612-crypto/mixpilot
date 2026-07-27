"""Совместимость треков и стратегии соединения (без аудио — только логика)."""

import pytest

from mixpilot_worker.merge import compat, strategies


def track(idx, bpm, root="C", mode="major", labels=(("intro", 0, 10, 0.3), ("chorus", 10, 40, 0.9))):
    return {
        "track_id": f"t{idx}",
        "title": f"Песня {idx}",
        "duration_s": labels[-1][2],
        "bpm": bpm,
        "key_root": root,
        "key_mode": mode,
        "sections": [
            {"id": f"{lab}{i}", "label": lab, "start_s": s, "end_s": e, "energy": en}
            for i, (lab, s, e, en) in enumerate(labels)
        ],
    }


# --- совместимость ---

def test_tempo_factor_direct():
    assert compat.tempo_factor(120, 126) == pytest.approx(1.05, abs=0.01)


def test_tempo_factor_uses_double_time():
    # 72 и 140: правильно играть 72 «вдвое быстрее», а не растягивать вдвое
    factor = compat.tempo_factor(72, 140)
    assert 0.9 < factor < 1.1, factor


def test_tempo_factor_half_time():
    factor = compat.tempo_factor(160, 82)
    assert 0.95 < factor < 1.05, factor


def test_key_shift_same_key():
    assert compat.key_shift({"key_root": "C", "key_mode": "major"},
                            {"key_root": "C", "key_mode": "major"}) == 0


def test_key_shift_relative_minor_is_free():
    # A minor и C major — одни и те же ноты, сдвигать не нужно
    assert compat.key_shift({"key_root": "A", "key_mode": "minor"},
                            {"key_root": "C", "key_mode": "major"}) == 0


def test_key_shift_takes_shortest_path():
    # из B в C ближе вверх на 1, чем вниз на 11
    assert compat.key_shift({"key_root": "B", "key_mode": "major"},
                            {"key_root": "C", "key_mode": "major"}) == 1


def test_anchor_minimises_stretch():
    # 120 посередине: к нему тянуть дешевле, чем к краям
    plan = compat.build_plan([track(1, 100), track(2, 120), track(3, 140)])
    assert plan["anchor"] == 1
    assert plan["tracks"][1]["tempo_factor"] == 1.0


def test_warning_on_far_tempo():
    plan = compat.build_plan([track(1, 90), track(2, 125)])
    assert any("%" in w for w in plan["warnings"])


def test_no_warning_on_close_tempo():
    plan = compat.build_plan([track(1, 120), track(2, 124)])
    assert plan["warnings"] == []


def test_far_key_is_not_shifted():
    plan = compat.build_plan([
        track(1, 120, "C", "major"),
        track(2, 120, "F#", "major"),  # тритон — 6 полутонов
    ])
    assert all(abs(t["pitch_semitones"]) <= compat.MAX_PITCH_SHIFT for t in plan["tracks"])
    assert any("тональности" in w for w in plan["warnings"])


# --- стратегии ---

def test_auto_two_tracks_is_vocal_over_music():
    assert strategies.resolve_strategy("auto", 2) == "vocal_instr"


def test_auto_many_tracks_is_best_parts():
    assert strategies.resolve_strategy("auto", 5) == "best_parts"


def test_vocal_instr_layers_vocals_over_other_track():
    plan = strategies.build("vocal_instr", [track(1, 120), track(2, 120)], vocal_from=0, music_from=1)
    assert plan["layers"][0]["track_index"] == 0
    assert plan["layers"][0]["stem"] == "vocals"
    assert plan["sequence"][0]["track_index"] == 1
    assert plan["sequence"][0]["stem"] == "instrumental"


def test_vocal_instr_fixes_same_source():
    plan = strategies.build("vocal_instr", [track(1, 120), track(2, 120)], vocal_from=1, music_from=1)
    assert plan["layers"][0]["track_index"] != plan["sequence"][0]["track_index"]


def test_club_interleaves_tracks():
    plan = strategies.build("club", [track(1, 128), track(2, 128), track(3, 128)])
    order = [p["track_index"] for p in plan["sequence"]]
    assert len(set(order)) == 3
    assert order[0] != order[1]  # чередуются, а не подряд
    assert plan["xfade_ms"] < 500  # клубный переход короткий


def test_smooth_is_long_crossfade():
    plan = strategies.build("smooth", [track(1, 120), track(2, 122)])
    assert plan["xfade_ms"] >= 1000
    assert len(plan["sequence"]) == 2


def test_best_parts_orders_by_energy():
    quiet = track(1, 120, labels=(("verse", 0, 30, 0.2),))
    loud = track(2, 120, labels=(("chorus", 0, 30, 0.95),))
    plan = strategies.build("best_parts", [quiet, loud])
    assert plan["sequence"][0]["track_index"] == 0  # от спокойного к мощному
    assert plan["sequence"][-1]["track_index"] == 1


def test_long_sections_are_clipped():
    long_track = track(1, 120, labels=(("chorus", 0, 300, 0.9),))
    plan = strategies.build("best_parts", [long_track, track(2, 120)])
    for piece in plan["sequence"]:
        assert piece["end_s"] - piece["start_s"] <= strategies.MAX_PIECE_S + 0.01


def test_missing_structure_still_produces_plan():
    bare = {"track_id": "x", "title": "Без структуры", "duration_s": 120, "bpm": 120,
            "key_root": "C", "key_mode": "major", "sections": []}
    plan = strategies.build("best_parts", [bare, track(2, 120)])
    assert len(plan["sequence"]) >= 1
