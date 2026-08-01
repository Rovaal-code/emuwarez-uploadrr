"""Real library, missing, and sync endpoints (Phase 4)."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from emuwarez_uploadrr.services.nomenclature import infer_provider_from_item
from emuwarez_uploadrr.services.library import content_display_title, episode_own_name
from emuwarez_uploadrr.services.source_assistant import EMU_PROVIDERS

_PROVIDER_NAME_BY_CODE = {p["code"]: p["name"] for p in EMU_PROVIDERS}


def _provider_label(code: Optional[str]) -> Optional[str]:
    """'Nombre (CÓDIGO)' for a provider code, e.g. 'Amazon (AMZN)'."""
    if not code:
        return None
    name = _PROVIDER_NAME_BY_CODE.get(code)
    return f"{name} ({code})" if name else code
from ..schemas import (
    LibraryItemResponse, LibraryListResponse,
    MissingItemResponse, MissingListResponse,
    OkResponse, SyncRequest, SyncResponse,
)

router = APIRouter(tags=["library"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _ignore_specials(conn) -> bool:
    """User setting: exclude specials (season 0) from a Series' availability /
    nomenclature / eMuwarez rollups. Default True (specials rarely matter and
    are rarely on the tracker); only an explicit "false" turns it off."""
    if conn is None:
        return True
    from ...database import get_setting_canonical
    return (get_setting_canonical(conn, "series.ignore_specials") or "true") != "false"


def _specials_clause(alias: str, ignore_specials: bool) -> str:
    """SQL fragment excluding season-0 episodes when ignore_specials is on."""
    if not ignore_specials:
        return ""
    return f" AND ({alias}.season_number IS NULL OR {alias}.season_number != 0)"


def _nomenclature_rollup(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> Optional[str]:
    """Aggregate the nomenclature status of a Season (from its episodes) or a
    Series (from all its episodes). 'Correcta' only when EVERY episode is
    'Correcta' — a missing/unadapted episode (N/A or No adaptada) prevents it.
    Returns:
      - 'Correcta'    when every episode is adapted,
      - 'No adaptada' when none is adapted (and none is N/A),
      - 'N/A'         when every episode is N/A (nothing to adapt yet),
      - 'Parcial'     otherwise (a mix),
      - None          when there's nothing to aggregate (keep the row's own).
    """
    if conn is None:
        return None
    if item_type == "season":
        sql = (
            "SELECT nomenclature_status AS s, COUNT(*) AS c FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode' GROUP BY nomenclature_status"
        )
    elif item_type == "series":
        sql = (
            "SELECT e.nomenclature_status AS s, COUNT(*) AS c FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'"
            + _specials_clause("se", ignore_specials)
            + " GROUP BY e.nomenclature_status"
        )
    else:
        return None
    counts = {r["s"]: r["c"] for r in conn.execute(sql, (item_id,)).fetchall()}
    if sum(counts.values()) == 0:
        return None
    correct = counts.get("Correcta", 0)
    not_adapted = counts.get("No adaptada", 0)
    unchecked = counts.get("No comprobada", 0)
    available = correct + not_adapted + unchecked  # episodes with a file
    if available == 0:
        return "N/A"                 # nothing on disk to adapt yet
    if unchecked > 0:
        return "No comprobada"       # some available episode still not checked
    if correct == available:
        return "Correcta"            # all available checked and correct
    if not_adapted == available:
        return "No adaptada"
    return "Parcial"


def _local_status_rollup(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> Optional[str]:
    """Availability of a Season/Series computed from its real EPISODES, not from
    Sonarr's own status (which reports 'Disponible' even when episodes are
    missing). 'Disponible' only when every counted episode has a file,
    'Faltante' when none does, 'Parcial' otherwise. With ignore_specials on,
    season-0 episodes are excluded from a Series' count."""
    if conn is None:
        return None
    if item_type == "season":
        sql = (
            "SELECT local_status AS s, COUNT(*) AS c FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode' GROUP BY local_status"
        )
    elif item_type == "series":
        sql = (
            "SELECT e.local_status AS s, COUNT(*) AS c FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'"
            + _specials_clause("se", ignore_specials)
            + " GROUP BY e.local_status"
        )
    else:
        return None
    counts = {r["s"]: r["c"] for r in conn.execute(sql, (item_id,)).fetchall()}
    total = sum(counts.values())
    if total == 0:
        return None
    available = counts.get("Disponible", 0)
    if available == total:
        return "Disponible"
    if available == 0:
        return "Faltante"
    return "Parcial"


