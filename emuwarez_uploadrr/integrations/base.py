"""Small urllib based HTTP helpers to avoid new dependencies."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class IntegrationError(RuntimeError):
    pass


def normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise IntegrationError("URL vacía")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def request_json(
    method: str,
    url: str,
    *,
    api_key: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
    data: Any = None,
    timeout: int = 20,
    verify_ssl: bool = True,
) -> Any:
    body: bytes | None = None
    req_headers = {"Accept": "application/json", "User-Agent": "emuwarez-uploadrr-cli/2"}
    if headers:
        req_headers.update(headers)
    if api_key:
        req_headers["X-Api-Key"] = api_key
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method.upper())
    context = None if verify_ssl else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise IntegrationError(f"HTTP {exc.code} en {url}: {raw[:500]}") from exc
    except urllib.error.URLError as exc:
        raise IntegrationError(f"No se pudo conectar con {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"Respuesta no JSON desde {url}") from exc


def build_url(base_url: str, path: str, params: Optional[dict[str, Any]] = None) -> str:
    url = normalize_base_url(base_url) + "/" + path.lstrip("/")
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return url
