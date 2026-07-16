"""Library synchronization and querying."""
from __future__ import annotations

import sqlite3
import threading
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
    on_progress=None,
    on_total=None,
) -> tuple[int, int]:
    imported = 0
    missing = 0

    def _bump() -> None:
        nonlocal imported
        imported = imported + 1
        if on_progress:
            on_progress(imported)
    if instance.type == "radarr":
        queue_records = radarr.get_queue(instance.url, instance.api_key)
        queue_map = radarr.build_queue_map(queue_records)
        movies = list(radarr.get_movies(instance.url, instance.api_key))
        if on_total:
            on_total(len(movies))  # total items to import from this instance
        for movie in movies:
            item = radarr.movie_to_library_item(
                movie,
                instance_id=int(instance.id),
                instance_name=instance.name,
                queue_map=queue_map,
            )
            upsert_library_item(conn, item)
            _bump()
            if item.local_status != LocalStatus.AVAILABLE.value:
                missing += 1

    elif instance.type == "sonarr":
        from .tmdb_titles import series_titles_localized, resolve_series_title
        localize_titles = series_titles_localized(conn)
        queue_records = sonarr.get_queue(instance.url, instance.api_key)
        series_queue = sonarr.build_series_queue_map(queue_records)
        ep_queue = sonarr.build_episode_queue_map(queue_records)
        series_list = list(sonarr.get_series(instance.url, instance.api_key))
        if on_total:
            # One row per series + all their episodes (from Sonarr's stats).
            total = len(series_list)
            if include_episodes:
                total += sum(int((s.get("statistics") or {}).get("totalEpisodeCount") or 0) for s in series_list)
            on_total(total)
        for series in series_list:
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
            _bump()
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
                    _bump()
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
                    _bump()
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
                    _bump()
                    if ep_item.local_status != LocalStatus.AVAILABLE.value:
                        missing += 1
    return imported, missing


# Live progress of the library sync, so the UI can show a card with the running
# element count. Single-process app → an in-memory dict is enough.
_LIB_SYNC_LOCK = threading.Lock()
_LIB_SYNC_PROGRESS: dict = {"active": False, "done": False, "phase": "", "imported": 0,
                           "missing": 0, "total": 0, "instance": "", "instance_type": "", "error": None}


def get_lib_sync_progress() -> dict:
    with _LIB_SYNC_LOCK:
        return dict(_LIB_SYNC_PROGRESS)


def _set_lib_progress(**kw) -> None:
    with _LIB_SYNC_LOCK:
        _LIB_SYNC_PROGRESS.update(kw)


