"""Library synchronization and querying."""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..integrations import radarr, sonarr
from ..models import InstanceConfig, LibraryItem, LocalStatus, NomenclatureStatus
from .instances import list_instances
from .tasks import start_task, finish_task


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_library_item(conn: sqlite3.Connection, item: LibraryItem) -> int:
    data = item.to_dict()
    columns = [
        "item_type", "title", "year", "original_title", "instance_id", "instance_type",
        "instance_name", "external_id", "tmdb_id", "imdb_id", "tvdb_id", "title_slug",
        "season_number", "episode_number", "parent_id", "path",
        "quality", "resolution", "source", "video_codec", "audio_codec", "audio_languages",
        "audio_channels", "dynamic_range", "subtitle_languages", "size_bytes", "local_status",
        "request_status", "nomenclature_status", "request_id", "added_at", "raw_json",
        "poster_url",
    ]
    values = [data.get(col) for col in columns]
    conn.execute(
        f"""
        INSERT INTO library_items({', '.join(columns)}, updated_at)
        VALUES ({', '.join(['?'] * len(columns))}, CURRENT_TIMESTAMP)
        ON CONFLICT(instance_id, item_type, external_id) DO UPDATE SET
            title = excluded.title,
            year = excluded.year,
            original_title = excluded.original_title,
            instance_type = excluded.instance_type,
            instance_name = excluded.instance_name,
            tmdb_id = excluded.tmdb_id,
            imdb_id = excluded.imdb_id,
            tvdb_id = excluded.tvdb_id,
            title_slug = excluded.title_slug,
            season_number = excluded.season_number,
            episode_number = excluded.episode_number,
            parent_id = excluded.parent_id,
            path = excluded.path,
            quality = excluded.quality,
            resolution = excluded.resolution,
            source = excluded.source,
            video_codec = excluded.video_codec,
            audio_codec = excluded.audio_codec,
            audio_languages = excluded.audio_languages,
            audio_channels = excluded.audio_channels,
            dynamic_range = excluded.dynamic_range,
            subtitle_languages = excluded.subtitle_languages,
            size_bytes = excluded.size_bytes,
            local_status = excluded.local_status,
            -- Keep the strict nomenclature verdict while the FILE is unchanged
            -- (same path + size); reset to whatever the sync brings ('No
            -- comprobada') when the file is new or changed (e.g. renamed after
            -- an upload / re-downloaded).
            nomenclature_status = CASE
                WHEN library_items.path IS excluded.path
                 AND library_items.size_bytes IS excluded.size_bytes
                THEN library_items.nomenclature_status
                ELSE excluded.nomenclature_status END,
            nomenclature_expected = CASE
                WHEN library_items.path IS excluded.path
                 AND library_items.size_bytes IS excluded.size_bytes
                THEN library_items.nomenclature_expected ELSE NULL END,
            nomenclature_checked_at = CASE
                WHEN library_items.path IS excluded.path
                 AND library_items.size_bytes IS excluded.size_bytes
                THEN library_items.nomenclature_checked_at ELSE NULL END,
            raw_json = excluded.raw_json,
            poster_url = excluded.poster_url,
            updated_at = CURRENT_TIMESTAMP
        """,
        values,
    )
    row = conn.execute(
        "SELECT id FROM library_items WHERE instance_id = ? AND item_type = ? AND external_id = ?",
        (item.instance_id, item.item_type, item.external_id),
    ).fetchone()
    conn.commit()
    return int(row["id"])


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def sync_instance(
    conn: sqlite3.Connection,
    instance: InstanceConfig,
    *,
    include_episodes: bool = False,
) -> tuple[int, int]:
    imported = 0
    missing = 0
    if instance.type == "radarr":
        queue_records = radarr.get_queue(instance.url, instance.api_key)
        queue_map = radarr.build_queue_map(queue_records)
        for movie in radarr.get_movies(instance.url, instance.api_key):
            item = radarr.movie_to_library_item(
                movie,
                instance_id=int(instance.id),
                instance_name=instance.name,
                queue_map=queue_map,
            )
            upsert_library_item(conn, item)
            imported += 1
            if item.local_status != LocalStatus.AVAILABLE.value:
                missing += 1

    elif instance.type == "sonarr":
        from .tmdb_titles import series_titles_localized, resolve_series_title
        localize_titles = series_titles_localized(conn)
        queue_records = sonarr.get_queue(instance.url, instance.api_key)
        series_queue = sonarr.build_series_queue_map(queue_records)
        ep_queue = sonarr.build_episode_queue_map(queue_records)
        for series in sonarr.get_series(instance.url, instance.api_key):
            # Sonarr's title is TVDB's (often English). Replace it with TMDb's
            # localized title so seasons/episodes (which embed it) inherit it too.
            if localize_titles and series.get("title") and series.get("tmdbId"):
                series["title"] = resolve_series_title(
                    conn, series.get("tmdbId"), series["title"]
                )
            series_item = sonarr.series_to_library_item(
                series,
                instance_id=int(instance.id),
                instance_name=instance.name,
                series_queue_map=series_queue,
            )
            series_row_id = upsert_library_item(conn, series_item)
            imported += 1
            if series_item.local_status in LocalStatus.not_available():
                missing += 1
            if include_episodes and series.get("id"):
                files = sonarr.get_episode_files(instance.url, instance.api_key, int(series["id"]))
                files_by_id = {f.get("id"): f for f in files if f.get("id") is not None}
                episodes = sonarr.get_episodes(instance.url, instance.api_key, int(series["id"]))

                # Group episodes by season to (a) resolve each episode's
                # parent season row id, and (b) compute a bottom-up
                # episode/file count fallback for seasons whose Sonarr
                # `statistics` block is missing/empty.
                episodes_by_season: dict[int, list[dict]] = {}
                for ep in episodes:
                    season_num = ep.get("seasonNumber")
                    if season_num is None:
                        continue
                    episodes_by_season.setdefault(int(season_num), []).append(ep)

                def _file_count(season_eps: list[dict]) -> int:
                    return sum(
                        1 for ep in season_eps
                        if ep.get("episodeFileId") and files_by_id.get(ep.get("episodeFileId"))
                    )

                season_row_id_by_number: dict[int, int] = {}
                seen_season_numbers: set[int] = set()
                for season_entry in series.get("seasons") or []:
                    season_num = season_entry.get("seasonNumber")
                    if season_num is None:
                        continue
                    season_num = int(season_num)
                    seen_season_numbers.add(season_num)
                    season_eps = episodes_by_season.get(season_num, [])
                    stats_present = bool(season_entry.get("statistics"))
                    season_item = sonarr.season_to_library_item(
                        series, season_entry,
                        instance_id=int(instance.id),
                        instance_name=instance.name,
                        parent_id=series_row_id,
                        episode_count_override=None if stats_present else len(season_eps),
                        file_count_override=None if stats_present else _file_count(season_eps),
                    )
                    season_row_id_by_number[season_num] = upsert_library_item(conn, season_item)
                    imported += 1
                    if season_item.local_status in LocalStatus.not_available():
                        missing += 1

                # Defensive fallback: series["seasons"] was empty/missing a
                # season that episodes actually reference — synthesize that
                # season row purely bottom-up so no episode is ever left
                # without a parent.
                for season_num, season_eps in episodes_by_season.items():
                    if season_num in seen_season_numbers:
                        continue
                    synthetic_entry = {"seasonNumber": season_num, "statistics": {}}
                    season_item = sonarr.season_to_library_item(
                        series, synthetic_entry,
                        instance_id=int(instance.id),
                        instance_name=instance.name,
                        parent_id=series_row_id,
                        episode_count_override=len(season_eps),
                        file_count_override=_file_count(season_eps),
                    )
                    season_row_id_by_number[season_num] = upsert_library_item(conn, season_item)
                    imported += 1
                    if season_item.local_status in LocalStatus.not_available():
                        missing += 1

                for episode in episodes:
                    ep_file = (
                        files_by_id.get(episode.get("episodeFileId"))
                        if episode.get("episodeFileId")
                        else None
                    )
                    season_num = episode.get("seasonNumber")
                    parent_season_id = (
                        season_row_id_by_number.get(int(season_num))
                        if season_num is not None else None
                    )
                    ep_item = sonarr.episode_to_library_item(
                        episode,
                        ep_file,
                        series,
                        instance_id=int(instance.id),
                        instance_name=instance.name,
                        ep_queue_map=ep_queue,
                        parent_id=parent_season_id,
                    )
                    upsert_library_item(conn, ep_item)
                    imported += 1
                    if ep_item.local_status != LocalStatus.AVAILABLE.value:
                        missing += 1
    return imported, missing


