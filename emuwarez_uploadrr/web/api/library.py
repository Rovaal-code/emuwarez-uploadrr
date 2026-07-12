"""Real library, missing, and sync endpoints (Phase 4)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from emuwarez_uploadrr.services.nomenclature import infer_provider_from_item
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
    total = sum(counts.values())
    if total == 0:
        return None
    correct = counts.get("Correcta", 0)
    not_adapted = counts.get("No adaptada", 0)
    # Correcta only when *every* episode is Correcta (N/A/missing counts against).
    if correct == total:
        return "Correcta"
    if correct == 0:
        # None adapted: N/A if there's simply nothing to adapt, else No adaptada.
        return "No adaptada" if not_adapted else "N/A"
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


def _to_lib_response(row: dict, conn=None) -> LibraryItemResponse:
    file_exists_raw = row.get("file_exists")
    nomenclature_status = row["nomenclature_status"]
    local_status = row["local_status"]
    size_bytes = row.get("size_bytes")
    provider = infer_provider_from_item(row)
    resolution = row.get("resolution")
    source = row.get("source")
    video_codec = row.get("video_codec")
    audio_codec = row.get("audio_codec")
    audio_languages = row.get("audio_languages")
    subtitle_languages = row.get("subtitle_languages")
    if row["item_type"] in ("season", "series"):
        ignore_specials = _ignore_specials(conn)
        rollup = _nomenclature_rollup(conn, row["id"], row["item_type"], ignore_specials)
        if rollup is not None:
            nomenclature_status = rollup
        rolled_size = _size_rollup(conn, row["id"], row["item_type"])
        if rolled_size is not None:
            size_bytes = rolled_size
        # Availability now rolls up from real episodes (Sonarr's own status
        # reports 'Disponible' even with missing episodes) — for both seasons
        # and series.
        loc = _local_status_rollup(conn, row["id"], row["item_type"], ignore_specials)
        if loc is not None:
            local_status = loc
        # Provider/quality/codecs/audio/subs: show the value shared by every
        # episode (else blank), so a uniform season/series reflects it.
        rq = _child_quality_rollup(conn, row["id"], row["item_type"], ignore_specials)
        provider = provider or rq["provider"]
        resolution = resolution or rq["resolution"]
        source = source or rq["source"]
        video_codec = rq["video_codec"]
        audio_codec = rq["audio_codec"]
        audio_languages = rq["audio_languages"]
        subtitle_languages = rq["subtitle_languages"]
    return LibraryItemResponse(
        id=row["id"],
        item_type=row["item_type"],
        title=row["title"],
        year=row.get("year"),
        original_title=row.get("original_title"),
        instance_type=row.get("instance_type"),
        instance_name=row.get("instance_name"),
        instance_id=row.get("instance_id"),
        external_id=row.get("external_id"),
        tmdb_id=row.get("tmdb_id"),
        imdb_id=row.get("imdb_id"),
        tvdb_id=row.get("tvdb_id"),
        title_slug=row.get("title_slug"),
        season_number=row.get("season_number"),
        episode_number=row.get("episode_number"),
        parent_id=row.get("parent_id"),
        path=row.get("path"),
        quality=row.get("quality"),
        resolution=resolution,
        source=source,
        provider=provider,
        provider_label=_provider_label(provider),
        video_codec=video_codec,
        audio_codec=audio_codec,
        audio_languages=audio_languages,
        subtitle_languages=subtitle_languages,
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

@router.post("/sync", response_model=SyncResponse)
def sync_all(
    body: Optional[SyncRequest] = None,
    current_user: dict = Depends(require_auth),
) -> SyncResponse:
    from emuwarez_uploadrr.services.library import sync_all as _sync_all
    include_episodes = body.include_episodes if body else True
    with _get_conn() as conn:
        try:
            result = _sync_all(conn, include_episodes=include_episodes)
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
        )
        items = [_to_lib_response(r, conn) for r in rows]
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
    """Distinct providers and qualities present anywhere in the library (all
    levels), for the Biblioteca filter dropdowns — otherwise a value that only
    appears in the episodes of a mixed-provider/quality series would be missing
    from the options. Defined before /library/{item_id} so it isn't captured
    as an item id."""
    with _get_conn() as conn:
        qrows = conn.execute(
            "SELECT DISTINCT resolution, source FROM library_items "
            "WHERE resolution IS NOT NULL OR source IS NOT NULL"
        ).fetchall()
        seen = {
            (r["resolution"], r["source"])
            for r in qrows
            if (r["resolution"] or r["source"])
        }
        # Order by real quality: resolution first (higher → better), then source.
        _RES_RANK = {"4320p": 8, "2160p": 7, "1080p": 6, "1080i": 5, "720p": 4, "576p": 3, "540p": 2, "480p": 1}
        _SRC_RANK = {"BDRemux": 6, "Remux": 6, "BluRay": 5, "WEB-DL": 4, "WEBRip": 3, "HDTV": 2, "DVD": 1}
        qualities = [
            " · ".join([x for x in (res, src) if x])
            for res, src in sorted(seen, key=lambda p: (_RES_RANK.get(p[0], 0), _SRC_RANK.get(p[1], 0)), reverse=True)
        ]
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
    return {"providers": providers, "qualities": qualities}


@router.get("/library/emu-sync-status")
def library_emu_sync_status(current_user: dict = Depends(require_auth)) -> dict:
    """Throttle status for the eMuwarez catalog comparison (1/hour)."""
    from emuwarez_uploadrr.services.emu_catalog import get_sync_status
    with _get_conn() as conn:
        return get_sync_status(conn)


@router.post("/library/emu-sync")
def library_emu_sync(current_user: dict = Depends(require_auth)) -> dict:
    """Download the whole eMuwarez catalog and recompute, per movie/season/series,
    whether it's already there and what your copy would add. Throttled 1/hour."""
    from emuwarez_uploadrr.services.emu_catalog import sync_emu_catalog
    from emuwarez_uploadrr.integrations.base import IntegrationError
    with _get_conn() as conn:
        try:
            result = sync_emu_catalog(conn)
        except IntegrationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    if result.get("status") == "throttled":
        raise HTTPException(
            status_code=429,
            detail=f"Espera {result['wait_seconds']}s antes de volver a sincronizar con eMuwarez",
        )
    return result


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
        return _to_lib_response(row, conn)


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
    return build_mediainfo_report(path)


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
