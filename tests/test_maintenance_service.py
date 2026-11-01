"""Tests for maintenance_service."""
from __future__ import annotations

import sqlite3

import pytest

from emuwarez_uploadrr.services.maintenance_service import (
    VACUUM_CONFIRMATION,
    get_database_maintenance_status,
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


def test_vacuum_reports_freed_bytes_while_app_holds_wal_connection(db_config):
    """La BD va en WAL y el servidor tiene conexiones abiertas: sin checkpoint,
    el VACUUM compactaba pero el fichero no encogía y decía "Liberados 0 bytes"."""
    app = sqlite3.connect(str(db_config / "emuwarez_uploadrr.db"))
    app.execute("PRAGMA journal_mode=WAL")
    app.execute("CREATE TABLE t (x TEXT)")
    app.executemany("INSERT INTO t VALUES (?)", [("x" * 500,)] * 2000)
    app.commit()
    app.execute("DELETE FROM t")
    app.commit()
    app.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    try:
        result = run_database_vacuum(dry_run=False, apply=True, confirmation=VACUUM_CONFIRMATION)
    finally:
        app.close()
    assert result["ok"] is True
    assert result["bytes_saved"] > 500_000


def test_vacuum_with_a_read_still_open_does_not_claim_freed_bytes(db_config, monkeypatch):
    """Una lectura abierta impide el checkpoint: el VACUUM se hace, pero el
    fichero aún no ha encogido y el mensaje no puede decir que sí."""
    real_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: real_connect(*a, **{**k, "timeout": 0.1}))
    db = str(db_config / "emuwarez_uploadrr.db")
    app = real_connect(db)
    app.execute("PRAGMA journal_mode=WAL")
    app.execute("CREATE TABLE t (x TEXT)")
    app.executemany("INSERT INTO t VALUES (?)", [("x" * 500,)] * 2000)
    app.commit()
    app.execute("DELETE FROM t")
    app.commit()
    lector = real_connect(db)
    lector.execute("BEGIN")
    lector.execute("SELECT count(*) FROM settings").fetchone()
    try:
        result = run_database_vacuum(dry_run=False, apply=True, confirmation=VACUUM_CONFIRMATION)
    finally:
        lector.close()
        app.close()
    assert result["ok"] is True
    assert "Liberados" not in result["message"]


def test_vacuum_counts_the_wal_in_freed_bytes(db_config):
    """Con lo confirmado aún en el -wal, el checkpoint hace crecer el .db:
    midiendo solo el .db salían bytes liberados negativos."""
    app = sqlite3.connect(str(db_config / "emuwarez_uploadrr.db"))
    app.execute("PRAGMA journal_mode=WAL")
    app.execute("PRAGMA wal_autocheckpoint=0")
    app.execute("CREATE TABLE t (x TEXT)")
    app.executemany("INSERT INTO t VALUES (?)", [("x" * 500,)] * 2000)
    app.commit()
    try:
        result = run_database_vacuum(dry_run=False, apply=True, confirmation=VACUUM_CONFIRMATION)
    finally:
        app.close()
    assert result["ok"] is True
    assert result["bytes_saved"] >= 0
