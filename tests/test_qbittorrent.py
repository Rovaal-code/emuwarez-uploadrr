"""Tests for the qBittorrent WebUI connection test (integration + endpoint)."""
from __future__ import annotations

import urllib.error

import pytest

from emuwarez_uploadrr.integrations import qbittorrent as qb


class _FakeResponse:
    """Minimal stand-in for the object urlopen returns."""

    def __init__(self, body: str, cookie: str = "", status: int = 200):
        self._body = body.encode()
        self.status = status
        self.headers = {"Set-Cookie": cookie} if cookie else {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(monkeypatch, login_response, version: str = "5.2.3"):
    """Route /auth/login to login_response and /app/version to a fixed version."""
    def opener(req, *a, **k):
        if isinstance(login_response, Exception) and req.full_url.endswith("/auth/login"):
            raise login_response
        if req.full_url.endswith("/app/version"):
            return _FakeResponse(version)
        return login_response
    monkeypatch.setattr("urllib.request.urlopen", opener)


def test_login_ok_qbittorrent_5x(monkeypatch):
    """5.x answers 204 with an empty body and a port-scoped QBT_SID cookie."""
    _fake_urlopen(monkeypatch, _FakeResponse(
        "", cookie="QBT_SID_8085=Br4UJJJC06jn; HttpOnly; SameSite=Lax; path=/", status=204))
    r = qb.qbit_test_connection("http://qbit", "8085", "admin", "adminadmin")
    assert r["ok"] is True
    assert r["version"] == "5.2.3"


def test_login_ok_qbittorrent_4x(monkeypatch):
    """4.x answers 200 with the body "Ok." and a plain SID cookie."""
    _fake_urlopen(monkeypatch, _FakeResponse("Ok.", cookie="SID=abc123; path=/"), version="4.6.0")
    r = qb.qbit_test_connection("http://qbit", "8080", "admin", "x")
    assert r["ok"] is True
    assert r["version"] == "4.6.0"


def test_login_bad_credentials_qbittorrent_5x(monkeypatch):
    """5.x answers 401 instead of the old "Fails." body."""
    _fake_urlopen(monkeypatch, urllib.error.HTTPError(
        "http://qbit/api/v2/auth/login", 401, "Unauthorized", {}, None))
    r = qb.qbit_test_connection("http://qbit", "8085", "admin", "mala")
    assert r["ok"] is False
    assert r["error"] == qb.BAD_LOGIN_ERROR


def test_login_bad_credentials_qbittorrent_4x(monkeypatch):
    _fake_urlopen(monkeypatch, _FakeResponse("Fails."))
    r = qb.qbit_test_connection("http://qbit", "8080", "admin", "mala")
    assert r["ok"] is False
    assert r["error"] == qb.BAD_LOGIN_ERROR


def test_login_unexpected_body_is_reported(monkeypatch):
    _fake_urlopen(monkeypatch, _FakeResponse("<html>nginx</html>"))
    r = qb.qbit_test_connection("http://qbit", "8080", "admin", "x")
    assert r["ok"] is False
    assert "Respuesta inesperada" in r["error"]


@pytest.mark.parametrize("cookie,expected", [
    ("SID=abc; path=/", True),                      # 4.x
    ("QBT_SID_8085=abc; HttpOnly", True),           # 5.x, non-default port
    ("QBT_SID_8080=abc", True),
    ("", False),
    ("other=abc; path=/", False),
])
def test_has_session_cookie(cookie, expected):
    assert qb._has_session_cookie(cookie) is expected


def test_build_base_url_appends_port():
    assert qb.build_base_url("127.0.0.1", "8080") == "http://127.0.0.1:8080"
    assert qb.build_base_url("http://host", 9000) == "http://host:9000"
    # explicit port already present → keep it
    assert qb.build_base_url("http://host:1234", "8080") == "http://host:1234"
    assert qb.build_base_url("", "8080") == ""


def test_service_test_not_configured(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.integration_tests import test_qbit_connection
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    r = test_qbit_connection(conn=conn)
    assert r["ok"] is False
    assert r["status"] == "not_configured"


def test_endpoint_qbit_login_ok(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "emuwarez_uploadrr.integrations.qbittorrent.qbit_test_connection",
        lambda *a, **k: {"ok": True, "version": "4.6.0"},
    )
    resp = client.post("/api/integrations/test/qbit",
                       json={"url": "http://127.0.0.1", "port": "8080", "username": "admin", "password": "x"},
                       headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["service"] == "qbittorrent"


def test_endpoint_qbit_bad_credentials(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "emuwarez_uploadrr.integrations.qbittorrent.qbit_test_connection",
        lambda *a, **k: {"ok": False, "error": "Usuario o contraseña de qBittorrent incorrectos"},
    )
    resp = client.post("/api/integrations/test/qbit",
                       json={"url": "http://127.0.0.1", "port": "8080", "username": "admin", "password": "bad"},
                       headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_settings_roundtrip_qbit(client, auth_headers):
    """El puerto ya no es un ajuste: va dentro de la url. En su hueco está el
    tag que qBittorrent le pone al torrent."""
    client.put("/api/settings", json={
        "qbit_url": "http://192.168.0.5:9090", "qbit_tag": "Subidas",
        "qbit_username": "me", "qbit_password": "secret",
    }, headers=auth_headers)
    s = client.get("/api/settings", headers=auth_headers).json()
    assert s["qbit_url"] == "http://192.168.0.5:9090"
    assert s["qbit_tag"] == "Subidas"
    assert s["qbit_username"] == "me"
    assert s["qbit_configured"] is True
    assert s["qbit_password_configured"] is True
    # password never echoed back
    assert "secret" not in client.get("/api/settings", headers=auth_headers).text


def test_settings_rejects_invalid_qbit_url(client, auth_headers):
    r = client.put("/api/settings", json={"qbit_url": "not-a-url"}, headers=auth_headers)
    assert r.status_code == 422


def test_settings_accepts_valid_qbit_url(client, auth_headers):
    r = client.put("/api/settings", json={"qbit_url": "http://192.168.0.5"}, headers=auth_headers)
    assert r.status_code == 200


def test_settings_empty_qbit_url_ok(client, auth_headers):
    r = client.put("/api/settings", json={"qbit_url": ""}, headers=auth_headers)
    assert r.status_code == 200


def test_setup_qbit_rejects_invalid_url(client, auth_headers):
    r = client.post("/api/setup/qbit", json={"url": "ftp://x"}, headers=auth_headers)
    assert r.status_code == 422


def test_service_version_label_not_duplicated(isolated_db, monkeypatch):
    """qBittorrent reports "v5.2.3" already — the message must not read "vv5.2.3"."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.integration_tests import test_qbit_connection
    from emuwarez_uploadrr.services.settings import set_setting
    monkeypatch.setattr(
        "emuwarez_uploadrr.integrations.qbittorrent.qbit_test_connection",
        lambda *a, **k: {"ok": True, "version": "v5.2.3"},
    )
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    set_setting(conn, "qbit.url", "http://qbit")
    r = test_qbit_connection(conn=conn)
    assert r["ok"] is True
    assert r["message"] == "Conexión correcta (v5.2.3)"


def test_service_version_label_adds_v_when_missing(isolated_db, monkeypatch):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.integration_tests import test_qbit_connection
    from emuwarez_uploadrr.services.settings import set_setting
    monkeypatch.setattr(
        "emuwarez_uploadrr.integrations.qbittorrent.qbit_test_connection",
        lambda *a, **k: {"ok": True, "version": "4.6.0"},
    )
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    set_setting(conn, "qbit.url", "http://qbit")
    r = test_qbit_connection(conn=conn)
    assert r["message"] == "Conexión correcta (v4.6.0)"


# ---------------------------------------------------------------------------
# El puerto deja de ser un campo y pasa a ir dentro de la URL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,host,port", [
    ("http://192.168.0.136:8082", "http://192.168.0.136", "8082"),
    ("http://192.168.0.136", "http://192.168.0.136", "80"),      # por defecto del esquema
    ("https://qbit.midominio.com", "https://qbit.midominio.com", "443"),
    ("https://qbit.midominio.com:9443", "https://qbit.midominio.com", "9443"),
    ("192.168.0.5:8080", "http://192.168.0.5", "8080"),          # sin esquema
    ("http://[::1]:8080", "http://[::1]", "8080"),               # IPv6
    ("http://host:8080/", "http://host", "8080"),                # barra final
    ("", "", ""),
])
def test_split_base_url(url, host, port):
    from emuwarez_uploadrr.integrations.qbittorrent import split_base_url
    assert split_base_url(url) == (host, port)


def test_split_and_build_are_inverses():
    """Uploadrr-EMU quiere host y puerto separados, la app guarda una sola url:
    partir y volver a juntar no puede cambiar a dónde se llama."""
    from emuwarez_uploadrr.integrations.qbittorrent import build_base_url, split_base_url
    for url in ("http://192.168.0.136:8082", "https://qbit.midominio.com:9443", "http://[::1]:8080"):
        host, port = split_base_url(url)
        assert build_base_url(host, port) == url


def test_migration_folds_the_stored_port_into_the_url(isolated_db):
    """Al quitar el campo Puerto, a quien ya lo tuviera configurado se le
    quedaría la url sin puerto y qBittorrent dejaría de conectar sin decir
    nada. La migración lo mete dentro."""
    import os
    from emuwarez_uploadrr.database import connect, init_db, _migrate_qbit_port_into_url
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('qbit.url', 'http://192.168.0.136')")
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('qbit.port', '8082')")
    conn.commit()

    _migrate_qbit_port_into_url(conn)
    conn.commit()

    url = conn.execute("SELECT value FROM settings WHERE key = 'qbit.url'").fetchone()["value"]
    assert url == "http://192.168.0.136:8082"
    # Y el ajuste viejo desaparece: una sola fuente de verdad.
    assert conn.execute("SELECT value FROM settings WHERE key = 'qbit.port'").fetchone() is None


def test_migration_leaves_a_url_that_already_had_its_port_alone(isolated_db):
    import os
    from emuwarez_uploadrr.database import connect, init_db, _migrate_qbit_port_into_url
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('qbit.url', 'http://host:9999')")
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('qbit.port', '8080')")
    conn.commit()
    _migrate_qbit_port_into_url(conn)
    conn.commit()
    assert conn.execute("SELECT value FROM settings WHERE key = 'qbit.url'").fetchone()["value"] == "http://host:9999"
