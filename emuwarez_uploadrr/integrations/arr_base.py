"""Base helpers and error hierarchy for Radarr/Sonarr (*Arr) API clients.

Error hierarchy:
    ArrClientError          base class for all *arr client errors
    ├── ArrConnectionError  network/timeout — server unreachable
    ├── ArrAuthError        HTTP 401/403 — wrong API key
    └── ArrApiError         HTTP 4xx/5xx with body — server error

The existing ``IntegrationError`` from ``integrations.base`` remains in use
by the CLI layer; new web-layer code should raise ``ArrClientError`` subclasses.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from .base import IntegrationError

_DEFAULT_TIMEOUT = 15


class ArrClientError(IntegrationError):
    """Base for all *arr client errors. Also IS-A IntegrationError for CLI compat."""


class ArrConnectionError(ArrClientError):
    """Network error — server unreachable or timed out."""


class ArrAuthError(ArrClientError):
    """Authentication error — wrong or missing API key (HTTP 401/403)."""


class ArrApiError(ArrClientError):
    """API-level error — unexpected HTTP status with body."""

    def __init__(self, message: str, status_code: int = 0, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ArrClientError("URL vacía")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def join_api_path(base_url: str, path: str, params: Optional[dict[str, Any]] = None) -> str:
    url = normalize_base_url(base_url) + "/api/v3/" + path.lstrip("/")
    if params:
        encoded = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if encoded:
            url += "?" + encoded
    return url


def arr_request(
    method: str,
    url: str,
    api_key: str,
    *,
    data: Any = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Any:
    """Low-level HTTP request that raises ``ArrClientError`` subclasses."""
    body: bytes | None = None
    headers = {
        "Accept": "application/json",
        "X-Api-Key": api_key,
        "User-Agent": "emuwarez-uploadrr/3",
    }
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise ArrAuthError(
                f"Autenticación fallida en {url} (HTTP {exc.code}). Comprueba la API key."
            ) from exc
        raise ArrApiError(
            f"HTTP {exc.code} desde {url}: {raw[:300]}",
            status_code=exc.code,
            body=raw,
        ) from exc
    except urllib.error.URLError as exc:
        raise ArrConnectionError(
            f"No se pudo conectar con {url}: {exc.reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ArrApiError(f"Respuesta no-JSON desde {url}") from exc
    except TimeoutError as exc:
        raise ArrConnectionError(f"Timeout conectando con {url}") from exc


def registros_de(data: Any, que: str) -> list[dict]:
    """Los registros de una página de cola o historial (`{"records": [...]}`, o una lista a secas). Cualquier otra
    cosa lanza: devolver [] haría pasar un fallo por «no hay nada»."""
    if isinstance(data, dict):
        data = data.get("records")
    if not isinstance(data, list):
        raise ArrApiError(f"{que} no ha devuelto una lista de registros")
    return data


_TAMANO_PAGINA = 500
_MAX_PAGINAS = 100


def todas_las_paginas(pedir: Callable[[int, int], Any], que: str) -> list[dict]:
    """Todos los registros de la cola, página a página hasta `totalRecords`. Una cola cortada se leería como que lo
    que no está ya no se descarga; si no llega entera, lanza."""
    registros: list[dict] = []
    total = 0
    for pagina in range(1, _MAX_PAGINAS + 1):
        data = pedir(pagina, _TAMANO_PAGINA)
        registros += registros_de(data, que)
        total = data.get("totalRecords") if isinstance(data, dict) else None
        if not isinstance(total, int) or len(registros) >= total:
            return registros
        if not data["records"]:
            break
    raise ArrApiError(f"{que} ha devuelto {len(registros)} de {total} registros")


def safe_api_key(api_key: str) -> str:
    """Return a masked API key — never log the full key."""
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "…" + api_key[-4:]


__all__ = [
    "ArrClientError", "ArrConnectionError", "ArrAuthError", "ArrApiError",
    "normalize_base_url", "join_api_path", "arr_request", "safe_api_key", "registros_de", "todas_las_paginas",
]
