"""«На телефон»: ссылка работает, гаснет по времени и закрывается по кнопке.

Это единственное место, где приложение слушает не только 127.0.0.1,
поэтому границы проверяем отдельно и придирчиво.
"""

import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from mixpilot_worker import share


@pytest.fixture(autouse=True)
def stop_server():
    yield
    share.revoke_all()


@pytest.fixture()
def song(tmp_path):
    path = tmp_path / "Летний дождь - Вариант A.mp3"
    path.write_bytes(b"ID3" + b"\x00" * 4096)
    return path


# Прокси из окружения к домашней сети не относится: ходим напрямую.
_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch(url: str, timeout: float = 5.0):
    # quote: в пути может быть кириллица, urllib сам её не кодирует
    scheme, rest = url.split("://", 1)
    host, _, path = rest.partition("/")
    return _direct.open(f"{scheme}://{host}/{urllib.parse.quote(path)}", timeout=timeout)


def test_link_serves_the_file(song):
    link = share.publish(song)
    with _fetch(link["url"]) as res:
        assert res.status == 200
        assert res.read() == song.read_bytes()
    assert link["qr_svg"].startswith("<svg")
    assert "домашней сети" in link["hint_ru"]


def test_filename_is_offered_for_download(song):
    link = share.publish(song)
    with _fetch(link["url"]) as res:
        disposition = res.headers["Content-Disposition"]
    # Кириллица в заголовке ломает загрузку — уезжает транслитом в ASCII
    assert "attachment" in disposition
    assert disposition.isascii()


def test_wrong_token_gives_404(song):
    link = share.publish(song)
    base = link["url"].rsplit("/", 1)[0]
    with pytest.raises(urllib.error.HTTPError) as exc:
        _fetch(f"{base}/чужой-токен")
    assert exc.value.code == 404


def test_other_files_are_not_reachable(song, tmp_path):
    """По ссылке доступен ровно один файл, соседние — нет."""
    secret = tmp_path / "секрет.txt"
    secret.write_text("личное", encoding="utf-8")
    link = share.publish(song)
    base = link["url"].rsplit("/", 1)[0]

    for probe in ("/секрет.txt", "/../секрет.txt", "/"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _fetch(base + probe)
        assert exc.value.code == 404


def test_link_expires(song):
    link = share.publish(song, ttl_s=1)
    with _fetch(link["url"]) as res:
        assert res.status == 200
    time.sleep(1.2)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _fetch(link["url"])
    assert exc.value.code == 404


def test_revoke_closes_access(song):
    link = share.publish(song)
    assert share.active_links() == 1
    assert share.revoke_all() == 1
    assert share.active_links() == 0
    with pytest.raises(urllib.error.URLError):
        _fetch(link["url"], timeout=2.0)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        share.publish(tmp_path / "нет-такого.mp3")


def test_lan_ip_is_an_address():
    parts = share.lan_ip().split(".")
    assert len(parts) == 4 and all(p.isdigit() for p in parts)


def test_ascii_name_keeps_extension():
    assert share._ascii_name("Летний дождь.mp3").endswith(".mp3")
    assert share._ascii_name("").isascii()
