"""Real /api/requests endpoints (Phase 5B)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    OkResponse,
    RequestDetailResponse,
    RequestItemResponse,
    RequestListResponse,
    RequestMatchResponse,
    RequestSyncBody,
    RequestSyncResponse,
    RequestSyncStatusResponse,
)

router = APIRouter(prefix="/requests", tags=["requests"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _row_to_item(r: dict, my_username: str | None = None) -> RequestItemResponse:
    author = r.get("author")
    is_mine = bool(
        my_username and author
        and author.strip().lower() == my_username.strip().lower()
    )
    return RequestItemResponse(
        id=r["id"],
        emu_id=r["emu_id"],
        title=r["title"],
        is_example=bool(r.get("is_example")),
        category=r.get("category"),
        requested_source=r.get("requested_source"),
        requested_resolution=r.get("requested_resolution"),
        emu_status=r.get("emu_status"),
        points=r.get("points"),
        comments=r.get("comments"),
        votes=r.get("votes"),
        author=author,
        is_mine=is_mine,
        req_scope=r.get("req_scope"),
        req_season=r.get("req_season"),
        req_episode=r.get("req_episode"),
        created_at=r.get("created_at"),
        tmdb_id=r.get("tmdb_id"),
        imdb_id=r.get("imdb_id"),
        tvdb_id=r.get("tvdb_id"),
        mal_id=r.get("mal_id"),
        url=r.get("url"),
        compatibility_status=r.get("compatibility_status"),
        compatibility_confidence=r.get("compatibility_confidence"),
        library_item_id=r.get("library_item_id"),
        library_title=r.get("library_title"),
        library_year=r.get("library_year"),
        instance_type=r.get("instance_type"),
        instance_name=r.get("instance_name"),
        instance_id=r.get("instance_id"),
        title_slug=r.get("title_slug"),
        library_tmdb_id=r.get("library_tmdb_id"),
        display_title=r.get("display_title"),
        local_status=r.get("local_status"),
        poster_url=r.get("poster_url"),
        backdrop_url=r.get("backdrop_url"),
        reviewed_at=r.get("reviewed_at"),
        updated_at=r.get("updated_at"),
        # Phase 8B readiness fields
        readiness_status=r.get("readiness_status"),
        readiness_action=r.get("readiness_action"),
        readiness_best_library_item_id=r.get("readiness_best_library_item_id"),
    )


def _match_dict_to_response(match_data: dict | None) -> RequestMatchResponse | None:
    if not match_data:
        return None
    return RequestMatchResponse(
        id=match_data["id"],
        library_item_id=match_data.get("library_item_id"),
        library_target_id=match_data.get("library_target_id"),
        library_title=match_data.get("library_title"),
        local_status=match_data.get("local_status"),
        local_resolution=match_data.get("local_resolution"),
        local_source=match_data.get("local_source"),
        local_video_codec=match_data.get("local_video_codec"),
        local_audio_languages=match_data.get("local_audio_languages"),
        local_size=match_data.get("local_size"),
        local_tmdb_id=match_data.get("local_tmdb_id"),
        local_imdb_id=match_data.get("local_imdb_id"),
        local_tvdb_id=match_data.get("local_tvdb_id"),
        local_mal_id=match_data.get("local_mal_id"),
        local_path=match_data.get("local_path"),
        content_name=match_data.get("content_name"),
        nomenclature_status=match_data.get("nomenclature_status"),
        status=match_data["status"],
        confidence=float(match_data["confidence"]),
        resolution_match=match_data.get("resolution_match"),
        source_match=match_data.get("source_match"),
        id_match=bool(match_data.get("id_match")),
        reasons=match_data.get("reasons") or [],
    )


@router.get("", response_model=RequestListResponse)
def list_requests(
    search: str | None = Query(None),
    status: str | None = Query(None),
    category: str | None = Query(None),
    resolution: str | None = Query(None),
    source: str | None = Query(None),
    author: str | None = Query(None),
    emu_status: str | None = Query(None),
    sort: str | None = Query(None),
    limit: int = Query(50, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_auth),
) -> RequestListResponse:
    from emuwarez_uploadrr.services.requests import list_request_items
    from emuwarez_uploadrr.web.services.settings_service import get_setting
    with _get_conn() as conn:
        my_username = get_setting(conn, "emu.username")
        result = list_request_items(
            conn, limit=limit, offset=offset, search=search, status=status,
            category=category, resolution=resolution, source=source,
            author=author, emu_status=emu_status, sort=sort,
        )
    return RequestListResponse(
        items=[_row_to_item(r, my_username) for r in result["items"]],
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
    )


@router.get("/sync-status", response_model=RequestSyncStatusResponse)
def get_sync_status(current_user: dict = Depends(require_auth)) -> RequestSyncStatusResponse:
    from emuwarez_uploadrr.services.requests import get_request_sync_status
    with _get_conn() as conn:
        status = get_request_sync_status(conn)
    return RequestSyncStatusResponse(**status)


@router.post("/sync", response_model=RequestSyncResponse)
def sync_requests(
    body: RequestSyncBody = RequestSyncBody(),
    current_user: dict = Depends(require_auth),
) -> RequestSyncResponse:
    from emuwarez_uploadrr.services.requests import sync_emu_requests
    from emuwarez_uploadrr.integrations.base import IntegrationError
    with _get_conn() as conn:
        try:
            result = sync_emu_requests(conn, force=body.force)
        except IntegrationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.get("status") == "throttled":
        wait = int(result.get("wait_seconds", 0))
        mins = wait // 60
        secs = wait % 60
        return RequestSyncResponse(
            ok=False,
            status="throttled",
            wait_seconds=wait,
            message=f"Peticiones actualizadas recientemente. Disponible en {mins}m {secs}s.",
        )
    if result.get("status") == "unavailable":
        return RequestSyncResponse(
            ok=False,
            status="unavailable",
            message=str(result.get("message") or "Sincronización de peticiones no disponible."),
        )
    return RequestSyncResponse(
        ok=True,
        status="ok",
        imported=int(result.get("imported", 0)),
        matched=int(result.get("matched", 0)),
        message=(
            f"{result.get('imported', 0)} peticiones importadas, "
            f"{result.get('matched', 0)} cruces actualizados."
        ),
    )


# --- Demo requests (TEMPORARY) ---------------------------------------------
# Goes away with the real eMuwarez requests endpoint; see
# services/request_examples.py. Declared BEFORE /{request_id} so "examples"
# isn't swallowed as a request id.

@router.get("/examples")
def get_examples_status(current_user: dict = Depends(require_auth)) -> dict:
    """How many demo requests exist. The Generar button derives its disabled
    state from THIS, not from frontend state — otherwise reloading the page
    would re-enable it and you'd end up with several rounds of them."""
    from emuwarez_uploadrr.services.request_examples import count_examples
    with _get_conn() as conn:
        return {"count": count_examples(conn)}


