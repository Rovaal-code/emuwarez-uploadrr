"""Tests for backup_service."""
from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from emuwarez_uploadrr.services.backup_service import (
    RESTORE_CONFIRMATION,
    create_config_backup,
    get_config_inventory,
    list_config_backups,
    restore_config_backup,
)


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    (d / "emuwarez_uploadrr.db").write_text("fake db")
    (d / "settings.json").write_text("{}")
    monkeypatch.setenv("CONFIG_DIR", str(d))
    return d


def test_get_config_inventory_exists(config_dir):
    result = get_config_inventory()
    assert result["exists"] is True
    assert result["total_size_bytes"] > 0
    names = [f["name"] for f in result["files"]]
    assert any("emuwarez_uploadrr.db" in n for n in names)


def test_get_config_inventory_no_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "nonexistent"))
    result = get_config_inventory()
    assert result["exists"] is False
    assert result["files"] == []


def test_create_backup_ok(config_dir):
    result = create_config_backup()
    assert result["ok"] is True
    assert Path(result["archive_path"]).exists()
    assert result["size_bytes"] > 0


def test_create_backup_no_secrets_by_default(config_dir):
    result = create_config_backup()
    assert result["include_secrets"] is False


def test_create_backup_include_secrets_requires_confirmation(config_dir):
    result = create_config_backup(include_secrets=True, confirmation=None)
    assert result["ok"] is False
    assert RESTORE_CONFIRMATION in result["error"]


def test_create_backup_include_secrets_with_confirmation(config_dir):
    result = create_config_backup(include_secrets=True, confirmation=RESTORE_CONFIRMATION)
    assert result["ok"] is True
    assert result["include_secrets"] is True


def test_list_config_backups(config_dir):
    create_config_backup()
    backups = list_config_backups()
    assert len(backups) >= 1
    for b in backups:
        assert "name" in b
        assert "size_bytes" in b
        assert "created_at" in b


def test_restore_config_backup_dry_run(config_dir):
    create_result = create_config_backup()
    archive = create_result["archive_path"]
    result = restore_config_backup(archive, dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["action"] == "preview"
    assert result["files_in_archive"] > 0


def test_restore_config_backup_requires_confirmation(config_dir):
    create_result = create_config_backup()
    archive = create_result["archive_path"]
    result = restore_config_backup(archive, dry_run=False, apply=True, confirmation="WRONG")
    assert result["ok"] is False
    assert RESTORE_CONFIRMATION in result["error"]


def test_restore_config_backup_not_found(config_dir):
    result = restore_config_backup("/nonexistent/path.tar.gz")
    assert result["ok"] is False
    assert "no encontrado" in result["error"].lower()
