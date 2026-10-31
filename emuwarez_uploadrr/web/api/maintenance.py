"""Maintenance API endpoints — backup, restore, DB and log cleanup."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..schemas import (
    BackupRequest,
    CleanupLogsRequest,
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


@router.post("/restore")
def restore_backup(
    body: RestoreRequest,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Restaura un backup. dry_run=True por defecto; apply=True + confirmation para ejecutar."""
    from emuwarez_uploadrr.services.backup_service import restore_config_backup
    return restore_config_backup(
        body.backup_path,
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


@router.post("/logs/cleanup")
def logs_cleanup(
    body: CleanupLogsRequest,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Elimina logs más antiguos de N días. dry_run=True por defecto."""
    from emuwarez_uploadrr.services.maintenance_service import cleanup_old_logs
    return cleanup_old_logs(
        days=body.days,
        dry_run=body.dry_run,
        apply=body.apply,
        confirmation=body.confirmation,
    )
