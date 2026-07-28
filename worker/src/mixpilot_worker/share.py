"""«Отправить на телефон»: временная ссылка в домашней сети + QR-код.

Единственное место, где приложение слушает не только 127.0.0.1, поэтому
ограничений много и они намеренные:
- сервер поднимается только по явному действию пользователя и сам гаснет;
- отдаётся ровно один файл по случайному токену, обхода каталогов нет;
- ссылка живёт 15 минут, после этого 404 и сервер останавливается;
- наружу, в интернет, ничего не уходит: адрес — из локальной сети.
"""

from __future__ import annotations

import logging
import mimetypes
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("mixpilot.share")

TTL_S = 15 * 60
SWEEP_S = 30

_lock = threading.Lock()
_links: dict[str, dict] = {}
_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None
_sweeper: threading.Timer | None = None


def lan_ip() -> str:
    """Адрес компьютера в домашней сети. Наружу пакет не отправляется —
    UDP-сокету достаточно «выбрать маршрут», чтобы узнать свой адрес."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class _Handler(BaseHTTPRequestHandler):
    server_version = "MixPilot"

    def log_message(self, fmt, *args):  # noqa: A003 — гасим вывод в stderr
        log.debug("share: " + fmt, *args)

    def do_GET(self) -> None:  # noqa: N802 — имя задано базовым классом
        token = self.path.rsplit("/", 1)[-1].split("?")[0]
        # Токен ищем только в словаре: имя файла из запроса не используется
        # вовсе, поэтому «../» и абсолютные пути ничего не дают.
        link = _valid_link(token)
        if link is None:
            self.send_error(404, "Not Found")
            return
        path = Path(link["path"])
        if not path.exists():
            self.send_error(404, "Not Found")
            return

        data = path.read_bytes()
        ctype = mimetypes.guess_type(link["filename"])[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{link["ascii_name"]}"')
        self.end_headers()
        self.wfile.write(data)
        with _lock:
            link["downloads"] += 1


def _valid_link(token: str) -> dict | None:
    with _lock:
        link = _links.get(token)
        if link is None:
            return None
        if link["expires_at"] < time.time():
            _links.pop(token, None)
            return None
        return link


def _ensure_server() -> int:
    global _server, _thread
    with _lock:
        if _server is not None:
            return _server.server_address[1]
        _server = ThreadingHTTPServer(("0.0.0.0", 0), _Handler)
        _server.daemon_threads = True
        _thread = threading.Thread(target=_server.serve_forever, name="share", daemon=True)
        _thread.start()
        port = _server.server_address[1]
    log.info("share server started", extra={"ctx": {"port": port}})
    _schedule_sweep()
    return port


def _schedule_sweep() -> None:
    global _sweeper
    if _sweeper is not None:
        _sweeper.cancel()
    _sweeper = threading.Timer(SWEEP_S, _sweep)
    _sweeper.daemon = True
    _sweeper.start()


def _sweep() -> None:
    """Просроченные ссылки убираем, без ссылок — гасим сервер."""
    with _lock:
        now = time.time()
        for token in [t for t, l in _links.items() if l["expires_at"] < now]:
            _links.pop(token, None)
        alive = bool(_links)
    if alive:
        _schedule_sweep()
    else:
        stop()


def _ascii_name(name: str) -> str:
    """Имя файла для заголовка: кириллица в HTTP-заголовке ломает загрузку."""
    safe = "".join(c if c.isascii() and (c.isalnum() or c in "._- ") else "_" for c in name)
    return safe.strip() or "mixpilot.mp3"


def publish(path: Path, filename: str | None = None, ttl_s: int = TTL_S) -> dict:
    """Открывает временный доступ к одному файлу. Возвращает ссылку и QR."""
    import segno

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    port = _ensure_server()
    token = secrets.token_urlsafe(18)
    name = filename or path.name
    with _lock:
        _links[token] = {
            "path": str(path), "filename": name, "ascii_name": _ascii_name(name),
            "expires_at": time.time() + ttl_s, "downloads": 0,
        }

    url = f"http://{lan_ip()}:{port}/d/{token}"
    qr = segno.make(url, error="m")
    return {
        "url": url,
        "qr_svg": qr.svg_inline(scale=6, dark="#0a0b10", light="#ffffff", border=2),
        "expires_in_s": ttl_s,
        "filename": name,
        "hint_ru": "Наведите камеру телефона. Ссылка работает только в вашей "
                   f"домашней сети и погаснет через {ttl_s // 60} минут",
    }


def revoke_all() -> int:
    """Кнопка «закрыть доступ»: гасим все ссылки немедленно."""
    with _lock:
        count = len(_links)
        _links.clear()
    stop()
    return count


def active_links() -> int:
    with _lock:
        now = time.time()
        return sum(1 for l in _links.values() if l["expires_at"] >= now)


def stop() -> None:
    global _server, _thread, _sweeper
    with _lock:
        server, _server = _server, None
        _thread = None
        if _sweeper is not None:
            _sweeper.cancel()
            _sweeper = None
    if server is not None:
        server.shutdown()
        server.server_close()
        log.info("share server stopped")
