"""API tests for /api/instances — Phase 11B: edit endpoint, Seerr instance
type, and the instances.type CHECK-constraint widening migration.

Real *arr/Seerr HTTP calls are always mocked — never real network traffic.
"""
from __future__ import annotations

from unittest.mock import patch

from emuwarez_uploadrr.database import connect, db_path, init_db


def _add_instance(client, auth_headers, *, type="radarr", name="Test", url="http://x:7878", api_key="key123"):
    resp = client.post(
        "/api/instances",
        json={"type": type, "name": name, "url": url, "api_key": api_key},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    instances = client.get("/api/instances", headers=auth_headers).json()
    return next(i for i in instances if i["type"] == type and i["name"] == name)


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------

def test_list_requires_auth(client):
    assert client.get("/api/instances").status_code == 401


def test_update_requires_auth(client):
    assert client.put("/api/instances/1", json={"name": "x"}).status_code == 401


# ---------------------------------------------------------------------------
# Seerr as a valid instance type (CHECK constraint widened)
# ---------------------------------------------------------------------------

def test_create_seerr_instance(client, auth_headers):
    inst = _add_instance(client, auth_headers, type="seerr", name="Seerr", url="http://seerr:5055", api_key="seerrkey")
    assert inst["type"] == "seerr"
    assert inst["api_key_masked"] != "seerrkey"


def test_create_radarr_and_sonarr_still_work_after_migration(client, auth_headers):
    radarr = _add_instance(client, auth_headers, type="radarr", name="R1")
    sonarr = _add_instance(client, auth_headers, type="sonarr", name="S1")
    assert radarr["type"] == "radarr"
    assert sonarr["type"] == "sonarr"


def test_create_invalid_type_rejected(client, auth_headers):
    resp = client.post(
        "/api/instances",
        json={"type": "jellyfin", "name": "x", "url": "http://x", "api_key": "k"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/instances/{id} — edit (Phase 11B)
# ---------------------------------------------------------------------------

def test_update_instance_requires_auth_and_returns_404_for_unknown(client, auth_headers):
    resp = client.put("/api/instances/9999", json={"name": "x"}, headers=auth_headers)
    assert resp.status_code == 404


def test_update_instance_name_and_url(client, auth_headers):
    inst = _add_instance(client, auth_headers, name="Original")
    resp = client.put(
        f"/api/instances/{inst['id']}",
        json={"name": "Renamed", "url": "http://newhost:7878"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Renamed"
    assert data["url"] == "http://newhost:7878"
    assert data["id"] == inst["id"]  # same ID preserved, not recreated


def test_update_instance_blank_api_key_keeps_existing(client, auth_headers):
    inst = _add_instance(client, auth_headers, api_key="original-secret-key")
    original_masked = inst["api_key_masked"]

    resp = client.put(f"/api/instances/{inst['id']}", json={"name": "Still Original"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["api_key_masked"] == original_masked


def test_update_instance_new_api_key_changes_masked_value(client, auth_headers):
    inst = _add_instance(client, auth_headers, api_key="original-secret-key")
    resp = client.put(f"/api/instances/{inst['id']}", json={"api_key": "brand-new-secret-key"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["api_key_masked"] != inst["api_key_masked"]


def test_update_instance_can_disable(client, auth_headers):
    inst = _add_instance(client, auth_headers)
    resp = client.put(f"/api/instances/{inst['id']}", json={"enabled": False}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_update_instance_is_4k_and_is_anime(client, auth_headers):
    inst = _add_instance(client, auth_headers, type="radarr", name="R4k")
    resp = client.put(f"/api/instances/{inst['id']}", json={"is_4k": True, "is_anime": True}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_4k"] is True
    assert data["is_anime"] is True


def test_update_instance_response_never_contains_raw_key(client, auth_headers):
    inst = _add_instance(client, auth_headers)
    secret = "brand-new-super-secret"
    resp = client.put(f"/api/instances/{inst['id']}", json={"api_key": secret}, headers=auth_headers)
    assert secret not in resp.text


def test_update_instance_after_edit_can_be_tested_again(client, auth_headers):
    inst = _add_instance(client, auth_headers, type="radarr", name="R-edit-test")
    client.put(f"/api/instances/{inst['id']}", json={"url": "http://edited-host:7878"}, headers=auth_headers)

    with patch("emuwarez_uploadrr.services.instances.radarr.radarr_test_connection") as mock_test:
        mock_test.return_value = {"ok": True, "version": "5.0.0"}
        resp = client.post(f"/api/instances/{inst['id']}/test", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# Seerr test-connection through the instance-level /test route + username
# ---------------------------------------------------------------------------

def test_instance_test_seerr_returns_username(client, auth_headers):
    inst = _add_instance(client, auth_headers, type="seerr", name="Seerr Test")
    with patch("emuwarez_uploadrr.services.instances.seerr.seerr_test_connection") as mock_test:
        mock_test.return_value = {"ok": True, "version": "1.33.2", "username": "Alvaro"}
        resp = client.post(f"/api/instances/{inst['id']}/test", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["username"] == "Alvaro"


# ---------------------------------------------------------------------------
# Sync is not supported for Seerr yet (explicit 400, not a crash)
# ---------------------------------------------------------------------------

def test_sync_seerr_instance_returns_400(client, auth_headers):
    inst = _add_instance(client, auth_headers, type="seerr", name="Seerr NoSync")
    resp = client.post(f"/api/instances/{inst['id']}/sync", headers=auth_headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# instances.type CHECK-constraint widening migration
# ---------------------------------------------------------------------------

def test_migration_widens_type_check_and_is_idempotent(isolated_db):
    conn = connect(db_path())
    init_db(conn)  # first run performs the rebuild
    init_db(conn)  # second run must be a no-op, not an error

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'instances'"
    ).fetchone()
    assert "'seerr'" in row["sql"]

    # A seerr row can now be inserted directly without violating the CHECK constraint.
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key) VALUES ('seerr', 'x', 'http://x', 'k')"
    )
    conn.commit()
    conn.close()


def test_migration_preserves_existing_rows_and_ids(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO instances (type, name, url, api_key) VALUES ('radarr', 'Preserved', 'http://x', 'k')"
    )
    conn.commit()
    original_id = cur.lastrowid

    # Re-running init_db (and therefore the migration guard) must not touch existing rows.
    init_db(conn)
    row = conn.execute("SELECT * FROM instances WHERE id = ?", (original_id,)).fetchone()
    assert row is not None
    assert row["name"] == "Preserved"
    assert row["id"] == original_id
    conn.close()
