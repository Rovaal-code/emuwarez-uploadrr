"""Real instance management endpoints (Phase 4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    AddInstanceRequest, InstanceSafeResponse, InstanceTestResponse, OkResponse, SyncResponse,
    UpdateInstanceRequest,
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
        from ...services.instances import list_instance_rows
        rows = list_instance_rows(conn)
    return [_row_to_safe(r) for r in rows]


@router.post("", response_model=OkResponse, status_code=201)
def create_instance(
    body: AddInstanceRequest,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from emuwarez_uploadrr.services.instances import add_instance
    with _get_conn() as conn:
        try:
            # Verify the *arr connection before persisting — a well-formed but
            # unreachable/unauthorized instance must not be created.
            iid = add_instance(conn, body.type, body.name, body.url, body.api_key, test_connection=True)
            if body.is_4k or body.is_anime:
                from ...services.instances import set_instance_flags
                set_instance_flags(iid, is_4k=body.is_4k, is_anime=body.is_anime, conn=conn)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OkResponse(message=f"Instancia '{body.name}' ({body.type}) creada con ID {iid}")


@router.put("/{instance_id}", response_model=InstanceSafeResponse)
def update_instance_endpoint(
    instance_id: int,
    body: UpdateInstanceRequest,
    current_user: dict = Depends(require_auth),
) -> InstanceSafeResponse:
    """Phase 11B — edit an existing instance in place (keeps its ID/history).
    Leaving api_key blank keeps the currently stored key, same convention
    as the Settings API keys."""
    from emuwarez_uploadrr.services.instances import get_instance, update_instance
    with _get_conn() as conn:
        inst = get_instance(conn, instance_id)
        if not inst:
            raise HTTPException(status_code=404, detail="Instancia no encontrada")
        try:
            update_instance(
                conn,
                instance_id,
                name=body.name,
                url=body.url,
                api_key=body.api_key,
                enabled=body.enabled,
                is_4k=body.is_4k,
                is_anime=body.is_anime,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        from ...services.instances import get_instance_row
        row = get_instance_row(instance_id, conn)
    return _row_to_safe(row)


@router.delete("/{instance_id}", response_model=OkResponse)
def delete_instance_endpoint(
    instance_id: int,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    """Borra la instancia y lo que se sincronizó de ella; sus subidas se quedan en el historial."""
    from emuwarez_uploadrr.services.instances import get_instance, remove_instance
    from emuwarez_uploadrr.services.library import SyncAlreadyRunning
    with _get_conn() as conn:
        inst = get_instance(conn, instance_id)
        if not inst:
            raise HTTPException(status_code=404, detail="Instancia no encontrada")
        try:
            remove_instance(conn, instance_id)
        except SyncAlreadyRunning:
            raise HTTPException(status_code=429, detail="Hay una sincronización de biblioteca en marcha; "
                                                        "borra la instancia cuando termine")
    return OkResponse(message=f"Instancia '{inst.name}' eliminada")


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
        username=result.get("username"),
        error=result.get("error"),
    )


@router.post("/{instance_id}/sync", response_model=SyncResponse)
def sync_instance(
    instance_id: int,
    current_user: dict = Depends(require_auth),
) -> SyncResponse:
    from emuwarez_uploadrr.services.instances import get_instance
    from emuwarez_uploadrr.services.library import (
        SyncAlreadyRunning,
        _lib_sync_guard,
        _set_lib_progress,
        recompute_after_sync,
    )
    from emuwarez_uploadrr.services.library import sync_instance as _sync
    with _get_conn() as conn:
        inst = get_instance(conn, instance_id)
        if not inst:
            raise HTTPException(status_code=404, detail="Instancia no encontrada")
        if inst.type not in ("radarr", "sonarr"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sincronización de biblioteca no soportada para el tipo '{inst.type}'.",
            )
        try:
            # Mismo candado y barra de progreso que la sincronización global.
            with _lib_sync_guard():
                # Otra vez ya con el candado: si se borró mientras, sincronizarla volvería a escribir lo suyo.
                if get_instance(conn, instance_id) is None:
                    raise HTTPException(status_code=404, detail="Instancia no encontrada")
                _set_lib_progress(phase=f"Sincronizando {inst.type.capitalize()}: {inst.name}…",
                                  instance=inst.name, instance_type=inst.type)
                try:
                    imported, missing = _sync(
                        conn, inst, include_episodes=True,
                        on_progress=lambda c: _set_lib_progress(imported=c),
                        on_total=lambda t: _set_lib_progress(total=t),
                    )
                finally:
                    recompute_after_sync(conn)
        except SyncAlreadyRunning:
            raise HTTPException(status_code=429, detail="Ya hay una sincronización de biblioteca en marcha")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error en sync: {exc}")
    return SyncResponse(
        imported=imported,
        missing=missing,
        instances=1,
        message=f"Instancia '{inst.name}' sincronizada: {imported} elementos, {missing} no disponibles",
    )
