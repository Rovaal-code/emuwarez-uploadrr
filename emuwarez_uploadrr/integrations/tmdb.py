"""TMDb integration — watch providers and metadata helpers (Phase 10A).

Uses the urllib-based HTTP helper from base.py to avoid new dependencies.
"""
from __future__ import annotations

from .base import request_json, IntegrationError

_TMDB_BASE = "https://api.themoviedb.org/3"


def _get_tmdb_api_key(conn=None) -> str | None:
    _conn = None
    try:
        from ..database import connect, get_setting_canonical
        _conn = conn or connect()
        # Settings are written under the canonical dotted key (tmdb.api_key);
        # resolve both that and the legacy underscore alias (tmdb_api_key).
        return get_setting_canonical(_conn, "tmdb.api_key")
    except Exception:
        return None
    finally:
        if _conn is not None and conn is None:
            _conn.close()


def get_movie_watch_providers(tmdb_id: int, *, region: str = "ES", api_key: str | None = None, conn=None) -> dict:
    """Fetch /movie/{id}/watch/providers from TMDb. Returns full response dict."""
    _key = api_key or _get_tmdb_api_key(conn)
    if not _key:
        raise IntegrationError("TMDb API key no configurada")
    url = f"{_TMDB_BASE}/movie/{tmdb_id}/watch/providers?api_key={_key}"
    return request_json("GET", url)


def get_tv_watch_providers(tmdb_id: int, *, region: str = "ES", api_key: str | None = None, conn=None) -> dict:
    """Fetch /tv/{id}/watch/providers from TMDb."""
    _key = api_key or _get_tmdb_api_key(conn)
    if not _key:
        raise IntegrationError("TMDb API key no configurada")
    url = f"{_TMDB_BASE}/tv/{tmdb_id}/watch/providers?api_key={_key}"
    return request_json("GET", url)


def get_tv_title(tmdb_id: int, *, language: str = "es-ES", api_key: str | None = None, conn=None) -> str | None:
    """Localized TV series title from TMDb (/tv/{id}?language=xx). Returns the
    localized `name`, falling back to `original_name`; None if unavailable."""
    _key = api_key or _get_tmdb_api_key(conn)
    if not _key:
        raise IntegrationError("TMDb API key no configurada")
    url = f"{_TMDB_BASE}/tv/{tmdb_id}?api_key={_key}&language={language}"
    data = request_json("GET", url)
    if not isinstance(data, dict):
        return None
    name = (data.get("name") or "").strip()
    return name or (data.get("original_name") or "").strip() or None


def get_tv_original_name(tmdb_id: int, *, api_key: str | None = None, conn=None) -> str | None:
    """A series' ORIGINAL name from TMDb (/tv/{id} `original_name`), for the
    Título dropdown's second option. Needed because Sonarr's series payload has
    no originalTitle field at all (unlike Radarr's movie one), so
    library_items.original_title is always empty for a series."""
    _key = api_key or _get_tmdb_api_key(conn)
    if not _key:
        raise IntegrationError("TMDb API key no configurada")
    url = f"{_TMDB_BASE}/tv/{tmdb_id}?api_key={_key}"
    data = request_json("GET", url)
    if not isinstance(data, dict):
        return None
    return (data.get("original_name") or "").strip() or None


def get_movie_original_title(tmdb_id: int, *, api_key: str | None = None, conn=None) -> str | None:
    """A movie's ORIGINAL title from TMDb (/movie/{id} `original_title`)."""
    _key = api_key or _get_tmdb_api_key(conn)
    if not _key:
        raise IntegrationError("TMDb API key no configurada")
    url = f"{_TMDB_BASE}/movie/{tmdb_id}?api_key={_key}"
    data = request_json("GET", url)
    if not isinstance(data, dict):
        return None
    return (data.get("original_title") or "").strip() or None


def get_movie_title(tmdb_id: int, *, language: str = "es-ES", api_key: str | None = None, conn=None) -> str | None:
    """Localized movie title from TMDb (/movie/{id}?language=xx). Returns the
    localized `title`, falling back to `original_title`; None if unavailable."""
    _key = api_key or _get_tmdb_api_key(conn)
    if not _key:
        raise IntegrationError("TMDb API key no configurada")
    url = f"{_TMDB_BASE}/movie/{tmdb_id}?api_key={_key}&language={language}"
    data = request_json("GET", url)
    if not isinstance(data, dict):
        return None
    title = (data.get("title") or "").strip()
    return title or (data.get("original_title") or "").strip() or None


def map_tmdb_provider_to_emu_provider(provider_name: str) -> str | None:
    """Convenience wrapper — delegates to source_assistant."""
    from ..services.source_assistant import map_tmdb_provider_to_emu_provider as _map
    return _map(provider_name)
