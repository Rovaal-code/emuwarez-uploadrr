"""API tests for POST /api/integrations/test/seerr (Phase 11B).

All external HTTP calls are mocked at the service layer — no real
Overseerr/Jellyseerr traffic.
"""
from __future__ import annotations

from unittest.mock import patch


def test_seerr_test_requires_auth(client):
    resp = client.post("/api/integrations/test/seerr", json={})
    assert resp.status_code == 401


def test_seerr_missing_credentials_without_instance_id_returns_422(client, auth_headers):
    resp = client.post("/api/integrations/test/seerr", json={}, headers=auth_headers)
    assert resp.status_code == 422


def test_seerr_unsaved_credentials_connected(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_seerr_connection") as mock_svc:
        mock_svc.return_value = {
            "ok": True, "service": "seerr", "status": "connected", "message": "OK",
            "details": {"version": "1.33.2", "username": "Alvaro"},
        }
        resp = client.post(
            "/api/integrations/test/seerr",
            json={"base_url": "http://seerr:5055", "api_key": "somekey"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["details"]["username"] == "Alvaro"


def test_seerr_by_instance_id_uses_saved_instance(client, auth_headers):
    add_resp = client.post(
        "/api/instances",
        json={"type": "seerr", "name": "Seerr saved", "url": "http://seerr:5055", "api_key": "saved-key"},
        headers=auth_headers,
    )
    assert add_resp.status_code == 201
    instances = client.get("/api/instances", headers=auth_headers).json()
    instance_id = next(i["id"] for i in instances if i["type"] == "seerr")

    with patch("emuwarez_uploadrr.services.integration_tests.test_seerr_connection") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "seerr", "status": "connected", "message": "OK", "details": {}}
        resp = client.post(
            "/api/integrations/test/seerr",
            json={"instance_id": instance_id},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_seerr_by_instance_id_not_found(client, auth_headers):
    resp = client.post("/api/integrations/test/seerr", json={"instance_id": 999}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_configured"


def test_seerr_response_never_contains_raw_key(client, auth_headers):
    secret = "seerr_secret_api_key_abcdef"
    with patch("emuwarez_uploadrr.services.integration_tests.test_seerr_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "seerr", "status": "connection_error", "message": "fail", "details": {}}
        resp = client.post(
            "/api/integrations/test/seerr",
            json={"base_url": "http://localhost:5055", "api_key": secret},
            headers=auth_headers,
        )
    assert secret not in resp.text
