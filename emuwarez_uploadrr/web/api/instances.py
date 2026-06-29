"""Real instance management endpoints (Phase 4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    AddInstanceRequest, InstanceSafeResponse, InstanceTestResponse, OkResponse, SyncResponse,
)

router = APIRouter(prefix="/instances", tags=["instances"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _row_to_safe(row: dict) -> InstanceSafeResponse:
    from emuwarez_uploadrr.integrations.arr_base import safe_api_key
    return InstanceSafeResponse(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        url=row["url"],
        api_key_masked=safe_api_key(row.get("api_key") or ""),
        enabled=bool(row["enabled"]),
        is_4k=bool(row.get("is_4k") or 0),
        is_anime=bool(row.get("is_anime") or 0),
        last_test_status=row.get("last_test_status"),
        last_test_at=row.get("last_test_at"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


@router.get("", response_model=list[InstanceSafeResponse])
def list_instances(current_user: dict = Depends(require_auth)) -> list[InstanceSafeResponse]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM instances ORDER BY type, name").fetchall()
    return [_row_to_safe(dict(r)) for r in rows]


@router.post("", response_model=OkResponse, status_code=201)
def create_instance(
    body: AddInstanceRequest,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from emuwarez_uploadrr.services.instances import add_instance
    with _get_conn() as conn:
        try:
            iid = add_instance(conn, body.type, body.name, body.url, body.api_key)
            if body.is_4k or body.is_anime:
                conn.execute(
                    "UPDATE instances SET is_4k=?, is_anime=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (int(body.is_4k), int(body.is_anime), iid),
                )
                conn.commit()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OkResponse(message=f"Instancia '{body.name}' ({body.type}) creada con ID {iid}")


@router.post("/{instance_id}/test", response_model=InstanceTestResponse)
def test_instance(
    instance_id: int,
    current_user: dict = Depends(require_auth),
) -> InstanceTestResponse:
    from emuwarez_uploadrr.services.instances import get_instance, mark_instance_test_result, test_instance_safe
    with _get_conn() as conn:
        inst = get_instance(conn, instance_id)
        if not inst:
            raise HTTPException(status_code=404, detail="Instancia no encontrada")
        result = test_instance_safe(inst)
        mark_instance_test_result(conn, instance_id, result.get("ok", False), result.get("error"))
    return InstanceTestResponse(
        ok=bool(result.get("ok")),
        instance_id=instance_id,
        instance_name=inst.name,
        version=result.get("version"),
        error=result.get("error"),
    )


@router.post("/{instance_id}/sync", response_model=SyncResponse)
def sync_instance(
    instance_id: int,
    current_user: dict = Depends(require_auth),
) -> SyncResponse:
    from emuwarez_uploadrr.services.instances import get_instance
    from emuwarez_uploadrr.services.library import sync_instance as _sync
    with _get_conn() as conn:
        inst = get_instance(conn, instance_id)
        if not inst:
            raise HTTPException(status_code=404, detail="Instancia no encontrada")
        try:
            imported, missing = _sync(conn, inst, include_episodes=True)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error en sync: {exc}")
    return SyncResponse(
        imported=imported,
        missing=missing,
        instances=1,
        message=f"Instancia '{inst.name}' sincronizada: {imported} elementos, {missing} no disponibles",
    )