def _size_rollup(conn, item_id: int, item_type: str) -> Optional[int]:
    """Total size of a Season/Series as the sum of its episodes' file sizes —
    season/series rows have no file of their own, so their size only makes
    sense as the aggregate of the episodes below them."""
    if conn is None:
        return None
    if item_type == "season":
        r = conn.execute(
            "SELECT SUM(size_bytes) AS s FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode'",
            (item_id,),
        ).fetchone()
    elif item_type == "series":
        r = conn.execute(
            "SELECT SUM(e.size_bytes) AS s FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'",
            (item_id,),
        ).fetchone()
    else:
        return None
    return int(r["s"]) if r and r["s"] is not None else None


def _rollup_path(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> Optional[str]:
    """Folder path for a Season/Series rollup, derived from its episodes'
    files: the common parent directory (a season's own folder, e.g.
    '…/Attack on Titan/Season 2'; a series' root folder)."""
    if conn is None:
        return None
    if item_type == "season":
        rows = conn.execute(
            "SELECT path FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode' AND path IS NOT NULL",
            (item_id,),
        ).fetchall()
    elif item_type == "series":
        rows = conn.execute(
            "SELECT e.path AS path FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode' AND e.path IS NOT NULL"
            + _specials_clause("se", ignore_specials),
            (item_id,),
        ).fetchall()
    else:
        return None
    paths = [r["path"] for r in rows if r["path"]]
    if not paths:
        return None
    dirs = {os.path.dirname(p) for p in paths}
    if len(dirs) == 1:
        return next(iter(dirs))
    try:
        return os.path.commonpath(paths)
    except ValueError:
        return None


_ROLLUP_EMPTY = {
    "provider": None, "resolution": None, "source": None, "video_codec": None,
    "audio_codec": None, "audio_languages": None, "subtitle_languages": None,
}


def _child_quality_rollup(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> dict:
    """Per-attribute value shared by ALL episodes of a Season/Series (or None
    when they differ or are absent): provider, resolution, source, video/audio
    codec, audio and subtitle languages. Lets a uniform season/series show the
    same attributes as its episodes. Specials (season 0) are excluded from a
    Series rollup when ignore_specials is on."""
    if conn is None:
        return dict(_ROLLUP_EMPTY)
    if item_type == "season":
        rows = conn.execute(
            "SELECT path, resolution, source, video_codec, audio_codec, "
            "audio_languages, subtitle_languages FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode'",
            (item_id,),
        ).fetchall()
    elif item_type == "series":
        rows = conn.execute(
            "SELECT e.path AS path, e.resolution AS resolution, e.source AS source, "
            "e.video_codec AS video_codec, e.audio_codec AS audio_codec, "
            "e.audio_languages AS audio_languages, e.subtitle_languages AS subtitle_languages "
            "FROM library_items e JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'"
            + _specials_clause("se", ignore_specials),
            (item_id,),
        ).fetchall()
    else:
        return dict(_ROLLUP_EMPTY)
    if not rows:
        return dict(_ROLLUP_EMPTY)

    def uniq(key: str):
        vals = {r[key] for r in rows}
        return next(iter(vals)) if len(vals) == 1 else None

    providers: set = set()
    for r in rows:
        providers.add(infer_provider_from_item({"path": r["path"], "source": r["source"]}))
        if len(providers) > 1:
            break
    return {
        "provider": next(iter(providers)) if len(providers) == 1 else None,
        "resolution": uniq("resolution"),
        "source": uniq("source"),
        "video_codec": uniq("video_codec"),
        "audio_codec": uniq("audio_codec"),
        "audio_languages": uniq("audio_languages"),
        "subtitle_languages": uniq("subtitle_languages"),
    }


# ---------------------------------------------------------------------------
# Batched rollups for library_list() — the single-id helpers above are still
# used as-is for the single-item lookup (GET /api/library/{id}, one row, no
# N+1 concern), but calling them once PER season/series row in a list of many
# was the real cost behind a slow /api/library: ~5 extra queries per row, so
# a page with a few hundred series meant a few hundred round trips. These
# fetch every relevant episode row for ALL ids in the page in a couple of
# queries total, then do the exact same aggregation in Python, keyed by id.
# ---------------------------------------------------------------------------

def _aggregate_nomenclature(statuses: list) -> Optional[str]:
    counts: dict = {}
    for s in statuses:
        counts[s] = counts.get(s, 0) + 1
    if sum(counts.values()) == 0:
        return None
    correct = counts.get("Correcta", 0)
    not_adapted = counts.get("No adaptada", 0)
    unchecked = counts.get("No comprobada", 0)
    available = correct + not_adapted + unchecked
    if available == 0:
        return "N/A"
    if unchecked > 0:
        return "No comprobada"
    if correct == available:
        return "Correcta"
    if not_adapted == available:
        return "No adaptada"
    return "Parcial"


def _aggregate_local_status(statuses: list) -> Optional[str]:
    counts: dict = {}
    for s in statuses:
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return None
    available = counts.get("Disponible", 0)
    if available == total:
        return "Disponible"
    if available == 0:
        return "Faltante"
    return "Parcial"


def _aggregate_size(sizes: list) -> Optional[int]:
    if not any(s is not None for s in sizes):
        return None
    return sum(s for s in sizes if s is not None)


def _aggregate_quality(rows: list[dict]) -> dict:
    if not rows:
        return dict(_ROLLUP_EMPTY)

    def uniq(key: str):
        vals = {r[key] for r in rows}
        return next(iter(vals)) if len(vals) == 1 else None

    providers: set = set()
    for r in rows:
        providers.add(infer_provider_from_item({"path": r["path"], "source": r["source"]}))
        if len(providers) > 1:
            break
    return {
        "provider": next(iter(providers)) if len(providers) == 1 else None,
        "resolution": uniq("resolution"),
        "source": uniq("source"),
        "video_codec": uniq("video_codec"),
        "audio_codec": uniq("audio_codec"),
        "audio_languages": uniq("audio_languages"),
        "subtitle_languages": uniq("subtitle_languages"),
    }


def _aggregate_path(rows: list[dict]) -> Optional[str]:
    paths = [r["path"] for r in rows if r["path"]]
    if not paths:
        return None
    dirs = {os.path.dirname(p) for p in paths}
    if len(dirs) == 1:
        return next(iter(dirs))
    try:
        return os.path.commonpath(paths)
    except ValueError:
        return None


def _batch_rollups(conn, series_ids: list[int], season_ids: list[int], ignore_specials: bool) -> dict[int, dict]:
    """{item_id: {"nomenclature", "size", "local_status", "quality", "path"}}
    for every id in series_ids/season_ids, computed from at most 2 queries
    total (one per grouping depth) instead of ~5 queries per id."""
    groups: dict[int, list[dict]] = {}

    if season_ids:
        placeholders = ",".join("?" * len(season_ids))
        rows = conn.execute(
            "SELECT parent_id AS gid, path, resolution, source, video_codec, audio_codec, "
            "audio_languages, subtitle_languages, nomenclature_status, local_status, size_bytes "
            f"FROM library_items WHERE parent_id IN ({placeholders}) AND item_type = 'episode'",
            season_ids,
        ).fetchall()
        for r in rows:
            groups.setdefault(r["gid"], []).append(dict(r))

    if series_ids:
        placeholders = ",".join("?" * len(series_ids))
        rows = conn.execute(
            "SELECT se.parent_id AS gid, e.path AS path, e.resolution AS resolution, e.source AS source, "
            "e.video_codec AS video_codec, e.audio_codec AS audio_codec, "
            "e.audio_languages AS audio_languages, e.subtitle_languages AS subtitle_languages, "
            "e.nomenclature_status AS nomenclature_status, e.local_status AS local_status, e.size_bytes AS size_bytes "
            "FROM library_items e JOIN library_items se ON e.parent_id = se.id "
            f"WHERE se.parent_id IN ({placeholders}) AND e.item_type = 'episode'"
            + _specials_clause("se", ignore_specials),
            series_ids,
        ).fetchall()
        for r in rows:
            groups.setdefault(r["gid"], []).append(dict(r))

    result: dict[int, dict] = {}
    for gid, episode_rows in groups.items():
        result[gid] = {
            "nomenclature": _aggregate_nomenclature([r["nomenclature_status"] for r in episode_rows]),
            "size": _aggregate_size([r["size_bytes"] for r in episode_rows]),
            "local_status": _aggregate_local_status([r["local_status"] for r in episode_rows]),
            "quality": _aggregate_quality(episode_rows),
            "path": _aggregate_path(episode_rows),
        }
    return result


def _to_lib_response(row: dict, conn=None, rollups: Optional[dict] = None) -> LibraryItemResponse:
    file_exists_raw = row.get("file_exists")
    nomenclature_status = row["nomenclature_status"]
    local_status = row["local_status"]
    size_bytes = row.get("size_bytes")
    provider = infer_provider_from_item(row)
    resolution = row.get("resolution")
    source = row.get("source")
    path = row.get("path")
    prepared_path = row.get("prepared_path")
    video_codec = row.get("video_codec")
    audio_codec = row.get("audio_codec")
    audio_languages = row.get("audio_languages")
    subtitle_languages = row.get("subtitle_languages")
    if row["item_type"] in ("season", "series"):
        if rollups is not None:
            # library_list() already batched every season/series' rollup in
            # a couple of queries total — reuse it instead of hitting the DB
            # again for this one row (this dict simply won't have an entry
            # for an id with no episodes at all, same as the live helpers
            # below returning None/empty for it).
            precomputed = rollups.get(row["id"], {})
        else:
            ignore_specials = _ignore_specials(conn)
            precomputed = {
                "nomenclature": _nomenclature_rollup(conn, row["id"], row["item_type"], ignore_specials),
                "size": _size_rollup(conn, row["id"], row["item_type"]),
                # Availability now rolls up from real episodes (Sonarr's own
                # status reports 'Disponible' even with missing episodes).
                "local_status": _local_status_rollup(conn, row["id"], row["item_type"], ignore_specials),
                "quality": _child_quality_rollup(conn, row["id"], row["item_type"], ignore_specials),
                "path": _rollup_path(conn, row["id"], row["item_type"], ignore_specials) if not path else None,
            }
        rollup = precomputed.get("nomenclature")
        if rollup is not None:
            nomenclature_status = rollup
        rolled_size = precomputed.get("size")
        if rolled_size is not None:
            size_bytes = rolled_size
        loc = precomputed.get("local_status")
        if loc is not None:
            local_status = loc
        # Provider/quality/codecs/audio/subs: show the value shared by every
        # episode (else blank), so a uniform season/series reflects it.
        rq = precomputed.get("quality") or dict(_ROLLUP_EMPTY)
        provider = provider or rq["provider"]
        resolution = resolution or rq["resolution"]
        source = source or rq["source"]
        video_codec = rq["video_codec"]
        audio_codec = rq["audio_codec"]
        audio_languages = rq["audio_languages"]
        subtitle_languages = rq["subtitle_languages"]
        # A season/series rollup has no file of its own — show its folder path
        # derived from the episodes (e.g. '…/Attack on Titan/Season 2').
        if not path:
            path = precomputed.get("path")
    # Only computed for the single-item detail response (rollups is None) —
    # a per-row parent-walk query for every list row would be wasteful there.
    display_title = None
    if rollups is None and conn is not None:
        display_title = content_display_title(conn, row)
        if row["item_type"] == "episode":
            own_name = episode_own_name(row)
            if own_name:
                display_title = f"{display_title} - {own_name}"
    return LibraryItemResponse(
        id=row["id"],
        item_type=row["item_type"],
        title=row["title"],
        display_title=display_title,
        year=row.get("year"),
        original_title=row.get("original_title"),
        instance_type=row.get("instance_type"),
        instance_name=row.get("instance_name"),
        instance_id=row.get("instance_id"),
        external_id=row.get("external_id"),
        tmdb_id=row.get("tmdb_id"),
        imdb_id=row.get("imdb_id"),
        tvdb_id=row.get("tvdb_id"),
        tvmaze_id=row.get("tvmaze_id"),
        mal_id=row.get("mal_id"),
        title_slug=row.get("title_slug"),
        season_number=row.get("season_number"),
        episode_number=row.get("episode_number"),
        parent_id=row.get("parent_id"),
        path=path,
        prepared_path=prepared_path,
        quality=row.get("quality"),
        resolution=resolution,
        source=source,
        provider=provider,
        provider_label=_provider_label(provider),
        video_codec=video_codec,
        audio_codec=audio_codec,
        audio_languages=audio_languages,
        subtitle_languages=subtitle_languages,
        # Already rolled up and stored per row (recompute_spanish_flags), so
        # unlike the audio_languages above they need no per-row rollup here.
        has_spanish_audio=row.get("has_spanish_audio"),
        has_spanish_subs=row.get("has_spanish_subs"),
        has_spanish_ok=row.get("has_spanish_ok"),
        size_bytes=size_bytes,
        local_status=local_status,
        request_status=row["request_status"],
        nomenclature_status=nomenclature_status,
        updated_at=row.get("updated_at"),
        file_exists=bool(file_exists_raw) if file_exists_raw is not None else None,
        file_verified_at=row.get("file_verified_at"),
        diagnostic_status=row.get("diagnostic_status"),
        diagnostic_summary=row.get("diagnostic_summary"),
        recommended_action=row.get("recommended_action"),
        arr_queue_status=row.get("arr_queue_status"),
        arr_history_status=row.get("arr_history_status"),
        poster_url=row.get("poster_url"),
        backdrop_url=row.get("backdrop_url"),
        emu_in_catalog=row.get("emu_in_catalog"),
        emu_aportes=_parse_aportes(row.get("emu_aportes")),
    )


def _parse_aportes(raw) -> Optional[list]:
    if not raw:
        return None
    import json as _json
    try:
        return _json.loads(raw)
    except (ValueError, TypeError):
        return None


def _to_missing_response(row: dict) -> MissingItemResponse:
    file_exists_raw = row.get("file_exists")
    import json as _json
    try:
        rec_reasons = _json.loads(row.get("recommendation_reasons_json") or "[]")
    except Exception:
        rec_reasons = []
    return MissingItemResponse(
        id=row["id"],
        item_type=row["item_type"],
        title=row["title"],
        year=row.get("year"),
        instance_type=row.get("instance_type"),
        instance_name=row.get("instance_name"),
        tmdb_id=row.get("tmdb_id"),
        imdb_id=row.get("imdb_id"),
        local_status=row["local_status"],
        request_status=row["request_status"],
        updated_at=row.get("updated_at"),
        arr_queue_status=row.get("arr_queue_status"),
        arr_queue_progress=row.get("arr_queue_progress"),
        arr_queue_timeleft=row.get("arr_queue_timeleft"),
        arr_queue_error=row.get("arr_queue_error"),
        arr_history_error=row.get("arr_history_error"),
        file_exists=bool(file_exists_raw) if file_exists_raw is not None else None,
        diagnostic_status=row.get("diagnostic_status"),
        recommended_action=row.get("recommended_action"),
        recommendation_reasons=rec_reasons,
    )


# ---------------------------------------------------------------------------
# POST /api/sync — sync all instances
# ---------------------------------------------------------------------------

@router.post("/library/sync-start")
def library_sync_start(
    body: Optional[SyncRequest] = None,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Start the Radarr/Sonarr library sync in the background (poll
    /library/sync-progress for the live element count)."""
    from emuwarez_uploadrr.services.library import start_library_sync_background
    include_episodes = body.include_episodes if body else True
    return start_library_sync_background(include_episodes=include_episodes)


@router.get("/library/sync-progress")
def library_sync_progress(current_user: dict = Depends(require_auth)) -> dict:
    """Live progress of the Radarr/Sonarr library sync, for the process card."""
    from emuwarez_uploadrr.services.library import get_lib_sync_progress
    return get_lib_sync_progress()


@router.post("/sync", response_model=SyncResponse)
def sync_all(
    body: Optional[SyncRequest] = None,
    current_user: dict = Depends(require_auth),
) -> SyncResponse:
    from emuwarez_uploadrr.services.library import SyncAlreadyRunning, _lib_sync_guard
    from emuwarez_uploadrr.services.library import sync_all as _sync_all
    include_episodes = body.include_episodes if body else True
    with _get_conn() as conn:
        try:
            with _lib_sync_guard():
                result = _sync_all(conn, include_episodes=include_episodes)
        except SyncAlreadyRunning:
            raise HTTPException(status_code=429, detail="Ya hay una sincronización de biblioteca en marcha")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error en sync: {exc}")
    return SyncResponse(
        imported=result.get("imported", 0),
        missing=result.get("missing", 0),
        instances=result.get("instances", 0),
        errors=result.get("errors", []),
        message=(
            f"Sincronizadas {result.get('instances', 0)} instancias: "
            f"{result.get('imported', 0)} elementos, {result.get('missing', 0)} no disponibles"
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/library
# ---------------------------------------------------------------------------

@router.get("/library", response_model=LibraryListResponse)
def library_list(
    current_user: dict = Depends(require_auth),
    item_type: Optional[str] = Query(None, alias="type"),
    origin: Optional[str] = Query(None),
    instance_id: Optional[int] = Query(None),
    parent_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    request_status: Optional[str] = Query(None, alias="request_status"),
    nomenclature: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    spanish: Optional[str] = Query(None, pattern="^(yes|no|unknown)$"),
    sort: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=20000),
    offset: int = Query(0, ge=0),
) -> LibraryListResponse:
    from emuwarez_uploadrr.services.library import list_library, count_library
    with _get_conn() as conn:
        rows = list_library(
            conn,
            status=status,
            request=request_status,
            nomenclature=nomenclature,
            item_type=item_type,
            origin=origin,
            instance_id=instance_id,
            parent_id=parent_id,
            search=search,
            spanish=spanish,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        total = count_library(
            conn,
            status=status,
            request=request_status,
            nomenclature=nomenclature,
            item_type=item_type,
            origin=origin,
            instance_id=instance_id,
            parent_id=parent_id,
            search=search,
            spanish=spanish,
        )
        series_ids = [r["id"] for r in rows if r["item_type"] == "series"]
        season_ids = [r["id"] for r in rows if r["item_type"] == "season"]
        rollups = (
            _batch_rollups(conn, series_ids, season_ids, _ignore_specials(conn))
            if (series_ids or season_ids) else {}
        )
        items = [_to_lib_response(r, conn, rollups) for r in rows]
    return LibraryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/library/{item_id}
# ---------------------------------------------------------------------------

@router.get("/library/filter-options")
def library_filter_options(current_user: dict = Depends(require_auth)) -> dict:
    """Distinct values actually present anywhere in the library (all levels),
    for every Biblioteca column filter dropdown — Excel-style: a filter only
    ever offers values that really occur in the data, never an invented fixed
    list (e.g. LocalStatus has ~10 possible values, but only the ones some
    item actually has should show up; a value that only appears in the
    episodes of a mixed-provider/quality series would otherwise be missing
    too). Defined before /library/{item_id} so it isn't captured as an item id."""
    import json as _json

    with _get_conn() as conn:
        qrows = conn.execute(
            "SELECT DISTINCT resolution, source FROM library_items "
            "WHERE resolution IS NOT NULL OR source IS NOT NULL"
        ).fetchall()
        # Order by real quality: resolution first (higher → better), then source.
        _RES_RANK = {"4320p": 8, "2160p": 7, "1080p": 6, "1080i": 5, "720p": 4, "576p": 3, "540p": 2, "480p": 1}
        _SRC_RANK = {"BDRemux": 6, "Remux": 6, "BluRay": 5, "WEB-DL": 4, "WEBRip": 3, "HDTV": 2, "DVD": 1}
        # Calidad and Source are now their own table columns/filters (see
        # Biblioteca's list view) — each needs its own distinct-values list
        # instead of the old single "resolution · source" combined string.
        resolutions = {r["resolution"] for r in qrows if r["resolution"]}
        sources_seen = {r["source"] for r in qrows if r["source"]}
        qualities = sorted(resolutions, key=lambda r: _RES_RANK.get(r, 0), reverse=True)
        sources = sorted(sources_seen, key=lambda s: _SRC_RANK.get(s, 0), reverse=True)
        prows = conn.execute(
            "SELECT path, source FROM library_items "
            "WHERE item_type IN ('movie', 'episode') AND path IS NOT NULL"
        ).fetchall()
        codes = set()
        for r in prows:
            c = infer_provider_from_item({"path": r["path"], "source": r["source"]})
            if c:
                codes.add(c)
        providers = sorted({lbl for c in codes if (lbl := _provider_label(c))})

        types = [r[0] for r in conn.execute(
            "SELECT DISTINCT item_type FROM library_items WHERE item_type IS NOT NULL ORDER BY item_type"
        ).fetchall()]
        statuses = [r[0] for r in conn.execute(
            "SELECT DISTINCT local_status FROM library_items WHERE local_status IS NOT NULL ORDER BY local_status"
        ).fetchall()]
        request_statuses = [r[0] for r in conn.execute(
            "SELECT DISTINCT request_status FROM library_items WHERE request_status IS NOT NULL ORDER BY request_status"
        ).fetchall()]
        nomenclature_statuses = [r[0] for r in conn.execute(
            "SELECT DISTINCT nomenclature_status FROM library_items WHERE nomenclature_status IS NOT NULL ORDER BY nomenclature_status"
        ).fetchall()]
        instances = [
            {"id": r["id"], "type": r["type"], "name": r["name"]}
            for r in conn.execute(
                "SELECT DISTINCT i.id, i.type, i.name FROM instances i "
                "WHERE EXISTS (SELECT 1 FROM library_items li WHERE li.instance_id = i.id) "
                "ORDER BY i.name"
            ).fetchall()
        ]

        # emu_in_catalog/emu_aportes only get computed by the (throttled)
        # eMuwarez catalog sync — read once and derive both which "¿En
        # eMuwarez?" values and which "Aportes" values actually occur, rather
        # than always offering both fixed options regardless of whether any
        # item currently has them.
        emu_rows = conn.execute("SELECT emu_in_catalog, emu_aportes FROM library_items").fetchall()
        has_candidate = has_present = has_aporte_yes = has_aporte_no = False
        for r in emu_rows:
            ic = r["emu_in_catalog"]
            if ic == 0:
                has_candidate = True
                has_aporte_yes = True
            elif ic == 1:
                has_present = True
                try:
                    aportes = _json.loads(r["emu_aportes"]) if r["emu_aportes"] else []
                except (TypeError, ValueError):
                    aportes = []
                if aportes:
                    has_aporte_yes = True
                else:
                    has_aporte_no = True
        emu_states = [v for v, present in [("candidate", has_candidate), ("present", has_present)] if present]
        aporte_states = [v for v, present in [("yes", has_aporte_yes), ("no", has_aporte_no)] if present]

        # Same "only offer what actually occurs" rule for the Español column.
        # "unknown" is offered too: on a library that has never been scanned
        # it's the only value there is, and hiding it would leave the filter
        # with nothing to pick.
        seen_spanish = {r[0] for r in conn.execute(
            "SELECT DISTINCT has_spanish_audio FROM library_items"
        ).fetchall()}
        spanish_states = [
            v for v, present in [
                ("yes", 1 in seen_spanish), ("no", 0 in seen_spanish), ("unknown", None in seen_spanish),
            ] if present
        ]

    return {
        "providers": providers,
        "qualities": qualities,
        "sources": sources,
        "types": types,
        "statuses": statuses,
        "request_statuses": request_statuses,
        "nomenclature_statuses": nomenclature_statuses,
        "instances": instances,
        "emu_states": emu_states,
        "aporte_states": aporte_states,
        "spanish_states": spanish_states,
    }


@router.get("/library/emu-sync-status")
def library_emu_sync_status(current_user: dict = Depends(require_auth)) -> dict:
    """Throttle status for the eMuwarez catalog comparison (1/hour)."""
    from emuwarez_uploadrr.services.emu_catalog import get_sync_status
    with _get_conn() as conn:
        return get_sync_status(conn)


@router.post("/library/emu-sync")
def library_emu_sync(mode: str = "incremental", current_user: dict = Depends(require_auth)) -> dict:
    """Start the eMuwarez catalog sync in the background (poll emu-sync-progress
    for the live status). Throttled 1/hour. mode="incremental" (only new
    torrents) or "full" (re-download the whole catalog and reconcile deletions)."""
    from emuwarez_uploadrr.services.emu_catalog import start_emu_sync_background
    mode = "full" if mode == "full" else "incremental"
    result = start_emu_sync_background(mode=mode)
    if result.get("status") == "throttled":
        raise HTTPException(
            status_code=429,
            detail=f"Espera {result['wait_seconds']}s antes de volver a sincronizar con eMuwarez",
        )
    return result


@router.get("/library/emu-sync-progress")
def library_emu_sync_progress(current_user: dict = Depends(require_auth)) -> dict:
    """Live progress of the eMuwarez catalog sync, for the process card."""
    from emuwarez_uploadrr.services.emu_catalog import get_sync_progress
    return get_sync_progress()


@router.get("/library/{item_id}/emu-comparison")
def library_emu_comparison(item_id: int, current_user: dict = Depends(require_auth)) -> dict:
    """Your copy vs eMuwarez's matching torrents, for the detail-card table."""
    from emuwarez_uploadrr.services.emu_catalog import get_item_comparison
    with _get_conn() as conn:
        return get_item_comparison(conn, item_id)


@router.get("/library/{item_id}", response_model=LibraryItemResponse)
def library_detail(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> LibraryItemResponse:
    from emuwarez_uploadrr.services.library import get_library_item
    with _get_conn() as conn:
        row = get_library_item(conn, item_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        from emuwarez_uploadrr.services.library import rollup_all_values
        response = _to_lib_response(row, conn)
        # Solo en la ficha: la lista no lo necesita y son una consulta por fila.
        response.rollup_all = rollup_all_values(conn, row)
        return response


@router.get("/library/{item_id}/mediainfo")
def library_mediainfo(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Run MediaInfo on demand for a single item and return, per field, the raw
    MediaInfo value and the value that would go to eMuwarez."""
    from emuwarez_uploadrr.services.library import get_library_item
    from emuwarez_uploadrr.services.media_info_service import build_mediainfo_report

    with _get_conn() as conn:
        row = get_library_item(conn, item_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        path = row["path"] if "path" in row.keys() else None
        radarr_source = row["source"] if "source" in row.keys() else None
    return build_mediainfo_report(path, radarr_source=radarr_source)


@router.get("/library/{item_id}/nomenclature-check")
def library_nomenclature_info(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Info for the 'Comprobar Nomenclatura' confirmation + stored result.

    Returns {item_type, status, pending, available, seasons, result} where
    `result` (only for a checked leaf) is {status, expected, actual, diff} for
    the 'Ver resultados' view. `pending`/`available`/`seasons` drive the
    confirmation message (¿Comprobar N capítulos? / N temporadas con X...)."""
    from emuwarez_uploadrr.services.nomenclature_check import count_pending, compare
    from emuwarez_uploadrr.services.mkv_title import to_filesystem_name
    from emuwarez_uploadrr.services.source_assistant import _get_default_tag

    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        item = dict(row)
        item_type = item.get("item_type")
        pending, available, seasons = count_pending(conn, item_id, item_type)
        result = None
        expected = item.get("nomenclature_expected")
        path = item.get("path")
        if item_type in ("movie", "episode") and expected and path:
            base = os.path.basename(path)
            matches, diff = compare(base, expected)
            # Show the user's configured group tag in the expected name (it is
            # NOT part of the comparison — the group is always ignored).
            tag = _get_default_tag(conn)
            expected_display = f"{expected}-{tag}" if tag else expected
            result = {
                "status": item.get("nomenclature_status"),
                "expected": expected_display,
                "actual": to_filesystem_name(os.path.splitext(base)[0]),
                "diff": diff,
            }
        return {
            "item_type": item_type,
            "status": item.get("nomenclature_status"),
            "pending": pending,
            "available": available,
            "seasons": seasons,
            "result": result,
        }


@router.post("/library/{item_id}/nomenclature-check")
def library_nomenclature_check(
    item_id: int,
    force: bool = Query(False),
    current_user: dict = Depends(require_auth),
) -> dict:
    """Run the MediaInfo-based nomenclature check on a leaf/season/series.
    Only DISPONIBLE + 'No comprobada' files are checked unless force=True.
    Returns {checked, correct, not_adapted, results}."""
    from emuwarez_uploadrr.services.nomenclature_check import check_item

    with _get_conn() as conn:
        result = check_item(conn, item_id, force=force)
        if result.get("error") == "not found":
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        return result


@router.get("/library/{item_id}/suggest-provider")
def library_suggest_provider(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Suggest the EMU provider for a WEB-DL item via TMDb watch providers +
    the configured priority. This is the on-demand call the upload wizard makes
    when Source=WEB-DL and no provider was detected from the filename.

    Returns {suggested, tmdb_providers, reason}. Never raises on TMDb issues —
    a missing/invalid TMDb key just yields suggested=None."""
    from emuwarez_uploadrr.services.library import get_library_item
    from emuwarez_uploadrr.services.source_assistant import suggest_provider_for_item

    with _get_conn() as conn:
        row = get_library_item(conn, item_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        return suggest_provider_for_item(item_id, conn=conn)


# ---------------------------------------------------------------------------
# GET /api/missing
# ---------------------------------------------------------------------------

@router.get("/missing", response_model=MissingListResponse)
def missing_list(
    current_user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=20000),
    offset: int = Query(0, ge=0),
) -> MissingListResponse:
    from emuwarez_uploadrr.services.library import list_missing, count_library
    from emuwarez_uploadrr.models import LocalStatus
    with _get_conn() as conn:
        rows = list_missing(conn, limit=limit, offset=offset)
    return MissingListResponse(
        items=[_to_missing_response(r) for r in rows],
        total=len(rows),
        limit=limit,
        offset=offset,
    )
