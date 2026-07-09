"""Placeholder endpoints for phases still pending implementation.

These all return structured stubs. Protected endpoints return 401 without
a valid Bearer token. Phase 4 moved instances, dashboard, library, missing
and sync to their own real routers; those are no longer stubs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..dependencies import require_auth

router = APIRouter(tags=["placeholders"])

_STUB = {"implemented": False, "phase": "future", "message": "Endpoint reservado para fase posterior"}

_EMU_REQUEST_STUB = {
    "implemented": False,
    "phase": "final",
    "stub": True,
    "message": (
        "La creación automática de peticiones en eMuwarez está preparada como stub y queda "
        "bloqueada hasta capturar y validar la request real desde DevTools/Network. "
        "No se enviará ninguna petición a eMuwarez hasta entonces."
    ),
}


def _stub(endpoint: str, phase: str = "future") -> JSONResponse:
    return JSONResponse({
        "implemented": False, "phase": phase,
        "message": _STUB["message"], "endpoint": endpoint,
    })


# ---------------------------------------------------------------------------
# Dashboard extras — protected (real dashboard/summary and /activity are in dashboard.py)
# ---------------------------------------------------------------------------

@router.get("/dashboard/upload-activity")
def dashboard_upload_activity(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/upload-activity", "phase-8")

@router.get("/dashboard/events")
def dashboard_events(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/events", "phase-7")

@router.get("/dashboard/tasks")
def dashboard_tasks(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/tasks", "phase-4")

# ---------------------------------------------------------------------------
# Missing extras — protected (real /missing list is in library.py)
# ---------------------------------------------------------------------------

@router.post("/missing/{item_id}/check-emu")
def missing_check_emu(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/missing/{item_id}/check-emu", "phase-5")

@router.post("/missing/{item_id}/create-emu-request")
def missing_create_emu_request(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return JSONResponse({**_EMU_REQUEST_STUB, "endpoint": f"POST /api/missing/{item_id}/create-emu-request"})

# ---------------------------------------------------------------------------
# Library extras — protected (real /library list/detail are in library.py)
# ---------------------------------------------------------------------------

# NOTE: adapt-nomenclature, nomenclature/preview, upload/preflight moved to
# web/api/nomenclature.py and web/api/uploads.py (Phase 6A — real implementation)

@router.post("/library/{item_id}/upload")
def library_upload(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/library/{item_id}/upload", "phase-8")

# Requests endpoints moved to web/api/requests.py (Phase 5B — real implementation)

# ---------------------------------------------------------------------------
# Uploads — protected (real GET /uploads, GET/POST /uploads/{id} in uploads.py)
# ---------------------------------------------------------------------------

@router.post("/uploads/{upload_id}/cancel")
def uploads_cancel(upload_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/uploads/{upload_id}/cancel", "phase-8")

# ---------------------------------------------------------------------------
# Tasks — protected
# ---------------------------------------------------------------------------

@router.get("/tasks")
def tasks_list(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/tasks", "phase-4")

@router.post("/tasks/{task_name}/run")
def tasks_run(task_name: str, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/tasks/{task_name}/run", "phase-4")

# ---------------------------------------------------------------------------
# Logs — protected
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Config — protected
# ---------------------------------------------------------------------------

@router.get("/config")
def config_get(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/config", "phase-3")

@router.post("/config/general")
def config_general(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/config/general", "phase-3")

@router.post("/config/tmdb")
def config_tmdb(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/config/tmdb", "phase-3")

@router.post("/config/emu")
def config_emu(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/config/emu", "phase-3")

@router.post("/config/uploadrr")
def config_uploadrr(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/config/uploadrr", "phase-3")
