"""API endpoints for upload jobs, preflight, and controlled execution (Phase 6A/6C)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ...database import connect, init_db
from ...services.upload_preflight import (
    build_upload_preflight,
    get_upload_job as preflight_get_job,
    list_upload_jobs as preflight_list_jobs,
)
from ...services.upload_execution import (
    get_upload_job as exec_get_job,
    list_upload_jobs as exec_list_jobs,
    get_upload_job_logs,
    start_upload_job,
    cancel_upload_job,
)
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    CommandPreviewResponse,
    UploadJobDetail,
    UploadJobLog,
    UploadJobLogsResponse,
    UploadJobResponse,
    UploadPreflightBody,
    UploadPreflightResponse,
    UploadStartRequest,
    UploadStartResult,
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


def _job_to_detail(j: dict) -> UploadJobDetail:
    prepared = j.get("prepared_path")
    source = j.get("source_path") or j.get("path")
    using_prepared = bool(prepared) if (prepared or source) else None
    return UploadJobDetail(
        id=j.get("id"),
        library_item_id=j.get("library_item_id"),
        request_item_id=j.get("request_item_id"),
        status=j.get("status", "draft"),
        stage=j.get("stage"),
        title=j.get("title"),
        source_path=source,
        prepared_path=prepared,
        using_prepared_path=using_prepared,
        error_message=j.get("error_message"),
        exit_code=j.get("exit_code"),
        process_id=j.get("process_id"),
        started_at=j.get("started_at"),
        finished_at=j.get("finished_at"),
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
            using_prepared_path=cmd.get("using_prepared_path"),
        )

    return UploadPreflightResponse(
        status=result.get("status", "blocked"),
        job=_job_to_response(job) if job else None,
        preflight=result.get("preflight", {}),
        command_preview=cmd_response,
        warnings=result.get("warnings", []),
        errors=result.get("errors", []),
    )


@router.get("/uploads", response_model=list[UploadJobDetail])
def get_uploads(current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        jobs = exec_list_jobs(conn=conn)
    return [_job_to_detail(j) for j in jobs]


@router.get("/uploads/{job_id}", response_model=UploadJobDetail)
def get_upload(job_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        job = exec_get_job(job_id, conn=conn)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return _job_to_detail(job)


@router.get("/uploads/{job_id}/logs", response_model=UploadJobLogsResponse)
def get_upload_logs(
    job_id: int,
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        job = exec_get_job(job_id, conn=conn)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado.")
        result = get_upload_job_logs(job_id, limit=limit, offset=offset, conn=conn)

    logs = [
        UploadJobLog(
            id=log.get("id"),
            upload_job_id=log["upload_job_id"],
            level=log["level"],
            message=log["message"],
            stream=log.get("stream"),
            created_at=log["created_at"],
        )
        for log in result.get("logs", [])
    ]
    return UploadJobLogsResponse(
        job_id=job_id,
        logs=logs,
        total=result.get("total", 0),
        limit=limit,
        offset=offset,
    )


@router.post("/uploads/{job_id}/start", response_model=UploadStartResult)
def start_upload(
    job_id: int,
    body: UploadStartRequest,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        result = start_upload_job(
            job_id,
            dry_run=body.dry_run,
            start=body.start,
            confirmation=body.confirmation,
            conn=conn,
        )

    if result.get("error") in ("confirmation_required", "validation_failed", "blocked"):
        raise HTTPException(
            status_code=400,
            detail={
                "message": result.get("message") or "Bloqueado",
                "errors": result.get("errors", []),
                "error": result.get("error"),
            },
        )

    return UploadStartResult(
        job_id=job_id,
        action=result.get("action", "unknown"),
        status=result.get("status", "unknown"),
        stage=result.get("stage"),
        dry_run=result.get("dry_run", True),
        command_preview=result.get("command_preview"),
        message=result.get("message"),
        error=result.get("error"),
    )


@router.post("/uploads/{job_id}/cancel")
def cancel_upload(job_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        result = cancel_upload_job(job_id, conn=conn)
    return result
