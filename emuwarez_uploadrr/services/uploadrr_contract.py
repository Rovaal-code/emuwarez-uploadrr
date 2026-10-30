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
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Uploadrr-EMU is bundled inside the Docker image as an internal dependency
# (like mediainfo/ffmpeg) — the user configures nothing. These defaults point
# at the in-image location and interpreter; both can still be overridden by a
# setting or an env var for local development.
DEFAULT_UPLOADRR_PATH = os.environ.get("UPLOADRR_PATH", "/opt/Uploadrr")
DEFAULT_UPLOADRR_PYTHON = os.environ.get("UPLOADRR_PYTHON", sys.executable)

from ..database import get_setting_canonical
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
        "uploadrr_path": get_setting_canonical(conn, "uploadrr.path") or DEFAULT_UPLOADRR_PATH,
        "python_path": get_setting_canonical(conn, "uploadrr.python_path") or DEFAULT_UPLOADRR_PYTHON,
        "runtime_type": get_setting_canonical(conn, "uploadrr.runtime_type") or DEFAULT_RUNTIME_TYPE,
        "timeout": timeout,
        "allowed_roots": get_allowed_roots(conn),
    }


DEFAULT_ALLOWED_ROOTS = ["/data"]


def get_allowed_roots(conn: sqlite3.Connection) -> list[str]:
    """Return the configured allowed roots for prepared_path checks.

    This is the folder(s) where THIS app's own container reaches the media,
    not necessarily the same path Radarr/Sonarr themselves report. Defaults
    to DEFAULT_ALLOWED_ROOTS ("/data") when `uploadrr.allowed_roots` has
    never been set — the same mount point convention used by Radarr/Sonarr's
    own generic docker-compose (see Settings > Acceso a la biblioteca),
    so a fresh install works without touching this setting. Set it
    explicitly to override (e.g. a split /movies + /tv layout), or to an
    empty list to fail closed and block real uploads entirely.
    """
    raw = get_setting_canonical(conn, "uploadrr.allowed_roots")
    if raw is None:
        return list(DEFAULT_ALLOWED_ROOTS)
    roots: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                roots = [str(r) for r in parsed if r]
        except (TypeError, ValueError):
            pass
    return roots


def path_within_allowed_roots(path: str, allowed_roots: list[str]) -> bool:
    """Return True if path resolves inside at least one allowed root.

    Returns False (never grants access) when allowed_roots is empty.
    """
    if not path or not allowed_roots:
        return False
    return any(ensure_path_under_base(path, root) for root in allowed_roots if root)


# Formato de la nomenclatura → `-t` de Uploadrr-EMU, que si no lo deduce del nombre (y «Charlotte's Web»
# pasaba por WEB-DL). SD y DVD no tienen tipo allí: sin `-t`, como antes.
_UPLOADRR_TYPES = {
    "Full BluRay": "disc",
    "FBD": "disc",
    "FDVD": "disc",
    "BDRemux": "remux",
    "BDReMux": "remux",
    "BluRay": "encode",
    "MHD": "encode",
    "WEB-DL": "webdl",
    "WEBRip": "webrip",
    "WEBRIP": "webrip",
    "HDTV": "hdtv",
}


def _format_season(value) -> str:
    if isinstance(value, int):
        return f"S{value:02d}"
    return str(value)


def _format_episode(value) -> str:
    if isinstance(value, int):
        return f"E{value:02d}"
    return str(value)


# Uploadrr's `-res` argument is an argparse `choices=[...]` field: any value
# outside that set makes upload.py abort before it starts. legacy.py guarded
# against this with uploadrr_resolution() (regex → `\d+p` or "other"); we
# replicate that here so the contract is robust by construction, not just by
# convention on whatever upstream stored in proposal.resolution.
_UPLOADRR_RES_CHOICES = {
    "2160p", "1080p", "1080i", "720p", "576p", "576i",
    "480p", "480i", "8640p", "4320p", "other",
}


def _normalize_resolution(value: str) -> str:
    """Coerce an arbitrary resolution string into a value Uploadrr `-res` accepts.

    Returns "" when there is no resolution to pass (caller then omits `-res`
    entirely and lets Uploadrr auto-detect). A non-empty but unrecognized
    value collapses to "other" — matching legacy.py::uploadrr_resolution.
    """
    if not value:
        return ""
    text = str(value).strip().lower()
    if text in _UPLOADRR_RES_CHOICES:
        return text
    m = re.match(r"(\d+p)", text)
    if m and m.group(1) in _UPLOADRR_RES_CHOICES:
        return m.group(1)
    return "other"


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
    release_format: Optional[str] = None,
) -> list[str]:
    """Build the real Uploadrr-EMU argv. Always a list[str], never a shell string.

    `release_format` is the nomenclature's source code (WEB-DL, BDRemux…), sent as `-t`.

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
    resolution = _normalize_resolution(resolution)
    if resolution:
        cmd += ["-res", resolution]
    # La temporada 0 (especiales) también cuenta: «if season» la perdía.
    if season is not None and season != "":
        cmd += ["-season", _format_season(season)]
    if episode is not None and episode != "":
        cmd += ["-episode", _format_episode(episode)]
    release_type = _UPLOADRR_TYPES.get(str(release_format or "").strip())
    if release_type:
        cmd += ["-t", release_type]
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
