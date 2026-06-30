"""API tests for POST /api/integrations/test/* (Phase 10C).

All external HTTP calls are mocked — no real internet traffic.
"""
from __future__ import annotations

from unittest.mock import patch


# ---------------------------------------------------------------------------
# Auth guard — all three endpoints require Bearer token
# ---------------------------------------------------------------------------

def test_tmdb_test_requires_auth(client):
    resp = client.post("/api/integrations/test/tmdb", json={})
    assert resp.status_code == 401


def test_emuwarez_test_requires_auth(client):
    resp = client.post("/api/integrations/test/emuwarez", json={})
    assert resp.status_code == 401


def test_arr_test_requires_auth(client):
    resp = client.post("/api/integrations/test/arr", json={"kind": "radarr", "base_url": "http://x", "api_key": "k"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/integrations/test/tmdb
# ---------------------------------------------------------------------------

def test_tmdb_not_configured(client, auth_headers):
    """No api_key in body and none stored → not_configured."""
    with patch("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "tmdb", "status": "not_configured", "message": "No key", "details": {}}
        resp = client.post("/api/integrations/test/tmdb", json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["status"] == "not_configured"
    assert data["service"] == "tmdb"


def test_tmdb_connected(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "tmdb", "status": "connected", "message": "OK", "details": {"http_status": 200}}
        resp = client.post("/api/integrations/test/tmdb", json={"api_key": "goodkey"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "connected"


def test_tmdb_invalid_key(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "tmdb", "status": "invalid_key", "message": "API key inválida", "details": {}}
        resp = client.post("/api/integrations/test/tmdb", json={"api_key": "badkey"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["status"] == "invalid_key"


def test_tmdb_with_language_and_region_forwarded(client, auth_headers):
    """language and region from body are passed to the service."""
    with patch("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "tmdb", "status": "connected", "message": "OK", "details": {}}
        resp = client.post(
            "/api/integrations/test/tmdb",
            json={"api_key": "k", "language": "en-US", "region": "US"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    call_kwargs = mock_svc.call_args
    assert call_kwargs.kwargs.get("language") == "en-US" or (call_kwargs.args and "en-US" in call_kwargs.args)


def test_tmdb_response_never_contains_raw_key(client, auth_headers):
    """The full API key sent in the request must not appear in the response."""
    secret = "my_secret_tmdb_key_12345"
    with patch("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "tmdb", "status": "connected", "message": "OK", "details": {}}
        resp = client.post("/api/integrations/test/tmdb", json={"api_key": secret}, headers=auth_headers)
    assert secret not in resp.text


# ---------------------------------------------------------------------------
# POST /api/integrations/test/emuwarez
# ---------------------------------------------------------------------------

def test_emuwarez_not_configured(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "emuwarez", "status": "not_configured", "message": "No key", "details": {}}
        resp = client.post("/api/integrations/test/emuwarez", json={}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_configured"


def test_emuwarez_connected(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "emuwarez", "status": "connected", "message": "OK", "details": {}}
        resp = client.post("/api/integrations/test/emuwarez", json={"api_key": "key123"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_emuwarez_invalid_key(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "emuwarez", "status": "invalid_key", "message": "bad key", "details": {}}
        resp = client.post("/api/integrations/test/emuwarez", json={"api_key": "bad"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "invalid_key"


def test_emuwarez_invalid_url(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "emuwarez", "status": "invalid_url", "message": "bad url", "details": {}}
        resp = client.post("/api/integrations/test/emuwarez", json={"api_key": "k", "base_url": "not-a-url"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "invalid_url"


def test_emuwarez_response_never_contains_raw_key(client, auth_headers):
    secret = "emu_secret_key_99999"
    with patch("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "emuwarez", "status": "invalid_url", "message": "bad", "details": {}}
        resp = client.post("/api/integrations/test/emuwarez", json={"api_key": secret, "base_url": "bad"}, headers=auth_headers)
    assert secret not in resp.text


# ---------------------------------------------------------------------------
# POST /api/integrations/test/arr
# ---------------------------------------------------------------------------

def test_arr_missing_body_fields(client, auth_headers):
    """kind, base_url, api_key are required."""
    resp = client.post("/api/integrations/test/arr", json={}, headers=auth_headers)
    assert resp.status_code == 422


def test_arr_radarr_connected(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_arr_connection") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "radarr", "status": "connected", "message": "OK", "details": {"version": "5.3.6"}}
        resp = client.post(
            "/api/integrations/test/arr",
            json={"kind": "radarr", "base_url": "http://localhost:7878", "api_key": "abc"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["service"] == "radarr"
    assert data["details"]["version"] == "5.3.6"


def test_arr_sonarr_connected(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_arr_connection") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "sonarr", "status": "connected", "message": "OK", "details": {}}
        resp = client.post(
            "/api/integrations/test/arr",
            json={"kind": "sonarr", "base_url": "http://localhost:8989", "api_key": "xyz"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_arr_invalid_key(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_arr_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "radarr", "status": "invalid_key", "message": "bad key", "details": {}}
        resp = client.post(
            "/api/integrations/test/arr",
            json={"kind": "radarr", "base_url": "http://localhost:7878", "api_key": "wrong"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "invalid_key"


def test_arr_connection_error(client, auth_headers):
    with patch("emuwarez_uploadrr.services.integration_tests.test_arr_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "radarr", "status": "connection_error", "message": "unreachable", "details": {}}
        resp = client.post(
            "/api/integrations/test/arr",
            json={"kind": "radarr", "base_url": "http://192.168.0.1:7878", "api_key": "k"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_arr_response_never_contains_raw_key(client, auth_headers):
    secret = "arr_secret_api_key_abcdef"
    with patch("emuwarez_uploadrr.services.integration_tests.test_arr_connection") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "radarr", "status": "connection_error", "message": "fail", "details": {}}
        resp = client.post(
            "/api/integrations/test/arr",
            json={"kind": "radarr", "base_url": "http://localhost:7878", "api_key": secret},
            headers=auth_headers,
        )
    assert secret not in resp.text


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------

def test_all_endpoints_return_integration_test_result_shape(client, auth_headers):
    """Every endpoint returns {ok, service, status, message, details}."""
    expected_keys = {"ok", "service", "status", "message", "details"}

    endpoints_and_bodies = [
        ("/api/integrations/test/tmdb", {}),
        ("/api/integrations/test/emuwarez", {}),
        ("/api/integrations/test/arr", {"kind": "radarr", "base_url": "http://x", "api_key": "k"}),
    ]
    mocks = [
        "emuwarez_uploadrr.services.integration_tests.test_tmdb_connection",
        "emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection",
        "emuwarez_uploadrr.services.integration_tests.test_arr_connection",
    ]
    services = ["tmdb", "emuwarez", "radarr"]

    for (url, body), mock_path, svc in zip(endpoints_and_bodies, mocks, services):
        with patch(mock_path) as mock_svc:
            mock_svc.return_value = {
                "ok": False, "service": svc, "status": "not_configured",
                "message": "test", "details": {}
            }
            resp = client.post(url, json=body, headers=auth_headers)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"
        data = resp.json()
        assert expected_keys.issubset(data.keys()), f"{url} missing keys: {expected_keys - data.keys()}"
