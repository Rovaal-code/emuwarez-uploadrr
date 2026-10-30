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
    assert data["next_step"] == "emu"


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
    # Phase 4: dashboard/summary is now a real endpoint
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Real response has library_total, not implemented=False
    assert "library_total" in data or "implemented" in data


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

def _ok_test_result(service: str) -> dict:
    return {"ok": True, "service": service, "status": "connected", "message": "Conexión correcta"}


def _fail_test_result(service: str) -> dict:
    return {"ok": False, "service": service, "status": "invalid_key", "message": f"API key de {service} inválida"}


def test_setup_tmdb_success(client, auth_headers, monkeypatch):
    # TMDb is mandatory now: setup_tmdb() live-tests the key before saving it.
    monkeypatch.setattr(
        "emuwarez_uploadrr.services.integration_tests.test_tmdb_connection",
        lambda *a, **k: _ok_test_result("tmdb"),
    )
    resp = client.post(
        "/api/setup/tmdb",
        json={"api_key": "abc123tmdb"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    status_resp = client.get("/api/setup/status")
    assert status_resp.json()["tmdb_configured"] is True


def test_setup_tmdb_rejects_invalid_key(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "emuwarez_uploadrr.services.integration_tests.test_tmdb_connection",
        lambda *a, **k: _fail_test_result("tmdb"),
    )
    resp = client.post("/api/setup/tmdb", json={"api_key": "bad"}, headers=auth_headers)
    assert resp.status_code == 400

    status_resp = client.get("/api/setup/status")
    assert status_resp.json()["tmdb_configured"] is False


def test_setup_emu_success(client, auth_headers, monkeypatch):
    # eMuwarez is mandatory: setup_emu() live-tests the key before saving it.
    monkeypatch.setattr(
        "emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection",
        lambda *a, **k: _ok_test_result("emuwarez"),
    )
    resp = client.post(
        "/api/setup/emu",
        json={"api_key": "abc123emu", "endpoint_url": "https://emu.example.com/api"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    status_resp = client.get("/api/setup/status")
    assert status_resp.json()["emu_configured"] is True


def test_setup_emu_rejects_invalid_key(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection",
        lambda *a, **k: _fail_test_result("emuwarez"),
    )
    resp = client.post("/api/setup/emu", json={"api_key": "bad"}, headers=auth_headers)
    assert resp.status_code == 400

    status_resp = client.get("/api/setup/status")
    assert status_resp.json()["emu_configured"] is False


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


def test_setup_complete_fails_without_tmdb_or_emu(client, auth_headers):
    # TMDb and eMuwarez are mandatory — instances/Uploadrr stay skippable,
    # but completing without a validated TMDb/eMuwarez key must be blocked.
    resp = client.post("/api/setup/complete", headers=auth_headers)
    assert resp.status_code == 400
    assert "emu" in resp.json()["detail"]
    assert "tmdb" in resp.json()["detail"]


def test_full_setup_flow(client, auth_headers, monkeypatch):
    """Complete the entire setup wizard end to end."""
    monkeypatch.setattr(
        "emuwarez_uploadrr.services.integration_tests.test_tmdb_connection",
        lambda *a, **k: _ok_test_result("tmdb"),
    )
    monkeypatch.setattr(
        "emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection",
        lambda *a, **k: _ok_test_result("emuwarez"),
    )
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


# ---------------------------------------------------------------------------
# Change credentials
# ---------------------------------------------------------------------------

def test_change_password_success(client, auth_headers):
    resp = client.post("/api/auth/change-credentials", headers=auth_headers, json={
        "current_password": "TestPass1!secret",
        "new_password": "NewerPass2!secret",
    })
    assert resp.status_code == 200, resp.text
    # Old password no longer works, new one does.
    old = client.post("/api/auth/login", json={"username": "testadmin", "password": "TestPass1!secret"})
    assert old.status_code == 401
    new = client.post("/api/auth/login", json={"username": "testadmin", "password": "NewerPass2!secret"})
    assert new.status_code == 200


def test_change_password_revokes_other_sessions(client, auth_headers):
    otra = client.post("/api/auth/login", json={"username": "testadmin", "password": "TestPass1!secret"}).json()["token"]
    resp = client.post("/api/auth/change-credentials", headers=auth_headers, json={
        "current_password": "TestPass1!secret",
        "new_password": "NewerPass2!secret",
    })
    assert resp.status_code == 200, resp.text
    # La sesión que cambia la contraseña sigue; la otra ya no vale.
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {otra}"}).status_code == 401


def test_reset_password_revokes_every_session(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path
    from emuwarez_uploadrr.web.services.auth_service import get_user_by_username, update_password
    # Lo que hace `web reset-password`: sin token que conservar.
    with connect(db_path()) as conn:
        update_password(conn, get_user_by_username(conn, "testadmin")["id"], "NewerPass2!secret")
        conn.commit()
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401


def test_concurrent_create_admin_creates_only_one(client):
    import threading

    from emuwarez_uploadrr.database import connect, db_path
    from emuwarez_uploadrr.web.app import create_app

    client.get("/api/setup/status")  # crea las tablas
    for ronda in range(3):
        with connect(db_path()) as conn:
            conn.execute("DELETE FROM users")
            conn.commit()
        salida = threading.Event()
        estados = []

        def crear(nombre):
            otro = TestClient(create_app())
            salida.wait()
            r = otro.post("/api/setup/admin", json={"username": nombre, "password": "TestPass1!secret"})
            estados.append(r.status_code)

        hilos = [threading.Thread(target=crear, args=(f"admin{ronda}{i}",)) for i in range(2)]
        for h in hilos:
            h.start()
        salida.set()
        for h in hilos:
            h.join()
        with connect(db_path()) as conn:
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        assert admins == 1, estados
        assert sorted(estados)[0] == 201 and sorted(estados)[1] in (400, 409)


def test_change_username_success(client, auth_headers):
    resp = client.post("/api/auth/change-credentials", headers=auth_headers, json={
        "current_password": "TestPass1!secret",
        "new_username": "renamedadmin",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "renamedadmin"
    new = client.post("/api/auth/login", json={"username": "renamedadmin", "password": "TestPass1!secret"})
    assert new.status_code == 200


def test_change_credentials_wrong_current_password(client, auth_headers):
    resp = client.post("/api/auth/change-credentials", headers=auth_headers, json={
        "current_password": "WrongOne1!",
        "new_password": "NewerPass2!secret",
    })
    # 400, not 401 — the frontend treats any 401 as "session expired" and
    # clears the active token, which must not happen just for a typo'd
    # current password.
    assert resp.status_code == 400


def test_change_credentials_weak_new_password(client, auth_headers):
    resp = client.post("/api/auth/change-credentials", headers=auth_headers, json={
        "current_password": "TestPass1!secret",
        "new_password": "weak",
    })
    assert resp.status_code == 422


def test_change_credentials_nothing_to_change(client, auth_headers):
    resp = client.post("/api/auth/change-credentials", headers=auth_headers, json={
        "current_password": "TestPass1!secret",
    })
    assert resp.status_code == 400


def test_change_credentials_requires_auth(client):
    resp = client.post("/api/auth/change-credentials", json={
        "current_password": "TestPass1!secret",
        "new_password": "NewerPass2!secret",
    })
    assert resp.status_code == 401
