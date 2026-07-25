"""API tests for GET /api/settings and PUT /api/settings (Phase 10B)."""
from __future__ import annotations

import json
import pytest


def _mock_tmdb_ok(monkeypatch):
    """TMDb/eMuwarez keys are mandatory and live-tested before being saved
    (both in the setup wizard and in PUT /settings) — tests that seed or
    change a key must mock that live probe instead of hitting the network.

    setup_service.py imports test_tmdb_connection lazily (inside the
    function), so patching the integration_tests module is enough there.
    web/api/settings.py imports it at module load time, so PUT /settings
    needs the name patched where it was bound: web.api.settings."""
    ok = lambda *a, **k: {"ok": True, "service": "tmdb", "status": "connected", "message": "Conexión correcta"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection", ok)
    monkeypatch.setattr("emuwarez_uploadrr.web.api.settings.test_tmdb_connection", ok)


def _seed_tmdb_key(client, auth_headers, monkeypatch, key="testkey12345"):
    """Store a TMDb API key via the setup endpoint (mocks the live TMDb probe)."""
    _mock_tmdb_ok(monkeypatch)
    resp = client.post("/api/setup/tmdb", json={"api_key": key}, headers=auth_headers)
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_get_settings_requires_auth(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 401


def test_put_settings_requires_auth(client):
    resp = client.put("/api/settings", json={"default_release_tag": "TEST"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------

def test_get_settings_returns_defaults(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_release_tag"] == "EMUWAREZ"
    assert isinstance(data["provider_priority_order"], list)
    assert data["tmdb_watch_region"] == "ES"
    assert data["tmdb_api_key_configured"] is False
    assert data["tmdb_api_key_masked"] is None


def test_get_settings_does_not_expose_full_tmdb_key(client, auth_headers, monkeypatch):
    _seed_tmdb_key(client, auth_headers, monkeypatch, "supersecretkey9999")
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tmdb_api_key_configured"] is True
    assert "supersecretkey9999" not in json.dumps(data)
    assert data["tmdb_api_key_masked"] is not None
    assert len(data["tmdb_api_key_masked"]) < len("supersecretkey9999")


# ---------------------------------------------------------------------------
# PUT /api/settings
# ---------------------------------------------------------------------------

def test_put_updates_default_release_tag(client, auth_headers):
    resp = client.put("/api/settings", json={"default_release_tag": "TESTAG"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["default_release_tag"] == "TESTAG"


def test_put_updates_provider_priority_order(client, auth_headers):
    order = ["NF", "AMZN", "DSNP"]
    resp = client.put("/api/settings", json={"provider_priority_order": order}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["provider_priority_order"] == order


def test_put_rejects_invalid_provider_codes(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"provider_priority_order": ["AMZN", "INVALID_CODE"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_put_rejects_duplicate_providers(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"provider_priority_order": ["AMZN", "NF", "AMZN"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_put_rejects_empty_release_tag(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"default_release_tag": "   "},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_put_updates_tmdb_watch_region(client, auth_headers):
    resp = client.put("/api/settings", json={"tmdb_watch_region": "US"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tmdb_watch_region"] == "US"


def test_put_empty_tmdb_api_key_is_rejected(client, auth_headers, monkeypatch):
    # TMDb is mandatory: explicitly sending an empty key must be rejected
    # outright (not silently ignored) and must not touch the existing key.
    _seed_tmdb_key(client, auth_headers, monkeypatch, "original_key_abc")
    resp = client.put("/api/settings", json={"tmdb_api_key": ""}, headers=auth_headers)
    assert resp.status_code == 422

    get_resp = client.get("/api/settings", headers=auth_headers)
    assert get_resp.json()["tmdb_api_key_configured"] is True, "Key should remain configured"


def test_put_null_tmdb_api_key_does_not_clear_existing(client, auth_headers, monkeypatch):
    # Omitting the field (or sending JSON null, indistinguishable from omitted)
    # means "not touching this setting" — unlike an explicit empty string.
    _seed_tmdb_key(client, auth_headers, monkeypatch, "another_key_xyz")
    resp = client.put("/api/settings", json={"tmdb_api_key": None}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tmdb_api_key_configured"] is True


def test_put_updates_tmdb_api_key_when_provided(client, auth_headers, monkeypatch):
    _mock_tmdb_ok(monkeypatch)
    resp = client.put("/api/settings", json={"tmdb_api_key": "newkey_abcdefgh"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tmdb_api_key_configured"] is True
    assert "newkey_abcdefgh" not in json.dumps(data)


def test_put_rejects_invalid_tmdb_api_key(client, auth_headers, monkeypatch):
    fail = lambda *a, **k: {"ok": False, "service": "tmdb", "status": "invalid_key", "message": "API key de TMDb inválida o no autorizada"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection", fail)
    monkeypatch.setattr("emuwarez_uploadrr.web.api.settings.test_tmdb_connection", fail)
    resp = client.put("/api/settings", json={"tmdb_api_key": "bad_key"}, headers=auth_headers)
    assert resp.status_code == 422

    get_resp = client.get("/api/settings", headers=auth_headers)
    assert get_resp.json()["tmdb_api_key_configured"] is False


def test_put_empty_emu_api_key_is_rejected(client, auth_headers, monkeypatch):
    ok = lambda *a, **k: {"ok": True, "service": "emuwarez", "status": "connected", "message": "Conexión correcta"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection", ok)
    monkeypatch.setattr("emuwarez_uploadrr.web.api.settings.test_emuwarez_connection", ok)
    seed = client.put("/api/settings", json={"emu_api_key": "original_emu_key"}, headers=auth_headers)
    assert seed.status_code == 200

    resp = client.put("/api/settings", json={"emu_api_key": ""}, headers=auth_headers)
    assert resp.status_code == 422

    get_resp = client.get("/api/settings", headers=auth_headers)
    assert get_resp.json()["emu_api_key_configured"] is True, "Key should remain configured"
