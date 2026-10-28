"""Automatic tasks scheduler endpoints — Phase 11D.

GET  /api/tasks/scheduled                 — list all scheduled tasks + bookkeeping
PUT  /api/tasks/scheduled/{task_key}      — update interval (enforces per-task minimum)
POST /api/tasks/scheduled/{task_key}/run  — run now (blocked for tasks with manual_allowed=False)
GET  /api/tasks/scheduled/{task_key}/logs — recent run history (reuses task_runs)

All endpoints require auth. Manual runs execute synchronously in this
request's thread (FastAPI already runs sync `def` handlers in a worker
thread, so this never blocks the event loop) — same UX as the existing
"Sincronizar biblioteca" dashboard button, which also blocks until done.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    RunScheduledTaskResponse,
    ScheduledTaskResponse,
    TaskRunLogsResponse,
    UpdateScheduledTaskRequest,
)

router = APIRouter(prefix="/tasks/scheduled", tags=["tasks"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _to_response(task: dict) -> ScheduledTaskResponse:
    return ScheduledTaskResponse(
        task_key=task["task_key"],
        name=task["name"],
        description=task["description"],
        interval_minutes=task["interval_minutes"],
        min_interval_minutes=task["min_interval_minutes"],
        manual_allowed=bool(task["manual_allowed"]),
        enabled=bool(task["enabled"]),
        last_run_at=task.get("last_run_at"),
        last_status=task.get("last_status"),
        last_summary=task.get("last_summary"),
        next_run_at=task.get("next_run_at"),
    )


@router.get("", response_model=list[ScheduledTaskResponse])
def list_scheduled_tasks(current_user: dict = Depends(require_auth)) -> list[ScheduledTaskResponse]:
    from emuwarez_uploadrr.services.scheduler import list_scheduled_tasks as _list
    with _get_conn() as conn:
        tasks = _list(conn)
    return [_to_response(t) for t in tasks]


@router.put("/{task_key}", response_model=ScheduledTaskResponse)
def update_scheduled_task(
    task_key: str,
    body: UpdateScheduledTaskRequest,
    current_user: dict = Depends(require_auth),
) -> ScheduledTaskResponse:
    from emuwarez_uploadrr.services.scheduler import set_task_interval
    with _get_conn() as conn:
        try:
            task = set_task_interval(conn, task_key, body.interval_minutes)
        except ValueError as exc:
            code = 404 if "desconocida" in str(exc).lower() else 422
            raise HTTPException(status_code=code, detail=str(exc))
    return _to_response(task)


@router.post("/{task_key}/run", response_model=RunScheduledTaskResponse)
def run_scheduled_task_now(
    task_key: str,
    current_user: dict = Depends(require_auth),
) -> RunScheduledTaskResponse:
    from emuwarez_uploadrr.services.scheduler import run_scheduled_task
    with _get_conn() as conn:
        try:
            result = run_scheduled_task(conn, task_key, manual=True)
        except ValueError as exc:
            code = status.HTTP_404_NOT_FOUND if "desconocida" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
            raise HTTPException(status_code=code, detail=str(exc))
    return RunScheduledTaskResponse(**result)


@router.get("/{task_key}/logs", response_model=TaskRunLogsResponse)
def get_scheduled_task_logs(
    task_key: str,
    limit: int = Query(default=20, ge=1, le=200),
    current_user: dict = Depends(require_auth),
) -> TaskRunLogsResponse:
    from emuwarez_uploadrr.services.scheduler import get_scheduled_task
    from emuwarez_uploadrr.services.tasks import list_tasks_by_name
    with _get_conn() as conn:
        task = get_scheduled_task(conn, task_key)
        if not task:
            raise HTTPException(status_code=404, detail=f"Tarea desconocida: {task_key}")
        logs = list_tasks_by_name(conn, task_key, limit=limit)
    return TaskRunLogsResponse(task_key=task_key, logs=logs)
