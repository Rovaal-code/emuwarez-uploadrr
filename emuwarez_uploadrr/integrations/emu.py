"""eMuwarez API connector.

eMuwarez runs on the UNIT3D platform (https://emu-warez.com).
UNIT3D API authentication uses ?api_token=<key> as a query parameter.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable

from .base import IntegrationError, build_url, request_json
from ..constants import EMU_BASE_URL, EMU_TEST_URL
from ..models import RequestItem


# ---------------------------------------------------------------------------
# UNIT3D-pattern functions (primary, api_token query param)
# ---------------------------------------------------------------------------

def emu_test_connection(api_key: str, base_url: str | None = None) -> dict[str, Any]:
    """Test connectivity to eMuwarez using UNIT3D ?api_token= auth."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, "/api/torrents/filter", {"api_token": api_key, "perPage": "1"})
    return request_json("GET", url)


def emu_get_requests(
    api_key: str,
    base_url: str | None = None,
    page: int = 1,
    per_page: int = 100,
) -> dict[str, Any]:
    """Fetch paginated EMU request list (bounties / want list) via UNIT3D API.

    Returns the full response dict — caller checks data[], meta.last_page, etc.
    """
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(
        base,
        "/api/requests",
        {"api_token": api_key, "page": str(page), "perPage": str(per_page)},
    )
    return request_json("GET", url)


