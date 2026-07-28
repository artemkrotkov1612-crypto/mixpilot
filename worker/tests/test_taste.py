"""Профиль вкуса: учится на выборе, объясняет словами, выключается и стирается."""

import json

import pytest

from mixpilot_worker import db, taste
from mixpilot_worker.styles.base import StyleParams


def _generation(conn, project_id="p1"):
    conn.execute("INSERT OR IGNORE INTO projects(id,user_id,mode,title,created_at,updated_at) "
                 "VALUES(?,?,?,?,?,?)",
                 (project_id, db.LOCAL_USER, "remix", "тест", db.now_iso(), db.now_iso()))
    gen_id = db.new_id()
    conn.execute("INSERT INTO generations(id,project_id,request_json,created_at) VALUES(?,?,?,?)",
                 (gen_id, project_id, "{}", db.now_iso()))
    return gen_id


def _variant(conn, gen_id, idx, params: StyleParams) -> str:
    vid = db.new_id()
    conn.execute(
        "INSERT INTO generation_variants(id,generation_id,idx,title_ru,params_json) VALUES(?,?,?,?,?)",
        (vid, gen_id, idx, f"Вариант {idx}", json.dumps(params.to_dict(), ensure_ascii=False)),
    )
    return vid


def _bassy_generation(conn, bass_db=6.0):
    """Три варианта, отличающиеся только количеством низа."""
    gen_id = _generation(conn)
    heavy = _variant(conn, gen_id, 0, StyleParams(bass_shelf_db=bass_db))
    mid = _variant(conn, gen_id, 1, StyleParams(bass_shelf_db=0.0))
    light = _variant(conn, gen_id, 2, StyleParams(bass_shelf_db=-bass_db))
    return heavy, mid, light


def test_axes_read_human_dimensions():
    axes = taste.axes_of(StyleParams(bass_shelf_db=4.0, sub_db=2.0, tempo_factor=0.9,
                                     vocal_reverb=0.5, air_db=3.0))
    assert axes["bass"] == pytest.approx(6.0)
    assert axes["tempo"] == pytest.approx(2.0)   # медленнее = плюс
    assert axes["space"] == pytest.approx(5.0)
    assert axes["bright"] == pytest.approx(3.0)


def test_likes_teach_preference(client):
    with db.connect() as conn:
        for _ in range(taste.MIN_EVENTS):
            heavy, _mid, _light = _bassy_generation(conn)
            taste.record_choice(conn, heavy, 1)

    profile = taste.get_profile()
    assert profile["active"] is True
    assert profile["bias"]["bass"] > taste.MIN_BIAS
    assert "мощный низ" in profile["summary_ru"]


def test_dislikes_teach_the_opposite(client):
    with db.connect() as conn:
        for _ in range(taste.MIN_EVENTS):
            heavy, _mid, _light = _bassy_generation(conn)
            taste.record_choice(conn, heavy, -1)

    profile = taste.get_profile()
    assert profile["bias"]["bass"] < -taste.MIN_BIAS
    assert "лёгкий низ" in profile["summary_ru"]


def test_preference_is_relative_not_absolute(client):
    """Если у всех вариантов бас одинаковый, лайк ничему не учит:
    иначе профиль выучил бы стиль, а не вкус."""
    with db.connect() as conn:
        for _ in range(5):
            gen_id = _generation(conn)
            same = [_variant(conn, gen_id, i, StyleParams(bass_shelf_db=6.0)) for i in range(3)]
            taste.record_choice(conn, same[0], 1)

    assert taste.get_profile()["bias"]["bass"] == pytest.approx(0.0, abs=1e-6)


def test_single_variant_gives_no_signal(client):
    with db.connect() as conn:
        gen_id = _generation(conn)
        only = _variant(conn, gen_id, 0, StyleParams(bass_shelf_db=6.0))
        taste.record_choice(conn, only, 1)

    assert taste.get_profile()["events"] == 0


def test_quiet_until_enough_events(client):
    with db.connect() as conn:
        heavy, _mid, _light = _bassy_generation(conn)
        taste.record_choice(conn, heavy, 1)

    profile = taste.get_profile()
    assert profile["active"] is False
    assert "присматриваюсь" in profile["summary_ru"]


def test_profile_nudges_variants(client):
    with db.connect() as conn:
        for _ in range(taste.MIN_EVENTS):
            heavy, _mid, _light = _bassy_generation(conn)
            taste.record_choice(conn, heavy, 1)

    variants = [{"params": StyleParams(bass_shelf_db=0.0)}]
    summary = taste.apply_to_variants(variants)
    assert variants[0]["params"].bass_shelf_db > 0
    assert "мощный низ" in summary


def test_disabled_learning_changes_nothing(client):
    with db.connect() as conn:
        for _ in range(taste.MIN_EVENTS):
            heavy, _mid, _light = _bassy_generation(conn)
            taste.record_choice(conn, heavy, 1)
    client.put("/settings", json={"key": "learning_enabled", "value": False})

    variants = [{"params": StyleParams(bass_shelf_db=0.0)}]
    assert taste.apply_to_variants(variants) == ""
    assert variants[0]["params"].bass_shelf_db == 0.0


def test_nudge_is_bounded(client):
    """Даже при полном предпочтении профиль не уводит звук в крайность."""
    params = StyleParams(tempo_factor=1.0, vocal_reverb=0.9)
    taste.apply_bias(params, {a: 1.0 for a in taste.AXES})
    assert 0.9 < params.tempo_factor <= 1.0
    assert params.vocal_reverb <= 1.0
    assert params.bass_shelf_db <= 2.0


def test_repeated_clicks_count_once(client):
    """Пять раз ткнуть 👍 по одной карточке — это по-прежнему одно мнение,
    иначе один трек перекосил бы весь профиль (поймано живым прогоном M7)."""
    with db.connect() as conn:
        heavy, _mid, _light = _bassy_generation(conn)
        for _ in range(5):
            taste.record_choice(conn, heavy, 1)

    assert taste.get_profile()["events"] == 1


def test_changing_your_mind_replaces_the_old_opinion(client):
    with db.connect() as conn:
        heavy, _mid, _light = _bassy_generation(conn)
        taste.record_choice(conn, heavy, 1)
        taste.record_choice(conn, heavy, -1)

    profile = taste.get_profile()
    assert profile["events"] == 1
    assert profile["bias"]["bass"] < 0  # осталась только последняя оценка


def test_removing_rating_forgets_it(client):
    with db.connect() as conn:
        heavy, _mid, _light = _bassy_generation(conn)
        taste.record_choice(conn, heavy, 1)
        taste.record_choice(conn, heavy, 0)

    assert taste.get_profile()["events"] == 0


def test_reset_forgets_everything(client):
    with db.connect() as conn:
        for _ in range(taste.MIN_EVENTS):
            heavy, _mid, _light = _bassy_generation(conn)
            taste.record_choice(conn, heavy, 1)

    after = taste.reset()
    assert after["events"] == 0
    assert after["active"] is False
    assert taste.apply_to_variants([{"params": StyleParams()}]) == ""


def test_feedback_endpoint_feeds_profile(client, monkeypatch):
    with db.connect() as conn:
        heavy, _mid, _light = _bassy_generation(conn)
    res = client.post(f"/variants/{heavy}/feedback", json={"rating": 1})
    assert res.status_code == 200
    assert taste.get_profile()["events"] == 1


def test_taste_endpoints(client):
    assert client.get("/taste").json()["enabled"] is True
    assert client.delete("/taste").json()["events"] == 0
