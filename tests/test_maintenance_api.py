"""Tests for maintenance API endpoints."""
from __future__ import annotations

import pytest


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


# ---------- /api/maintenance/export-settings ----------

def test_export_settings_requires_auth(client):
    resp = client.get("/api/maintenance/export-settings")
    assert resp.status_code == 401


def test_export_settings_masks_secrets(client, auth_headers):
    resp = client.get("/api/maintenance/export-settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["secrets_masked"] is True
    settings = data["settings"]
    assert settings.get("tmdb_api_key") in (None, "***MASKED***")
    assert settings.get("emu_api_key") in (None, "***MASKED***")


def test_export_settings_no_raw_secrets_in_response(client, auth_headers):
    resp = client.get("/api/maintenance/export-settings", headers=auth_headers)
    text = resp.text
    # real secret values must not appear; masked token is OK
    assert "secret-tmdb" not in text
    assert "secret-emu" not in text


# ---------- /api/maintenance/import-settings ----------

def test_import_settings_requires_auth(client):
    resp = client.post("/api/maintenance/import-settings", json={"payload": {}})
    assert resp.status_code == 401


def test_import_settings_dry_run_default(client, auth_headers):
    resp = client.post(
        "/api/maintenance/import-settings",
        json={"payload": {"app_name": "Nueva App"}, "dry_run": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["dry_run"] is True


def test_import_settings_rejects_unknown_keys(client, auth_headers):
    resp = client.post(
        "/api/maintenance/import-settings",
        json={"payload": {"unknown_field": "x"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "desconocidas" in data["error"].lower()


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
    resp = client.post("/api/maintenance/restore", json={"backup_path": "/tmp/x.tar.gz"})
    assert resp.status_code == 401


def test_restore_dry_run_nonexistent_path(client, auth_headers):
    resp = client.post(
        "/api/maintenance/restore",
        json={"backup_path": "/nonexistent/path.tar.gz", "dry_run": True},
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


# ---------- /api/maintenance/logs/cleanup ----------

def test_cleanup_logs_requires_auth(client):
    resp = client.post("/api/maintenance/logs/cleanup", json={})
    assert resp.status_code == 401


def test_cleanup_logs_dry_run(client, auth_headers):
    resp = client.post("/api/maintenance/logs/cleanup", json={"dry_run": True, "days": 30}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
