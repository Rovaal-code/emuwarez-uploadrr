"""Connection test helpers for external integrations (Phase 10C).

Safety rules:
- Read-only operations only.
- API keys are never returned or logged in full.
- No writes to TMDb, eMuwarez, Radarr or Sonarr.
- No eMuwarez request creation.
- No torrent uploads.
- Uploadrr is explicitly excluded from this module.
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

_TIMEOUT = 10  # seconds — short timeout for connection probes


def _ok(service: str, status: str = "connected", message: str = "Conexión correcta", details: Optional[dict] = None) -> dict:
    return {"ok": True, "service": service, "status": status, "message": message, "details": details or {}}


def _fail(service: str, status: str, message: str, details: Optional[dict] = None) -> dict:
    return {"ok": False, "service": service, "status": status, "message": message, "details": details or {}}


# ---------------------------------------------------------------------------
# TMDb
# ---------------------------------------------------------------------------

def test_tmdb_connection(
    api_key: Optional[str] = None,
    language: str = "es-ES",
    region: str = "ES",
    *,
    conn=None,
) -> dict:
    """Probe TMDb API using GET /3/configuration (read-only, no side effects).

    If api_key is None, reads the stored key from DB.
    Never returns or logs the full key.
    """
    _key = api_key
    if not _key and conn is not None:
        row = conn.execute("SELECT value FROM settings WHERE key = 'tmdb.api_key'").fetchone()
        _key = row["value"] if row else None

    if not _key or not _key.strip():
        return _fail("tmdb", "not_configured", "TMDb API key no configurada")

    _key = _key.strip()
    url = f"https://api.themoviedb.org/3/configuration?api_key={urllib.parse.quote(_key)}&language={urllib.parse.quote(language)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "emuwarez-uploadrr/3"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return _ok("tmdb", details={"http_status": resp.status})
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return _fail("tmdb", "invalid_key", "API key de TMDb inválida o no autorizada")
        return _fail("tmdb", "connection_error", f"Error HTTP {exc.code} al conectar con TMDb")
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower() or isinstance(exc.reason, socket.timeout):
            return _fail("tmdb", "timeout", "Timeout al conectar con TMDb")
        return _fail("tmdb", "connection_error", f"No se pudo conectar con TMDb: {reason}")
    except Exception as exc:
        return _fail("tmdb", "unexpected_error", f"Error inesperado: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# eMuwarez
# ---------------------------------------------------------------------------

def test_emuwarez_connection(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    *,
    conn=None,
) -> dict:
    """Probe eMuwarez using GET /api/torrents/filter?perPage=1 (read-only).

    If api_key/base_url are None, reads stored values from DB.
    Never creates requests. Never uploads torrents.
    """
    _key = api_key
    _base = base_url

    if conn is not None:
        if not _key:
            row = conn.execute("SELECT value FROM settings WHERE key = 'emu.api_key'").fetchone()
            _key = row["value"] if row else None
        if not _base:
            row = conn.execute("SELECT value FROM settings WHERE key = 'emu.endpoint_url'").fetchone()
            _base = row["value"] if row else None

    if not _key or not _key.strip():
        return _fail("emuwarez", "not_configured", "API key de eMuwarez no configurada")

    _key = _key.strip()
    _base = (_base or "https://emuwarez.com").rstrip("/")

    # Validate URL shape before hitting network
    if not _base.startswith(("http://", "https://")):
        return _fail("emuwarez", "invalid_url", f"URL de eMuwarez inválida: {_base}")

    url = f"{_base}/api/torrents/filter?api_token={urllib.parse.quote(_key)}&perPage=1"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "emuwarez-uploadrr/3"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return _ok("emuwarez", details={"base_url": _base, "http_status": resp.status})
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return _fail("emuwarez", "invalid_key", "API key de eMuwarez inválida o no autorizada")
        return _fail("emuwarez", "connection_error", f"Error HTTP {exc.code} al conectar con eMuwarez")
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower() or isinstance(exc.reason, socket.timeout):
            return _fail("emuwarez", "timeout", "Timeout al conectar con eMuwarez")
        return _fail("emuwarez", "connection_error", f"No se pudo conectar con eMuwarez ({_base}): {reason}")
    except Exception as exc:
        return _fail("emuwarez", "unexpected_error", f"Error inesperado: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Radarr / Sonarr
# ---------------------------------------------------------------------------

_VALID_ARR_KINDS = frozenset({"radarr", "sonarr"})


def test_arr_connection(
    *,
    kind: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    instance_id: Optional[int] = None,
    conn=None,
) -> dict:
    """Probe Radarr or Sonarr using GET /api/v3/system/status (read-only).

    Accepts either:
      - instance_id + conn  → look up saved instance
      - kind + base_url + api_key  → test without saving
    """
    from ..integrations.arr_base import (
        ArrAuthError, ArrConnectionError, ArrClientError,
        arr_request, join_api_path,
    )

    # Resolve from saved instance
    if instance_id is not None:
        if conn is None:
            return _fail("arr", "unexpected_error", "Se requiere conexión a BD para probar instancia guardada")
        row = conn.execute(
            "SELECT type, url, api_key FROM instances WHERE id = ? AND enabled = 1", (instance_id,)
        ).fetchone()
        if not row:
            return _fail("arr", "not_configured", f"Instancia {instance_id} no encontrada o deshabilitada")
        kind = row["type"]
        base_url = row["url"]
        api_key = row["api_key"]

    if not kind or kind not in _VALID_ARR_KINDS:
        return _fail("arr", "invalid_kind", f"Tipo de instancia inválido: '{kind}'. Debe ser 'radarr' o 'sonarr'")

    if not base_url or not base_url.strip():
        return _fail(kind, "not_configured", "URL de la instancia no configurada")

    if not api_key or not api_key.strip():
        return _fail(kind, "not_configured", "API key de la instancia no configurada")

    base_url = base_url.strip()
    api_key = api_key.strip()

    if not base_url.startswith(("http://", "https://")):
        base_url = "http://" + base_url

    try:
        url = join_api_path(base_url, "system/status")
        data: Any = arr_request("GET", url, api_key)
        version = data.get("version") if isinstance(data, dict) else None
        return _ok(kind, details={"version": version, "instance_id": instance_id})
    except ArrAuthError:
        return _fail(kind, "invalid_key", f"API key de {kind.capitalize()} inválida o permisos insuficientes")
    except ArrConnectionError as exc:
        reason = str(exc)
        if "timeout" in reason.lower() or "timed out" in reason.lower():
            return _fail(kind, "timeout", f"Timeout al conectar con {kind.capitalize()}")
        return _fail(kind, "connection_error", f"No se pudo conectar con {kind.capitalize()}: {reason}")
    except ArrClientError as exc:
        return _fail(kind, "connection_error", str(exc))
    except Exception as exc:
        return _fail(kind, "unexpected_error", f"Error inesperado: {type(exc).__name__}")
