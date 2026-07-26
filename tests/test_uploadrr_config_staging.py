"""Tests for Uploadrr-EMU data/config.yaml staging (Phase 10E).

Every test operates exclusively under tmp_path — this module (and these
tests) never touch a real Uploadrr/ installation.
"""
from __future__ import annotations

from emuwarez_uploadrr.services.uploadrr_config_staging import (
    SCREENS_API_KEY_HOSTS,
    backup_config,
    build_redacted_preview,
    diff_staged_changes,
    get_tmdb_key,
    read_config_lines,
    restore_config_from_backup,
    stage_emu_config,
    stage_image_hosts,
    stage_tmdb_key,
    write_staged_config,
)


def test_read_config_lines_missing_file_returns_empty(tmp_path):
    assert read_config_lines(tmp_path / "config.yaml") == []


def test_stage_tmdb_key_sets_default_tmdb():
    lines = ["DEFAULT:", "  other: 1"]
    staged, message = stage_tmdb_key(lines, "TMDB_REAL_KEY")
    assert get_tmdb_key(staged) == "TMDB_REAL_KEY"
    assert "creado" in message or "actualizado" in message


def test_stage_tmdb_key_does_not_mutate_original_lines():
    lines = ["DEFAULT:", "  tmdb: 'old'"]
    staged, _ = stage_tmdb_key(lines, "new_key")
    assert get_tmdb_key(lines) == "old"
    assert get_tmdb_key(staged) == "new_key"


def test_stage_emu_config_sets_api_key_and_anon():
    lines: list[str] = []
    staged, message = stage_emu_config(lines, api_key="EMU_REAL_KEY", anon=True)
    text = "\n".join(staged)
    assert "EMU_REAL_KEY" in text
    assert "anon: True" in text or "anon: true" in text.lower()


def test_stage_image_hosts_sets_ordered_img_hosts_list():
    lines = ["SCREENS:", "  img_hosts: [imgbox]"]
    staged, message = stage_image_hosts(lines, img_hosts=["pixhost", "imgbb", "imgbox"])
    text = "\n".join(staged)
    assert "img_hosts: [pixhost, imgbb, imgbox]" in text
    assert "creado" in message or "actualizado" in message


def test_stage_image_hosts_sets_api_keys_inline_mapping():
    lines: list[str] = []
    staged, _ = stage_image_hosts(lines, api_keys={"imgbb": "IMGBB_REAL_KEY", "ptpimg": "PTPIMG_REAL_KEY"})
    text = "\n".join(staged)
    assert "IMGBB_REAL_KEY" in text
    assert "PTPIMG_REAL_KEY" in text
    assert "API_KEYS" in text


def test_stage_image_hosts_skips_untouched_sections_when_nothing_given():
    lines = ["SCREENS:", "  img_hosts: [imgbox]"]
    staged, message = stage_image_hosts(lines)
    assert staged == lines
    assert message == "SCREENS sin cambios"


def test_stage_image_hosts_only_stages_known_key_hosts():
    # hamster/imghost.dev take a key in our own catalog but aren't part of
    # SCREENS.API_KEYS in the real fork config — callers must filter to
    # SCREENS_API_KEY_HOSTS before calling this (upload_execution.py does).
    assert "hamster" not in SCREENS_API_KEY_HOSTS
    assert "imghost" not in SCREENS_API_KEY_HOSTS
    assert set(SCREENS_API_KEY_HOSTS) == {"imgbb", "ptpimg", "lensdump", "ptscreens", "onlyimage"}


def test_backup_config_creates_bak_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("DEFAULT:\n  tmdb: 'k'\n")
    backup_path = backup_config(config_path)
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.read_text() == config_path.read_text()


def test_backup_config_missing_file_returns_none(tmp_path):
    assert backup_config(tmp_path / "does-not-exist.yaml") is None


def test_backup_config_does_not_overwrite_existing_backup(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("v1")
    backup_config(config_path)
    config_path.write_text("v2")
    backup_config(config_path)  # should NOT overwrite the .bak with v2
    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    assert backup_path.read_text() == "v1"


def test_write_staged_config_creates_backup_before_overwrite(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("DEFAULT:\n  tmdb: 'old'\n")
    write_staged_config(config_path, ["DEFAULT:", "  tmdb: 'new'"])

    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    assert backup_path.exists()
    assert "old" in backup_path.read_text()
    assert "new" in config_path.read_text()


def test_write_staged_config_creates_parent_dirs(tmp_path):
    config_path = tmp_path / "nested" / "data" / "config.yaml"
    write_staged_config(config_path, ["DEFAULT:", "  tmdb: 'x'"])
    assert config_path.exists()


def test_restore_config_from_backup(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("original")
    backup_config(config_path)
    config_path.write_text("modified")

    restored = restore_config_from_backup(config_path)
    assert restored is True
    assert config_path.read_text() == "original"


def test_restore_config_from_backup_no_backup_returns_false(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("only version")
    assert restore_config_from_backup(config_path) is False


def test_build_redacted_preview_hides_tmdb_and_api_key():
    lines = ["DEFAULT:", "  tmdb: 'REALTMDBKEY'", "TRACKERS:", "  EMU:", "    api_key: 'REALEMUKEY'"]
    preview = build_redacted_preview(lines)
    text = "\n".join(preview)
    assert "REALTMDBKEY" not in text
    assert "REALEMUKEY" not in text
    assert "***REDACTED:" in text


def test_diff_staged_changes_redacts_secrets():
    old_lines = ["DEFAULT:", "  tmdb: 'OLDKEY'"]
    new_lines, _ = stage_tmdb_key(old_lines, "NEWKEY")
    diff = diff_staged_changes(old_lines, new_lines)
    diff_text = "\n".join(diff)
    assert "OLDKEY" not in diff_text
    assert "NEWKEY" not in diff_text
    assert any(line.startswith(("+", "-")) for line in diff if not line.startswith(("+++", "---")))


def test_never_touches_real_uploadrr_path(tmp_path):
    """Structural guard: config_path is always caller-supplied (tmp_path in
    tests) — nothing in this module hardcodes or defaults to a real
    Uploadrr/ install path."""
    import emuwarez_uploadrr.services.uploadrr_config_staging as mod
    import inspect

    source = inspect.getsource(mod)
    assert "uploadrr_dir(" not in source
    assert "Uploadrr/data/config.yaml" not in source