@router.post("/examples")
def create_examples(current_user: dict = Depends(require_auth)) -> dict:
    from emuwarez_uploadrr.services.request_examples import generate_examples
    with _get_conn() as conn:
        result = generate_examples(conn)
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@router.delete("/examples")
def remove_examples(current_user: dict = Depends(require_auth)) -> dict:
    from emuwarez_uploadrr.services.request_examples import delete_examples
    with _get_conn() as conn:
        return {"deleted": delete_examples(conn)}


@router.get("/{request_id}", response_model=RequestDetailResponse)
def get_request_detail(
    request_id: int,
    current_user: dict = Depends(require_auth),
) -> RequestDetailResponse:
    from emuwarez_uploadrr.services.requests import get_request_detail as _svc_detail
    from emuwarez_uploadrr.web.services.settings_service import get_setting
    with _get_conn() as conn:
        my_username = get_setting(conn, "emu.username")
        data = _svc_detail(conn, request_id)
    if not data:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    match_data = data.pop("match", None)
    return RequestDetailResponse(**_row_to_item(data, my_username).model_dump(), match=_match_dict_to_response(match_data))


@router.post("/{request_id}/match", response_model=RequestDetailResponse)
def rematch_request(
    request_id: int,
    current_user: dict = Depends(require_auth),
) -> RequestDetailResponse:
    from emuwarez_uploadrr.services.requests import match_single_request, get_request_detail as _svc_detail
    from emuwarez_uploadrr.web.services.settings_service import get_setting
    with _get_conn() as conn:
        my_username = get_setting(conn, "emu.username")
        match_single_request(conn, request_id)
        data = _svc_detail(conn, request_id)
    if not data:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    match_data = data.pop("match", None)
    return RequestDetailResponse(**_row_to_item(data, my_username).model_dump(), match=_match_dict_to_response(match_data))


@router.post("/{request_id}/mark-reviewed", response_model=OkResponse)
def mark_reviewed(
    request_id: int,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from emuwarez_uploadrr.services.requests import mark_request_reviewed
    with _get_conn() as conn:
        found = mark_request_reviewed(conn, request_id)
    if not found:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    return OkResponse(ok=True, message=f"Petición {request_id} marcada como revisada")
