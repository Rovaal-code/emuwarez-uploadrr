"""Tests for config_export service."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from emuwarez_uploadrr.services.config_export import (
    EXPORT_SECRETS_CONFIRMATION,
    IMPORT_CONFIRMATION,
    SETTINGS_SCHEMA,
    export_settings,
    import_settings,
    mask_exported_secret,
)

_MASKED = "***MASKED***"


@pytest.fixture
def db_config(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    db = d / "emuwarez_uploadrr.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings VALUES ('app_name', 'Test App')")
    conn.execute("INSERT INTO settings VALUES ('tmdb_api_key', 'secret-tmdb')")
    conn.execute("INSERT INTO settings VALUES ('emu_api_key', 'secret-emu')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("CONFIG_DIR", str(d))
    return d


def test_mask_exported_secret_with_value():
    assert mask_exported_secret("abc") == _MASKED


def test_mask_exported_secret_empty():
    assert mask_exported_secret("") is None


def test_mask_exported_secret_none():
    assert mask_exported_secret(None) is None


def test_export_settings_masks_secrets_by_default(db_config):
    result = export_settings()
    assert result["ok"] is True
    assert result["secrets_masked"] is True
    assert result["settings"]["app_name"] == "Test App"
    assert result["settings"]["tmdb_api_key"] == _MASKED
    assert result["settings"]["emu_api_key"] == _MASKED


def test_export_settings_include_secrets_requires_confirmation(db_config):
    result = export_settings(include_secrets=True, confirmation=None)
    assert result["ok"] is False
    assert EXPORT_SECRETS_CONFIRMATION in result["error"]


def test_export_settings_include_secrets_with_confirmation(db_config):
    result = export_settings(include_secrets=True, confirmation=EXPORT_SECRETS_CONFIRMATION)
    assert result["ok"] is True
    assert result["include_secrets"] is True
    assert result["settings"]["tmdb_api_key"] == "secret-tmdb"


def test_import_settings_dry_run_preview(db_config):
    result = import_settings({"app_name": "Nueva App"}, dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert "app_name" in result["keys_to_write"]


def test_import_settings_apply_requires_confirmation(db_config):
    result = import_settings({"app_name": "X"}, dry_run=False, apply=True, confirmation="WRONG")
    assert result["ok"] is False
    assert IMPORT_CONFIRMATION in result["error"]


def test_import_settings_rejects_unknown_keys(db_config):
    result = import_settings({"unknown_key": "val"})
    assert result["ok"] is False
    assert "desconocidas" in result["error"].lower()


def test_import_settings_skips_masked_values(db_config):
    result = import_settings({"app_name": "X", "tmdb_api_key": _MASKED}, dry_run=True)
    assert result["ok"] is True
    assert "tmdb_api_key" in result["keys_skipped_masked"]
    assert "app_name" in result["keys_to_write"]


def test_settings_schema_has_secret_flags():
    assert SETTINGS_SCHEMA["tmdb_api_key"]["secret"] is True
    assert SETTINGS_SCHEMA["emu_api_key"]["secret"] is True
    assert SETTINGS_SCHEMA["app_name"]["secret"] is False
