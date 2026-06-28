"""eMuwarez API connector.

Only the validated API test endpoint is known for now.  Request listing and
request creation are deliberately configurable/stubbed because the real HTTP
request must be captured from eMuwarez before enabling it safely.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

from .base import IntegrationError, request_json
from ..legacy import EMU_TEST_URL
from ..models import RequestItem


def test_connection(api_key: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    return request_json("GET", EMU_TEST_URL, headers=headers)


def get_requests(api_key: str, endpoint_url: str | None = None) -> list[dict[str, Any]]:
    endpoint_url = endpoint_url or os.environ.get("EMUWAREZ_REQUESTS_URL")
    if not endpoint_url:
        raise IntegrationError(
            "Endpoint de peticiones EMU no configurado. "
            "Cuando capturemos la request real de eMuwarez, se configurará aquí."
        )
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    data = request_json("GET", endpoint_url, headers=headers)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "requests", "results", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise IntegrationError("La respuesta de peticiones EMU no tiene formato de lista reconocido")


def create_request(*_: Any, **__: Any) -> None:
    raise IntegrationError(
        "Crear peticiones en EMU está preparado en el contrato, pero no activo. "
        "Primero hay que capturar el POST real desde DevTools > Network."
    )


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _extract_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"(\d+)", text)
    return match.group(1) if match else None


def _extract_imdb(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"tt\d+", text)
    return match.group(0) if match else None


def normalize_request(raw: dict[str, Any]) -> RequestItem:
    emu_id = str(_first(raw, "id", "request_id", "requestId", "uuid") or _first(raw, "url", "link") or hash(json.dumps(raw, sort_keys=True)))
    title = str(_first(raw, "name", "title", "movie_title", "series_title") or "Sin título")
    tmdb_id = _extract_id(_first(raw, "tmdb_id", "tmdbId", "tmdb", "tmdb_url", "tmdbUrl"))
    imdb_id = _extract_imdb(_first(raw, "imdb_id", "imdbId", "imdb", "imdb_url", "imdbUrl"))
    points = _first(raw, "points", "bonus", "bounty", "reward")
    comments = _first(raw, "comments", "comment_count", "commentsCount")
    return RequestItem(
        id=None,
        emu_id=emu_id,
        title=title,
        category=_first(raw, "category", "category_name", "cat"),
        requested_source=_first(raw, "type", "source", "requested_source", "quality_type"),
        requested_resolution=_first(raw, "resolution", "requested_resolution"),
        emu_status=_first(raw, "status", "request_status", "filled", "filled_status"),
        points=int(points) if str(points).isdigit() else None,
        comments=int(comments) if str(comments).isdigit() else None,
        created_at=_first(raw, "created_at", "createdAt", "date", "created"),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        url=_first(raw, "url", "link", "request_url"),
        author=_first(raw, "author", "user", "username"),
        author_visible=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
    )


def normalize_requests(raw_items: Iterable[dict[str, Any]]) -> list[RequestItem]:
    return [normalize_request(item) for item in raw_items if isinstance(item, dict)]
