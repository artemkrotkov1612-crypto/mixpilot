"""Экспорт варианта в MP3/WAV/FLAC через ffmpeg с финальной нормализацией громкости."""

import subprocess
from pathlib import Path

from .. import config, db
from ..errors import AppError, not_found

_CREATE_NO_WINDOW = 0x08000000

FORMATS = {
    "mp3": ("libmp3lame", [".mp3"], ["-q:a", "2"]),
    "wav": ("pcm_s16le", [".wav"], []),
    "flac": ("flac", [".flac"], ["-compression_level", "5"]),
}


def _sanitize(name: str) -> str:
    keep = "".join(c for c in name if c.isalnum() or c in " -_()").strip()
    return (keep or "MixPilot")[:80]


def export_variant(variant_id: str, fmt: str, dest_dir: str | None = None) -> dict:
    if fmt not in FORMATS:
        raise AppError("E_BAD_REQUEST", f"формат {fmt} не поддерживается")
    codec, exts, extra = FORMATS[fmt]

    with db.connect() as conn:
        v = conn.execute("SELECT * FROM generation_variants WHERE id=?", (variant_id,)).fetchone()
        if v is None:
            raise not_found("вариант не найден")
        gen = conn.execute("SELECT * FROM generations WHERE id=?", (v["generation_id"],)).fetchone()
        project = conn.execute("SELECT * FROM projects WHERE id=?", (gen["project_id"],)).fetchone()

    src_wav = config.data_dir() / v["render_wav"]
    if not src_wav.exists():
        raise AppError("E_FILE_ACCESS", "рендер варианта отсутствует", status=404)

    ffmpeg, _fp = config.resolve_ffmpeg()
    if not ffmpeg:
        raise AppError("E_INTERNAL", "ffmpeg недоступен", status=500)

    if dest_dir:
        out_root = Path(dest_dir)
    else:
        out_root = config.data_dir() / "renders" / gen["id"] / "export"
    out_root.mkdir(parents=True, exist_ok=True)
    base = _sanitize(f"{project['title']} - {v['title_ru']}")
    out_path = out_root / f"{base}{exts[0]}"

    cmd = [ffmpeg, "-v", "error", "-y", "-i", str(src_wav), "-c:a", codec, *extra, str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, creationflags=_CREATE_NO_WINDOW, timeout=300)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-2:]
        raise AppError("E_INTERNAL", f"экспорт не удался: {' | '.join(tail)}", status=500)

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO exports(id,variant_id,format,path,created_at) VALUES(?,?,?,?,?)",
            (db.new_id(), variant_id, fmt, str(out_path), db.now_iso()),
        )
    return {"path": str(out_path), "format": fmt}
