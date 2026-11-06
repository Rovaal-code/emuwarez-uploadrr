"""Automatic tasks scheduler endpoints — Phase 11D.

GET  /api/tasks/scheduled                 — list all scheduled tasks + bookkeeping
PUT  /api/tasks/scheduled/{task_key}      — cambia el horario: cada N minutos (con mínimo por tarea) o cada día a las HH:MM
PUT  /api/tasks/scheduled/{task_key}/opciones — ajustes numéricos de la tarea (retención, copias que se guardan)
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
    UpdateTaskOptionsRequest,
)
from ...integrations.base import texto_de_error

router = APIRouter(prefix="/tasks/scheduled", tags=["tasks"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _to_response(task: dict, opciones: list[dict]) -> ScheduledTaskResponse:
    from emuwarez_uploadrr.services.scheduler import nombre_zona_horaria
    return ScheduledTaskResponse(
        task_key=task["task_key"],
        name=task["name"],
        description=task["description"],
        interval_minutes=task["interval_minutes"],
        min_interval_minutes=task["min_interval_minutes"],
        run_at=task.get("run_at"),
        timezone=nombre_zona_horaria(),
        manual_allowed=bool(task["manual_allowed"]),
        enabled=bool(task["enabled"]),
        last_run_at=task.get("last_run_at"),
        last_status=task.get("last_status"),
        last_summary=task.get("last_summary"),
        next_run_at=task.get("next_run_at"),
        opciones=opciones,
    )


@router.get("", response_model=list[ScheduledTaskResponse])
def list_scheduled_tasks(current_user: dict = Depends(require_auth)) -> list[ScheduledTaskResponse]:
    from emuwarez_uploadrr.services.scheduler import list_scheduled_tasks as _list, opciones_de_tarea
    with _get_conn() as conn:
        return [_to_response(t, opciones_de_tarea(conn, t["task_key"])) for t in _list(conn)]


@router.put("/{task_key}", response_model=ScheduledTaskResponse)
def update_scheduled_task(
    task_key: str,
    body: UpdateScheduledTaskRequest,
    current_user: dict = Depends(require_auth),
) -> ScheduledTaskResponse:
    from emuwarez_uploadrr.services.scheduler import opciones_de_tarea, set_task_schedule
    with _get_conn() as conn:
        try:
            task = set_task_schedule(conn, task_key, interval_minutes=body.interval_minutes, run_at=body.run_at)
        except ValueError as exc:
            texto = texto_de_error(exc)
            code = 404 if "desconocida" in texto.lower() else 422
            raise HTTPException(status_code=code, detail=texto)
        return _to_response(task, opciones_de_tarea(conn, task_key))


@router.put("/{task_key}/opciones", response_model=ScheduledTaskResponse)
def update_scheduled_task_options(
    task_key: str,
    body: UpdateTaskOptionsRequest,
    current_user: dict = Depends(require_auth),
) -> ScheduledTaskResponse:
    from emuwarez_uploadrr.services.scheduler import get_scheduled_task, set_task_options
    with _get_conn() as conn:
        try:
            opciones = set_task_options(conn, task_key, body.valores)
        except ValueError as exc:
            texto = texto_de_error(exc)
            code = 404 if "desconocida" in texto.lower() else 422
            raise HTTPException(status_code=code, detail=texto)
        return _to_response(get_scheduled_task(conn, task_key), opciones)


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
            texto = texto_de_error(exc)
            code = status.HTTP_404_NOT_FOUND if "desconocida" in texto.lower() else status.HTTP_400_BAD_REQUEST
            raise HTTPException(status_code=code, detail=texto)
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
