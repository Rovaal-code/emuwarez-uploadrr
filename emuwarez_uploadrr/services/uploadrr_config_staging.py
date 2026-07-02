"""Uploadrr-EMU data/config.yaml staging — Phase 10E.

SAFETY CONTRACT:
- Every function here takes an explicit config_path: Path supplied by the
  caller. Nothing in this module resolves or defaults to a real Uploadrr/
  installation — tests always point config_path at tmp_path.
- write_staged_config() always creates a .bak backup before overwriting an
  existing file.
- Any preview/diff output redacts DEFAULT.tmdb and TRACKERS.EMU.api_key
  values — never returns raw secrets.

Reuses the pure, filesystem-agnostic YAML line helpers already implemented
in emuwarez_uploadrr/legacy.py (ported from the original monolithic
script): find_top_block, set_block_key, get_block_key,
set_child_inline_mapping, set_emu_config, yaml_scalar. Those functions only
operate on `lines: list[str]` in memory — no filesystem or subprocess
access — so reusing them here does not import any Uploadrr execution path.
"""
from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path
from typing import Any, Optional

from ..legacy import (
    get_block_key,
    get_emu_anon,
    get_emu_api_key,
    set_block_key,
    set_emu_config,
    yaml_scalar,
)

_SECRET_LINE_PATTERNS = [
    re.compile(r"^(\s*api_key\s*:\s*).+$"),
    re.compile(r"^(\s*tmdb\s*:\s*).+$"),
]


def default_uploadrr_config_path(uploadrr_dir: str) -> Path:
    """Return the conventional Uploadrr-EMU config.yaml path under uploadrr_dir/data.

    Pure path arithmetic — does not check existence or touch the filesystem.
    """
    return Path(uploadrr_dir) / "data" / "config.yaml"


def read_config_lines(config_path: Path) -> list[str]:
    """Read config.yaml lines from an explicit path. Returns [] if missing."""
    if not config_path.exists():
        return []
    return config_path.read_text(encoding="utf-8", errors="ignore").splitlines()


def backup_config(config_path: Path) -> Optional[Path]:
    """Create a .bak copy next to config_path if one doesn't already exist.

    Returns the backup path, or None if there was nothing to back up.
    """
    if not config_path.exists():
        return None
    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    if not backup_path.exists():
        backup_path.write_bytes(config_path.read_bytes())
    return backup_path


def restore_config_from_backup(config_path: Path) -> bool:
    """Restore config_path from its .bak file. Returns True if restored."""
    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    if not backup_path.exists():
        return False
    config_path.write_bytes(backup_path.read_bytes())
    return True


def write_staged_config(config_path: Path, lines: list[str]) -> Path:
    """Write staged lines to config_path, backing up any existing file first."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    backup_config(config_path)
    config_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return config_path


def get_tmdb_key(lines: list[str]) -> Optional[str]:
    return get_block_key(lines, "DEFAULT", "tmdb")


def stage_tmdb_key(lines: list[str], api_key: str) -> tuple[list[str], str]:
    """Stage DEFAULT.tmdb = <api_key> in memory. Returns (new_lines, change_message)."""
    staged = list(lines)
    message = set_block_key(staged, "DEFAULT", "tmdb", yaml_scalar(api_key))
    return staged, message


def stage_emu_config(
    lines: list[str], *, api_key: Optional[str] = None, anon: Optional[bool] = None
) -> tuple[list[str], str]:
    """Stage TRACKERS.EMU.api_key / anon in memory. Returns (new_lines, change_message)."""
    staged = list(lines)
    message = set_emu_config(staged, api_key=api_key, anon=anon)
    return staged, message


def _redact_value(value: str) -> str:
    """Redact a secret value to a short, non-reversible, deterministic
    fingerprint — different values redact differently, so a diff can still
    show that a change happened without revealing either value."""
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"***REDACTED:{digest}***"


def _redact_lines(lines: list[str]) -> list[str]:
    redacted = []
    for line in lines:
        out = line
        for pattern in _SECRET_LINE_PATTERNS:
            m = pattern.match(line)
            if m:
                out = m.group(1) + _redact_value(line[m.end(1):])
                break
        redacted.append(out)
    return redacted


def build_redacted_preview(lines: list[str]) -> list[str]:
    """Return a copy of lines with DEFAULT.tmdb / TRACKERS.EMU.api_key redacted."""
    return _redact_lines(lines)


def diff_staged_changes(old_lines: list[str], new_lines: list[str]) -> list[str]:
    """Return a unified diff between old and new lines, with secrets redacted."""
    old_redacted = _redact_lines(old_lines)
    new_redacted = _redact_lines(new_lines)
    return list(
        difflib.unified_diff(
            old_redacted,
            new_redacted,
            fromfile="config.yaml (actual)",
            tofile="config.yaml (propuesto)",
            lineterm="",
        )
    )


__all__ = [
    "default_uploadrr_config_path",
    "read_config_lines",
    "backup_config",
    "restore_config_from_backup",
    "write_staged_config",
    "get_tmdb_key",
    "stage_tmdb_key",
    "stage_emu_config",
    "get_emu_api_key",
    "get_emu_anon",
    "build_redacted_preview",
    "diff_staged_changes",
]