def sync_all(conn: sqlite3.Connection, *, include_episodes: bool = False) -> dict:
    task_id = start_task(conn, "sync-library", "Sincronizando Radarr/Sonarr")
    total = 0
    missing = 0
    details: list[str] = []
    errors: list[str] = []
    try:
        for instance in list_instances(conn, enabled_only=True):
            try:
                imported, miss = sync_instance(conn, instance, include_episodes=include_episodes)
                total += imported
                missing += miss
                details.append(f"{instance.type}:{instance.name}: {imported} importados, {miss} faltantes")
            except Exception as exc:
                err = f"{instance.type}:{instance.name}: {exc}"
                errors.append(err)
                details.append(f"ERROR — {err}")
        summary = f"{total} elementos sincronizados; {missing} no disponibles"
        finish_task(conn, task_id, "completed", summary, "\n".join(details))
        return {"imported": total, "missing": missing, "instances": len(list_instances(conn)), "errors": errors}
    except Exception as exc:
        finish_task(conn, task_id, "failed", str(exc), "\n".join(details))
        raise


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_MISSING_STATUSES = LocalStatus.not_available()


# Sentinel status value the Biblioteca filter uses for "todos los no
# disponibles" — expands to the same LocalStatus.not_available() set that
# list_missing()/the dashboard's `missing` count already use, so removing
# the standalone Faltantes tab doesn't lose the ability to see this
# combined view from Biblioteca's own status filter.
NOT_AVAILABLE_STATUS_FILTER = "__not_available__"

