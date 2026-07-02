"""Uploadrr-EMU CLI contract — Phase 10E.

SAFETY CONTRACT:
- Never executes anything. Only builds argv lists and validates inputs.
- Never accepts a source_path — only prepared_path/applied_path.
- Never puts secrets (API keys) on the command line — Uploadrr-EMU reads
  them from its own Uploadrr/data/config.yaml, never from CLI args or env.
- shell=False always — callers must pass the returned list directly to
  subprocess, never join it into a string.

Confirms the real Uploadrr-EMU flag mapping documented in
docs/codex_phase_10d_uploadrr_emu_runtime_audit.md and
docs/codex_phase_10e0_uploadrr_backend_inventory.md:

    python upload.py <prepared_path> -tk EMU -mt "<title>" -tmdb <id> \
        -ua -c movie|tv -res <resolution> [-season Sxx] [-episode Exx]

This is the mapping already implemented (but disconnected from the job
pipeline) in emuwarez_uploadrr/legacy.py::build_uploadrr_command.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from ..database import get_setting_canonical, get_state
from .filesystem_apply import ensure_path_under_base

RUNTIME_GENERIC = "uploadrr_generic"
RUNTIME_EMU = "uploadrr_emu"

DEFAULT_RUNTIME_TYPE = RUNTIME_EMU
DEFAULT_TIMEOUT_SECONDS = 7200

VALID_CATEGORIES = ("movie", "tv")


def get_runtime_settings(conn: sqlite3.Connection) -> dict:
    """Resolve the Uploadrr runtime settings needed to build/validate a command."""
    timeout_raw = get_setting_canonical(conn, "uploadrr.timeout")
    try:
        timeout = int(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS

    return {
        "uploadrr_path": get_setting_canonical(conn, "uploadrr.path") or "",
        "python_path": get_setting_canonical(conn, "uploadrr.python_path") or "",
        "runtime_type": get_setting_canonical(conn, "uploadrr.runtime_type") or DEFAULT_RUNTIME_TYPE,
        "timeout": timeout,
        "allowed_roots": get_allowed_roots(conn),
    }


def get_allowed_roots(conn: sqlite3.Connection) -> list[str]:
    """Return the configured allowed roots for prepared_path checks.

    An empty `uploadrr.allowed_roots` setting means "fall back to the
    existing hardlink_base setting" (same base already enforced by
    services/filesystem_apply.py for nomenclature hardlinks).
    """
    raw = get_setting_canonical(conn, "uploadrr.allowed_roots")
    roots: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                roots = [str(r) for r in parsed if r]
        except (TypeError, ValueError):
            pass
    if roots:
        return roots

    hardlink_base = None
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'hardlink_base'"
        ).fetchone()
        hardlink_base = row["value"] if row else None
    except Exception:
        hardlink_base = None
    if not hardlink_base:
        hardlink_base = get_state(conn, "hardlink_base")
    return [hardlink_base] if hardlink_base else []


def path_within_allowed_roots(path: str, allowed_roots: list[str]) -> bool:
    """Return True if path resolves inside at least one allowed root.

    Returns False (never grants access) when allowed_roots is empty.
    """
    if not path or not allowed_roots:
        return False
    return any(ensure_path_under_base(path, root) for root in allowed_roots if root)


def _format_season(value) -> str:
    if isinstance(value, int):
        return f"S{value:02d}"
    return str(value)


def _format_episode(value) -> str:
    if isinstance(value, int):
        return f"E{value:02d}"
    return str(value)


def build_uploadrr_emu_command(
    *,
    python_path: str,
    uploadrr_script_path: str,
    prepared_path: str,
    torrent_name: str,
    tmdb_id: Optional[int | str] = None,
    category: str,
    resolution: str = "",
    season: Optional[int | str] = None,
    episode: Optional[int | str] = None,
) -> list[str]:
    """Build the real Uploadrr-EMU argv. Always a list[str], never a shell string.

    Only accepts prepared_path (or applied_path passed as prepared_path by
    the caller) — there is intentionally no source_path parameter, so the
    original library file can never be passed to this builder by mistake.
    """
    cmd: list[str] = [
        python_path,
        uploadrr_script_path,
        prepared_path,
        "-tk", "EMU",
        "-mt", torrent_name,
    ]
    if tmdb_id:
        cmd += ["-tmdb", str(tmdb_id)]
    cmd += ["-ua", "-c", "tv" if category == "tv" else "movie"]
    if resolution:
        cmd += ["-res", resolution]
    if season:
        cmd += ["-season", _format_season(season)]
    if episode:
        cmd += ["-episode", _format_episode(episode)]
    return cmd


def render_command_preview(command: list[str]) -> str:
    """Render an argv list as a human-readable, quoted command line."""
    return " ".join(f'"{a}"' if " " in a else a for a in command)


def redact_uploadrr_command(command: list[str], secrets: Optional[list[str]] = None) -> list[str]:
    """Return a redacted copy of an argv list.

    Uploadrr-EMU never receives API keys as CLI args (they live only in its
    own config.yaml), so this is a defensive second layer in case a secret
    value ever leaks into an unrelated field (e.g. a torrent_name).
    """
    secrets = [s for s in (secrets or []) if s and len(s) > 3]
    redacted = []
    for arg in command:
        value = arg
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, "***REDACTED***")
        redacted.append(value)
    return redacted


def validate_uploadrr_emu_contract(
    *,
    prepared_path: str,
    torrent_name: str,
    tmdb_id: Optional[int | str],
    category: str,
    resolution: str,
    allowed_roots: list[str],
    python_path: str,
    uploadrr_script_path: str,
) -> dict:
    """Validate all preconditions for building/using an Uploadrr-EMU command.

    Never executes anything. Returns {"valid", "errors", "warnings"}.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not prepared_path:
        errors.append("No hay una ruta preparada (prepared_path/applied_path) para Uploadrr-EMU.")
    elif not path_within_allowed_roots(prepared_path, allowed_roots):
        errors.append(
            f"La ruta preparada está fuera de los allowed_roots configurados: {prepared_path}"
        )

    if not torrent_name or not torrent_name.strip():
        errors.append("Falta el título (torrent_name) requerido para -mt.")

    if not tmdb_id:
        warnings.append("No hay tmdb_id asociado; el comando real no incluirá -tmdb.")

    if category not in VALID_CATEGORIES:
        errors.append(f"category inválida para Uploadrr-EMU: {category!r} (debe ser movie|tv).")

    if not resolution:
        warnings.append("No hay resolución configurada; el comando real no incluirá -res.")

    if not python_path:
        errors.append("uploadrr.python_path no configurado.")
    elif not Path(python_path).exists():
        errors.append(f"uploadrr.python_path no existe: {python_path}")

    if not uploadrr_script_path:
        errors.append("uploadrr.path no configurado.")
    elif not Path(uploadrr_script_path).exists():
        errors.append(f"Script de Uploadrr no encontrado: {uploadrr_script_path}")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


__all__ = [
    "RUNTIME_GENERIC",
    "RUNTIME_EMU",
    "DEFAULT_RUNTIME_TYPE",
    "DEFAULT_TIMEOUT_SECONDS",
    "VALID_CATEGORIES",
    "get_runtime_settings",
    "get_allowed_roots",
    "path_within_allowed_roots",
    "build_uploadrr_emu_command",
    "render_command_preview",
    "redact_uploadrr_command",
    "validate_uploadrr_emu_contract",
]
