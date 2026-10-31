"""MAL (MyAnimeList) id resolution via Fribb/anime-lists — a community-
maintained GitHub table mapping tvdb_id/tmdb_id to mal_id for (almost) every
anime. Radarr/Sonarr never provide a MAL id themselves, and this is the ONLY
source used — no best-effort title search against MyAnimeList's own API,
since id-based lookups never produce false positives and every fuzzy-search
fallback does.

The table is anime-only, so matching every library item against it
unconditionally (movies included) is harmless: e.g. Shrek's tmdb_id simply
never appears in it. No is_anime/genre flag is needed to gate the lookup —
checked by hand against real Sonarr/Radarr data before choosing this design:
Sonarr's own `seriesType` field ("standard"/"anime") turned out unreliable
(real anime series sync as "standard"), and Radarr/TMDb never tags "Anime" as
a genre at all, so neither could have gated this reliably anyway.

`anime-list-full.json` already merges tvdb_id + themoviedb_id.movie + mal_id
into a single record per anidb_id (unlike the "-reduced" files, which need a
join across two separate files) — one HTTP call, no extra joining needed.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Optional

from ..database import get_state, set_state
from ..integrations.base import IntegrationError, request_json

logger = logging.getLogger("emuwarez.anime_lists")

_SOURCE_URL = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"
# Community-maintained and static-ish (a handful of updates a month) — a
# weekly refresh is plenty; no need to redownload a ~7MB file every sync.
_REFRESH_SECONDS = 7 * 86400
_SYNC_STATE_KEY = "last_anime_id_map_sync_utc"


def _download_and_store(conn: sqlite3.Connection) -> int:
    data = request_json("GET", _SOURCE_URL, timeout=30)
    if not isinstance(data, list):
        raise IntegrationError("Formato inesperado de anime-list-full.json (se esperaba una lista)")

    rows: list[tuple[Optional[str], Optional[int], Optional[str], str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        mal_id = entry.get("mal_id")
        if not mal_id:
            continue
        mal_id = str(mal_id)
        tvdb_id = entry.get("tvdb_id")
        tvdb_id = str(tvdb_id) if tvdb_id else None
        if tvdb_id:
            season = (entry.get("season") or {}).get("tvdb")
            rows.append((tvdb_id, int(season) if season is not None else None, None, mal_id))
        tmdb_movie_ids = ((entry.get("themoviedb_id") or {}).get("movie")) or []
        for tm in tmdb_movie_ids:
            rows.append((None, None, str(tm), mal_id))

    # Una lista vacía o recortada no sustituye a la tabla: se queda la que había
    # y se reintenta en la próxima sincronización.
    previas = conn.execute("SELECT COUNT(*) FROM anime_id_map").fetchone()[0]
    if not rows or len(rows) < previas // 2:
        raise IntegrationError(
            f"anime-list-full.json trae {len(rows)} filas y la tabla tiene {previas}: no se reemplaza")

    # Full replace, not incremental — the upstream file is small enough to
    # redownload whole, and a partial diff would need to track deletions too
    # (an anidb entry can get its ids corrected/removed upstream).
    conn.execute("DELETE FROM anime_id_map")
    conn.executemany(
        "INSERT INTO anime_id_map (tvdb_id, season_number, tmdb_movie_id, mal_id) VALUES (?, ?, ?, ?)",
        rows,
    )
    set_state(conn, _SYNC_STATE_KEY, str(int(time.time())))
    conn.commit()
    logger.info("anime_id_map actualizado: %d filas desde %d entradas de anime-list-full.json", len(rows), len(data))
    return len(rows)


def _needs_refresh(conn: sqlite3.Connection) -> bool:
    last = get_state(conn, _SYNC_STATE_KEY)
    try:
        last_ts = int(last) if last else 0
    except ValueError:
        last_ts = 0
    return (time.time() - last_ts) >= _REFRESH_SECONDS


def ensure_anime_id_map(conn: sqlite3.Connection, *, force: bool = False) -> None:
    """Populate/refresh `anime_id_map` when empty or stale. Best-effort — a
    failed/slow download must never block a library sync: on any error this
    just leaves whatever's already in the table (even if stale, or empty on
    a first-ever failed attempt), never raises."""
    if not force:
        has_any = conn.execute("SELECT 1 FROM anime_id_map LIMIT 1").fetchone() is not None
        if has_any and not _needs_refresh(conn):
            return
    try:
        _download_and_store(conn)
    except Exception:
        logger.warning("No se pudo descargar/actualizar anime-list-full.json (Fribb/anime-lists)", exc_info=True)


def get_mal_id(
    conn: sqlite3.Connection,
    *,
    item_type: str,
    tvdb_id: Optional[str],
    tmdb_id: Optional[str],
    season_number: Optional[int],
) -> Optional[str]:
    """Best-effort MAL id lookup against the local anime_id_map mirror —
    never raises. Movies match by tmdb_id; series/season/episode match by
    tvdb_id, preferring an exact season match when known (a multi-season
    anime can have a distinct MAL entry per season sharing the same
    tvdb_id) and falling back to any season otherwise."""
    try:
        if item_type == "movie":
            if not tmdb_id:
                return None
            row = conn.execute(
                "SELECT mal_id FROM anime_id_map WHERE tmdb_movie_id = ? LIMIT 1",
                (str(tmdb_id),),
            ).fetchone()
            return row["mal_id"] if row else None

        if not tvdb_id:
            return None
        if season_number is not None:
            row = conn.execute(
                "SELECT mal_id FROM anime_id_map WHERE tvdb_id = ? AND season_number = ? LIMIT 1",
                (str(tvdb_id), season_number),
            ).fetchone()
            if row:
                return row["mal_id"]
        row = conn.execute(
            "SELECT mal_id FROM anime_id_map WHERE tvdb_id = ? LIMIT 1",
            (str(tvdb_id),),
        ).fetchone()
        return row["mal_id"] if row else None
    except Exception:
        logger.warning("Fallo resolviendo mal_id", exc_info=True)
        return None