# Sentinel parent_id value meaning "top level only" (WHERE parent_id IS
# NULL) — 0 is never a real row id (AUTOINCREMENT starts at 1), so it's
# safe to use as a sentinel. Must be checked with `is not None`, never a
# bare `if parent_id:`, since 0 would otherwise be mistaken for "no filter".
TOP_LEVEL_PARENT_FILTER = 0


def _build_library_filter(
    *,
    status: Optional[str] = None,
    request: Optional[str] = None,
    nomenclature: Optional[str] = None,
    item_type: Optional[str] = None,
    origin: Optional[str] = None,
    instance_id: Optional[int] = None,
    parent_id: Optional[int] = None,
    search: Optional[str] = None,
) -> tuple[list[str], list]:
    """Shared WHERE-clause builder for list_library()/count_library() — used
    to be duplicated (and count_library() silently dropped request/
    nomenclature/origin, making its `total` wrong once those filters were
    used), now both always apply the exact same filters."""
    where = []
    params: list = []
    if status == NOT_AVAILABLE_STATUS_FILTER:
        placeholders = ",".join("?" * len(_MISSING_STATUSES))
        where.append(f"local_status IN ({placeholders})")
        params.extend(_MISSING_STATUSES)
    elif status:
        where.append("local_status = ?")
        params.append(status)
    if request:
        where.append("request_status = ?")
        params.append(request)
    if nomenclature:
        where.append("nomenclature_status = ?")
        params.append(nomenclature)
    if item_type:
        where.append("item_type = ?")
        params.append(item_type)
    if origin:
        where.append("instance_type = ?")
        params.append(origin)
    if instance_id:
        where.append("instance_id = ?")
        params.append(instance_id)
    if parent_id is not None:
        if parent_id == TOP_LEVEL_PARENT_FILTER:
            where.append("parent_id IS NULL")
        else:
            where.append("parent_id = ?")
            params.append(parent_id)
    if search:
        where.append("title LIKE ?")
        params.append(f"%{search}%")
    return where, params


# User-selectable ordering for the top-level library list. Applied as the
# tie-break AFTER the season/episode numeric ordering, so expanding a series
# always shows its seasons/episodes in numeric order regardless of this choice.
# "title_asc" (COLLATE NOCASE) gives símbolos < números < A-Z, the default.
# TITLE_SORT (registered in database.connect) folds accents and orders
# símbolos < números < letras; NOCASE would drop accented titles at the end.
_LIBRARY_SORT = {
    "title_asc": "title COLLATE TITLE_SORT ASC, updated_at DESC",
    "title_desc": "title COLLATE TITLE_SORT DESC, updated_at DESC",
    "updated_desc": "updated_at DESC, title COLLATE TITLE_SORT ASC",
    "year_desc": "year IS NULL, year DESC, title COLLATE TITLE_SORT ASC",
    "year_asc": "year IS NULL, year ASC, title COLLATE TITLE_SORT ASC",
}
DEFAULT_LIBRARY_SORT = "title_asc"


