"""Tests for maintenance API endpoints."""
from __future__ import annotations



# ---------- /api/maintenance/status ----------

def test_maintenance_status_requires_auth(client):
    resp = client.get("/api/maintenance/status")
    assert resp.status_code == 401


def test_maintenance_status_ok(client, auth_headers):
    resp = client.get("/api/maintenance/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "config_inventory" in data
    assert "database" in data
    assert "backups_count" in data


# ---------- /api/maintenance/backup ----------

def test_create_backup_requires_auth(client):
    resp = client.post("/api/maintenance/backup", json={})
    assert resp.status_code == 401


def test_create_backup_ok(client, auth_headers):
    resp = client.post("/api/maintenance/backup", json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "archive_path" in data


# ---------- /api/maintenance/backups ----------

def test_list_backups_requires_auth(client):
    resp = client.get("/api/maintenance/backups")
    assert resp.status_code == 401


def test_list_backups_ok(client, auth_headers):
    resp = client.get("/api/maintenance/backups", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "backups" in data
    assert "count" in data


# ---------- /api/maintenance/restore ----------

def test_restore_requires_auth(client):
    resp = client.post("/api/maintenance/restore", json={"backup_name": "x.tar.gz"})
    assert resp.status_code == 401


def test_restore_dry_run_nonexistent_backup(client, auth_headers):
    resp = client.post(
        "/api/maintenance/restore",
        json={"backup_name": "emuwarez_config_no_existe.tar.gz", "dry_run": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "error" in data


# ---------- /api/maintenance/db/integrity-check ----------

def test_integrity_check_requires_auth(client):
    resp = client.post("/api/maintenance/db/integrity-check")
    assert resp.status_code == 401


def test_integrity_check_ok(client, auth_headers):
    resp = client.post("/api/maintenance/db/integrity-check", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["result"] == ["ok"]


# ---------- /api/maintenance/db/vacuum ----------

def test_vacuum_requires_auth(client):
    resp = client.post("/api/maintenance/db/vacuum", json={})
    assert resp.status_code == 401


def test_vacuum_dry_run(client, auth_headers):
    resp = client.post("/api/maintenance/db/vacuum", json={"dry_run": True}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["dry_run"] is True


def test_vacuum_apply_requires_confirmation(client, auth_headers):
    resp = client.post(
        "/api/maintenance/db/vacuum",
        json={"dry_run": False, "apply": True, "confirmation": "WRONG"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "MANTENIMIENTO_DB" in data["error"]
