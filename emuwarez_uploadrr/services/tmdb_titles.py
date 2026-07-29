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
    # eMuwarez requires titles always in Spanish (see references/nomenclatura-emuwarez.md)
    # — this is intentionally not a user setting.
    return "es-ES"


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


def tmdb_configured(conn: sqlite3.Connection) -> bool:
    """Whether a TMDb API key is set (so titles can be localized to Spanish)."""
    return bool((get_setting_canonical(conn, "tmdb.api_key") or "").strip())


def resolve_movie_title(
    conn: sqlite3.Connection,
    tmdb_id: Optional[str | int],
    fallback: str,
    *,
    language: Optional[str] = None,
) -> str:
    """Localized movie title from TMDb, or `fallback` (Radarr title) if TMDb has
    nothing / errors / no key. Cached per (tmdb_id, language)."""
    if not tmdb_id:
        return fallback
    tmdb_id = str(tmdb_id)
    lang = language or _configured_language(conn)
    row = conn.execute(
        "SELECT title FROM tmdb_title_cache WHERE tmdb_id = ? AND media_type = 'movie' AND language = ?",
        (tmdb_id, lang),
    ).fetchone()
    if row is not None:
        return row["title"] or fallback
    try:
        title = tmdb.get_movie_title(int(tmdb_id), language=lang, conn=conn)
    except Exception:
        return fallback
    conn.execute(
        "INSERT OR REPLACE INTO tmdb_title_cache (tmdb_id, media_type, language, title, fetched_at) "
        "VALUES (?, 'movie', ?, ?, CURRENT_TIMESTAMP)",
        (tmdb_id, lang, title),
    )
    return title or fallback


# The Título dropdown's second option is the ENGLISH title, not TMDb's
# `original_name`/`original_title`: those hold the title in the content's
# original language, which for an anime is Japanese (ワンピース) and never what
# a release name wants. eMuwarez release names use the English one.
#
# It can't come from Sonarr either: the library sync overwrites series["title"]
# with the Spanish TMDb title (services/library.py), and Sonarr's payload has
# no originalTitle field at all (that one is Radarr-only), so nothing English
# survives in library_items for a series.
_ENGLISH_LANG = "en-US"


def resolve_english_title(
    conn: sqlite3.Connection,
    media_type: str,
    tmdb_id: Optional[str | int],
    fallback: Optional[str],
) -> Optional[str]:
    """The content's ENGLISH title, for the Título dropdown's second option.
    Cached per (tmdb_id, media_type, 'en-US') like the Spanish one. Falls back
    to `fallback` (library_items.original_title) when TMDb can't answer.
    Never raises."""
    if not tmdb_id or not tmdb_configured(conn):
        return fallback
    is_movie = media_type in ("movie", "film")
    resolver = resolve_movie_title if is_movie else resolve_series_title
    # `fallback or ""` because these resolvers return the fallback verbatim on
    # any miss, and they expect a string.
    title = resolver(conn, tmdb_id, fallback or "", language=_ENGLISH_LANG)
    return (title or "").strip() or fallback


def resolve_localized_title(
    conn: sqlite3.Connection,
    media_type: str,
    tmdb_id: Optional[str | int],
    fallback: str,
) -> tuple[str, Optional[str]]:
    """Force the Spanish (configured-language) title for a nomenclature field.

    Returns (title, warning). `warning` is set when the title could NOT be
    confirmed in Spanish via TMDb (no API key, or no tmdb_id), so the upload
    wizard can flag the Title field for the user to fix manually.
    """
    if not tmdb_configured(conn):
        return fallback, ("TMDb no está configurado: el título no se ha traducido al "
                          "español; revísalo y ponlo en español manualmente.")
    if not tmdb_id:
        return fallback, ("Sin ID de TMDb: no se ha podido traducir el título al "
                          "español; revísalo manualmente.")
    is_movie = media_type in ("movie", "film")
    title = (resolve_movie_title(conn, tmdb_id, fallback) if is_movie
             else resolve_series_title(conn, tmdb_id, fallback))
    return title, None
