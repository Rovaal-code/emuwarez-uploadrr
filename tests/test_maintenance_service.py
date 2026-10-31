"""Tests for maintenance_service."""
from __future__ import annotations

import sqlite3

import pytest

from emuwarez_uploadrr.services.maintenance_service import (
    VACUUM_CONFIRMATION,
    get_database_maintenance_status,
    run_database_analyze,
    run_database_integrity_check,
    run_database_vacuum,
)


@pytest.fixture
def db_config(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    db = d / "emuwarez_uploadrr.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings VALUES ('app_name', 'Test')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("CONFIG_DIR", str(d))
    return d


def test_get_database_maintenance_status_ok(db_config):
    result = get_database_maintenance_status()
    assert result["ok"] is True
    assert result["size_bytes"] > 0
    assert result["page_count"] > 0


def test_get_database_maintenance_status_no_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "noexist"))
    result = get_database_maintenance_status()
    assert result["ok"] is False
    assert "error" in result


def test_integrity_check_passes(db_config):
    result = run_database_integrity_check()
    assert result["ok"] is True
    assert result["result"] == ["ok"]


def test_integrity_check_no_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "noexist"))
    result = run_database_integrity_check()
    assert result["ok"] is False


def test_vacuum_dry_run_preview(db_config):
    result = run_database_vacuum(dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True


def test_vacuum_requires_confirmation(db_config):
    result = run_database_vacuum(dry_run=False, apply=True, confirmation="WRONG")
    assert result["ok"] is False
    assert VACUUM_CONFIRMATION in result["error"]


def test_vacuum_apply_with_confirmation(db_config):
    result = run_database_vacuum(dry_run=False, apply=True, confirmation=VACUUM_CONFIRMATION)
    assert result["ok"] is True
    assert result["dry_run"] is False
    assert "size_bytes_after" in result
