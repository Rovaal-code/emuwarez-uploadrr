"""Real library, missing, and sync endpoints (Phase 4)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from emuwarez_uploadrr.services.nomenclature import infer_provider_from_item
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


def _nomenclature_rollup(conn, item_id: int, item_type: str) -> Optional[str]:
    """Aggregate the nomenclature status of a Season (from its episodes) or a
    Series (from all its episodes). Only counts episodes that have a real
    nomenclature state (Correcta / No adaptada) — missing episodes (N/A) are
    ignored. Returns:
      - 'Correcta'    when every counted episode is adapted,
      - 'No adaptada' when none is,
      - 'Parcial'     when some are and some aren't,
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
            "WHERE se.parent_id = ? AND e.item_type = 'episode' GROUP BY e.nomenclature_status"
        )
    else:
        return None
    counts = {r["s"]: r["c"] for r in conn.execute(sql, (item_id,)).fetchall()}
    correct = counts.get("Correcta", 0)
    not_adapted = counts.get("No adaptada", 0)
    relevant = correct + not_adapted
    if relevant == 0:
        return None
    if not_adapted == 0:
        return "Correcta"
    if correct == 0:
        return "No adaptada"
    return "Parcial"


def _local_status_rollup(conn, item_id: int) -> Optional[str]:
    """Availability of a Series aggregated from its seasons (excluding specials,
    season 0): 'Disponible' only when every season is available, 'Faltante' when
    none is, 'Parcial' otherwise. Sonarr's own series status counts only
    monitored/aired episodes, so a series with a downloaded season and other
    missing seasons wrongly shows 'Disponible' — this fixes that."""
    if conn is None:
        return None
    counts = {
        r["s"]: r["c"] for r in conn.execute(
            "SELECT local_status AS s, COUNT(*) AS c FROM library_items "
            "WHERE parent_id = ? AND item_type = 'season' "
            "AND (season_number IS NULL OR season_number != 0) GROUP BY local_status",
            (item_id,),
        ).fetchall()
    }
    total = sum(counts.values())
    if total == 0:
        return None
    available = counts.get("Disponible", 0)
    partial = counts.get("Parcial", 0)
    if available == total:
        return "Disponible"
    if available == 0 and partial == 0:
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


def _to_lib_response(row: dict, conn=None) -> LibraryItemResponse:
    file_exists_raw = row.get("file_exists")
    nomenclature_status = row["nomenclature_status"]
    local_status = row["local_status"]
    size_bytes = row.get("size_bytes")
    if row["item_type"] in ("season", "series"):
        rollup = _nomenclature_rollup(conn, row["id"], row["item_type"])
        if rollup is not None:
            nomenclature_status = rollup
        rolled_size = _size_rollup(conn, row["id"], row["item_type"])
        if rolled_size is not None:
            size_bytes = rolled_size
    if row["item_type"] == "series":
        loc = _local_status_rollup(conn, row["id"])
        if loc is not None:
            local_status = loc
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
        resolution=row.get("resolution"),
        source=row.get("source"),
        provider=infer_provider_from_item(row),
        video_codec=row.get("video_codec"),
        audio_codec=row.get("audio_codec"),
        audio_languages=row.get("audio_languages"),
        subtitle_languages=row.get("subtitle_languages"),
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
    )


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