def list_library(
    conn: sqlite3.Connection,
    *,
    status: Optional[str] = None,
    request: Optional[str] = None,
    nomenclature: Optional[str] = None,
    item_type: Optional[str] = None,
    origin: Optional[str] = None,
    instance_id: Optional[int] = None,
    parent_id: Optional[int] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    where, params = _build_library_filter(
        status=status, request=request, nomenclature=nomenclature,
        item_type=item_type, origin=origin, instance_id=instance_id,
        parent_id=parent_id, search=search,
    )
    sql = "SELECT * FROM library_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # Seasons/episodes carry season_number/episode_number and must sort
    # numerically (Temporada 1, 2, …, 10, not string order). Top-level rows
    # (movies/series) have both NULL, so they tie there and fall through to the
    # user-selected sort.
    sort_sql = _LIBRARY_SORT.get(sort or DEFAULT_LIBRARY_SORT, _LIBRARY_SORT[DEFAULT_LIBRARY_SORT])
    sql += (
        " ORDER BY season_number IS NOT NULL, season_number, episode_number,"
        f" {sort_sql} LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def count_library(
    conn: sqlite3.Connection,
    *,
    status: Optional[str] = None,
    request: Optional[str] = None,
    nomenclature: Optional[str] = None,
    item_type: Optional[str] = None,
    origin: Optional[str] = None,
    instance_id: Optional[int] = None,
    parent_id: Optional[int] = None,
    search: Optional[str] = None,
) -> int:
    where, params = _build_library_filter(
        status=status, request=request, nomenclature=nomenclature,
        item_type=item_type, origin=origin, instance_id=instance_id,
        parent_id=parent_id, search=search,
    )
    sql = "SELECT COUNT(*) FROM library_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def get_library_item(conn: sqlite3.Connection, item_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def list_missing(conn: sqlite3.Connection, *, limit: int = 50, offset: int = 0) -> list[dict]:
    placeholders = ", ".join(["?"] * len(_MISSING_STATUSES))
    sql = (
        f"SELECT * FROM library_items WHERE local_status IN ({placeholders})"
        " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, [*_MISSING_STATUSES, limit, offset]).fetchall()
    return [dict(row) for row in rows]


def get_dashboard_summary(conn: sqlite3.Connection) -> dict:
    """Return aggregated counts from library_items.

    Restricted to item_type IN ('movie','episode') — real content units —
    so series/season rollup rows (organizational, not real content) never
    double-count against these totals (a series with 10 episodes must
    contribute 10, not 11 by also counting the series row itself)."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS available,
            SUM(CASE WHEN local_status IN ({missing_ph}) THEN 1 ELSE 0 END) AS missing_count,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS uploading,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS uploaded,
            SUM(CASE WHEN instance_type = 'radarr' THEN 1 ELSE 0 END) AS radarr_items,
            SUM(CASE WHEN instance_type = 'sonarr' THEN 1 ELSE 0 END) AS sonarr_items
        FROM library_items
        WHERE item_type IN ('movie', 'episode')
        """.format(missing_ph=", ".join(["?"] * len(_MISSING_STATUSES))),
        [
            LocalStatus.AVAILABLE.value,
            *_MISSING_STATUSES,
            LocalStatus.UPLOADING.value,
            LocalStatus.UPLOADED.value,
        ],
    ).fetchone()

    # "Contenido único": lo disponible que sale como "No" en ¿En eMuwarez?
    # (emu_in_catalog = 0). Se cuenta por unidad subible: cada película, cada
    # temporada completa de serie/documental, y sus capítulos. emu_in_catalog
    # se calcula a nivel de película y de serie/temporada (nunca por episodio),
    # así que los capítulos se cuentan por su temporada única.
    avail = LocalStatus.AVAILABLE.value
    uniq = conn.execute(
        """
        SELECT
            SUM(CASE WHEN item_type = 'movie'  THEN 1 ELSE 0 END) AS movies,
            SUM(CASE WHEN item_type = 'season' THEN 1 ELSE 0 END) AS seasons
        FROM library_items
        WHERE emu_in_catalog = 0 AND local_status = ?
        """,
        [avail],
    ).fetchone()
    uniq_ep = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM library_items e
        JOIN library_items s ON e.parent_id = s.id
        WHERE e.item_type = 'episode' AND e.local_status = ?
          AND s.item_type = 'season' AND s.emu_in_catalog = 0
        """,
        [avail],
    ).fetchone()
    unique_movies = int(uniq["movies"] or 0)
    unique_seasons = int(uniq["seasons"] or 0)
    unique_episodes = int(uniq_ep["n"] or 0)

    last_sync = conn.execute(
        "SELECT started_at FROM task_runs WHERE name = 'sync-library' AND status = 'completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    return {
        "library_total": int(row["total"] or 0),
        "available": int(row["available"] or 0),
        "missing": int(row["missing_count"] or 0),
        "uploading": int(row["uploading"] or 0),
        "completed": int(row["uploaded"] or 0),
        # Headline = unidades subibles (películas + temporadas completas).
        "unique_content": unique_movies + unique_seasons,
        "unique_movies": unique_movies,
        "unique_seasons": unique_seasons,
        "unique_episodes": unique_episodes,
        "radarr_items": int(row["radarr_items"] or 0),
        "sonarr_items": int(row["sonarr_items"] or 0),
        "last_sync_at": last_sync["started_at"] if last_sync else None,
    }


def get_dashboard_diagnostics(conn: sqlite3.Connection) -> dict:
    """Return Phase 8A diagnostic counts for the dashboard."""
    try:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN file_exists = 1 THEN 1 ELSE 0 END) AS files_verified,
                SUM(CASE WHEN local_status = 'Disponible' AND file_exists = 0 AND file_verified_at IS NOT NULL THEN 1 ELSE 0 END) AS files_missing_on_disk,
                SUM(CASE WHEN recommended_action = 'adapt_nomenclature' THEN 1 ELSE 0 END) AS items_ready_for_nomenclature,
                SUM(CASE WHEN recommended_action IN ('upload', 'run_preflight') THEN 1 ELSE 0 END) AS items_ready_for_upload,
                SUM(CASE WHEN arr_queue_status IN ('downloading', 'queued') THEN 1 ELSE 0 END) AS items_waiting_download,
                SUM(CASE WHEN recommended_action = 'review_arr' THEN 1 ELSE 0 END) AS items_need_arr_review
            FROM library_items
            """
        ).fetchone()
        if row:
            return {
                "files_verified": int(row["files_verified"] or 0),
                "files_missing_on_disk": int(row["files_missing_on_disk"] or 0),
                "items_ready_for_nomenclature": int(row["items_ready_for_nomenclature"] or 0),
                "items_ready_for_upload": int(row["items_ready_for_upload"] or 0),
                "items_waiting_download": int(row["items_waiting_download"] or 0),
                "items_need_arr_review": int(row["items_need_arr_review"] or 0),
            }
    except Exception:
        pass
    return {
        "files_verified": 0,
        "files_missing_on_disk": 0,
        "items_ready_for_nomenclature": 0,
        "items_ready_for_upload": 0,
        "items_waiting_download": 0,
        "items_need_arr_review": 0,
    }


