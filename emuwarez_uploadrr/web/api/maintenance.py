"""Maintenance API endpoints — backup, restore and DB maintenance."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from ..dependencies import require_auth
from ..schemas import (
    BackupRequest,
    RestoreRequest,
    VacuumRequest,
)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/status")
def maintenance_status(current_user: dict = Depends(require_auth)) -> dict:
    """Estado general de mantenimiento: inventario config, estado BD y logs."""
    from emuwarez_uploadrr.services.backup_service import get_config_inventory, list_config_backups
    from emuwarez_uploadrr.services.maintenance_service import get_database_maintenance_status
    inventory = get_config_inventory()
    db_status = get_database_maintenance_status()
    backups = list_config_backups()
    return {
        "ok": True,
        "config_inventory": inventory,
        "database": db_status,
        "backups_count": len(backups),
        "latest_backup": backups[0] if backups else None,
    }


@router.post("/backup")
def create_backup(
    body: BackupRequest,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Crea un backup comprimido del directorio de configuración."""
    from emuwarez_uploadrr.services.backup_service import create_config_backup
    return create_config_backup(
        include_secrets=body.include_secrets,
        confirmation=body.confirmation,
    )


@router.get("/backups")
def list_backups(current_user: dict = Depends(require_auth)) -> dict:
    """Lista los backups existentes (nombre, ruta, tamaño, fecha)."""
    from emuwarez_uploadrr.services.backup_service import get_backup_dir, list_config_backups
    backups = list_config_backups()
    return {"ok": True, "backups": backups, "count": len(backups), "backup_dir": str(get_backup_dir())}


@router.get("/backups/{name}/download")
def download_backup(name: str, current_user: dict = Depends(require_auth)) -> FileResponse:
    """Descarga un backup de la carpeta de backups, por su nombre."""
    from emuwarez_uploadrr.services.backup_service import resolver_copia
    ruta = resolver_copia(name)
    if ruta is None:
        raise HTTPException(status_code=404, detail="No hay ningún backup con ese nombre")
    return FileResponse(ruta, media_type="application/gzip", filename=ruta.name)


@router.post("/backups/upload")
async def upload_backup(request: Request, current_user: dict = Depends(require_auth)) -> dict:
    """Guarda en la carpeta de backups el .tar.gz que va en el cuerpo de la petición (sin multipart).
    Restaurarlo es cosa de /restore, que lo toma de ahí."""
    from emuwarez_uploadrr.services.backup_service import LIMITE_SUBIDA_BYTES, CopiaSubida
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > LIMITE_SUBIDA_BYTES:
        raise HTTPException(status_code=413, detail=f"El archivo pasa de {LIMITE_SUBIDA_BYTES // 1024 ** 2} MB")
    subida = CopiaSubida()
    try:
        async for trozo in request.stream():
            await asyncio.to_thread(subida.escribir, trozo)  # la escritura a disco no frena el bucle
        return await asyncio.to_thread(subida.terminar)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        subida.descartar()


@router.post("/restore")
def restore_backup(
    body: RestoreRequest,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Restaura un backup por su nombre (el de /backups). dry_run=True por defecto; apply=True + confirmation para ejecutar."""
    from emuwarez_uploadrr.services.backup_service import resolver_copia, restore_config_backup
    ruta = resolver_copia(body.backup_name)
    if ruta is None:
        return {"ok": False, "dry_run": body.dry_run, "error": f"Backup no encontrado: {body.backup_name}"}
    return restore_config_backup(
        str(ruta),
        dry_run=body.dry_run,
        apply=body.apply,
        confirmation=body.confirmation,
    )


@router.post("/db/integrity-check")
def db_integrity_check(current_user: dict = Depends(require_auth)) -> dict:
    """Ejecuta PRAGMA integrity_check — solo lectura, sin confirmación."""
    from emuwarez_uploadrr.services.maintenance_service import run_database_integrity_check
    return run_database_integrity_check()


@router.post("/db/vacuum")
def db_vacuum(
    body: VacuumRequest,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Ejecuta VACUUM en la BD. dry_run=True por defecto."""
    from emuwarez_uploadrr.services.maintenance_service import run_database_vacuum
    return run_database_vacuum(
        dry_run=body.dry_run,
        apply=body.apply,
        confirmation=body.confirmation,
    )
