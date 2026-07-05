"""Phase 8C — Unified operational queue endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    OperationalQueueItem,
    OperationalQueueListResponse,
    OperationalQueueSummary,
    OperationalQueueRefreshBody,
    OperationalQueueRefreshResponse,
    OperationalQueueResolveBody,
    OperationalQueueActionResponse,
    OkResponse,
)

router = APIRouter(tags=["operational_queue"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _item_to_response(item: dict) -> OperationalQueueItem:
    return OperationalQueueItem(
        id=item["id"],
        queue_key=item["queue_key"],
        item_type=item["item_type"],
        entity_type=item["entity_type"],
        entity_id=item.get("entity_id"),
        request_item_id=item.get("request_item_id"),
        library_item_id=item.get("library_item_id"),
        upload_job_id=item.get("upload_job_id"),
        title=item.get("title"),
        subtitle=item.get("subtitle"),
        status=item["status"],
        action=item["action"],
        blockers=item.get("blockers") or [],
        reasons=item.get("reasons") or [],
        context=item.get("context") or {},
        target_url=item.get("target_url"),
        created_at=item.get("created_at"),
        updated_at=item.get("updated_at"),
        last_seen_at=item.get("last_seen_at"),
        resolved_at=item.get("resolved_at"),
    )


# ---------------------------------------------------------------------------
# POST /api/operational-queue/refresh
# ---------------------------------------------------------------------------

@router.post("/operational-queue/refresh", response_model=OperationalQueueRefreshResponse)
def refresh_queue(
    body: OperationalQueueRefreshBody = OperationalQueueRefreshBody(),
    current_user: dict = Depends(require_auth),
) -> OperationalQueueRefreshResponse:
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue
    with _get_conn() as conn:
        result = refresh_operational_queue(
            conn,
            limit=body.limit,
            include_requests=body.include_requests,
            include_library=body.include_library,
            include_uploads=body.include_uploads,
            include_arr=body.include_arr,
        )
    summary = result.get("summary", {})
    return OperationalQueueRefreshResponse(
        ok=True,
        items_built=result.get("items_built", 0),
        summary=OperationalQueueSummary(**summary),
    )


# ---------------------------------------------------------------------------
# GET /api/operational-queue
# ---------------------------------------------------------------------------

@router.get("/operational-queue", response_model=OperationalQueueListResponse)
def list_queue(
    status: str = Query(None),
    action: str = Query(None),
    item_type: str = Query(None),
    entity_type: str = Query(None),
    search: str = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_auth),
) -> OperationalQueueListResponse:
    from emuwarez_uploadrr.services.operational_queue import list_operational_queue
    filters = {}
    if status:
        filters["status"] = status
    if action:
        filters["action"] = action
    if item_type:
        filters["item_type"] = item_type
    if entity_type:
        filters["entity_type"] = entity_type
    if search:
        filters["search"] = search
    with _get_conn() as conn:
        items = list_operational_queue(conn, filters=filters, limit=limit, offset=offset)
    return OperationalQueueListResponse(
        items=[_item_to_response(i) for i in items],
        total=len(items),
    )


# ---------------------------------------------------------------------------
# GET /api/operational-queue/summary
# ---------------------------------------------------------------------------

@router.get("/operational-queue/summary", response_model=OperationalQueueSummary)
def queue_summary(
    current_user: dict = Depends(require_auth),
) -> OperationalQueueSummary:
    from emuwarez_uploadrr.services.operational_queue import get_operational_queue_summary
    with _get_conn() as conn:
        summary = get_operational_queue_summary(conn)
    return OperationalQueueSummary(**summary)


# ---------------------------------------------------------------------------
# GET /api/operational-queue/{id}
# ---------------------------------------------------------------------------

@router.get("/operational-queue/{item_id}", response_model=OperationalQueueItem)
def get_queue_item(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> OperationalQueueItem:
    from emuwarez_uploadrr.services.operational_queue import get_operational_queue_item
    with _get_conn() as conn:
        item = get_operational_queue_item(item_id, conn)
    if not item:
        raise HTTPException(status_code=404, detail="Item de cola no encontrado")
    return _item_to_response(item)


# ---------------------------------------------------------------------------
# POST /api/operational-queue/{id}/resolve
# ---------------------------------------------------------------------------

@router.post("/operational-queue/{item_id}/resolve", response_model=OperationalQueueActionResponse)
def resolve_queue_item(
    item_id: int,
    body: OperationalQueueResolveBody = OperationalQueueResolveBody(),
    current_user: dict = Depends(require_auth),
) -> OperationalQueueActionResponse:
    from emuwarez_uploadrr.services.operational_queue import mark_queue_item_resolved
    with _get_conn() as conn:
        result = mark_queue_item_resolved(item_id, conn, reason=body.reason)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "No encontrado"))
    return OperationalQueueActionResponse(
        ok=True,
        item_id=item_id,
        status="resolved",
        reason=body.reason,
    )


# ---------------------------------------------------------------------------
# POST /api/operational-queue/{id}/ignore
# ---------------------------------------------------------------------------

@router.post("/operational-queue/{item_id}/ignore", response_model=OperationalQueueActionResponse)
def ignore_queue_item_endpoint(
    item_id: int,
    body: OperationalQueueResolveBody = OperationalQueueResolveBody(),
    current_user: dict = Depends(require_auth),
) -> OperationalQueueActionResponse:
    from emuwarez_uploadrr.services.operational_queue import ignore_queue_item
    with _get_conn() as conn:
        result = ignore_queue_item(item_id, conn, reason=body.reason)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "No encontrado"))
    return OperationalQueueActionResponse(
        ok=True,
        item_id=item_id,
        status="ignored",
        reason=body.reason,
    )
