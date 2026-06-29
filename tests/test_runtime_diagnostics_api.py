"""Tests for GET /api/runtime/diagnostics endpoint."""
from __future__ import annotations

import pytest


def test_diagnostics_endpoint_requires_auth(client):
    resp = client.get("/api/runtime/diagnostics")
    assert resp.status_code == 401


def test_diagnostics_endpoint_with_token(client, auth_headers):
    resp = client.get("/api/runtime/diagnostics", headers=auth_headers)
    assert resp.status_code == 200


def test_diagnostics_response_has_ok_field(client, auth_headers):
    resp = client.get("/api/runtime/diagnostics", headers=auth_headers)
    data = resp.json()
    assert "ok" in data
    assert isinstance(data["ok"], bool)


def test_diagnostics_response_has_checks(client, auth_headers):
    resp = client.get("/api/runtime/diagnostics", headers=auth_headers)
    data = resp.json()
    assert "checks" in data
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) > 0


def test_diagnostics_checks_have_required_fields(client, auth_headers):
    resp = client.get("/api/runtime/diagnostics", headers=auth_headers)
    data = resp.json()
    for check in data["checks"]:
        assert "name" in check
        assert "status" in check
        assert "message" in check
        assert check["status"] in ("ok", "warning", "error", "unknown")


def test_diagnostics_response_has_warnings_and_errors(client, auth_headers):
    resp = client.get("/api/runtime/diagnostics", headers=auth_headers)
    data = resp.json()
    assert "warnings" in data
    assert "errors" in data
    assert isinstance(data["warnings"], list)
    assert isinstance(data["errors"], list)


def test_diagnostics_no_secrets_in_response(client, auth_headers):
    resp = client.get("/api/runtime/diagnostics", headers=auth_headers)
    text = resp.text.lower()
    assert "api_token=" not in text
    assert "tmdb_api_key" not in text
    assert "emu_api_key" not in text


def test_diagnostics_invalid_token_returns_401(client):
    resp = client.get(
        "/api/runtime/diagnostics",
        headers={"Authorization": "Bearer invalidtoken123"},
    )
    assert resp.status_code == 401


def test_diagnostics_wrong_method_returns_405(client, auth_headers):
    resp = client.post("/api/runtime/diagnostics", headers=auth_headers)
    assert resp.status_code == 405


def test_diagnostics_warns_about_uploadrr_not_mounted(client, auth_headers):
    """Uploadrr not being mounted should produce a warning, not break the endpoint."""
    resp = client.get("/api/runtime/diagnostics", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    uploadrr_check = next(
        (c for c in data["checks"] if c["name"] == "uploadrr_mount"), None
    )
    assert uploadrr_check is not None
    # In test env /opt/Uploadrr doesn't exist; should be warning not error
    assert uploadrr_check["status"] in ("ok", "warning")
