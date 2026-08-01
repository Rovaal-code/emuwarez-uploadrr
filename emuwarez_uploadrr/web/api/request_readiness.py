"""Phase 8B — Request readiness and prioritization endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    OkResponse,
    RequestReadinessResponse,
    RequestReadinessListResponse,
    RequestCandidateResponse,
    RequestReadinessRefreshBody,
    RequestReadinessEvaluateResponse,
)

router = APIRouter(tags=["request_readiness"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _rr_to_response(r: dict) -> RequestReadinessResponse:
    return RequestReadinessResponse(
        id=r.get("id", 0),
        request_item_id=r["request_item_id"],
        title=r.get("title"),
        emu_id=r.get("emu_id"),
        best_library_item_id=r.get("best_library_item_id"),
        status=r["status"],
        recommended_action=r.get("recommended_action"),
        compatibility_score=r.get("compatibility_score"),
        upload_readiness_score=r.get("upload_readiness_score"),
        blockers=r.get("blockers") or [],
        reasons=r.get("reasons") or [],
        candidate_summary=r.get("candidate_summary") or [],
        last_evaluated_at=r.get("last_evaluated_at"),
        updated_at=r.get("updated_at"),
    )


def _candidate_to_response(c: dict) -> RequestCandidateResponse:
    return RequestCandidateResponse(
        id=c.get("id", 0),
        request_item_id=c["request_item_id"],
        library_item_id=c["library_item_id"],
        candidate_rank=c.get("candidate_rank", 0),
        match_status=c.get("match_status", ""),
        match_score=c.get("match_score"),
        compatibility_status=c.get("compatibility_status"),
        compatibility_score=c.get("compatibility_score"),
        readiness_status=c.get("readiness_status"),
        readiness_score=c.get("readiness_score"),
        blockers=c.get("blockers") or [],
        reasons=c.get("reasons") or [],
        lib_title=c.get("lib_title"),
        local_status=c.get("local_status"),
        resolution=c.get("resolution"),
        source=c.get("source"),
    )


# ---------------------------------------------------------------------------
# POST /api/requests/readiness/refresh
# ---------------------------------------------------------------------------

@router.post("/requests/readiness/refresh", response_model=OkResponse)
def refresh_readiness(
    body: RequestReadinessRefreshBody = RequestReadinessRefreshBody(),
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from emuwarez_uploadrr.services.request_readiness import refresh_request_readiness
    with _get_conn() as conn:
        result = refresh_request_readiness(conn, limit=body.limit)
    return OkResponse(
        ok=True,
        message=f"Readiness recalculado: {result['items_updated']} peticiones, {result['errors']} errores",
    )


# ---------------------------------------------------------------------------
# GET /api/requests/readiness
# ---------------------------------------------------------------------------

@router.get("/requests/readiness", response_model=RequestReadinessListResponse)
def list_readiness(
    status: str | None = Query(None),
    action: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_auth),
) -> RequestReadinessListResponse:
    from emuwarez_uploadrr.services.request_readiness import list_request_readiness
    filters = {k: v for k, v in {
        "status": status, "action": action, "search": search,
    }.items() if v is not None}
    with _get_conn() as conn:
        items = list_request_readiness(conn, filters=filters, limit=limit, offset=offset)
    return RequestReadinessListResponse(
        items=[_rr_to_response(i) for i in items],
        total=len(items),
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/requests/{id}/readiness
# ---------------------------------------------------------------------------

@router.get("/requests/{request_id}/readiness", response_model=RequestReadinessResponse)
def get_readiness(
    request_id: int,
    current_user: dict = Depends(require_auth),
) -> RequestReadinessResponse:
    from emuwarez_uploadrr.services.request_readiness import get_request_readiness
    with _get_conn() as conn:
        data = get_request_readiness(request_id, conn)
    if not data:
        raise HTTPException(status_code=404, detail="Readiness no calculado para esta petición")
    return _rr_to_response(data)


# ---------------------------------------------------------------------------
# POST /api/requests/{id}/readiness/evaluate
# ---------------------------------------------------------------------------

@router.post("/requests/{request_id}/readiness/evaluate", response_model=RequestReadinessEvaluateResponse)
def evaluate_readiness(
    request_id: int,
    current_user: dict = Depends(require_auth),
) -> RequestReadinessEvaluateResponse:
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    with _get_conn() as conn:
        result = evaluate_request_readiness(request_id, conn)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "No encontrada"))
    return RequestReadinessEvaluateResponse(
        ok=True,
        request_item_id=result["request_item_id"],
        title=result.get("title"),
        status=result["status"],
        recommended_action=result.get("recommended_action"),
        compatibility_score=result.get("compatibility_score"),
        upload_readiness_score=result.get("upload_readiness_score"),
        best_library_item_id=result.get("best_library_item_id"),
        blockers=result.get("blockers", []),
        reasons=result.get("reasons", []),
        candidates_count=result.get("candidates_count", 0),
    )


# ---------------------------------------------------------------------------
# GET /api/requests/{id}/candidates
# ---------------------------------------------------------------------------

@router.get("/requests/{request_id}/candidates", response_model=list[RequestCandidateResponse])
def list_candidates(
    request_id: int,
    current_user: dict = Depends(require_auth),
) -> list[RequestCandidateResponse]:
    from emuwarez_uploadrr.services.request_readiness import get_candidates_for_request
    with _get_conn() as conn:
        # Verify request exists
        from ...services.request_readiness import request_exists
        if not request_exists(request_id, conn):
            raise HTTPException(status_code=404, detail="Petición no encontrada")
        items = get_candidates_for_request(request_id, conn)
    return [_candidate_to_response(c) for c in items]
