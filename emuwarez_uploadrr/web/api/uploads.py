"""API endpoints for upload jobs, preflight, and controlled execution (Phase 6A/6C/6D/10F)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import connect, init_db
from ...services.library import content_display_title
from ...services.upload_preflight import (
    build_upload_preflight,
    get_upload_job as preflight_get_job,
    list_upload_jobs as preflight_list_jobs,
)
from ...services.upload_execution import (
    get_upload_job as exec_get_job,
    list_upload_jobs as exec_list_jobs,
    get_upload_job_logs,
    get_upload_job_artifacts,
    start_upload_job,
    cancel_upload_job,
    delete_upload_job,
    retry_upload_job,
    compute_progress_phase,
)
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    AutoUploadRequest,
    AutoUploadSourceCheckResponse,
    CommandPreviewResponse,
    OkResponse,
    UploadArtifact,
    UploadArtifactsResponse,
    UploadDeleteRequest,
    UploadJobDetail,
    UploadJobLog,
    UploadJobLogsResponse,
    UploadJobResponse,
    UploadPreflightBody,
    UploadPreflightResponse,
    UploadQueueBody,
    UploadQueueResponse,
    UploadRetryRequest,
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


def _extract_runtime_type(j: dict) -> str | None:
    raw = j.get("uploadrr_command_json")
    if not raw:
        return None
    try:
        return json.loads(raw).get("runtime_type")
    except Exception:
        return None


def _extract_command_preview(j: dict) -> str | None:
    """Prefer the safe (redacted) preview captured at execution start; fall
    back to the preflight preview (never contains secrets either way)."""
    safe_raw = j.get("safe_command_json")
    if safe_raw:
        try:
            preview = json.loads(safe_raw).get("args_preview")
            if preview:
                return preview
        except Exception:
            pass
    preflight_raw = j.get("uploadrr_command_json")
    if preflight_raw:
        try:
            return json.loads(preflight_raw).get("command_preview")
        except Exception:
            return None
    return None


def _extract_json_dict(j: dict, key: str) -> dict | None:
    raw = j.get(key)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _job_to_detail(
    j: dict,
    media_type: str | None = None,
    poster_url: str | None = None,
    backdrop_url: str | None = None,
    instance_type: str | None = None,
    instance_name: str | None = None,
    request_status: str | None = None,
    year: int | None = None,
    instance_id: int | None = None,
    tmdb_id: str | None = None,
    title_slug: str | None = None,
    display_title: str | None = None,
) -> UploadJobDetail:
    prepared = j.get("prepared_path")
    source = j.get("source_path") or j.get("path")
    using_prepared = bool(prepared) if (prepared or source) else None
    return UploadJobDetail(
        media_type=media_type,
        poster_url=poster_url,
        backdrop_url=backdrop_url,
        year=year,
        display_title=display_title,
        instance_type=instance_type,
        instance_name=instance_name,
        instance_id=instance_id,
        tmdb_id=tmdb_id,
        title_slug=title_slug,
        request_status=request_status,
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
        # Phase 6D
        result_url=j.get("result_url"),
        result_torrent_id=j.get("result_torrent_id"),
        result_tracker=j.get("result_tracker"),
        result_category=j.get("result_category"),
        duration_seconds=j.get("duration_seconds"),
        retry_count=j.get("retry_count") or 0,
        retry_of_job_id=j.get("retry_of_job_id"),
        safe_command_json=j.get("safe_command_json"),
        last_success_at=j.get("last_success_at"),
        last_error_at=j.get("last_error_at"),
        last_log_at=j.get("last_log_at"),
        runtime_type=_extract_runtime_type(j),
        command_preview=_extract_command_preview(j),
        progress_phase=compute_progress_phase(j.get("status", ""), j.get("stage")),
        queued_until=j.get("queued_until"),
        nomenclature_snapshot=_extract_json_dict(j, "nomenclature_snapshot_json"),
        remux_snapshot=_extract_json_dict(j, "remux_snapshot_json"),
        checks_snapshot=_extract_json_dict(j, "checks_snapshot_json"),
        progress=_extract_json_dict(j, "progress_json"),
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
            runtime_type=cmd.get("runtime_type"),
            contract_valid=cmd.get("contract_valid"),
            contract_errors=cmd.get("contract_errors"),
            contract_warnings=cmd.get("contract_warnings"),
            can_execute=cmd.get("can_execute"),
            requires_confirmation=cmd.get("requires_confirmation"),
            safe_to_execute=cmd.get("safe_to_execute"),
        )

    return UploadPreflightResponse(
        status=result.get("status", "blocked"),
        job=_job_to_response(job) if job else None,
        preflight=result.get("preflight", {}),
        command_preview=cmd_response,
        warnings=result.get("warnings", []),
        errors=result.get("errors", []),
    )


@router.post("/library/{item_id}/upload/checks")
def upload_checks(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Run the pre-upload checks (fail-fast, eMuwarez last) for the 'Subida a
    eMuwarez' step. Returns each check's result + a `ready` flag. Can take
    ~30s (real network calls) — poll GET .../checks/progress concurrently to
    show each check landing as it completes instead of a static wait."""
    from emuwarez_uploadrr.services.upload_checks import run_upload_checks
    with _get_conn() as conn:
        return run_upload_checks(conn, item_id)


