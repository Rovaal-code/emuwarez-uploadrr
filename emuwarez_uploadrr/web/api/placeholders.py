"""Placeholder endpoints for future phases.

Every route returns a structured stub so the frontend can be wired up ahead
of the real implementation. Protected endpoints require a valid Bearer token
and return 401 without one.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
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
    return JSONResponse({"implemented": False, "phase": phase, "message": _STUB["message"], "endpoint": endpoint})


# ---------------------------------------------------------------------------
# Dashboard — protected
# ---------------------------------------------------------------------------

@router.get("/dashboard/summary")
def dashboard_summary(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/summary", "phase-4")

@router.get("/dashboard/activity")
def dashboard_activity(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/activity", "phase-4")

@router.get("/dashboard/upload-activity")
def dashboard_upload_activity(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/upload-activity", "phase-8")

@router.get("/dashboard/tasks")
def dashboard_tasks(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/tasks", "phase-4")

@router.get("/dashboard/events")
def dashboard_events(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/dashboard/events", "phase-7")

# ---------------------------------------------------------------------------
# Instances — protected
# ---------------------------------------------------------------------------

@router.get("/instances")
def instances_list(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/instances", "phase-4")

@router.post("/instances")
def instances_create(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/instances", "phase-4")

@router.post("/instances/{instance_id}/test")
def instances_test(instance_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/instances/{instance_id}/test", "phase-4")

@router.post("/instances/{instance_id}/sync")
def instances_sync(instance_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/instances/{instance_id}/sync", "phase-4")

# ---------------------------------------------------------------------------
# Sync — protected
# ---------------------------------------------------------------------------

@router.post("/sync/library")
def sync_library(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/sync/library", "phase-4")

@router.post("/sync/requests")
def sync_requests(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/sync/requests", "phase-5")

# ---------------------------------------------------------------------------
# Library — protected
# ---------------------------------------------------------------------------

@router.get("/library")
def library_list(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/library", "phase-4")

@router.get("/library/{item_id}")
def library_detail(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"/api/library/{item_id}", "phase-4")

@router.post("/library/{item_id}/adapt-nomenclature")
def library_adapt_nomenclature(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/library/{item_id}/adapt-nomenclature", "phase-8")

@router.post("/library/{item_id}/upload")
def library_upload(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/library/{item_id}/upload", "phase-8")

# ---------------------------------------------------------------------------
# Missing — protected
# ---------------------------------------------------------------------------

@router.get("/missing")
def missing_list(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/missing", "phase-4")

@router.post("/missing/{item_id}/check-emu")
def missing_check_emu(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/missing/{item_id}/check-emu", "phase-5")

@router.post("/missing/{item_id}/create-emu-request")
def missing_create_emu_request(item_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return JSONResponse({**_EMU_REQUEST_STUB, "endpoint": f"POST /api/missing/{item_id}/create-emu-request"})

# ---------------------------------------------------------------------------
# Requests — protected
# ---------------------------------------------------------------------------

@router.get("/requests")
def requests_list(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/requests", "phase-5")

@router.post("/requests/sync")
def requests_sync(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("POST /api/requests/sync", "phase-5")

@router.get("/requests/{request_id}")
def requests_detail(request_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"/api/requests/{request_id}", "phase-5")

@router.post("/requests/{request_id}/match")
def requests_match(request_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/requests/{request_id}/match", "phase-6")

@router.post("/requests/{request_id}/mark-reviewed")
def requests_mark_reviewed(request_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"POST /api/requests/{request_id}/mark-reviewed", "phase-7")

# ---------------------------------------------------------------------------
# Uploads — protected
# ---------------------------------------------------------------------------

@router.get("/uploads")
def uploads_list(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/uploads", "phase-8")

@router.get("/uploads/{upload_id}")
def uploads_detail(upload_id: int, current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub(f"/api/uploads/{upload_id}", "phase-8")

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
def logs(current_user: dict = Depends(require_auth)) -> JSONResponse:
    return _stub("/api/logs", "phase-4")

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
