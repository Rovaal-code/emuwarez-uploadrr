"""Tests for Phase 3: setup wizard + local authentication.

Run with:
    .venv/bin/pytest tests/test_setup_auth.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Security unit tests
# ---------------------------------------------------------------------------

def test_hash_password_and_verify():
    from emuwarez_uploadrr.web.security import hash_password, verify_password
    pw = "MySecure!Pass1"
    h = hash_password(pw)
    assert h.startswith("pbkdf2_sha256$210000$")
    assert verify_password(pw, h)
    assert not verify_password("WrongPass!1A", h)


def test_hash_password_unique_salts():
    from emuwarez_uploadrr.web.security import hash_password
    h1 = hash_password("SamePass1!")
    h2 = hash_password("SamePass1!")
    assert h1 != h2


def test_create_and_hash_token():
    from emuwarez_uploadrr.web.security import create_token, hash_token, verify_token
    token = create_token()
    assert len(token) >= 60
    th = hash_token(token)
    assert len(th) == 64  # SHA-256 hex
    assert verify_token(token, th)
    assert not verify_token("wrongtoken", th)


def test_password_strength_rules():
    from emuwarez_uploadrr.web.security import validate_password_strength
    assert validate_password_strength("short") is not None
    assert validate_password_strength("alllowercase123!") is not None
    assert validate_password_strength("ALLUPPERCASE123!") is not None
    assert validate_password_strength("NoDigitSymbol!!A") is not None
    assert validate_password_strength("NoSymbol1234Abcd") is not None
    assert validate_password_strength("ValidPass1!abcd") is None


# ---------------------------------------------------------------------------
# Setup status — initial (no DB)
# ---------------------------------------------------------------------------

def test_setup_status_initial(client):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is False
    assert data["admin_configured"] is False
    assert data["next_step"] == "admin"


# ---------------------------------------------------------------------------
# POST /api/setup/admin
# ---------------------------------------------------------------------------

def test_create_admin_success(client):
    resp = client.post("/api/setup/admin", json={
        "username": "admin",
        "password": "Secure!Pass1234",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["ok"] is True
    assert "admin" in data["message"]


def test_create_admin_weak_password(client):
    resp = client.post("/api/setup/admin", json={
        "username": "admin",
        "password": "weak",
    })
    assert resp.status_code == 422


def test_create_admin_duplicate(client):
    payload = {"username": "admin", "password": "Secure!Pass1234"}
    client.post("/api/setup/admin", json=payload)
    resp = client.post("/api/setup/admin", json=payload)
    assert resp.status_code == 409


def test_setup_status_after_admin(client):
    client.post("/api/setup/admin", json={"username": "admin", "password": "Secure!Pass1234"})
    resp = client.get("/api/setup/status")
    data = resp.json()
    assert data["admin_configured"] is True
    assert data["next_step"] == "base"


# ---------------------------------------------------------------------------
# Auth — login / me / logout
# ---------------------------------------------------------------------------

def test_login_success(client):
    client.post("/api/setup/admin", json={"username": "admin", "password": "Secure!Pass1234"})
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "Secure!Pass1234"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["username"] == "admin"
    assert data["role"] == "admin"


def test_login_wrong_password(client):
    client.post("/api/setup/admin", json={"username": "admin", "password": "Secure!Pass1234"})
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "WrongPass1!"})
    assert resp.status_code == 401


def test_login_wrong_username(client):
    client.post("/api/setup/admin", json={"username": "admin", "password": "Secure!Pass1234"})
    resp = client.post("/api/auth/login", json={"username": "nobody", "password": "Secure!Pass1234"})
    assert resp.status_code == 401


def test_me_with_valid_token(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testadmin"
    assert data["role"] == "admin"
    assert "id" in data


def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_invalid_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer faketoken123"})
    assert resp.status_code == 401


def test_logout_revokes_token(client):
    client.post("/api/setup/admin", json={"username": "admin", "password": "Secure!Pass1234"})
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "Secure!Pass1234"})
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # After logout, the token should be invalid
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected placeholders return 401 without token
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/dashboard/summary"),
    ("GET", "/api/dashboard/activity"),
    ("GET", "/api/instances"),
    ("GET", "/api/library"),
    ("GET", "/api/missing"),
    ("GET", "/api/requests"),
    ("GET", "/api/uploads"),
    ("GET", "/api/tasks"),
    ("GET", "/api/logs"),
    ("GET", "/api/config"),
])
def test_protected_endpoints_require_auth(client, method, path):
    if method == "GET":
        resp = client.get(path)
    else:
        resp = client.post(path, json={})
    assert resp.status_code == 401


def test_protected_endpoints_accessible_with_token(auth_headers, client):
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["implemented"] is False


def test_create_emu_request_requires_auth(client):
    resp = client.post("/api/missing/1/create-emu-request")
    assert resp.status_code == 401


def test_create_emu_request_stub_with_auth(client, auth_headers):
    resp = client.post("/api/missing/1/create-emu-request", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stub"] is True
    assert data["implemented"] is False


# ---------------------------------------------------------------------------
# Setup steps (requires auth)
# ---------------------------------------------------------------------------

def test_setup_base_requires_auth(client):
    resp = client.post("/api/setup/base", json={"app_name": "Test", "timezone": "UTC"})
    assert resp.status_code == 401


def test_setup_base_success(client, auth_headers):
    resp = client.post(
        "/api/setup/base",
        json={"app_name": "eMuwarez Test", "timezone": "Europe/Madrid"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


def test_setup_uploadrr_requires_auth(client):
    resp = client.post("/api/setup/uploadrr", json={"uploadrr_path": "/path/to/Uploadrr"})
    assert resp.status_code == 401


def test_setup_uploadrr_success(client, auth_headers):
    resp = client.post(
        "/api/setup/uploadrr",
        json={"uploadrr_path": "/srv/Uploadrr"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_setup_tmdb_success(client, auth_headers):
    resp = client.post(
        "/api/setup/tmdb",
        json={"api_key": "abc123tmdb"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    status_resp = client.get("/api/setup/status")
    assert status_resp.json()["tmdb_configured"] is True


def test_setup_emu_success(client, auth_headers):
    resp = client.post(
        "/api/setup/emu",
        json={"api_key": "abc123emu", "endpoint_url": "https://emu.example.com/api"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    status_resp = client.get("/api/setup/status")
    assert status_resp.json()["emu_configured"] is True


def test_setup_instance_success(client, auth_headers):
    resp = client.post(
        "/api/setup/instances",
        json={"type": "radarr", "name": "Radarr principal", "url": "http://radarr:7878", "api_key": "key1"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True

    status_resp = client.get("/api/setup/status")
    assert status_resp.json()["radarr_instances"] == 1


def test_setup_instance_invalid_type(client, auth_headers):
    resp = client.post(
        "/api/setup/instances",
        json={"type": "jellyfin", "name": "J", "url": "http://j:8096", "api_key": "k"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_setup_complete_missing_steps(client, auth_headers):
    # Try to complete without TMDb/EMU configured
    resp = client.post("/api/setup/complete", headers=auth_headers)
    assert resp.status_code == 400
    assert "tmdb" in resp.json()["detail"].lower() or "pendientes" in resp.json()["detail"].lower()


def test_full_setup_flow(client, auth_headers):
    """Complete the entire setup wizard end to end."""
    client.post("/api/setup/base",
                json={"app_name": "E2E Test", "timezone": "UTC"}, headers=auth_headers)
    client.post("/api/setup/uploadrr",
                json={"uploadrr_path": "/srv/Uploadrr"}, headers=auth_headers)
    client.post("/api/setup/tmdb",
                json={"api_key": "tmdb_key_e2e"}, headers=auth_headers)
    client.post("/api/setup/emu",
                json={"api_key": "emu_key_e2e"}, headers=auth_headers)
    client.post("/api/setup/instances",
                json={"type": "radarr", "name": "Radarr E2E", "url": "http://radarr:7878", "api_key": "r"},
                headers=auth_headers)

    complete_resp = client.post("/api/setup/complete", headers=auth_headers)
    assert complete_resp.status_code == 200

    status_resp = client.get("/api/setup/status")
    data = status_resp.json()
    assert data["initialized"] is True
    assert data["next_step"] is None


# ---------------------------------------------------------------------------
# Token not in DB (no secrets logged)
# ---------------------------------------------------------------------------

def test_token_not_stored_as_clear(client, isolated_db):
    """Verify the raw token is NOT stored in the DB."""
    import sqlite3
    from emuwarez_uploadrr.web.security import hash_token

    client.post("/api/setup/admin", json={"username": "admin", "password": "Secure!Pass1234"})
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "Secure!Pass1234"})
    token = login_resp.json()["token"]

    db_file = str(isolated_db / "emuwarez_uploadrr.db")
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT token_hash FROM auth_sessions").fetchall()
    conn.close()

    stored_hashes = [r[0] for r in rows]
    assert token not in stored_hashes, "El token claro NO debe guardarse en la BD"
    expected_hash = hash_token(token)
    assert expected_hash in stored_hashes, "El hash del token debe estar en la BD"