def emu_get_request_detail(
    api_key: str,
    request_id: int,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Fetch detail for a single EMU request by ID."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, f"/api/requests/{request_id}", {"api_token": api_key})
    return request_json("GET", url)


def emu_search_existing(
    api_key: str,
    query: str | None = None,
    base_url: str | None = None,
    tmdb_id: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Search for existing torrents on eMuwarez's real catalog (/api/torrents/filter).

    Mirrors the dupe-check Uploadrr-EMU itself performs before uploading
    (Uploadrr/src/trackers/UNIT3D.py::search_existing): when `tmdb_id` is
    given it is the authoritative filter (same param name, `tmdbId`, that
    the real UNIT3D tracker API expects). `query` (free-text `name`) is kept
    as a fallback for callers that don't have a tmdb_id yet — title-only
    search is inherently fuzzier and matches Uploadrr-EMU's own behavior
    only when it lacks a tmdb_id either.
    """
    base = (base_url or EMU_BASE_URL).rstrip("/")
    params: dict[str, str] = {"api_token": api_key, "perPage": "25"}
    if tmdb_id:
        params["tmdbId"] = str(tmdb_id)
    if query:
        params["name"] = query
    if category:
        params["categories[]"] = category
    url = build_url(base, "/api/torrents/filter", params)
    return request_json("GET", url)


def emu_fetch_all_pages(api_key: str, base_url: str | None = None) -> list[dict[str, Any]]:
    """Fetch all pages from the EMU requests endpoint and return flat list of raw items."""
    all_items: list[dict[str, Any]] = []
    page = 1
    while True:
        data = emu_get_requests(api_key, base_url=base_url, page=page, per_page=100)
        if isinstance(data, list):
            all_items.extend(data)
            break
        if not isinstance(data, dict):
            break
        page_items = data.get("data", [])
        if not isinstance(page_items, list) or not page_items:
            break
        all_items.extend(page_items)
        meta = data.get("meta", {})
        current_page = int(meta.get("current_page", page))
        last_page = int(meta.get("last_page", 1))
        if current_page >= last_page:
            break
        page += 1
    return all_items


# eMuwarez rate-limits the API to 30 requests/minute (x-ratelimit-limit: 30)
# and caps perPage at 100 server-side, so a full ~11k-torrent catalog is ~112
# sequential requests. We deliberately pace to ~10/min (one every 6s) to stay
# well under the limit and never trip a 429.
EMU_MIN_REQUEST_INTERVAL = 6.0  # seconds between torrent-catalog requests


def emu_fetch_all_torrents(
    api_key: str,
    base_url: str | None = None,
    per_page: int = 100,
    max_pages: int = 500,
    progress=None,
    stop_after_id: int | None = None,
    min_interval: float = EMU_MIN_REQUEST_INTERVAL,
) -> list[dict[str, Any]]:
    """Fetch eMuwarez torrents (paginated /api/torrents/filter), newest first.
    Returns the flat list of raw torrent objects ({type, id, attributes}).

    Incremental: when `stop_after_id` is given, the walk stops as soon as a
    torrent already known (id <= stop_after_id) is reached — so only the
    newly-uploaded torrents come back, instead of re-downloading the whole
    catalog. The catalog's default order is created_at desc, so ids decrease as
    we page and the first known id means everything after it is known too.

    Requests are paced to `min_interval` seconds apart (rate limit).

    `progress(page, total_pages, items_so_far, total_items)` is called after each
    page (total_pages/total_items from the API `meta`, or None if absent)."""
    import time
    base = (base_url or EMU_BASE_URL).rstrip("/")
    all_items: list[dict[str, Any]] = []
    total_pages: int | None = None
    total_items: int | None = None
    page = 1
    reached_known = False
    while page <= max_pages and not reached_known:
        if page > 1:
            time.sleep(min_interval)  # rate limit (~10/min, well under 30/min)
        url = build_url(base, "/api/torrents/filter", {"api_token": api_key, "perPage": str(per_page), "page": str(page)})
        data = request_json("GET", url)
        items = data.get("data") if isinstance(data, dict) else None
        meta = data.get("meta") if isinstance(data, dict) else None
        if isinstance(meta, dict):
            total_pages = meta.get("last_page") or total_pages
            total_items = meta.get("total") or total_items
        if not isinstance(items, list) or not items:
            break
        if stop_after_id is not None:
            for t in items:
                try:
                    tid = int(t.get("id") or 0)
                except (TypeError, ValueError):
                    tid = 0
                if tid <= stop_after_id:
                    reached_known = True
                    break
                all_items.append(t)
        else:
            all_items.extend(items)
        if progress:
            try:
                progress(page, total_pages, len(all_items), total_items)
            except Exception:  # noqa: BLE001 — progress is best-effort
                pass
        if len(items) < per_page:
            break
        page += 1
    return all_items


# ---------------------------------------------------------------------------
# Legacy Bearer-header functions (kept for backward compatibility)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

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


def _flatten_unit3d(raw: dict[str, Any]) -> dict[str, Any]:
    """If raw has nested UNIT3D 'attributes', merge them into a flat dict."""
    if "attributes" not in raw:
        return raw
    flat = dict(raw)
    attrs = raw["attributes"]
    if isinstance(attrs, dict):
        flat.update(attrs)
    links = raw.get("links", {})
    if isinstance(links, dict) and "self" in links and not flat.get("url"):
        flat["url"] = links["self"]
    return flat


def normalize_request(raw: dict[str, Any]) -> RequestItem:
    flat = _flatten_unit3d(raw)
    emu_id = str(
        _first(flat, "id", "request_id", "requestId", "uuid")
        or _first(flat, "url", "link")
        or hash(json.dumps(raw, sort_keys=True))
    )
    title = str(_first(flat, "name", "title", "movie_title", "series_title") or "Sin título")
    tmdb_id = _extract_id(_first(flat, "tmdb_id", "tmdbId", "tmdb", "tmdb_url", "tmdbUrl", "tmdb"))
    imdb_id = _extract_imdb(_first(flat, "imdb_id", "imdbId", "imdb", "imdb_url", "imdbUrl", "imdb"))
    tvdb_id = _extract_id(_first(flat, "tvdb_id", "tvdbId", "tvdb"))
    mal_id = _extract_id(_first(flat, "mal_id", "malId", "mal"))
    points = _first(flat, "points", "bonus", "bounty", "reward")
    comments = _first(flat, "comments", "comment_count", "commentsCount")
    url = _first(flat, "url", "link", "request_url") or (
        f"{EMU_BASE_URL}/requests/{emu_id}" if emu_id.isdigit() else None
    )
    # anon=true means author should stay hidden
    anon = flat.get("anon", True)
    author = _first(flat, "user", "username", "author") if not anon else None
    return RequestItem(
        id=None,
        emu_id=emu_id,
        title=title,
        category=_first(flat, "category", "category_name", "cat"),
        requested_source=_first(flat, "type", "source", "requested_source", "quality_type"),
        requested_resolution=_first(flat, "resolution", "requested_resolution"),
        emu_status=_first(flat, "status", "request_status", "filled", "filled_status"),
        points=int(points) if str(points).isdigit() else None,
        comments=int(comments) if str(comments).isdigit() else None,
        created_at=_first(flat, "created_at", "createdAt", "date", "created"),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        tvdb_id=tvdb_id,
        mal_id=mal_id,
        url=url,
        author=author,
        author_visible=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
    )


def normalize_requests(raw_items: Iterable[dict[str, Any]]) -> list[RequestItem]:
    return [normalize_request(item) for item in raw_items if isinstance(item, dict)]
