"""TMDb series-title localization.

Sonarr titles come from TVDB, whose default series title is usually English even
for Spanish shows ("Los Serrano" → "The Serrano"). Radarr titles come from TMDb
and are already localized. This resolves a series' title from TMDb in the
configured language during the library sync, cached per (tmdb_id, language) so
TMDb is hit only once per series instead of on every sync. Any failure falls
back to the original Sonarr title — it never breaks a sync.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..database import get_setting_canonical
from ..integrations import tmdb

_SETTING_KEY = "tmdb.localize_series_titles"


def series_titles_localized(conn: sqlite3.Connection) -> bool:
    """Whether to replace Sonarr/TVDB series titles with TMDb localized ones.
    Default ON — only an explicit "false" disables it."""
    return (get_setting_canonical(conn, _SETTING_KEY) or "true") != "false"


def _configured_language(conn: sqlite3.Connection) -> str:
    return (get_setting_canonical(conn, "tmdb_language") or "es-ES").strip() or "es-ES"


def resolve_series_title(
    conn: sqlite3.Connection,
    tmdb_id: Optional[str | int],
    fallback: str,
    *,
    language: Optional[str] = None,
) -> str:
    """Return the TMDb localized title for a series, or `fallback` (the Sonarr
    title) if TMDb has nothing / errors / no key. Cached per (tmdb_id, language)."""
    if not tmdb_id:
        return fallback
    tmdb_id = str(tmdb_id)
    lang = language or _configured_language(conn)

    row = conn.execute(
        "SELECT title FROM tmdb_title_cache WHERE tmdb_id = ? AND media_type = 'tv' AND language = ?",
        (tmdb_id, lang),
    ).fetchone()
    if row is not None:
        # Cache hit — a NULL cached title means TMDb had nothing, use fallback.
        return row["title"] or fallback

    try:
        title = tmdb.get_tv_title(int(tmdb_id), language=lang, conn=conn)
    except Exception:
        # Transient error (no key, network, rate limit): don't cache, retry next
        # sync, keep the Sonarr title for now.
        return fallback

    conn.execute(
        "INSERT OR REPLACE INTO tmdb_title_cache (tmdb_id, media_type, language, title, fetched_at) "
        "VALUES (?, 'tv', ?, ?, CURRENT_TIMESTAMP)",
        (tmdb_id, lang, title),
    )
    return title or fallback
