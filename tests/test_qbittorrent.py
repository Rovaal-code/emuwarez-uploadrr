"""Tests for the qBittorrent WebUI connection test (integration + endpoint)."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations import qbittorrent as qb


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
    client.put("/api/settings", json={
        "qbit_url": "http://192.168.0.5", "qbit_port": "9090",
        "qbit_username": "me", "qbit_password": "secret",
    }, headers=auth_headers)
    s = client.get("/api/settings", headers=auth_headers).json()
    assert s["qbit_url"] == "http://192.168.0.5"
    assert s["qbit_port"] == "9090"
    assert s["qbit_username"] == "me"
    assert s["qbit_configured"] is True
    assert s["qbit_password_configured"] is True
    # password never echoed back
    assert "secret" not in client.get("/api/settings", headers=auth_headers).text
