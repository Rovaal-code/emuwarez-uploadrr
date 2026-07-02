"""Overseerr/Jellyseerr-compatible ("Seerr") API client — Phase 11B.

Overseerr and Jellyseerr (a compatible fork) expose the same REST API under
/api/v1/, authenticated via the X-Api-Key header — same convention already
used for Radarr/Sonarr, so this reuses integrations.arr_base.arr_request.

This module is read-only: it only probes connectivity/identity endpoints.
It does not implement request sync/creation (out of scope for Phase 11B —
the instance data model and test-connection are prepared, sync is a
separate future phase).
"""
from __future__ import annotations

from typing import Any, Optional

from .arr_base import ArrAuthError, ArrClientError, ArrConnectionError, arr_request, normalize_base_url


def _join(base_url: str, path: str) -> str:
    return normalize_base_url(base_url) + "/api/v1/" + path.lstrip("/")


def seerr_test_connection(instance: dict) -> dict:
    """Read-only connection test against a Seerr (Overseerr/Jellyseerr) instance.

    Returns {"ok": True, "version"?, "username"?} or {"ok": False, "error"}.
    `username` comes from /api/v1/auth/me (displayName/username/email,
    whichever is present) — this is the "detected account" the UI shows,
    the Seerr equivalent of what isn't available for eMuwarez.
    """
    url = instance.get("url") or ""
    api_key = instance.get("api_key") or ""
    try:
        me: Any = arr_request("GET", _join(url, "auth/me"), api_key)
        username: Optional[str] = None
        if isinstance(me, dict):
            username = me.get("displayName") or me.get("username") or me.get("email")

        version: Optional[str] = None
        try:
            status_data = arr_request("GET", _join(url, "status"), api_key)
            if isinstance(status_data, dict):
                version = status_data.get("version")
        except ArrClientError:
            pass  # version is best-effort — auth/me already confirmed the key works

        return {"ok": True, "version": version, "username": username}
    except ArrAuthError:
        return {"ok": False, "error": "API key incorrecta o permisos insuficientes"}
    except ArrConnectionError as exc:
        return {"ok": False, "error": f"No se pudo conectar: {exc}"}
    except ArrClientError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Error inesperado: {type(exc).__name__}"}


__all__ = ["seerr_test_connection"]
