"""API tests for GET /api/settings and PUT /api/settings (Phase 10B)."""
from __future__ import annotations

import json
import pytest


def _seed_tmdb_key(client, auth_headers, key="testkey12345"):
    """Store a TMDb API key via the setup endpoint."""
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
    assert data["tmdb_language"] == "es-ES"
    assert data["tmdb_api_key_configured"] is False
    assert data["tmdb_api_key_masked"] is None


def test_get_settings_does_not_expose_full_tmdb_key(client, auth_headers):
    _seed_tmdb_key(client, auth_headers, "supersecretkey9999")
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


def test_put_empty_tmdb_api_key_does_not_clear_existing(client, auth_headers):
    _seed_tmdb_key(client, auth_headers, "original_key_abc")
    # update with empty key — should not wipe the existing key
    resp = client.put("/api/settings", json={"tmdb_api_key": ""}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tmdb_api_key_configured"] is True, "Key should remain configured"


def test_put_null_tmdb_api_key_does_not_clear_existing(client, auth_headers):
    _seed_tmdb_key(client, auth_headers, "another_key_xyz")
    resp = client.put("/api/settings", json={"tmdb_api_key": None}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tmdb_api_key_configured"] is True


def test_put_updates_tmdb_api_key_when_provided(client, auth_headers):
    resp = client.put("/api/settings", json={"tmdb_api_key": "newkey_abcdefgh"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tmdb_api_key_configured"] is True
    assert "newkey_abcdefgh" not in json.dumps(data)
