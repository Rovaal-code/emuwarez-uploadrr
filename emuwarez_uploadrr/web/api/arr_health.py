"""ARR health, filesystem verification and recommendations endpoints (Phase 8A)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_auth
from ..runtime import _db_path

router = APIRouter(tags=["arr-health"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# GET /api/arr/health
# ---------------------------------------------------------------------------

@router.get("/arr/health")
def arr_health(current_user: dict = Depends(require_auth)):
    """Devuelve salud de instancias ARR. Solo lectura."""
    from emuwarez_uploadrr.services.arr_health import collect_arr_health
    with _get_conn() as conn:
        result = collect_arr_health(conn)
    return result


# ---------------------------------------------------------------------------
# POST /api/arr/health/refresh
# ---------------------------------------------------------------------------

class _ArrHealthRefreshRequest:
    def __init__(self, include_queue: bool = True, include_history: bool = True, history_page_size: int = 100):
        self.include_queue = include_queue
        self.include_history = include_history
        self.history_page_size = history_page_size


@router.post("/arr/health/refresh")
def arr_health_refresh(
    include_queue: bool = True,
    include_history: bool = True,
    history_page_size: int = 100,
    current_user: dict = Depends(require_auth),
):
    """Refresca queue e historial ARR y actualiza diagnósticos de biblioteca."""
    from emuwarez_uploadrr.services.arr_health import (
        collect_arr_health,
        refresh_arr_queue_diagnostics,
        refresh_arr_history_diagnostics,
    )
    with _get_conn() as conn:
        health = collect_arr_health(conn)
        queue_result = {}
        history_result = {}
        if include_queue:
            queue_result = refresh_arr_queue_diagnostics(conn)
        if include_history:
            history_result = refresh_arr_history_diagnostics(conn, page_size=history_page_size)

    return {
        "ok": True,
        "health": health,
        "queue_refresh": queue_result if include_queue else None,
        "history_refresh": history_result if include_history else None,
    }


# ---------------------------------------------------------------------------
# POST /api/library/verify-files
# ---------------------------------------------------------------------------

@router.post("/library/verify-files")
def verify_library_files(
    limit: Optional[int] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(require_auth),
):
    """Verifica existencia de archivos en disco para items de biblioteca."""
    from emuwarez_uploadrr.services.library_verification import verify_library_files as _verify
    filters: dict = {}
    if status:
        filters["status"] = status
    with _get_conn() as conn:
        result = _verify(conn, filters=filters, limit=limit)
    return result


# ---------------------------------------------------------------------------
# POST /api/library/{item_id}/verify-file
# ---------------------------------------------------------------------------

@router.post("/library/{item_id}/verify-file")
def verify_single_file(
    item_id: int,
    current_user: dict = Depends(require_auth),
):
    """Verifica existencia del archivo en disco para un item concreto."""
    from emuwarez_uploadrr.services.library_verification import verify_library_item_file
    with _get_conn() as conn:
        result = verify_library_item_file(item_id, conn)
    if not result.get("ok", True) and result.get("error", "").startswith("Item"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# POST /api/library/recommendations/refresh
# ---------------------------------------------------------------------------

@router.post("/library/recommendations/refresh")
def refresh_recommendations(
    status: Optional[str] = None,
    current_user: dict = Depends(require_auth),
):
    """Recalcula recomendaciones para items de biblioteca."""
    from emuwarez_uploadrr.services.recommendations import refresh_recommendations as _refresh
    filters: dict = {}
    if status:
        filters["status"] = status
    with _get_conn() as conn:
        result = _refresh(conn, filters=filters)
    return result


# ---------------------------------------------------------------------------
# GET /api/library/{item_id}/recommendation
# ---------------------------------------------------------------------------

@router.get("/library/{item_id}/recommendation")
def get_recommendation(
    item_id: int,
    current_user: dict = Depends(require_auth),
):
    """Devuelve recomendación almacenada para un item."""
    from emuwarez_uploadrr.services.recommendations import get_recommendation_for_item
    with _get_conn() as conn:
        result = get_recommendation_for_item(item_id, conn)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
    return result


# ---------------------------------------------------------------------------
# GET /api/library/diagnostics
# ---------------------------------------------------------------------------

@router.get("/library/diagnostics")
def library_diagnostics(
    severity: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_auth),
):
    """Devuelve diagnósticos de items de biblioteca con filtros."""
    with _get_conn() as conn:
        from ...services.library import list_library_diagnostics
        rows, total = list_library_diagnostics(
            status=status, search=search, limit=limit, offset=offset, conn=conn,
        )

    import json
    items = []
    for d in rows:
        try:
            d["recommendation_reasons"] = json.loads(d.pop("recommendation_reasons_json") or "[]")
        except Exception:
            d["recommendation_reasons"] = []
        items.append(d)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# GET /api/missing/diagnostics
# ---------------------------------------------------------------------------

@router.get("/missing/diagnostics")
def missing_diagnostics(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_auth),
):
    """Devuelve faltantes enriquecidos con queue/history/recomendación."""
    with _get_conn() as conn:
        from ...services.library import list_missing_diagnostics
        rows, total = list_missing_diagnostics(limit=limit, offset=offset, conn=conn)

    import json
    items = []
    for d in rows:
        try:
            d["recommendation_reasons"] = json.loads(d.pop("recommendation_reasons_json") or "[]")
        except Exception:
            d["recommendation_reasons"] = []
        items.append(d)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
