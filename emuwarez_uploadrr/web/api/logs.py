"""Registros recientes de la aplicación — GET /api/logs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..dependencies import require_auth

router = APIRouter(tags=["logs"])


@router.get("/logs")
def logs(
    limit: int = Query(500, ge=1, le=5000),
    level: str | None = Query(None),
    search: str | None = Query(None),
    current_user: dict = Depends(require_auth),
) -> JSONResponse:
    """Recent application logs (newest first) from the in-memory capture buffer.

    Everything any module logs — plus every HTTP request — is captured here and
    mirrored to CONFIG_DIR/logs/app.log.
    """
    from ..logging_setup import get_recent_logs
    items = get_recent_logs(limit=limit, level=level, search=search)
    return JSONResponse({"items": items, "count": len(items)})
