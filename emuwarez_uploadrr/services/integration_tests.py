"""Connection test helpers for external integrations (Phase 10C).

Safety rules:
- Read-only operations only.
- API keys are never returned or logged in full.
- No writes to TMDb, eMuwarez, Radarr or Sonarr.
- No eMuwarez request creation.
- No torrent uploads.
- test_uploadrr_connection() (Phase 10F) only checks filesystem paths — it
  never executes Uploadrr-EMU, never reads config.yaml secrets, and never
  spawns a subprocess.
"""
from __future__ import annotations

import datetime as dt
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from ..constants import EMU_BASE_URL

_TIMEOUT = 10  # seconds — short timeout for connection probes

# Rate-limit the live eMuwarez connection probe so the "Probar conexión" button
# cannot hammer the real server. Mirrors the sync throttle pattern in
# services/requests.py (state timestamp in app_state + wait_seconds), but at a
# much finer 1/minute granularity since a connectivity check is cheap and a
# user may legitimately re-test after fixing a key.
EMU_TEST_STATE_KEY = "last_emu_test_utc"
MIN_EMU_TEST_SECONDS = 60


def _emu_test_wait_seconds(conn) -> int:
    """Seconds remaining before another live eMuwarez probe is allowed (0 = now)."""
    from emuwarez_uploadrr.database import get_state
    last_str = get_state(conn, EMU_TEST_STATE_KEY)
    if not last_str:
        return 0
    try:
        last = dt.datetime.fromisoformat(last_str)
    except ValueError:
        return 0
    elapsed = (dt.datetime.now(dt.timezone.utc) - last).total_seconds()
    return max(0, int(MIN_EMU_TEST_SECONDS - elapsed))


def _ok(service: str, status: str = "connected", message: str = "Conexión correcta", details: Optional[dict] = None) -> dict:
    return {"ok": True, "service": service, "status": status, "message": message, "details": details or {}}


def _fail(service: str, status: str, message: str, details: Optional[dict] = None) -> dict:
    return {"ok": False, "service": service, "status": status, "message": message, "details": details or {}}


# ---------------------------------------------------------------------------
# qBittorrent
# ---------------------------------------------------------------------------

def _setting(conn, key: str) -> Optional[str]:
    if conn is None:
        return None
    from .settings import get_setting_canonical
    return get_setting_canonical(conn, key)


def test_qbit_connection(
    url: Optional[str] = None,
    port: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    *,
    conn=None,
) -> dict:
    """Validate host + login against the qBittorrent WebUI. Falls back to the
    stored config (settings.qbit.*) for any field left None. Read-only."""
    from ..integrations.qbittorrent import qbit_test_connection

    _url = url if url is not None else _setting(conn, "qbit.url")
    # El puerto ya no es un ajuste propio: va dentro de qbit.url, y
    # qbit_test_connection acepta una url que ya lo trae. El parámetro sigue
    # existiendo para quien quiera probar una combinación suelta sin guardarla.
    _port = port
    _user = username if username is not None else _setting(conn, "qbit.username")
    _pass = password if password is not None else _setting(conn, "qbit.password")

    if not _url or not str(_url).strip():
        return _fail("qbittorrent", "not_configured", "qBittorrent no configurado")

    result = qbit_test_connection(_url, _port, _user or "", _pass or "")
    if result.get("ok"):
        ver = (result.get("version") or "").strip()
        # qBittorrent already reports its version with a leading "v" ("v5.2.3"),
        # so only add one when it is missing (never render "vv5.2.3").
        label = ver if ver.lower().startswith("v") else f"v{ver}"
        return _ok("qbittorrent", message=f"Conexión correcta ({label})" if ver else "Conexión correcta",
                   details={"version": ver} if ver else None)
    return _fail("qbittorrent", "connection_error", result.get("error") or "No se pudo conectar")


# ---------------------------------------------------------------------------
# Image hosts
# ---------------------------------------------------------------------------

