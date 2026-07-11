"""Проекты-черновики: создание, автосохранение параметров, источники, недавние."""

import json

from fastapi import APIRouter
from pydantic import BaseModel

from .. import db
from ..errors import AppError, not_found

router = APIRouter(prefix="/projects", tags=["projects"])

MODES = {"remix", "merge", "voice_cover", "voice_self", "voice_overbeat"}
ROLES = {"source", "reference", "beat"}

DEFAULT_TITLES = {
    "remix": "Новый ремикс",
    "merge": "Соединение песен",
    "voice_cover": "Кавер моим голосом",
    "voice_self": "Моя запись",
    "voice_overbeat": "Партия поверх бита",
}


def _project_with_tracks(conn, project_id: str) -> dict:
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise not_found("проект не найден")
    tracks = conn.execute(
        """SELECT t.*, pt.role, pt.position FROM project_tracks pt
           JOIN tracks t ON t.id = pt.track_id
           WHERE pt.project_id=? ORDER BY pt.position, t.added_at""",
        (project_id,),
    ).fetchall()
    project = dict(row)
    project["params"] = json.loads(project.pop("params_json") or "{}")
    project["tracks"] = [dict(t) for t in tracks]
    return project


class CreateBody(BaseModel):
    mode: str
    title: str | None = None


@router.post("")
def create_project(body: CreateBody) -> dict:
    if body.mode not in MODES:
        raise AppError("E_BAD_REQUEST", f"неизвестный режим: {body.mode}")
    now = db.now_iso()
    project_id = db.new_id()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO projects(id,user_id,mode,title,status,params_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (project_id, db.LOCAL_USER, body.mode,
             (body.title or DEFAULT_TITLES[body.mode]).strip(), "draft", "{}", now, now),
        )
        return _project_with_tracks(conn, project_id)


@router.get("")
def list_projects(limit: int = 20, mode: str = "") -> dict:
    where, params = ["user_id=?"], [db.LOCAL_USER]
    if mode:
        where.append("mode=?")
        params.append(mode)
    params.append(min(limit, 100))
    with db.connect() as conn:
        rows = conn.execute(
            f"""SELECT p.*, (SELECT COUNT(*) FROM project_tracks pt WHERE pt.project_id=p.id) AS track_count
                FROM projects p WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC LIMIT ?""",
            params,
        ).fetchall()
    projects = []
    for r in rows:
        p = dict(r)
        p["params"] = json.loads(p.pop("params_json") or "{}")
        projects.append(p)
    return {"projects": projects}


@router.get("/{project_id}")
def get_project(project_id: str) -> dict:
    with db.connect() as conn:
        return _project_with_tracks(conn, project_id)


class PatchBody(BaseModel):
    title: str | None = None
    params: dict | None = None
    status: str | None = None


@router.patch("/{project_id}")
def patch_project(project_id: str, body: PatchBody) -> dict:
    sets, params = ["updated_at=?"], [db.now_iso()]
    if body.title is not None and body.title.strip():
        sets.append("title=?")
        params.append(body.title.strip())
    if body.params is not None:
        sets.append("params_json=?")
        params.append(json.dumps(body.params, ensure_ascii=False))
    if body.status is not None:
        if body.status not in {"draft", "processing", "ready", "error"}:
            raise AppError("E_BAD_REQUEST", f"неизвестный статус: {body.status}")
        sets.append("status=?")
        params.append(body.status)
    params.append(project_id)
    with db.connect() as conn:
        cur = conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", params)
        if cur.rowcount == 0:
            raise not_found("проект не найден")
        return _project_with_tracks(conn, project_id)


class AttachBody(BaseModel):
    track_id: str
    role: str = "source"
    position: int = 0


@router.post("/{project_id}/tracks")
def attach_track(project_id: str, body: AttachBody) -> dict:
    if body.role not in ROLES:
        raise AppError("E_BAD_REQUEST", f"неизвестная роль: {body.role}")
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
            raise not_found("проект не найден")
        if conn.execute("SELECT 1 FROM tracks WHERE id=?", (body.track_id,)).fetchone() is None:
            raise not_found("трек не найден")
        conn.execute(
            "INSERT OR REPLACE INTO project_tracks(project_id,track_id,position,role) VALUES(?,?,?,?)",
            (project_id, body.track_id, body.position, body.role),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now_iso(), project_id))
        return _project_with_tracks(conn, project_id)


@router.delete("/{project_id}/tracks/{track_id}")
def detach_track(project_id: str, track_id: str) -> dict:
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM project_tracks WHERE project_id=? AND track_id=?",
            (project_id, track_id),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now_iso(), project_id))
        return _project_with_tracks(conn, project_id)


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict:
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        if cur.rowcount == 0:
            raise not_found("проект не найден")
    return {"deleted": project_id}