@router.get("/library/{item_id}/upload/checks/progress")
def upload_checks_progress(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Live progress of a checks run in flight for this item — {checks, done,
    ready}, `checks` growing one at a time. Meant to be polled while the
    POST above is running; returns the empty/initial shape if none is running."""
    from emuwarez_uploadrr.services.upload_checks import get_checks_progress
    return get_checks_progress(item_id)


@router.post("/library/{item_id}/upload/queue", response_model=UploadQueueResponse)
def queue_upload(
    item_id: int,
    body: UploadQueueBody,
    current_user: dict = Depends(require_auth),
):
    """Queue "Subir a eMuwarez": creates the upload_jobs row in status='queued'
    and returns immediately (the caller navigates to Subidas right after).
    The real work — integrity check, nomenclature rename, track remux, then
    the actual Uploadrr start — runs server-side after a grace period during
    which the job can still be cancelled (see services/upload_queue.py)."""
    from ...services.upload_queue import queue_upload_for_item
    overrides = None
    if body.remux_overrides:
        overrides = {}
        for raw_id, ov in body.remux_overrides.items():
            try:
                overrides[int(raw_id)] = {"new_name": ov.new_name, "default_after": ov.default_after}
            except (TypeError, ValueError):
                continue
    checks = body.checks.model_dump() if body.checks else None
    with _get_conn() as conn:
        result = queue_upload_for_item(
            item_id, remux_overrides=overrides, remux_snapshot=body.remux_snapshot, checks=checks, conn=conn,
        )

    job = result.get("job")
    return UploadQueueResponse(
        status=result.get("status", "blocked"),
        job=_job_to_detail(job) if job else None,
        errors=result.get("errors", []),
    )


@router.post("/library/{item_id}/upload/auto", response_model=UploadQueueResponse)
def queue_auto_upload(
    item_id: int,
    body: AutoUploadRequest = AutoUploadRequest(),
    current_user: dict = Depends(require_auth),
):
    """"Automático": no wizard involved. The job appears immediately in
    Subidas as 'staging' ("Preparando") while nomenclature/remux/checks
    previews are computed server-side; see services/upload_queue.py.

    `body.source`/`body.provider` come from the frontend's source-disparity
    gate (GET .../upload/auto/source-check, called right before this) —
    set only when the user had to resolve a disparity by hand."""
    from ...services.upload_queue import queue_auto_upload_for_item
    with _get_conn() as conn:
        result = queue_auto_upload_for_item(
            item_id, conn=conn,
            source_override=body.source, provider_override=body.provider,
        )

    job = result.get("job")
    return UploadQueueResponse(
        status=result.get("status", "blocked"),
        job=_job_to_detail(job) if job else None,
        errors=result.get("errors", []),
    )


@router.get("/library/{item_id}/upload/auto/source-check", response_model=AutoUploadSourceCheckResponse)
def check_auto_upload_source_route(
    item_id: int,
    current_user: dict = Depends(require_auth),
):
    """Quick pre-flight source check run right before an "Automático" upload
    — see services/source_assistant.py::check_auto_upload_source for the
    exact trigger condition."""
    from ...services.source_assistant import check_auto_upload_source
    with _get_conn() as conn:
        result = check_auto_upload_source(item_id, conn=conn)
    return AutoUploadSourceCheckResponse(**result)


@router.get("/uploads", response_model=list[UploadJobDetail])
def get_uploads(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    library_item_id: int | None = Query(default=None),
    request_item_id: int | None = Query(default=None),
    current_user: dict = Depends(require_auth),
):
    filters = {
        "status": status,
        "limit": limit,
        "offset": offset,
        "search": search,
        "library_item_id": library_item_id,
        "request_item_id": request_item_id,
    }
    with _get_conn() as conn:
        jobs = exec_list_jobs(filters=filters, conn=conn)
        # Resolve each job's media type (movie/series/…), poster, Origen
        # (Radarr/Sonarr instance) and Petición status in a single query —
        # same fields Biblioteca already shows per content.
        item_ids = {j.get("library_item_id") for j in jobs if j.get("library_item_id")}
        media_by_item: dict[int, str] = {}
        poster_by_item: dict[int, str] = {}
        backdrop_by_item: dict[int, str] = {}
        instance_type_by_item: dict[int, str] = {}
        instance_name_by_item: dict[int, str] = {}
        request_status_by_item: dict[int, str] = {}
        year_by_item: dict[int, int] = {}
        instance_id_by_item: dict[int, int] = {}
        tmdb_id_by_item: dict[int, str] = {}
        title_slug_by_item: dict[int, str] = {}
        if item_ids:
            placeholders = ",".join("?" * len(item_ids))
            for row in conn.execute(
                f"SELECT id, item_type, poster_url, backdrop_url, instance_type, instance_name, request_status, year, "
                f"instance_id, tmdb_id, title_slug "
                f"FROM library_items WHERE id IN ({placeholders})",
                tuple(item_ids),
            ):
                media_by_item[row["id"]] = row["item_type"]
                if row["poster_url"]:
                    poster_by_item[row["id"]] = row["poster_url"]
                if row["backdrop_url"]:
                    backdrop_by_item[row["id"]] = row["backdrop_url"]
                if row["instance_type"]:
                    instance_type_by_item[row["id"]] = row["instance_type"]
                if row["instance_name"]:
                    instance_name_by_item[row["id"]] = row["instance_name"]
                if row["request_status"]:
                    request_status_by_item[row["id"]] = row["request_status"]
                if row["year"]:
                    year_by_item[row["id"]] = row["year"]
                if row["instance_id"]:
                    instance_id_by_item[row["id"]] = row["instance_id"]
                if row["tmdb_id"]:
                    tmdb_id_by_item[row["id"]] = row["tmdb_id"]
                if row["title_slug"]:
                    title_slug_by_item[row["id"]] = row["title_slug"]
    return [
        _job_to_detail(
            j,
            media_by_item.get(j.get("library_item_id")),
            poster_by_item.get(j.get("library_item_id")),
            backdrop_by_item.get(j.get("library_item_id")),
            instance_type_by_item.get(j.get("library_item_id")),
            instance_name_by_item.get(j.get("library_item_id")),
            request_status_by_item.get(j.get("library_item_id")),
            year_by_item.get(j.get("library_item_id")),
            instance_id_by_item.get(j.get("library_item_id")),
            tmdb_id_by_item.get(j.get("library_item_id")),
            title_slug_by_item.get(j.get("library_item_id")),
        )
        for j in jobs
    ]


@router.get("/uploads/{job_id}", response_model=UploadJobDetail)
def get_upload(job_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        job = exec_get_job(job_id, conn=conn)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado.")
        media_type = poster_url = backdrop_url = instance_type = instance_name = request_status = None
        year = None
        instance_id = tmdb_id = title_slug = None
        display_title = None
        item_id = job.get("library_item_id")
        if item_id:
            row = conn.execute(
                "SELECT item_type, poster_url, backdrop_url, instance_type, instance_name, request_status, year, "
                "instance_id, tmdb_id, title_slug, title, season_number, episode_number, parent_id "
                "FROM library_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if row:
                media_type = row["item_type"]
                poster_url = row["poster_url"]
                backdrop_url = row["backdrop_url"]
                instance_type = row["instance_type"]
                instance_name = row["instance_name"]
                request_status = row["request_status"]
                year = row["year"]
                instance_id = row["instance_id"]
                tmdb_id = row["tmdb_id"]
                title_slug = row["title_slug"]
                display_title = content_display_title(conn, dict(row))
    return _job_to_detail(job, media_type, poster_url, backdrop_url, instance_type, instance_name, request_status, year,
                           instance_id, tmdb_id, title_slug, display_title)


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


@router.get("/uploads/{job_id}/artifacts", response_model=UploadArtifactsResponse)
def get_upload_artifacts(job_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        job = exec_get_job(job_id, conn=conn)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado.")
        artifacts = get_upload_job_artifacts(job_id, conn=conn)

    return UploadArtifactsResponse(
        job_id=job_id,
        artifacts=[
            UploadArtifact(
                id=a.get("id"),
                upload_job_id=a["upload_job_id"],
                artifact_type=a["artifact_type"],
                name=a.get("name"),
                path=a.get("path"),
                url=a.get("url"),
                value=a.get("value"),
                created_at=a["created_at"],
            )
            for a in artifacts
        ],
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

    if result.get("error") in ("confirmation_required", "validation_failed", "blocked", "unsupported_runtime"):
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


@router.post("/uploads/{job_id}/retry", response_model=UploadStartResult)
def retry_upload(
    job_id: int,
    body: UploadRetryRequest,
    current_user: dict = Depends(require_auth),
):
    result = retry_upload_job(
        job_id,
        dry_run=body.dry_run,
        start=body.start,
        confirmation=body.confirmation,
    )

    if result.get("error") in ("confirmation_required", "validation_failed", "blocked", "invalid_status", "not_found"):
        status_code = 404 if result.get("error") == "not_found" else 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": result.get("message") or "Bloqueado",
                "error": result.get("error"),
            },
        )

    new_job_id = result.get("new_job_id") or job_id
    return UploadStartResult(
        job_id=new_job_id,
        action=result.get("action", "unknown"),
        status=result.get("status", "unknown"),
        stage=result.get("stage"),
        dry_run=result.get("dry_run", True),
        command_preview=result.get("command_preview"),
        message=result.get("message"),
        error=result.get("error"),
    )


@router.post("/uploads/{job_id}/retry-queued", response_model=UploadQueueResponse)
def retry_upload_queued(job_id: int, current_user: dict = Depends(require_auth)):
    """Retry straight into the same queued/60s-countdown flow "Subir a
    eMuwarez" uses — no confirmation token, since it only ever creates a
    brand new job row (the original failed/cancelled job is never touched)."""
    from ...services.upload_queue import queue_retry_for_job
    with _get_conn() as conn:
        result = queue_retry_for_job(job_id, conn=conn)

    job = result.get("job")
    if result.get("status") != "queued":
        raise HTTPException(
            status_code=400,
            detail={"message": "; ".join(result.get("errors", [])) or "No se pudo reintentar."},
        )
    return UploadQueueResponse(
        status=result.get("status", "blocked"),
        job=_job_to_detail(job) if job else None,
        errors=result.get("errors", []),
    )


@router.post("/uploads/{job_id}/cancel")
def cancel_upload(job_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        result = cancel_upload_job(job_id, conn=conn)
    return result


@router.post("/uploads/{job_id}/delete", response_model=OkResponse)
def delete_upload(
    job_id: int,
    body: UploadDeleteRequest,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        result = delete_upload_job(job_id, confirmation=body.confirmation, conn=conn)

    if not result.get("ok"):
        status_code = 404 if result.get("error") == "not_found" else 400
        raise HTTPException(
            status_code=status_code,
            detail={"message": result.get("message") or "No se pudo borrar la subida.", "error": result.get("error")},
        )

    return OkResponse(message=result.get("message", "Subida eliminada."))
