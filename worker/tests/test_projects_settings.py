import time


def test_project_draft_autosave_and_recent(client, sine_wav):
    track = client.post("/library/import", json={"path": str(sine_wav)}).json()

    created = client.post("/projects", json={"mode": "remix"}).json()
    assert created["status"] == "draft" and created["title"] == "Новый ремикс"

    attached = client.post(
        f"/projects/{created['id']}/tracks", json={"track_id": track["id"]}
    ).json()
    assert [t["id"] for t in attached["tracks"]] == [track["id"]]

    params = {"style": "phonk", "chips": ["Мрачно"], "text": "бас мощнее", "quality": "max"}
    patched = client.patch(f"/projects/{created['id']}", json={"params": params}).json()
    assert patched["params"] == params

    # «перезапуск»: данные читаются заново и порядок недавних по updated_at
    time.sleep(1.1)  # ISO-секунды: гарантируем различие updated_at
    second = client.post("/projects", json={"mode": "merge"}).json()
    recent = client.get("/projects", params={"limit": 10}).json()["projects"]
    assert [p["id"] for p in recent][:2] == [second["id"], created["id"]]
    assert recent[1]["params"]["style"] == "phonk"
    assert recent[1]["track_count"] == 1

    restored = client.get(f"/projects/{created['id']}").json()
    assert restored["params"]["text"] == "бас мощнее"
    assert restored["tracks"][0]["title"] == "sine"


def test_project_validation(client):
    assert client.post("/projects", json={"mode": "unknown"}).status_code == 400
    assert client.get("/projects/deadbeef").status_code == 404


def test_settings_roundtrip(client):
    defaults = client.get("/settings").json()
    assert defaults["quality_mode"] == "fast"

    updated = client.put("/settings", json={"key": "quality_mode", "value": "max"}).json()
    assert updated["quality_mode"] == "max"

    bad = client.put("/settings", json={"key": "hack", "value": 1})
    assert bad.status_code == 400

    storage = client.get("/storage").json()
    assert storage["disk_free_gb"] > 0
    assert "MixPilot" in storage["data_dir"] or "data" in storage["data_dir"]
