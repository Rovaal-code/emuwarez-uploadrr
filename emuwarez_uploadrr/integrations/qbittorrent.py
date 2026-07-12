"""qBittorrent WebUI connector — connection test only.

Uses the WebUI API v2 login endpoint to validate host + credentials. qBittorrent
requires a Referer header matching the host (CSRF protection), and returns the
body "Ok." on a successful login or "Fails." on bad credentials. We only probe
connectivity/auth here — we never start/stop torrents.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def build_base_url(url: str, port: str | int | None) -> str:
    """Combine a host URL and port into a WebUI base like http://host:8080.
    Accepts a url that already includes a scheme and/or a port."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    # If the host part already has an explicit :port, keep it; else append.
    parsed = urllib.parse.urlparse(url)
    if parsed.port is None and port:
        url = f"{url}:{str(port).strip()}"
    return url


def qbit_test_connection(url: str, port: str | int | None, username: str, password: str,
                         *, timeout: int = 10) -> dict[str, Any]:
    """Log into the qBittorrent WebUI to validate host + credentials.
    Returns {ok, version?, error?}. Never raises."""
    base = build_base_url(url, port)
    if not base:
        return {"ok": False, "error": "URL de qBittorrent vacía"}

    login_url = f"{base}/api/v2/auth/login"
    data = urllib.parse.urlencode({"username": username or "", "password": password or ""}).encode()
    req = urllib.request.Request(login_url, data=data, method="POST")
    req.add_header("Referer", base)  # required by qBittorrent's CSRF guard
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
            cookie = resp.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return {"ok": False, "error": "qBittorrent rechazó la petición (403). ¿WebUI/host bien?"}
        return {"ok": False, "error": f"HTTP {exc.code} desde qBittorrent"}
    except Exception as exc:  # noqa: BLE001 — timeouts, DNS, connection refused…
        return {"ok": False, "error": f"No se pudo conectar con qBittorrent: {exc}"}

    if body == "Ok." or "SID=" in cookie:
        version = _get_version(base, cookie, timeout=timeout)
        return {"ok": True, "version": version}
    if body == "Fails.":
        return {"ok": False, "error": "Usuario o contraseña de qBittorrent incorrectos"}
    return {"ok": False, "error": f"Respuesta inesperada de qBittorrent: {body[:60] or '(vacía)'}"}


def _get_version(base: str, cookie: str, *, timeout: int) -> str | None:
    try:
        req = urllib.request.Request(f"{base}/api/v2/app/version")
        req.add_header("Referer", base)
        if cookie:
            req.add_header("Cookie", cookie.split(";", 1)[0])
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace").strip() or None
    except Exception:  # noqa: BLE001
        return None
