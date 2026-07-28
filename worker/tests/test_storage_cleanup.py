"""Очистка кеша: освобождает место, но никогда не трогает то, что не вернуть."""

from mixpilot_worker import config, db


def _fill(path, name, size=2048):
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_bytes(b"x" * size)


def test_storage_reports_free_space(client):
    body = client.get("/storage").json()
    assert body["disk_free_gb"] > 0
    assert body["disk_total_gb"] >= body["disk_free_gb"]
    for key in ("media_mb", "cache_mb", "renders_mb", "models_mb", "voice_mb", "tmp_mb"):
        assert key in body


def test_cleanup_options_show_sizes(client):
    base = config.data_dir()
    _fill(base / "cache" / "stems", "a.wav", 200_000)
    items = {i["key"]: i for i in client.get("/storage/cleanup").json()["items"]}
    assert items["cache"]["size_mb"] > 0
    assert items["cache"]["note_ru"]


def test_cleanup_frees_cache_and_keeps_originals(client):
    base = config.data_dir()
    _fill(base / "cache" / "stems", "vocals.wav", 200_000)
    _fill(base / "media" / "originals", "song.mp3", 200_000)
    _fill(base / "tmp", "leftover.tmp", 50_000)

    body = client.post("/storage/cleanup", json={"keys": ["cache", "tmp"]}).json()

    assert body["freed_mb"] > 0
    assert not (base / "cache" / "stems" / "vocals.wav").exists()
    assert not (base / "tmp" / "leftover.tmp").exists()
    # Оригинал пользователя на месте, папки восстановлены
    assert (base / "media" / "originals" / "song.mp3").exists()
    assert (base / "cache" / "stems").is_dir()


def test_cleanup_drops_stale_stem_records(client):
    """Записи о дорожках без файлов — путь к падению при следующей генерации."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO tracks(id,user_id,title,duration_s,media_path,content_hash,added_at) "
            "VALUES('t1',?,'песня',10,'t1.wav','hash1',?)", (db.LOCAL_USER, db.now_iso()))
        conn.execute("INSERT INTO stems_cache(track_id,model,path_vocals,created_at) "
                     "VALUES('t1','htdemucs','x.wav',?)", (db.now_iso(),))
        conn.execute("INSERT INTO track_analysis(track_id,bpm,engine_ver,analyzed_at) "
                     "VALUES('t1',120,'v1',?)", (db.now_iso(),))

    client.post("/storage/cleanup", json={"keys": ["cache"]})

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM stems_cache").fetchone()["c"] == 0
        # Темп и структура файлов не требуют — их выбрасывать незачем
        assert conn.execute("SELECT COUNT(*) c FROM track_analysis").fetchone()["c"] == 1


def test_cannot_clean_user_content(client):
    """Оригиналы и записи голоса не должны удаляться даже по прямому запросу."""
    for key in ("media", "voice", "renders", "db"):
        res = client.post("/storage/cleanup", json={"keys": [key]})
        assert res.status_code == 400, key
