from pathlib import Path

from mixpilot_worker import config


def test_import_and_list(client, sine_wav: Path):
    res = client.post("/library/import", json={"path": str(sine_wav)})
    assert res.status_code == 200, res.text
    track = res.json()
    assert track["duplicate"] is False
    assert 1.8 < track["duration_s"] < 2.2
    assert track["title"] == "sine"
    # копия в хранилище, исходник не тронут
    assert (config.originals_dir() / track["media_path"]).exists()
    assert sine_wav.exists()

    listing = client.get("/library/tracks").json()
    assert listing["total"] == 1
    assert listing["tracks"][0]["id"] == track["id"]


def test_import_duplicate(client, sine_wav: Path):
    first = client.post("/library/import", json={"path": str(sine_wav)}).json()
    second = client.post("/library/import", json={"path": str(sine_wav)}).json()
    assert second["duplicate"] is True
    assert second["id"] == first["id"]
    assert client.get("/library/tracks").json()["total"] == 1


def test_import_errors(client, tmp_path: Path):
    missing = client.post("/library/import", json={"path": str(tmp_path / "nope.mp3")})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "E_FILE_ACCESS"

    bad = tmp_path / "not_audio.mp3"
    bad.write_bytes(b"definitely not audio")
    res = client.post("/library/import", json={"path": str(bad)})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "E_DECODE"

    txt = tmp_path / "readme.txt"
    txt.write_text("hi")
    res = client.post("/library/import", json={"path": str(txt)})
    assert res.json()["error"]["code"] == "E_DECODE"


def test_peaks(client, sine_wav: Path):
    track = client.post("/library/import", json={"path": str(sine_wav)}).json()
    doc = client.get(f"/library/tracks/{track['id']}/peaks").json()
    assert doc["buckets"] == len(doc["peaks"]) == 1000
    assert max(doc["peaks"]) <= 1.0
    assert max(doc["peaks"]) > 0.05  # огибающая не пустая (lavfi-синус тихий: ~0.09)


def test_favorite_and_delete(client, sine_wav: Path):
    track = client.post("/library/import", json={"path": str(sine_wav)}).json()
    fav = client.patch(f"/library/tracks/{track['id']}", json={"is_favorite": True}).json()
    assert fav["is_favorite"] == 1
    assert client.get("/library/tracks", params={"favorite": True}).json()["total"] == 1

    media_file = config.originals_dir() / track["media_path"]
    assert client.delete(f"/library/tracks/{track['id']}").status_code == 200
    assert not media_file.exists()
    assert sine_wav.exists()  # исходник пользователя жив
    assert client.get("/library/tracks").json()["total"] == 0


def test_search_and_sort(client, sine_wav: Path, tmp_path: Path, ffmpeg_bin: str):
    import subprocess

    other = tmp_path / "Другая мелодия.wav"
    subprocess.run(
        [ffmpeg_bin, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
         "-ar", "44100", str(other)],
        check=True, capture_output=True,
    )
    client.post("/library/import", json={"path": str(sine_wav)})
    client.post("/library/import", json={"path": str(other)})

    found = client.get("/library/tracks", params={"q": "друга"}).json()["tracks"]
    assert len(found) == 1 and found[0]["title"] == "Другая мелодия"

    by_title = client.get("/library/tracks", params={"sort": "title"}).json()["tracks"]
    assert [t["title"] for t in by_title] == sorted(
        (t["title"] for t in by_title), key=str.casefold
    )