def start_library_sync_background(include_episodes: bool = True) -> dict:
    """Run sync_all in a background thread so the UI can poll the element count."""
    from ..database import connect, db_path
    with _LIB_SYNC_LOCK:
        if _LIB_SYNC_PROGRESS.get("active"):
            return {"status": "started"}
    _set_lib_progress(active=True, done=False, error=None, phase="Iniciando…",
                      imported=0, missing=0, total=0, instance="", instance_type="")

    def _run() -> None:
        c = connect(db_path())
        try:
            sync_all(c, include_episodes=include_episodes)
        except Exception as exc:  # noqa: BLE001
            _set_lib_progress(error=str(exc), phase="Error")
        finally:
            c.close()
            _set_lib_progress(active=False, done=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


def sync_all(conn: sqlite3.Connection, *, include_episodes: bool = False) -> dict:
    task_id = start_task(conn, "sync-library", "Sincronizando Radarr/Sonarr")
    total = 0
    missing = 0
    grand_total = 0  # total items expected (all instances), for the progress bar
    details: list[str] = []
    errors: list[str] = []

    def _report_total(t: int) -> None:
        nonlocal grand_total
        grand_total += t
        _set_lib_progress(total=grand_total)

    try:
        for instance in list_instances(conn, enabled_only=True):
            base = total  # cumulative count before this instance
            _set_lib_progress(phase=f"Sincronizando {instance.type.capitalize()}: {instance.name}…",
                              instance=instance.name, instance_type=instance.type)
            try:
                imported, miss = sync_instance(
                    conn, instance, include_episodes=include_episodes,
                    on_progress=lambda c, b=base: _set_lib_progress(imported=b + c),
                    on_total=_report_total,
                )
                total += imported
                missing += miss
                _set_lib_progress(imported=total, missing=missing)
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
    # When "ignorar especiales" is on, missing episodes of a special season
    # (season 0) don't count as Faltantes on the dashboard.
    from ..database import get_setting_canonical
    ignore_specials = (get_setting_canonical(conn, "series.ignore_specials") or "true") != "false"

    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS available,
            SUM(CASE WHEN local_status IN ({missing_ph})
                     AND NOT (? = 1 AND item_type = 'episode' AND COALESCE(season_number, -1) = 0)
                THEN 1 ELSE 0 END) AS missing_count,
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
            1 if ignore_specials else 0,
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


# Phase 11G — dashboard "Recomendaciones": actionable content, in three ranked
# groups. (1) content you have that satisfies a *compatible* eMuwarez request
# → click goes to that request. (2) content you have available that is NOT in
# eMuwarez yet ("Contenido único") → an upload opportunity. (3) content you are
# *missing* and that is monitored in Radarr/Sonarr and not on eMuwarez → a
# candidate to request on eMuwarez. Within each group items are ordered by
# type (movie / complete series → season → loose episode) then by title, like
# the library. Groups 2 & 3 link to the content's own detail page.
def _rec_series_title_year(conn: sqlite3.Connection, row: dict) -> tuple:
    """Series title + premiere year for a library item — walks up parent_id from
    a season/episode; a series/movie row returns its own title/year."""
    if row.get("item_type") == "series":
        return row.get("title"), row.get("year")
    pid = row.get("parent_id")
    seen: set = set()
    while pid and pid not in seen:
        seen.add(pid)
        prow = conn.execute(
            "SELECT title, year, item_type, parent_id FROM library_items WHERE id = ?", (pid,)
        ).fetchone()
        if not prow:
            break
        prow = dict(prow)
        if prow.get("item_type") == "series":
            return prow.get("title"), prow.get("year")
        pid = prow.get("parent_id")
    return row.get("title"), row.get("year")


def _rec_content_name(
    conn: sqlite3.Connection, row: dict, *,
    season: int | None = None, episode: int | None = None,
    scope: str | None = None, missing_count: int | None = None,
) -> str:
    """Friendly display name. Movies: "Título (año)". Series/season/episode:
    "Serie (año) - Season N [- SxxEyy]" using the given request scope (or the
    row's own season_number/episode_number when no scope is passed)."""
    it = row.get("item_type")
    sn = season if season is not None else row.get("season_number")
    ep = episode if episode is not None else row.get("episode_number")
    if it == "movie":
        name = row.get("title") or ""
        if row.get("year"):
            name += f" ({row.get('year')})"
        return name
    title, year = _rec_series_title_year(conn, row)
    name = title or row.get("title") or ""
    if year:
        name += f" ({year})"
    if sn is not None:
        name += f" - Season {sn}"
        is_episode = (scope == "episode") or (scope is None and it == "episode")
        if is_episode and ep is not None:
            try:
                name += f" - S{int(sn):02d}E{int(ep):02d}"
            except (TypeError, ValueError):
                pass
    if missing_count:
        name += f" · {missing_count} cap. faltante" + ("s" if missing_count != 1 else "")
    return name


def _rec_rolled_size(conn: sqlite3.Connection, row: dict, *, season: int | None = None, episode: int | None = None):
    """Size to show for a recommendation. Movies/episodes use their own file
    size; a series/season has none of its own, so we sum the file sizes of the
    episodes underneath (optionally restricted to one season, or a single
    episode of it). Returns None when nothing on disk contributes a size, so the
    UI shows "—"."""
    it = row.get("item_type")
    if it in ("movie", "episode"):
        return row.get("size_bytes")
    rid = int(row["id"])
    # A specific episode of a series → drill series → season → episode.
    if it == "series" and season is not None and episode is not None:
        r = conn.execute(
            "SELECT e.size_bytes AS s FROM library_items e "
            "JOIN library_items se ON se.id = e.parent_id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode' "
            "AND se.season_number = ? AND e.episode_number = ? LIMIT 1",
            (rid, season, episode),
        ).fetchone()
        return r["s"] if r else None
    if it == "season":
        r = conn.execute(
            "SELECT SUM(size_bytes) AS s, COUNT(size_bytes) AS c "
            "FROM library_items WHERE parent_id = ? AND item_type = 'episode'",
            (rid,),
        ).fetchone()
    elif season is not None:
        r = conn.execute(
            "SELECT SUM(e.size_bytes) AS s, COUNT(e.size_bytes) AS c "
            "FROM library_items e JOIN library_items se ON se.id = e.parent_id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode' AND se.season_number = ?",
            (rid, season),
        ).fetchone()
    else:
        r = conn.execute(
            "SELECT SUM(e.size_bytes) AS s, COUNT(e.size_bytes) AS c "
            "FROM library_items e JOIN library_items se ON se.id = e.parent_id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'",
            (rid,),
        ).fetchone()
    return r["s"] if r and r["c"] else None


# Order tier by content granularity: movie & complete series first, then whole
# season, then loose episode — the ordering the user asked for.
_REC_TYPE_RANK = {"movie": 0, "series": 0, "season": 1, "episode": 2}


def get_dashboard_recommendations(conn: sqlite3.Connection, *, limit: int = 60) -> list[dict]:
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    recs: list[dict] = []
    seen_lib: set[int] = set()  # library ids already shown (so a piece of
    # content isn't repeated across groups 2 & 3 or after appearing in group 1)

    cols = ("id, item_type, title, year, poster_url, local_status, "
            "season_number, episode_number, parent_id, size_bytes, "
            "resolution, source, tmdb_id, imdb_id, tvdb_id, instance_type")

    # Group 1 — every *compatible* eMuwarez request, sourced from the match
    # table (library_items.request_status only records one request per item, so
    # a series with several compatible requests would otherwise show just once).
    # One row per request, named/sized at the request's own scope (season /
    # episode), linking to that request.
    g1 = conn.execute(
        """
        SELECT ri.id AS req_id, ri.req_scope, ri.req_season, ri.req_episode,
               (SELECT rm.library_item_id FROM request_matches rm
                WHERE rm.request_item_id = ri.id ORDER BY rm.confidence DESC LIMIT 1) AS lib_id
        FROM request_items ri
        WHERE (SELECT rm.status FROM request_matches rm
               WHERE rm.request_item_id = ri.id ORDER BY rm.confidence DESC LIMIT 1) = 'Compatible'
        """
    ).fetchall()
    for r in g1:
        lib_id = r["lib_id"]
        if lib_id is None:
            continue
        lib_row = conn.execute(f"SELECT {cols} FROM library_items WHERE id = ?", (lib_id,)).fetchone()
        if not lib_row:
            continue
        lib = dict(lib_row)
        scope, season, episode = r["req_scope"], r["req_season"], r["req_episode"]
        # Display type follows the request scope, not the matched row (which is
        # usually the series): season request → "Temporada", episode → "Capítulo".
        if lib["item_type"] == "movie":
            disp_type = "movie"
        elif scope == "episode" or episode is not None:
            disp_type = "episode"
        elif season is not None:
            disp_type = "season"
        else:
            disp_type = lib["item_type"]
        d = dict(lib)
        d["item_type"] = disp_type
        d["rec_group"] = 1
        d["rec_request_id"] = r["req_id"]
        d["content_name"] = _rec_content_name(conn, lib, season=season, episode=episode, scope=scope)
        size_episode = episode if (scope == "episode" or disp_type == "episode") else None
        d["size_bytes"] = _rec_rolled_size(conn, lib, season=season, episode=size_episode)
        d["missing_count"] = None
        d["_type_rank"] = _REC_TYPE_RANK.get(disp_type, 3)
        d["_sort_title"] = (d["content_name"] or "").lower()
        recs.append(d)
        seen_lib.add(int(lib_id))

    def _push(row: dict, group: int, *, name: str | None = None, size=None, missing_count=None):
        rid = int(row["id"])
        if rid in seen_lib:
            return
        seen_lib.add(rid)
        d = dict(row)
        d["rec_group"] = group
        d["content_name"] = name if name is not None else _rec_content_name(conn, d)
        d["size_bytes"] = size if size is not None else _rec_rolled_size(conn, d)
        d["rec_request_id"] = None
        d["missing_count"] = missing_count
        d["_type_rank"] = _REC_TYPE_RANK.get(d.get("item_type"), 3)
        d["_sort_title"] = (d["content_name"] or "").lower()
        recs.append(d)

    # Group 2 — available content not in eMuwarez ("Contenido único"): movies,
    # whole unique series, and unique seasons whose parent series isn't itself
    # flagged unique (avoids listing a series and all its seasons twice).
    for row in conn.execute(
        f"""SELECT {cols} FROM library_items li
            WHERE li.local_status = 'Disponible' AND li.emu_in_catalog = 0
              AND li.item_type IN ('movie', 'series', 'season')
              AND NOT (li.item_type = 'season' AND EXISTS (
                  SELECT 1 FROM library_items s
                  WHERE s.id = li.parent_id AND s.emu_in_catalog = 0))"""
    ).fetchall():
        _push(dict(row), 2)

    # Group 3 — monitored content you're missing and that isn't on eMuwarez, a
    # candidate to request. Excludes anything not yet released (unreleased /
    # future air date / "TBA") — you can't request content that doesn't exist
    # yet. Movies directly; series rolled up to the season with monitored
    # missing episodes (you'd request the season, not each episode).
    for row in conn.execute(
        f"""SELECT {cols} FROM library_items
            WHERE item_type = 'movie' AND local_status = 'Faltante'
              AND emu_in_catalog = 0
              AND json_extract(raw_json, '$.monitored') = 1
              AND json_extract(raw_json, '$.status') = 'released'"""
    ).fetchall():
        _push(dict(row), 3)

    for row in conn.execute(
        f"""SELECT {cols}, cnt.missing_count FROM library_items s
            JOIN (
                SELECT ep.parent_id AS sid, COUNT(*) AS missing_count
                FROM library_items ep
                WHERE ep.item_type = 'episode' AND ep.local_status = 'Faltante'
                  AND ep.emu_in_catalog = 0
                  AND json_extract(ep.raw_json, '$.episode.monitored') = 1
                  AND json_extract(ep.raw_json, '$.episode.airDateUtc') IS NOT NULL
                  AND json_extract(ep.raw_json, '$.episode.airDateUtc') <= ?
                  AND UPPER(COALESCE(json_extract(ep.raw_json, '$.episode.title'), '')) <> 'TBA'
                GROUP BY ep.parent_id
            ) cnt ON cnt.sid = s.id
            WHERE s.item_type = 'season'""",
        (now_iso,),
    ).fetchall():
        row = dict(row)
        _push(row, 3, name=_rec_content_name(conn, row, missing_count=row.get("missing_count")),
              missing_count=row.get("missing_count"))

    recs.sort(key=lambda d: (d["rec_group"], d["_type_rank"], d["_sort_title"]))
    for d in recs:
        d.pop("_type_rank", None)
        d.pop("_sort_title", None)
    return recs[:limit]


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
