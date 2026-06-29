"""API endpoints for upload jobs and preflight (Phase 6A)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...database import connect, init_db
from ...services.upload_preflight import (
    build_upload_preflight,
    get_upload_job,
    list_upload_jobs,
)
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    CommandPreviewResponse,
    UploadJobResponse,
    UploadPreflightBody,
    UploadPreflightResponse,
)

router = APIRouter(tags=["uploads"])


def _get_conn():
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _job_to_response(j: dict) -> UploadJobResponse:
    return UploadJobResponse(
        id=j.get("id"),
        library_item_id=j.get("library_item_id"),
        request_item_id=j.get("request_item_id"),
        status=j.get("status", "draft"),
        stage=j.get("stage"),
        title=j.get("title"),
        source_path=j.get("source_path"),
        error_message=j.get("error_message"),
        created_at=j.get("created_at"),
        updated_at=j.get("updated_at"),
    )


@router.post("/library/{item_id}/upload/preflight", response_model=UploadPreflightResponse)
def upload_preflight(
    item_id: int,
    body: UploadPreflightBody,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        result = build_upload_preflight(item_id, request_id=body.request_id, conn=conn)

    job = result.get("job")
    cmd = result.get("command_preview", {})

    cmd_response = None
    if cmd:
        cmd_response = CommandPreviewResponse(
            uploadrr_path=cmd.get("uploadrr_path"),
            tracker=cmd.get("tracker"),
            category=cmd.get("category"),
            title=cmd.get("title"),
            tmdb_id=cmd.get("tmdb_id"),
            resolution=cmd.get("resolution"),
            source_path=cmd.get("source_path"),
            command_preview=cmd.get("command_preview"),
            note=cmd.get("note"),
        )

    return UploadPreflightResponse(
        status=result.get("status", "blocked"),
        job=_job_to_response(job) if job else None,
        preflight=result.get("preflight", {}),
        command_preview=cmd_response,
        warnings=result.get("warnings", []),
        errors=result.get("errors", []),
    )


@router.get("/uploads", response_model=list[UploadJobResponse])
def get_uploads(current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        jobs = list_upload_jobs(conn=conn)
    return [_job_to_response(j) for j in jobs]


@router.get("/uploads/{job_id}", response_model=UploadJobResponse)
def get_upload(job_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        job = get_upload_job(job_id, conn=conn)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return _job_to_response(job)
