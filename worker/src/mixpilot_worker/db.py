"""SQLite: полная схема из ТЗ §6, WAL, миграции через PRAGMA user_version.

Подключение — новое на операцию (дёшево для desktop-нагрузки, без гонок
между потоками threadpool'а FastAPI). Писатель один — этот процесс.
"""

import datetime as dt
import sqlite3
import uuid
from contextlib import contextmanager

from . import config

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(
  user_id TEXT NOT NULL REFERENCES users(id),
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  PRIMARY KEY(user_id, key)
);
CREATE TABLE IF NOT EXISTS tracks(
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  artist TEXT,
  duration_s REAL NOT NULL,
  sample_rate INTEGER,
  format TEXT,
  src_path TEXT,
  media_path TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  added_at TEXT NOT NULL,
  is_favorite INTEGER NOT NULL DEFAULT 0,
  origin TEXT NOT NULL DEFAULT 'import'
);
CREATE INDEX IF NOT EXISTS idx_tracks_added ON tracks(added_at DESC);
CREATE TABLE IF NOT EXISTS track_analysis(
  track_id TEXT PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
  bpm REAL, bpm_conf REAL,
  key_root TEXT, key_mode TEXT, key_conf REAL,
  beats_json TEXT, downbeats_json TEXT, sections_json TEXT,
  analyzed_at TEXT, engine_ver TEXT
);
CREATE TABLE IF NOT EXISTS stems_cache(
  track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  path_vocals TEXT, path_drums TEXT, path_bass TEXT, path_other TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY(track_id, model)
);
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  mode TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  params_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
CREATE TABLE IF NOT EXISTS project_tracks(
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 0,
  role TEXT NOT NULL DEFAULT 'source',
  PRIMARY KEY(project_id, track_id, role)
);
CREATE TABLE IF NOT EXISTS generations(
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  request_json TEXT NOT NULL,
  plan_json TEXT,
  quality_mode TEXT NOT NULL DEFAULT 'fast',
  status TEXT NOT NULL DEFAULT 'queued',
  error_code TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS generation_variants(
  id TEXT PRIMARY KEY,
  generation_id TEXT NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  title_ru TEXT NOT NULL,
  description_ru TEXT,
  render_wav TEXT,
  render_peaks TEXT,
  params_json TEXT NOT NULL DEFAULT '{}',
  parent_variant_id TEXT,
  rating INTEGER NOT NULL DEFAULT 0,
  cover_path TEXT,
  custom_title TEXT
);
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued',
  priority INTEGER NOT NULL DEFAULT 50,
  progress REAL NOT NULL DEFAULT 0,
  stage TEXT,
  error_code TEXT,
  error_detail TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  gpu INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority, created_at);
CREATE TABLE IF NOT EXISTS voice_profiles(
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'empty',
  dataset_dir TEXT,
  model_path TEXT,
  index_path TEXT,
  quality_json TEXT,
  minutes_recorded REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  trained_at TEXT
);
CREATE TABLE IF NOT EXISTS voice_clips(
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES voice_profiles(id) ON DELETE CASCADE,
  step INTEGER NOT NULL,
  idx INTEGER NOT NULL,
  path TEXT NOT NULL,
  duration_s REAL NOT NULL DEFAULT 0,
  quality_json TEXT,
  accepted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS taste_events(
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS taste_profile(
  user_id TEXT PRIMARY KEY REFERENCES users(id),
  profile_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL,
  learning_enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS lyrics(
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  text TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS exports(
  id TEXT PRIMARY KEY,
  variant_id TEXT NOT NULL REFERENCES generation_variants(id) ON DELETE CASCADE,
  format TEXT NOT NULL,
  path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""

LOCAL_USER = "local"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def connect():
    conn = sqlite3.connect(config.db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    # LIKE в SQLite не сворачивает регистр кириллицы — даём поиску честный casefold.
    conn.create_function(
        "casefold", 1, lambda s: s.casefold() if isinstance(s, str) else s, deterministic=True
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def init_db() -> None:
    config.ensure_dirs()
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA user_version=1")
            version = 1
        if version < 2:
            # M7: своё название и обложка варианта. На новой базе колонки уже
            # есть из _SCHEMA, на базе пользователя с M6 — добавляем.
            for column, ddl in (("cover_path", "TEXT"), ("custom_title", "TEXT")):
                if not _has_column(conn, "generation_variants", column):
                    conn.execute(f"ALTER TABLE generation_variants ADD COLUMN {column} {ddl}")
            conn.execute("PRAGMA user_version=2")
        conn.execute(
            "INSERT OR IGNORE INTO users(id, name, created_at) VALUES(?,?,?)",
            (LOCAL_USER, "Локальный пользователь", now_iso()),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