def test_imghost_connection(host_id: str, api_key: Optional[str] = None, *, conn=None) -> dict:
    """Reachability test for an image host. Falls back to the stored key."""
    from .image_hosts import test_image_host, get_host_key, host_meta

    meta = host_meta(host_id)
    label = meta["label"] if meta else host_id
    key = api_key if api_key is not None else (get_host_key(conn, host_id) if conn is not None else None)
    result = test_image_host(host_id, key)
    if result.get("ok"):
        return _ok("imghost", message=f"{label} responde", details={"host": host_id})
    return _fail("imghost", "connection_error", result.get("error") or f"{label} no responde",
                 details={"host": host_id})


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
        from .settings import get_setting_canonical
        _key = get_setting_canonical(conn, "tmdb.api_key")

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
    enforce_rate_limit: bool = True,
) -> dict:
    """Probe eMuwarez using GET /api/torrents/filter?perPage=1 (read-only).

    If api_key/base_url are None, reads stored values from DB.
    Never creates requests. Never uploads torrents.

    enforce_rate_limit=False skips the 1/minute throttle below — used when
    this is called as an internal precondition (e.g. validating a key before
    saving it in Settings) rather than from the user-facing "Probar conexión"
    button, which is what the throttle is meant to protect against.
    """
    _key = api_key
    _base = base_url

    if conn is not None:
        if not _key:
            from .settings import get_setting_canonical
            _key = get_setting_canonical(conn, "emu.api_key")
        if not _base:
            _base = get_setting_canonical(conn, "emu.endpoint_url")

    if not _key or not _key.strip():
        return _fail("emuwarez", "not_configured", "API key de eMuwarez no configurada")

    _key = _key.strip()
    _base = (_base or EMU_BASE_URL).rstrip("/")

    # Validate URL shape before hitting network
    if not _base.startswith(("http://", "https://")):
        return _fail("emuwarez", "invalid_url", f"URL de eMuwarez inválida: {_base}")

    # Rate-limit: at most one live probe per minute, to avoid saturating the
    # real eMuwarez server from the "Probar conexión" button. Only enforced
    # when we have a DB connection to persist the timestamp; the early
    # not_configured/invalid_url returns above never reach the network and are
    # deliberately not throttled.
    if conn is not None and enforce_rate_limit:
        wait = _emu_test_wait_seconds(conn)
        if wait > 0:
            return _fail(
                "emuwarez",
                "rate_limited",
                f"Espera {wait}s antes de volver a probar la conexión con eMuwarez.",
                details={"wait_seconds": wait, "min_interval_seconds": MIN_EMU_TEST_SECONDS},
            )
        from emuwarez_uploadrr.database import set_state
        set_state(conn, EMU_TEST_STATE_KEY, dt.datetime.now(dt.timezone.utc).isoformat())

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


def _arr_content_visibility(kind: str, base_url: str, api_key: str) -> dict:
    """Check whether the ARR's root folders are visible on THIS app's filesystem
    (i.e. the media volume is mounted into the container the same way). Returns
    {visible: bool|None, roots: [{path, exists}]}. visible=None means it
    couldn't be determined (root folders unreadable)."""
    try:
        if kind == "radarr":
            from ..integrations.radarr import get_root_folders
        else:
            from ..integrations.sonarr import get_root_folders
        folders = get_root_folders(base_url, api_key)
    except Exception:
        return {"visible": None, "roots": []}
    roots = []
    for f in folders or []:
        p = f.get("path") if isinstance(f, dict) else None
        if p:
            roots.append({"path": p, "exists": os.path.isdir(p)})
    visible = any(r["exists"] for r in roots) if roots else None
    return {"visible": visible, "roots": roots}


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
        vis = _arr_content_visibility(kind, base_url, api_key)
        return _ok(kind, details={
            "version": version,
            "instance_id": instance_id,
            "content_visible": vis["visible"],
            "root_folders": vis["roots"],
        })
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


# ---------------------------------------------------------------------------
# Uploadrr runtime (Phase 10F)
# ---------------------------------------------------------------------------

def test_uploadrr_connection(
    *,
    path: Optional[str] = None,
    python_path: Optional[str] = None,
    conn=None,
) -> dict:
    """Check that the configured Uploadrr runtime paths look usable.

    Read-only filesystem checks only: never executes upload.py, never
    reads Uploadrr's own config.yaml or its secrets, never spawns a
    subprocess. If path/python_path are None, reads the stored settings
    (uploadrr.path / uploadrr.python_path) from conn.
    """
    from .uploadrr_config_staging import default_uploadrr_config_path

    _path = path
    _python = python_path

    if conn is not None:
        from ..database import get_setting_canonical
        if not _path:
            _path = get_setting_canonical(conn, "uploadrr.path")
        if not _python:
            _python = get_setting_canonical(conn, "uploadrr.python_path")

    if not _path or not _path.strip():
        return _fail("uploadrr", "not_configured", "Ruta de Uploadrr (uploadrr.path) no configurada")

    uploadrr_dir = Path(_path.strip())
    if not uploadrr_dir.exists() or not uploadrr_dir.is_dir():
        return _fail("uploadrr", "not_found", f"Ruta de Uploadrr no existe o no es un directorio: {uploadrr_dir}")

    script = uploadrr_dir / "upload.py"
    if not script.exists():
        return _fail("uploadrr", "script_missing", f"Script upload.py no encontrado en {uploadrr_dir}")

    details: dict[str, Any] = {"uploadrr_path": str(uploadrr_dir), "script_found": True}

    config_path = default_uploadrr_config_path(str(uploadrr_dir))
    details["config_yaml_found"] = config_path.exists()

    if _python and _python.strip():
        python_ok = Path(_python.strip()).exists()
        details["python_path"] = _python.strip()
        details["python_path_found"] = python_ok
        if not python_ok:
            return _fail(
                "uploadrr", "python_missing",
                f"uploadrr.python_path no existe: {_python.strip()}",
                details=details,
            )
    else:
        details["python_path_found"] = None

    if not details["config_yaml_found"]:
        return _ok(
            "uploadrr", status="connected_no_config",
            message="Ruta y script de Uploadrr-EMU encontrados, pero config.yaml no existe todavía",
            details=details,
        )

    return _ok("uploadrr", message="Ruta, script y config.yaml de Uploadrr-EMU encontrados", details=details)
