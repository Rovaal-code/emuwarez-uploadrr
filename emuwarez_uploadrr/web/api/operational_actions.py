"""Phase 9A — Guided queue action endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import require_auth
from ..runtime import _db_path

router = APIRouter(tags=["operational_actions"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


class ExecuteSafeActionBody(BaseModel):
    action: Optional[str] = None


@router.get("/operational-queue/{item_id}/actions")
def get_queue_item_actions(
    item_id: int,
    _user: dict = Depends(require_auth),
):
    conn = _get_conn()
    try:
        from emuwarez_uploadrr.services.operational_actions import list_available_queue_actions
        actions = list_available_queue_actions(item_id, conn)
        if not actions:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        return {"item_id": item_id, "actions": actions}
    finally:
        conn.close()


@router.get("/operational-queue/{item_id}/action-plan")
def get_queue_action_plan(
    item_id: int,
    _user: dict = Depends(require_auth),
):
    conn = _get_conn()
    try:
        from emuwarez_uploadrr.services.operational_actions import get_queue_action_plan
        result = get_queue_action_plan(item_id, conn)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
        return result
    finally:
        conn.close()


@router.post("/operational-queue/{item_id}/execute-safe-action")
def execute_safe_action(
    item_id: int,
    body: ExecuteSafeActionBody,
    _user: dict = Depends(require_auth),
):
    conn = _get_conn()
    try:
        from emuwarez_uploadrr.services.operational_actions import execute_safe_queue_action
        result = execute_safe_queue_action(item_id, conn, action=body.action)
        if not result.get("ok") and result.get("blocked"):
            raise HTTPException(
                status_code=409,
                detail=result.get("message", "Acción bloqueada — requiere flujo guiado"),
            )
        if not result.get("ok") and "no encontrado" in result.get("error", ""):
            raise HTTPException(status_code=404, detail=result.get("error"))
        return result
    finally:
        conn.close()


@router.get("/operational-queue/{item_id}/action-events")
def get_queue_action_events(
    item_id: int,
    limit: int = 50,
    _user: dict = Depends(require_auth),
):
    conn = _get_conn()
    try:
        from emuwarez_uploadrr.services.operational_actions import (
            get_queue_action_events,
            get_queue_action_plan,
        )
        plan_result = get_queue_action_plan(item_id, conn)
        if not plan_result.get("ok"):
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        events = get_queue_action_events(item_id, conn, limit=limit)
        return {"item_id": item_id, "events": events, "total": len(events)}
    finally:
        conn.close()
