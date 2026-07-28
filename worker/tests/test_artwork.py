"""Название и обложка: работают всегда, в том числе без облака."""

import json

import pytest
from PIL import Image

from mixpilot_worker import config, db
from mixpilot_worker.artwork import cover, naming
from mixpilot_worker.errors import AppError


def _variant_with_peaks(client, tmp_path):
    """Готовая генерация с посчитанными пиками — как после настоящего рендера."""
    with db.connect() as conn:
        conn.execute("INSERT INTO tracks(id,user_id,title,duration_s,media_path,content_hash,added_at)"
                     " VALUES('t1',?,'Летний дождь',180,'t1.mp3','h1',?)",
                     (db.LOCAL_USER, db.now_iso()))
        conn.execute("INSERT INTO projects(id,user_id,mode,title,created_at,updated_at)"
                     " VALUES('p1',?,'remix','проект',?,?)",
                     (db.LOCAL_USER, db.now_iso(), db.now_iso()))
        conn.execute("INSERT INTO project_tracks(project_id,track_id,role) VALUES('p1','t1','source')")
        conn.execute("INSERT INTO track_analysis(track_id,bpm,engine_ver,analyzed_at)"
                     " VALUES('t1',128,'v1',?)", (db.now_iso(),))
        conn.execute("INSERT INTO generations(id,project_id,request_json,plan_json,created_at)"
                     " VALUES('g1','p1','{}',?,?)",
                     (json.dumps({"style": "phonk", "style_name": "Phonk"}), db.now_iso()))
        peaks_rel = "renders/g1/variant_0.peaks.json"
        path = config.data_dir() / peaks_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"peaks": [0.2, 0.9, 0.5, 0.7] * 30}), encoding="utf-8")
        conn.execute("INSERT INTO generation_variants(id,generation_id,idx,title_ru,description_ru,"
                     "render_peaks) VALUES('v1','g1',0,'Вариант A','Студийно',?)", (peaks_rel,))
    return "v1"


# --- обложка ---

def test_cover_is_a_real_image(tmp_path):
    out = cover.render_cover("Ночной ход", "Phonk · Летний дождь", [0.3, 0.8] * 60, "phonk",
                             tmp_path / "c.png")
    with Image.open(out) as img:
        assert img.size == (cover.SIZE, cover.SIZE)
        assert img.mode == "RGB"
        # Картинка не должна быть однотонной заливкой
        assert len(img.convert("RGB").getcolors(maxcolors=1 << 20)) > 500


def test_cover_differs_by_track(tmp_path):
    """Обложка строится из волны — у разных треков она разная."""
    a = cover.render_cover("Один", "", [0.1, 0.2] * 60, "club", tmp_path / "a.png")
    b = cover.render_cover("Один", "", [0.9, 0.4] * 60, "club", tmp_path / "b.png")
    assert a.read_bytes() != b.read_bytes()


def test_cover_differs_by_style(tmp_path):
    peaks = [0.5] * 120
    a = cover.render_cover("Раз", "", peaks, "phonk", tmp_path / "a.png")
    b = cover.render_cover("Раз", "", peaks, "house", tmp_path / "b.png")
    assert a.read_bytes() != b.read_bytes()


def test_cover_survives_long_title_and_no_peaks(tmp_path):
    out = cover.render_cover("Очень длинное название которое точно не влезет в одну строку",
                             "", [], "unknown_style", tmp_path / "c.png")
    assert out.exists() and out.stat().st_size > 0


def test_peaks_from_broken_file_are_empty(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("не json", encoding="utf-8")
    assert cover.peaks_from_file(bad) == []
    assert cover.peaks_from_file(tmp_path / "нет-такого.json") == []


# --- названия ---

def test_titles_fall_back_without_cloud(monkeypatch):
    def no_cloud():
        raise AppError("E_CLOUD_OFF", "облако выключено")

    monkeypatch.setattr(naming, "get_provider", no_cloud)
    result = naming.suggest_titles(source_title="Летний дождь", style="phonk")

    assert result["source"] == "local"
    assert len(result["titles"]) == 5
    assert any("Летний дождь" in t for t in result["titles"])


def test_titles_use_cloud_when_available(monkeypatch):
    class FakeProvider:
        def complete(self, system, user):
            return '{"titles": ["Дым", "Трасса"], "cover_idea_ru": "неон в тумане"}'

    monkeypatch.setattr(naming, "get_provider", lambda: FakeProvider())
    result = naming.suggest_titles(style="phonk")

    assert result["source"] == "cloud"
    assert result["titles"] == ["Дым", "Трасса"]


def test_garbage_from_cloud_falls_back(monkeypatch):
    class FakeProvider:
        def complete(self, system, user):
            return "конечно! вот названия: раз, два, три"

    monkeypatch.setattr(naming, "get_provider", lambda: FakeProvider())
    assert naming.suggest_titles(style="club")["source"] == "local"


# --- через API ---

def test_titles_endpoint(client, tmp_path, monkeypatch):
    variant_id = _variant_with_peaks(client, tmp_path)
    monkeypatch.setattr(naming, "get_provider",
                        lambda: (_ for _ in ()).throw(AppError("E_CLOUD_OFF", "выкл")))
    body = client.get(f"/variants/{variant_id}/titles").json()
    assert len(body["titles"]) == 5
    assert body["cloud"] is False


def test_cover_endpoint_makes_and_serves_png(client, tmp_path):
    variant_id = _variant_with_peaks(client, tmp_path)

    made = client.post(f"/variants/{variant_id}/cover", json={"title": "Ночной ход"}).json()
    assert made["title"] == "Ночной ход"
    assert (config.data_dir() / made["cover_path"]).exists()

    served = client.get(f"/variants/{variant_id}/cover.png")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"

    with db.connect() as conn:
        row = conn.execute("SELECT custom_title FROM generation_variants WHERE id=?",
                           (variant_id,)).fetchone()
    assert row["custom_title"] == "Ночной ход"


def test_cover_missing_before_it_is_made(client, tmp_path):
    variant_id = _variant_with_peaks(client, tmp_path)
    assert client.get(f"/variants/{variant_id}/cover.png").status_code == 404


def test_unknown_variant(client):
    assert client.get("/variants/нет-такого/titles").status_code == 404
