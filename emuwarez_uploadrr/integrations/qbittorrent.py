"""qBittorrent WebUI connector — connection test and read-only torrent listing.

Uses the WebUI API v2 login endpoint to validate host + credentials. qBittorrent
requires a Referer header matching the host (CSRF protection). The success reply
changed between major versions: 4.x answers 200 with the body "Ok." ("Fails." on
bad credentials), while 5.x answers 204 with an empty body and a 401 on bad
credentials. Both shapes are accepted below. We only probe connectivity/auth
here and list torrents — we never start/stop/recheck/delete anything.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from . import http_cliente

BAD_LOGIN_ERROR = (
    "Usuario o contraseña de qBittorrent incorrectos, o el puerto de la URL no "
    "coincide con el puerto en el que escucha su WebUI"
)


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


def split_base_url(url: str) -> tuple[str, str]:
    """Inverse of build_base_url: (host_url_without_port, port).

    Lives next to build_base_url on purpose. The app stores ONE URL with the
    port inside it, but Uploadrr-EMU's qBittorrent client wants host and port
    as two separate config keys, so the split has to happen somewhere — and
    the only sane somewhere is beside the function that joins them, or the two
    drift apart the day one of them learns about IPv6 or a trailing slash.

    A URL with no explicit port falls back to the scheme's default (443 for
    https, 80 otherwise), same as a browser would, rather than handing the
    client an empty port.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        return "", ""
    if "://" not in url:
        url = "http://" + url
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if ":" in host:                      # IPv6 literal, needs its brackets back
        host = f"[{host}]"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return f"{parsed.scheme}://{host}", str(port)


def _iniciar_sesion(base: str, sesion: Any, username: str, password: str, timeout: int) -> dict[str, Any]:
    """Inicia sesión en la WebUI con `sesion`, que se queda con la cookie. Devuelve {ok} o {ok: False, error}."""
    login_url = f"{base}/api/v2/auth/login"
    data = urllib.parse.urlencode({"username": username or "", "password": password or ""}).encode()
    cabeceras = {
        "Referer": base,  # required by qBittorrent's CSRF guard
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        resp = http_cliente.pedir("POST", login_url, cabeceras=cabeceras, contenido=data, timeout=timeout,
                                  en_sesion=sesion)
    except http_cliente.ErrorHTTP as exc:
        if exc.status == 401:
            # qBittorrent 5.x answers 401 both for wrong credentials and for a
            # rejected Host header (which happens when the port in the URL is
            # not the port the WebUI itself listens on, e.g. a Docker port map).
            return {"ok": False, "error": BAD_LOGIN_ERROR}
        if exc.status == 403:
            return {"ok": False, "error": "qBittorrent rechazó la petición (403). ¿WebUI/host bien?"}
        return {"ok": False, "error": f"HTTP {exc.status} desde qBittorrent"}
    except Exception as exc:  # noqa: BLE001 — timeouts, DNS, connection refused…
        return {"ok": False, "error": f"No se pudo conectar con qBittorrent: {exc}"}

    body = http_cliente.texto(resp.content).strip()
    cookie = resp.headers.get("Set-Cookie", "")
    # Success shape differs by version: 4.x replies 200 with the body "Ok." and a
    # "SID" cookie; 5.x replies 204 with an empty body and a port-scoped cookie
    # named "QBT_SID_<puerto>". Accept a session cookie under any of those names.
    if body == "Ok." or _has_session_cookie(cookie) or resp.status_code == 204:
        return {"ok": True}
    if body == "Fails.":
        return {"ok": False, "error": BAD_LOGIN_ERROR}
    return {"ok": False, "error": f"Respuesta inesperada de qBittorrent: {body[:60] or '(vacía)'}"}


def qbit_test_connection(url: str, port: str | int | None, username: str, password: str,
                         *, timeout: int = 10) -> dict[str, Any]:
    """Log into the qBittorrent WebUI to validate host + credentials.
    Returns {ok, version?, error?}. Never raises."""
    base = build_base_url(url, port)
    if not base:
        return {"ok": False, "error": "URL de qBittorrent vacía"}

    # Una sesión propia: la cookie del inicio de sesión viaja sola en la petición de la versión.
    with http_cliente.sesion() as sesion:
        login = _iniciar_sesion(base, sesion, username, password, timeout)
        if not login["ok"]:
            return login
        return {"ok": True, "version": _get_version(base, sesion, timeout=timeout)}


class ErrorQbit(Exception):
    """No se pudo leer de qBittorrent. El texto es fijo: nunca lleva la URL (la del proxy de qui lleva la clave)."""

    def __init__(self, texto: str, *, credenciales: bool = False):
        super().__init__(texto)
        self.credenciales = credenciales


# Un registro de torrents de miles de entradas cabe de sobra; más es un servidor que no es qBittorrent.
_MAX_BYTES_TORRENTS = 64 * 1024 * 1024


def qbit_listar_torrents(url: str, port: str | int | None, username: str, password: str,
                         *, timeout: int = 5) -> list[dict[str, Any]]:
    """Todos los torrents de qBittorrent (`GET /api/v2/torrents/info`), en una sola consulta. Solo lectura.

    Lanza `ErrorQbit` si no hay URL o no es válida, no se conecta, las credenciales fallan o la respuesta no es una lista."""
    try:
        base = build_base_url(url, port)
    except ValueError:  # un puerto que no es un número, como en «http://qbit:bad»
        raise ErrorQbit("La URL de qBittorrent no es válida") from None
    if not base:
        raise ErrorQbit("qBittorrent no está configurado")
    with http_cliente.sesion() as sesion:
        login = _iniciar_sesion(base, sesion, username, password, timeout)
        if not login["ok"]:
            raise ErrorQbit("Usuario o contraseña de qBittorrent incorrectos" if login["error"] == BAD_LOGIN_ERROR
                            else "No se pudo conectar con qBittorrent", credenciales=login["error"] == BAD_LOGIN_ERROR)
        try:
            resp = http_cliente.pedir("GET", f"{base}/api/v2/torrents/info", cabeceras={"Referer": base},
                                      timeout=timeout, en_sesion=sesion, limite=_MAX_BYTES_TORRENTS)
            datos = json.loads(http_cliente.texto(resp.content))
        except Exception:  # noqa: BLE001 — red, HTTP 4xx/5xx o un cuerpo que no es JSON
            raise ErrorQbit("qBittorrent no devolvió la lista de torrents") from None
    if not isinstance(datos, list):
        raise ErrorQbit("qBittorrent no devolvió la lista de torrents")
    return [t for t in datos if isinstance(t, dict)]


def _has_session_cookie(cookie: str) -> bool:
    """True if the Set-Cookie header carries a qBittorrent session id.
    Covers "SID=" (4.x) and "QBT_SID_<puerto>=" (5.x)."""
    return bool(re.search(r"(?:^|[\s;,])(?:QBT_)?SID(?:_\d+)?=", cookie))


def _get_version(base: str, sesion: Any, *, timeout: int) -> str | None:
    """La versión de la WebUI, con la cookie que dejó el inicio de sesión en `sesion`."""
    try:
        resp = http_cliente.pedir("GET", f"{base}/api/v2/app/version", cabeceras={"Referer": base},
                                  timeout=timeout, en_sesion=sesion)
        return http_cliente.texto(resp.content).strip() or None
    except Exception:  # noqa: BLE001
        return None