def get_recent_activity(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict]:
    """Return recent task_runs as activity feed."""
    rows = conn.execute(
        "SELECT * FROM task_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


# Phase 11F — dashboard "Actividad reciente" priority: items with a filled
# (satisfied) EMU request first, then compatible/partial candidates, then
# everything else; ties broken by most-recently-updated (a deterministic,
# honest stand-in for "then random" — re-shuffling on every dashboard load
# would be noisy, not more useful).
_REQUEST_PRIORITY_SQL = """
    CASE request_status
        WHEN 'Llena' THEN 0
        WHEN 'Compatible' THEN 1
        WHEN 'Parcial' THEN 2
        WHEN 'No compatible' THEN 3
        WHEN 'Desconocida' THEN 4
        ELSE 5
    END
"""


def get_dashboard_library_activity(conn: sqlite3.Connection, *, limit: int = 10) -> list[dict]:
    """Top-level items only (parent_id IS NULL) — movies and series, never
    raw episode/season rows flooding the 'Actividad reciente' feed."""
    rows = conn.execute(
        f"SELECT * FROM library_items WHERE parent_id IS NULL "
        f"ORDER BY {_REQUEST_PRIORITY_SQL}, updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_request_status(
    conn: sqlite3.Connection,
    library_item_id: int,
    request_status: str,
    request_id: Optional[int] = None,
) -> None:
    conn.execute(
        "UPDATE library_items SET request_status = ?, request_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (request_status, request_id, library_item_id),
    )
    conn.commit()


def mark_nomenclature(conn: sqlite3.Connection, library_item_id: int, status: str) -> None:
    conn.execute(
        "UPDATE library_items SET nomenclature_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, library_item_id),
    )
    conn.commit()
