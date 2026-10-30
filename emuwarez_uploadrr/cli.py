"""Modern console entry point for eMuwarez Uploadrr.

This CLI is the functional mirror of the future web interface.  The original
single-path uploader is still available and is used for prepare/upload actions.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

from .database import connect, init_db, db_path, get_state
from .integrations.base import IntegrationError
from .models import LocalStatus, NomenclatureStatus, RequestStatus
from .services import instances as instance_service
from .services import library as library_service
from .services import requests as request_service
from .constants import LOG_DIR
from .services import tasks as task_service

MODERN_COMMANDS = {
    "instances", "sync", "library",
    "requests", "missing", "upload", "tasks", "logs",
    "db", "web", "nomenclature", "maintenance", "arr", "queue",
    "demo", "mkv-title",
}


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell) if cell is not None else ""))
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["─" * w for w in widths]))
    for row in rows:
        print(fmt.format(*["" if c is None else str(c) for c in row]))


def _status_arg(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lookup = {
        "available": LocalStatus.AVAILABLE.value,
        "disponible": LocalStatus.AVAILABLE.value,
        "missing": LocalStatus.MISSING.value,
        "faltante": LocalStatus.MISSING.value,
        "uploading": LocalStatus.UPLOADING.value,
        "subiendo": LocalStatus.UPLOADING.value,
        "uploaded": LocalStatus.UPLOADED.value,
        "subido": LocalStatus.UPLOADED.value,
        "error": LocalStatus.ERROR.value,
        "partial": LocalStatus.PARTIAL.value,
        "parcial": LocalStatus.PARTIAL.value,
    }
    return lookup.get(value.lower(), value)


def _request_arg(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lookup = {
        "none": RequestStatus.NONE.value,
        "sin": RequestStatus.NONE.value,
        "compatible": RequestStatus.COMPATIBLE.value,
        "partial": RequestStatus.PARTIAL.value,
        "parcial": RequestStatus.PARTIAL.value,
        "not-compatible": RequestStatus.NOT_COMPATIBLE.value,
        "no-compatible": RequestStatus.NOT_COMPATIBLE.value,
        "filled": RequestStatus.FILLED.value,
        "llena": RequestStatus.FILLED.value,
    }
    return lookup.get(value.lower(), value)


def _nomenclature_arg(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lookup = {
        "correct": NomenclatureStatus.CORRECT.value,
        "correcta": NomenclatureStatus.CORRECT.value,
        "missing": NomenclatureStatus.NOT_ADAPTED.value,
        "not-adapted": NomenclatureStatus.NOT_ADAPTED.value,
        "no-adaptada": NomenclatureStatus.NOT_ADAPTED.value,
        "na": NomenclatureStatus.NA.value,
        "n/a": NomenclatureStatus.NA.value,
    }
    return lookup.get(value.lower(), value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emuwarez-uploadrr",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="CLI modular de eMuwarez Uploadrr. Espejo funcional de la futura interfaz web.",
    )
    parser.add_argument("--db", default=str(db_path()), help="Ruta de SQLite. Por defecto: ~/.config/emuwarez-renamer/emuwarez_uploadrr.db")
    sub = parser.add_subparsers(dest="command", required=True)

    # configure / doctor / test-apis se borraron con el CLI antiguo (2026-08-01):
    # los tres eran envoltorios de sus asistentes interactivos y los tres tienen
    # equivalente en la aplicación web (asistente de configuración, pestaña
    # Diagnóstico y los botones "Probar conexión"). El diagnóstico del runtime
    # sigue disponible aquí como `web doctor`.

    p_db = sub.add_parser("db", help="Operaciones de base de datos local")
    db_sub = p_db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("init", help="Crear/actualizar tablas SQLite")
    db_sub.add_parser("path", help="Mostrar ruta de SQLite")

    p_inst = sub.add_parser("instances", help="Gestionar instancias Radarr/Sonarr")
    inst_sub = p_inst.add_subparsers(dest="instances_command", required=True)
    inst_sub.add_parser("list", help="Listar instancias")
    p_add = inst_sub.add_parser("add", help="Añadir o actualizar instancia")
    p_add.add_argument("type", choices=["radarr", "sonarr"])
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--api-key", required=True)
    p_test = inst_sub.add_parser("test", help="Probar conexión")
    p_test.add_argument("id", nargs="?", type=int)
    p_remove = inst_sub.add_parser("remove", help="Eliminar instancia")
    p_remove.add_argument("id", type=int)

    p_sync = sub.add_parser("sync", help="Sincronizar biblioteca desde Radarr/Sonarr")
    p_sync.add_argument("--episodes", action="store_true", help="En Sonarr, importar también episodios")

    p_lib = sub.add_parser("library", help="Biblioteca local sincronizada")
    lib_sub = p_lib.add_subparsers(dest="library_command", required=True)
    p_lib_list = lib_sub.add_parser("list", help="Listar biblioteca")
    p_lib_list.add_argument("--status")
    p_lib_list.add_argument("--request")
    p_lib_list.add_argument("--nomenclature")
    p_lib_list.add_argument("--type")
    p_lib_list.add_argument("--search")
    p_lib_list.add_argument("--limit", type=int, default=50)
    p_lib_show = lib_sub.add_parser("show", help="Ver detalle de item")
    p_lib_show.add_argument("id", type=int)
    # Phase 8A
    p_lib_verify = lib_sub.add_parser("verify-files", help="Verificar existencia de archivos en disco (solo lectura)")
    p_lib_verify.add_argument("--limit", type=int, default=None, help="Máximo de items a verificar")
    p_lib_verify.add_argument("--status", default=None, help="Filtrar por estado (ej: Disponible)")
    p_lib_vfile = lib_sub.add_parser("verify-file", help="Verificar un archivo concreto")
    p_lib_vfile.add_argument("id", type=int)
    lib_sub.add_parser("recommendations", help="Recalcular recomendaciones para toda la biblioteca")
    p_lib_rec = lib_sub.add_parser("recommendation", help="Ver recomendación de un item")
    p_lib_rec.add_argument("id", type=int)
    p_lib_diag = lib_sub.add_parser("diagnostics", help="Listar diagnósticos de biblioteca")
    p_lib_diag.add_argument("--limit", type=int, default=50)
    p_lib_diag.add_argument("--status", default=None)

    p_req = sub.add_parser("requests", help="Peticiones EMU")
    req_sub = p_req.add_subparsers(dest="requests_command", required=True)
    p_req_sync = req_sub.add_parser("sync", help="Sincronizar peticiones EMU. Mínimo 1 vez/hora salvo --force")
    p_req_sync.add_argument("--force", action="store_true", help="Forzar sincronización ignorando el límite de una hora")
    p_req_list = req_sub.add_parser("list", help="Listar peticiones sincronizadas")
    p_req_list.add_argument("--search")
    p_req_list.add_argument("--limit", type=int, default=50)
    p_req_show = req_sub.add_parser("show", help="Detalle de petición y cruce con biblioteca")
    p_req_show.add_argument("id", type=int)
    req_sub.add_parser("match", help="Recalcular cruces petición/biblioteca")
    p_req_reviewed = req_sub.add_parser("mark-reviewed", help="Marcar petición como revisada")
    p_req_reviewed.add_argument("id", type=int)
    p_req_create = req_sub.add_parser("create", help="Preparado para futuro: crear petición EMU")
    p_req_create.add_argument("library_id", type=int)
    p_req_create.add_argument("--dry-run", action="store_true")
    # Phase 8B
    p_req_readiness = req_sub.add_parser("readiness", help="Listar readiness de peticiones o detalle de una")
    p_req_readiness.add_argument("id", type=int, nargs="?", default=None, help="ID de petición (opcional)")
    p_req_readiness.add_argument("--limit", type=int, default=50)
    req_sub.add_parser("readiness-refresh", help="Recalcular readiness para todas las peticiones")
    p_req_candidates = req_sub.add_parser("candidates", help="Candidatos locales para una petición")
    p_req_candidates.add_argument("id", type=int)

    p_missing = sub.add_parser("missing", help="Contenido faltante")
    missing_sub = p_missing.add_subparsers(dest="missing_command", required=True)
    p_missing_list = missing_sub.add_parser("list", help="Listar faltantes")
    p_missing_list.add_argument("--limit", type=int, default=50)
    p_missing_req = missing_sub.add_parser("create-request", help="Preparado para futuro: crear petición EMU desde faltante")
    p_missing_req.add_argument("library_id", type=int)
    p_missing_req.add_argument("--dry-run", action="store_true")
    # Phase 8A
    p_missing_diag = missing_sub.add_parser("diagnostics", help="Faltantes enriquecidos con queue/history/recomendación")
    p_missing_diag.add_argument("--limit", type=int, default=50)

    # Phase 8A — ARR health
    p_arr = sub.add_parser("arr", help="Diagnóstico avanzado Radarr/Sonarr")
    arr_sub = p_arr.add_subparsers(dest="arr_command", required=True)
    arr_sub.add_parser("health", help="Mostrar salud de instancias ARR")
    p_arr_refresh = arr_sub.add_parser("refresh-health", help="Refrescar queue e historial ARR y actualizar diagnósticos")
    p_arr_refresh.add_argument("--no-queue", action="store_true", help="Omitir lectura de queue")
    p_arr_refresh.add_argument("--no-history", action="store_true", help="Omitir lectura de historial")
    p_arr_refresh.add_argument("--history-size", type=int, default=100, help="Número de entradas de historial (default: 100)")

    p_queue = sub.add_parser("queue", help="Cola operativa unificada de acciones")
    queue_sub = p_queue.add_subparsers(dest="queue_command", required=True)
    queue_sub.add_parser("summary", help="Resumen de la cola operativa")
    p_queue_list = queue_sub.add_parser("list", help="Listar items de la cola")
    p_queue_list.add_argument("--status", help="Filtrar por status (open/ready/waiting/blocked)")
    p_queue_list.add_argument("--action", help="Filtrar por acción")
    p_queue_list.add_argument("--type", dest="item_type", help="Filtrar por item_type")
    p_queue_list.add_argument("--limit", type=int, default=50, help="Número máximo de items (default: 50)")
    queue_sub.add_parser("refresh", help="Reconstruir cola desde todas las fuentes")
    p_queue_show = queue_sub.add_parser("show", help="Detalle de un item de la cola")
    p_queue_show.add_argument("id", type=int, help="ID del item de la cola")
    p_queue_resolve = queue_sub.add_parser("resolve", help="Marcar item como resuelto")
    p_queue_resolve.add_argument("id", type=int, help="ID del item de la cola")
    p_queue_resolve.add_argument("--reason", help="Motivo opcional")
    p_queue_ignore = queue_sub.add_parser("ignore", help="Ignorar item de la cola")
    p_queue_ignore.add_argument("id", type=int, help="ID del item de la cola")
    p_queue_ignore.add_argument("--reason", help="Motivo opcional")
    p_queue_actions = queue_sub.add_parser("actions", help="Listar acciones disponibles para un item")
    p_queue_actions.add_argument("id", type=int, help="ID del item de la cola")
    p_queue_plan = queue_sub.add_parser("action-plan", help="Ver plan de acción guiada para un item")
    p_queue_plan.add_argument("id", type=int, help="ID del item de la cola")
    p_queue_exec = queue_sub.add_parser("execute-safe", help="Ejecutar acción segura (solo read-only/local)")
    p_queue_exec.add_argument("id", type=int, help="ID del item de la cola")
    p_queue_exec.add_argument("--action", default=None, help="Acción: verify_file, refresh_queue_item, view_plan")
    p_queue_events = queue_sub.add_parser("events", help="Ver historial de eventos de acción de un item")
    p_queue_events.add_argument("id", type=int, help="ID del item de la cola")
    p_queue_events.add_argument("--limit", type=int, default=20, help="Número máximo de eventos")

    p_nomenclature = sub.add_parser("nomenclature", help="Previsualización de nomenclatura eMuwarez (no modifica archivos)")
    nom_sub = p_nomenclature.add_subparsers(dest="nomenclature_command", required=True)
    p_nom_preview = nom_sub.add_parser("preview", help="Generar propuesta de nomenclatura para un item")
    p_nom_preview.add_argument("id", type=int, help="ID del library_item")
    p_nom_preview.add_argument("--force", action="store_true", help="Forzar regeneración aunque ya exista propuesta")
    p_nom_show = nom_sub.add_parser("show", help="Mostrar última propuesta de nomenclatura")
    p_nom_show.add_argument("id", type=int, help="ID del library_item")
    p_nom_apply = nom_sub.add_parser("apply", help="Adaptar nomenclatura renombrando el archivo original")
    p_nom_apply.add_argument("id", type=int, help="ID del library_item")
    p_nom_apply.add_argument("--dry-run", action="store_true", help="Solo previsualización (no escribe nada)")
    p_nom_apply.add_argument("--apply", action="store_true", dest="nom_apply", help="Aplicar cambios reales")
    p_nom_apply.add_argument("--confirm", metavar="TOKEN", dest="confirm_token", help="Token de confirmación: APLICAR_NOMENCLATURA")
    # Phase 10A subcommands
    nom_sub.add_parser("sources", help="Listar sources eMuwarez disponibles")
    nom_sub.add_parser("providers", help="Listar providers eMuwarez disponibles")
    p_nom_fields = nom_sub.add_parser("fields", help="Ver campos editables de nomenclatura para un item")
    p_nom_fields.add_argument("id", type=int)
    p_nom_pfields = nom_sub.add_parser("preview-fields", help="Previsualizar nombre con campos dados (JSON)")
    p_nom_pfields.add_argument("id", type=int)
    p_nom_pfields.add_argument("--fields-json", dest="fields_json", help="JSON de campos editables")

    # Phase 10A — mkv-title command
    p_mkv = sub.add_parser("mkv-title", help="Título interno MKV (Phase 10A)")
    mkv_sub = p_mkv.add_subparsers(dest="mkv_command", required=True)
    p_mkv_prev = mkv_sub.add_parser("preview", help="Previsualizar título interno MKV sin modificar nada")
    p_mkv_prev.add_argument("id", type=int, help="ID del library_item")
    p_mkv_apply = mkv_sub.add_parser("apply", help="Aplicar título interno MKV a prepared_path")
    p_mkv_apply.add_argument("id", type=int, help="ID del library_item")
    p_mkv_apply.add_argument("--dry-run", action="store_true", default=True)
    p_mkv_apply.add_argument("--apply", action="store_true", dest="mkv_apply")
    p_mkv_apply.add_argument("--confirm", metavar="TOKEN", dest="mkv_confirm",
                             help="Token de confirmación: APLICAR_TITULO_MKV")

    p_upload = sub.add_parser("upload", help="Subir contenido / preflight Uploadrr")
    up_sub = p_upload.add_subparsers(dest="upload_command")
    p_up_preflight = up_sub.add_parser("preflight", help="Validar precondiciones de subida (no ejecuta Uploadrr)")
    p_up_preflight.add_argument("id", type=int, help="ID del library_item")
    p_up_preflight.add_argument("--request-id", type=int, default=None, help="ID opcional de request_item vinculada")
    p_up_job = up_sub.add_parser("job", help="Ver detalle de un upload job/preflight")
    p_up_job.add_argument("id", type=int, help="ID del upload job")
    p_up_status = up_sub.add_parser("status", help="Alias de 'job': ver detalle/estado de un upload job")
    p_up_status.add_argument("id", type=int, help="ID del upload job")
    p_up_jobs = up_sub.add_parser("jobs", help="Listar upload jobs/preflights")
    p_up_jobs.add_argument("--status", default=None, help="Filtrar por estado (ready, running, completed, failed, cancelled)")
    p_up_logs = up_sub.add_parser("logs", help="Ver logs de un upload job")
    p_up_logs.add_argument("id", type=int, help="ID del upload job")
    p_up_logs.add_argument("--limit", type=int, default=200, help="Número máximo de entradas")
    p_up_start = up_sub.add_parser("start", help="Iniciar/previsualizar ejecución de Uploadrr")
    p_up_start.add_argument("id", type=int, help="ID del upload job")
    p_up_start.add_argument("--dry-run", action="store_true", default=True, help="Solo previsualización (por defecto)")
    p_up_start.add_argument("--apply", action="store_true", dest="up_apply", help="Iniciar ejecución real")
    p_up_start.add_argument("--confirm", metavar="TOKEN", dest="up_confirm", help=f"Token de confirmación: INICIAR_UPLOADRR")
    p_up_cancel = up_sub.add_parser("cancel", help="Cancelar un upload job en ejecución")
    p_up_cancel.add_argument("id", type=int, help="ID del upload job")
    p_up_artifacts = up_sub.add_parser("artifacts", help="Ver artefactos de un upload job")
    p_up_artifacts.add_argument("id", type=int, help="ID del upload job")
    p_up_retry = up_sub.add_parser("retry", help="Reintentar un upload job failed/cancelled")
    p_up_retry.add_argument("id", type=int, help="ID del upload job original")
    p_up_retry.add_argument("--dry-run", action="store_true", default=True, help="Solo previsualización (por defecto)")
    p_up_retry.add_argument("--apply", action="store_true", dest="up_apply", help="Crear job nuevo y ejecutar")
    p_up_retry.add_argument("--confirm", metavar="TOKEN", dest="up_confirm", help="Token: INICIAR_UPLOADRR")

    p_tasks = sub.add_parser("tasks", help="Tareas ejecutadas")
    tasks_sub = p_tasks.add_subparsers(dest="tasks_command", required=True)
    p_tasks_list = tasks_sub.add_parser("list", help="Listar últimas tareas")
    p_tasks_list.add_argument("--limit", type=int, default=20)

    p_logs = sub.add_parser("logs", help="Logs del uploader heredado")
    p_logs.add_argument("--tail", type=int, default=80)

    p_web = sub.add_parser("web", help="Servidor web backend FastAPI")
    web_sub = p_web.add_subparsers(dest="web_command", required=True)
    web_sub.add_parser("info", help="Mostrar información del servidor web")
    p_serve = web_sub.add_parser("serve", help="Arrancar servidor web")
    p_serve.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=9494, help="Puerto (default: 9494)")
    p_serve.add_argument("--reload", action="store_true", help="Recarga automática (solo desarrollo)")
    web_sub.add_parser("setup-status", help="Mostrar estado del asistente de configuración")
    web_sub.add_parser("doctor", help="Diagnóstico del runtime de la aplicación")
    p_create_admin = web_sub.add_parser("create-admin", help="Crear usuario administrador web")
    p_create_admin.add_argument("--username", required=True, help="Nombre de usuario admin")

    p_reset_password = web_sub.add_parser("reset-password", help="Restablecer la contraseña de un usuario existente (requiere acceso al servidor)")
    p_reset_password.add_argument("--username", required=True, help="Nombre de usuario a restablecer")

    p_maint = sub.add_parser("maintenance", help="Mantenimiento: backup, configuración, BD y logs")
    maint_sub = p_maint.add_subparsers(dest="maintenance_command", required=True)

    maint_sub.add_parser("status", help="Estado general: inventario config, BD y backups")

    p_backup = maint_sub.add_parser("backup", help="Crear backup comprimido del directorio de configuración")
    p_backup.add_argument(
        "--include-secrets", action="store_true",
        help="Incluir las claves (sin esto van vacías, y sin el config.yaml ni las cookies de Uploadrr-EMU)",
    )
    p_backup.add_argument("--confirm", metavar="TOKEN", dest="confirm", help="Token de confirmación para incluir secretos: RESTAURAR_CONFIG")

    maint_sub.add_parser("list-backups", help="Listar backups existentes")

    p_restore = maint_sub.add_parser("restore", help="Restaurar un backup")
    p_restore.add_argument("backup_path", help="Ruta del archivo .tar.gz a restaurar")
    p_restore.add_argument("--dry-run", action="store_true", default=True, help="Solo previsualización (por defecto)")
    p_restore.add_argument("--apply", action="store_true", dest="maint_apply", help="Aplicar restauración real")
    p_restore.add_argument("--confirm", metavar="TOKEN", dest="confirm", help="Token: RESTAURAR_CONFIG")

    p_export = maint_sub.add_parser("export-settings", help="Exportar ajustes (secretos enmascarados por defecto)")
    p_export.add_argument("--include-secrets", action="store_true", help="Incluir secretos sin enmascarar")
    p_export.add_argument("--confirm", metavar="TOKEN", dest="confirm", help="Token para secretos: EXPORTAR_SECRETOS")

    maint_sub.add_parser("db-integrity", help="PRAGMA integrity_check (solo lectura)")

    p_vacuum = maint_sub.add_parser("db-vacuum", help="VACUUM en la BD SQLite")
    p_vacuum.add_argument("--dry-run", action="store_true", default=True, help="Solo previsualización (por defecto)")
    p_vacuum.add_argument("--apply", action="store_true", dest="maint_apply", help="Ejecutar VACUUM real")
    p_vacuum.add_argument("--confirm", metavar="TOKEN", dest="confirm", help="Token: MANTENIMIENTO_DB")

    p_cleanup = maint_sub.add_parser("cleanup-logs", help="Eliminar logs internos antiguos")
    p_cleanup.add_argument("--days", type=int, default=30, help="Eliminar logs más antiguos de N días (default: 30)")
    p_cleanup.add_argument("--dry-run", action="store_true", default=True, help="Solo previsualización (por defecto)")
    p_cleanup.add_argument("--apply", action="store_true", dest="maint_apply", help="Ejecutar limpieza real")
    p_cleanup.add_argument("--confirm", metavar="TOKEN", dest="confirm", help="Token: LIMPIAR_LOGS")

    # Phase 9B — Demo / E2E dev commands (clearly marked, require explicit confirmation)
    p_demo = sub.add_parser("demo", help="[DEV] Datos demo para E2E controlado. Requiere confirmación explícita.")
    demo_sub = p_demo.add_subparsers(dest="demo_command", required=True)
    p_demo_seed = demo_sub.add_parser("seed", help="Sembrar datos demo en una BD temporal (requiere --confirm DEMO_SEED)")
    p_demo_seed.add_argument("--media-root", required=True, help="Raíz de media simulada (ej: /data/media o tmpdir/data/media)")
    p_demo_seed.add_argument("--prepared-root", required=True, help="Raíz de archivos preparados (ej: /data/uploads/emu)")
    p_demo_seed.add_argument("--confirm", metavar="TOKEN", dest="confirm_token",
                             required=True, help="Token de seguridad obligatorio: DEMO_SEED")
    p_demo_reset = demo_sub.add_parser("reset", help="Eliminar datos demo de la BD (requiere --confirm DEMO_RESET)")
    p_demo_reset.add_argument("--confirm", metavar="TOKEN", dest="confirm_token",
                              required=True, help="Token de seguridad obligatorio: DEMO_RESET")

    return parser


def _open_conn(args) -> Any:
    conn = connect(Path(args.db))
    init_db(conn)
    return conn


def _target_to_path(conn, target: str) -> str:
    if target.isdigit():
        item = library_service.get_library_item(conn, int(target))
        if not item:
            raise SystemExit(f"No existe LibraryItem con ID {target}")
        if not item.get("path"):
            raise SystemExit(f"El item {target} no tiene ruta local utilizable")
        return str(item["path"])
    return target


def cmd_instances(args) -> int:
    with _open_conn(args) as conn:
        if args.instances_command == "add":
            item_id = instance_service.add_instance(conn, args.type, args.name, args.url, args.api_key)
            print(f"✓ Instancia guardada con ID {item_id}")
            return 0
        if args.instances_command == "list":
            rows = [
                [i.id, i.type, i.name, i.url, "sí" if i.enabled else "no"]
                for i in instance_service.list_instances(conn)
            ]
            _print_table(["ID", "Tipo", "Nombre", "URL", "Activa"], rows)
            return 0
        if args.instances_command == "test":
            items = [instance_service.get_instance(conn, args.id)] if args.id else instance_service.list_instances(conn)
            items = [i for i in items if i]
            if not items:
                print("No hay instancias configuradas.")
                return 1
            ok = True
            for item in items:
                try:
                    status = instance_service.test_instance(item)
                    version = status.get("version") or status.get("appVersion") or "OK"
                    print(f"✓ {item.type} {item.name}: conectado ({version})")
                except Exception as exc:
                    ok = False
                    print(f"✗ {item.type} {item.name}: {exc}")
            return 0 if ok else 1
        if args.instances_command == "remove":
            print("✓ Eliminada" if instance_service.remove_instance(conn, args.id) else "No encontrada")
            return 0
    return 1


def cmd_sync(args) -> int:
    with _open_conn(args) as conn:
        result = library_service.sync_all(conn, include_episodes=args.episodes)
        print(f"✓ Biblioteca sincronizada: {result['imported']} elementos, {result['missing']} faltantes, {result['instances']} instancias")
    return 0


def cmd_library(args) -> int:
    with _open_conn(args) as conn:
        if args.library_command == "list":
            rows = library_service.list_library(
                conn,
                status=_status_arg(args.status),
                request=_request_arg(args.request),
                nomenclature=_nomenclature_arg(args.nomenclature),
                item_type=args.type,
                search=args.search,
                limit=args.limit,
            )
            _print_table(
                ["ID", "Tipo", "Estado", "Petición", "Nomenclatura", "Origen", "Título"],
                [[r["id"], r["item_type"], r["local_status"], r["request_status"], r["nomenclature_status"], r["instance_name"], r["title"]] for r in rows],
            )
            return 0
        if args.library_command == "show":
            item = library_service.get_library_item(conn, args.id)
            if not item:
                print("No encontrado")
                return 1
            for key in [
                "id", "title", "item_type", "year", "instance_name", "local_status", "request_status",
                "nomenclature_status", "tmdb_id", "imdb_id", "quality", "resolution", "source", "path",
                "file_exists", "file_verified_at", "arr_queue_status", "recommended_action", "diagnostic_summary",
            ]:
                print(f"{key:26} {item.get(key) if item.get(key) is not None else ''}")
            return 0
        if args.library_command == "verify-files":
            from .services.library_verification import verify_library_files
            filters: dict = {}
            if getattr(args, "status", None):
                filters["status"] = args.status
            result = verify_library_files(conn, filters=filters, limit=getattr(args, "limit", None))
            print(f"✓ Verificados: {result['items_checked']}  |  Encontrados: {result['files_found']}  |  Errores: {result['errors']}  |  Advertencias: {result['warnings']}")
            return 0
        if args.library_command == "verify-file":
            from .services.library_verification import verify_library_item_file
            result = verify_library_item_file(args.id, conn)
            if result.get("error"):
                print(f"✗ {result['error']}")
                return 1
            print(f"ID {args.id}: {result.get('title')}")
            print(f"  path:       {result.get('path') or '–'}")
            print(f"  existe:     {'sí' if result.get('file_exists') else 'no'}")
            print(f"  es vídeo:   {'sí' if result.get('file_is_video') else 'no'}")
            print(f"  tamaño:     {result.get('file_size_on_disk') or '–'} bytes")
            if result.get("file_verification_error"):
                print(f"  error:      {result['file_verification_error']}")
            return 0
        if args.library_command == "recommendations":
            from .services.recommendations import refresh_recommendations
            result = refresh_recommendations(conn)
            print(f"✓ Recomendaciones recalculadas: {result['items_updated']}  |  Errores: {result['errors']}")
            return 0
        if args.library_command == "recommendation":
            from .services.recommendations import get_recommendation_for_item
            rec = get_recommendation_for_item(args.id, conn)
            if not rec:
                print("No encontrado")
                return 1
            print(f"ID {args.id}: {rec.get('title')}")
            print(f"  diagnóstico:       {rec.get('diagnostic_status') or '–'}")
            print(f"  resumen:           {rec.get('diagnostic_summary') or '–'}")
            print(f"  acción recomend.:  {rec.get('recommended_action') or '–'}")
            reasons = rec.get("recommendation_reasons") or []
            if reasons:
                print("  razones:")
                for r in reasons:
                    print(f"    - {r}")
            return 0
        if args.library_command == "diagnostics":
            limit = getattr(args, "limit", 50)
            status_filter = getattr(args, "status", None)
            where = ""
            params: list = []
            if status_filter:
                where = "WHERE local_status = ?"
                params.append(status_filter)
            rows = conn.execute(
                f"""
                SELECT id, title, local_status, file_exists, arr_queue_status,
                       diagnostic_status, recommended_action
                FROM library_items {where} ORDER BY updated_at DESC LIMIT ?
                """,
                params + [limit],
            ).fetchall()
            if not rows:
                if not conn.execute("SELECT COUNT(*) FROM library_items").fetchone()[0]:
                    print("Biblioteca vacía. Ejecuta: python3 emuwarez_uploader.py sync")
                else:
                    print("Sin resultados con ese filtro.")
                return 0
            _print_table(
                ["ID", "Estado", "Archivo", "Queue", "Diagnóstico", "Acción recomendada", "Título"],
                [
                    [
                        r["id"],
                        r["local_status"],
                        "OK" if r["file_exists"] else ("–" if r["file_exists"] is None else "NO"),
                        r["arr_queue_status"] or "–",
                        r["diagnostic_status"] or "–",
                        r["recommended_action"] or "–",
                        r["title"],
                    ]
                    for r in rows
                ],
            )
            return 0
    return 1


def cmd_requests(args) -> int:
    with _open_conn(args) as conn:
        if args.requests_command == "sync":
            result = request_service.sync_emu_requests(conn, force=args.force)
            if result.get("status") == "throttled":
                wait = int(result["wait_seconds"])
                print(f"⚠ Peticiones actualizadas hace menos de una hora. Disponible en {wait // 60} min {wait % 60} s.")
                return 0
            imported = result.get("imported", 0)
            matched = result.get("matched", 0)
            print(f"✓ Peticiones sincronizadas: {imported} importadas, {matched} cruces")
            return 0
        if args.requests_command == "list":
            rows = request_service.list_requests(conn, limit=args.limit, search=args.search)
            _print_table(
                ["ID", "Estado", "Resolución", "Source", "Puntos", "Título"],
                [[r["id"], r.get("emu_status"), r.get("requested_resolution"), r.get("requested_source"), r.get("points"), r["title"]] for r in rows],
            )
            return 0
        if args.requests_command == "show":
            req = request_service.get_request(conn, args.id)
            if not req:
                print("No encontrada")
                return 1
            for key in ["id", "emu_id", "title", "category", "requested_resolution", "requested_source", "emu_status", "points", "comments", "tmdb_id", "imdb_id", "url"]:
                print(f"{key:24} {req.get(key) or ''}")
            match = request_service.get_match_for_request(conn, args.id)
            if match:
                print("\nCruce con biblioteca")
                for key in ["status", "confidence", "library_title", "local_status", "local_resolution", "local_source", "local_path"]:
                    print(f"{key:24} {match.get(key) or ''}")
                if match.get("reasons"):
                    print("\nMotivos:")
                    for line in str(match["reasons"]).splitlines():
                        print(f"  - {line}")
            return 0
        if args.requests_command == "match":
            count = request_service.match_all_requests(conn)
            print(f"✓ Cruces recalculados: {count}")
            return 0
        if args.requests_command == "mark-reviewed":
            found = request_service.mark_request_reviewed(conn, args.id)
            if found:
                print(f"✓ Petición {args.id} marcada como revisada")
            else:
                print(f"✗ Petición {args.id} no encontrada")
            return 0 if found else 1
        if args.requests_command == "create":
            print("⚠ Crear peticiones EMU está preparado, pero no activado todavía.")
            print("  Falta capturar la request real desde DevTools > Network en eMuwarez.")
            return 0
        # Phase 8B
        if args.requests_command == "readiness-refresh":
            from .services.request_readiness import refresh_request_readiness
            result = refresh_request_readiness(conn)
            print(f"✓ Readiness recalculado: {result['items_updated']} peticiones  |  errores: {result['errors']}")
            return 0
        if args.requests_command == "readiness":
            from .services.request_readiness import list_request_readiness, get_request_readiness
            req_id = getattr(args, "id", None)
            if req_id:
                data = get_request_readiness(req_id, conn)
                if not data:
                    print(f"Sin readiness para petición {req_id}. Ejecuta: python3 emuwarez_uploader.py requests readiness-refresh")
                    return 1
                print(f"Petición: {data.get('title')} (ID {req_id})")
                print(f"  Estado readiness : {data['status']}")
                print(f"  Acción           : {data.get('recommended_action') or '—'}")
                print(f"  Compat. score    : {data.get('compatibility_score')}")
                print(f"  Readiness score  : {data.get('upload_readiness_score')}")
                print(f"  Candidato local  : #{data.get('best_library_item_id') or '—'}")
                if data.get("blockers"):
                    print("  Bloqueadores:")
                    for b in data["blockers"]:
                        print(f"    - {b}")
                return 0
            limit = getattr(args, "limit", 50)
            rows = list_request_readiness(conn, limit=limit)
            if not rows:
                print("Sin readiness calculado. Ejecuta: python3 emuwarez_uploader.py requests readiness-refresh")
                return 0
            _print_table(
                ["ID", "Título", "Estado", "Acción", "Candidato"],
                [
                    [
                        r["request_item_id"],
                        (r.get("title") or "")[:40],
                        r["status"],
                        r.get("recommended_action") or "—",
                        f"#{r.get('best_library_item_id')}" if r.get("best_library_item_id") else "—",
                    ]
                    for r in rows
                ],
            )
            return 0
        if args.requests_command == "candidates":
            from .services.request_readiness import get_candidates_for_request
            items = get_candidates_for_request(args.id, conn)
            if not items:
                print(f"Sin candidatos para petición {args.id}. Ejecuta: python3 emuwarez_uploader.py requests readiness-refresh")
                return 0
            _print_table(
                ["Rank", "Lib ID", "Título", "Compat.", "Readiness", "Acción"],
                [
                    [
                        c["candidate_rank"],
                        c["library_item_id"],
                        (c.get("lib_title") or "")[:35],
                        f"{c.get('compatibility_score', 0):.0f}",
                        c.get("readiness_status") or "—",
                        c.get("recommended_action") or "—",
                    ]
                    for c in items
                ],
            )
            return 0
    return 1


def cmd_missing(args) -> int:
    with _open_conn(args) as conn:
        if args.missing_command == "list":
            rows = library_service.list_missing(conn, limit=args.limit)
            _print_table(
                ["ID", "Tipo", "Petición", "Origen", "Título"],
                [[r["id"], r["item_type"], r["request_status"], r["instance_name"], r["title"]] for r in rows],
            )
            return 0
        if args.missing_command == "create-request":
            print("⚠ Crear peticiones EMU está preparado, pero no activado todavía.")
            print("  Cuando capturemos el POST real, este comando usará el LibraryItem indicado.")
            return 0
        if args.missing_command == "diagnostics":
            from .models import LocalStatus
            limit = getattr(args, "limit", 50)
            missing_statuses = list(LocalStatus.not_available())
            placeholders = ",".join("?" * len(missing_statuses))
            rows = conn.execute(
                f"""
                SELECT id, title, local_status, arr_queue_status, arr_queue_progress,
                       arr_queue_error, arr_history_error, diagnostic_status, recommended_action
                FROM library_items WHERE local_status IN ({placeholders})
                ORDER BY updated_at DESC LIMIT ?
                """,
                missing_statuses + [limit],
            ).fetchall()
            if not rows:
                print("Sin faltantes en biblioteca. Ejecuta: python3 emuwarez_uploader.py sync")
                return 0
            _print_table(
                ["ID", "Estado local", "Queue", "Diagnóstico", "Acción recomendada", "Título"],
                [
                    [
                        r["id"],
                        r["local_status"],
                        r["arr_queue_status"] or "–",
                        r["diagnostic_status"] or "–",
                        r["recommended_action"] or "–",
                        r["title"],
                    ]
                    for r in rows
                ],
            )
            return 0
    return 1


def cmd_arr(args) -> int:
    with _open_conn(args) as conn:
        instances = instance_service.list_instances(conn, enabled_only=True)
        if not instances:
            print("⚠ Sin instancias Radarr/Sonarr habilitadas. Añade una con:")
            print("  python3 emuwarez_uploader.py instances add radarr --name ... --url ... --api-key ...")
            return 0

        if args.arr_command == "health":
            from .services.arr_health import collect_arr_health
            result = collect_arr_health(conn)
            summary = result.get("summary", {})
            print(f"\n── Salud Radarr/Sonarr ──────────────────────────────────")
            print(f"  Radarr: {summary.get('radarr', 0)} instancias  |  Sonarr: {summary.get('sonarr', 0)} instancias")
            print(f"  OK: {summary.get('ok', 0)}  |  Warning: {summary.get('warning', 0)}  |  Error: {summary.get('error', 0)}")
            print()
            for inst in result.get("instances", []):
                mark = "✓" if inst.get("ok") else "✗"
                status = inst.get("health_status", "error")
                version = inst.get("version") or ""
                err = inst.get("error") or ""
                print(f"  {mark} [{inst.get('instance_type', '?')}] {inst.get('instance_name', '?')}  {version}  {err}")
            return 0

        if args.arr_command == "refresh-health":
            from .services.arr_health import collect_arr_health, refresh_arr_queue_diagnostics, refresh_arr_history_diagnostics
            include_queue = not getattr(args, "no_queue", False)
            include_history = not getattr(args, "no_history", False)
            history_size = getattr(args, "history_size", 100)
            print("Comprobando salud ARR...")
            health = collect_arr_health(conn)
            s = health.get("summary", {})
            print(f"  OK: {s.get('ok', 0)}  Warning: {s.get('warning', 0)}  Error: {s.get('error', 0)}")
            if include_queue:
                print("Actualizando diagnósticos de queue...")
                qr = refresh_arr_queue_diagnostics(conn)
                print(f"  Items actualizados: {qr.get('library_items_updated', 0)}  (queue encontrada: {qr.get('queue_items_found', 0)})")
                if qr.get("errors"):
                    for e in qr["errors"]:
                        print(f"  ✗ {e.get('instance')}: {e.get('error')}")
            if include_history:
                print("Actualizando diagnósticos de historial...")
                hr = refresh_arr_history_diagnostics(conn, page_size=history_size)
                print(f"  Items actualizados: {hr.get('library_items_updated', 0)}  (historial leído: {hr.get('history_items_found', 0)})")
                if hr.get("errors"):
                    for e in hr["errors"]:
                        print(f"  ✗ {e.get('instance')}: {e.get('error')}")
            print("✓ Salud ARR actualizada")
            return 0
    return 1


_STATUS_LABELS = {
    "open":     "abierto",
    "ready":    "listo",
    "waiting":  "esperando",
    "blocked":  "bloqueado",
    "running":  "en curso",
    "resolved": "resuelto",
    "ignored":  "ignorado",
    "completed": "completado",
}


def cmd_queue(args) -> int:
    with _open_conn(args) as conn:
        from .services.operational_queue import (
            refresh_operational_queue,
            list_operational_queue,
            get_operational_queue_summary,
            get_operational_queue_item,
            mark_queue_item_resolved,
            ignore_queue_item,
        )

        if args.queue_command == "summary":
            summary = get_operational_queue_summary(conn)
            print("\n── Cola operativa ──────────────────────────────────")
            print(f"  Total: {summary.get('total', 0)}")
            print(f"  Open:    {summary.get('open', 0)}   Ready:   {summary.get('ready', 0)}")
            print(f"  Waiting: {summary.get('waiting', 0)}   Blocked: {summary.get('blocked', 0)}")
            if summary.get("total", 0) == 0:
                print()
                print("  Sin items. Ejecuta: python3 emuwarez_uploader.py queue refresh")
            return 0

        if args.queue_command == "refresh":
            print("Reconstruyendo cola operativa...")
            result = refresh_operational_queue(conn)
            s = result.get("summary", {})
            print(f"✓ Cola actualizada: {result.get('items_built', 0)} items")
            print(f"  Listos: {s.get('ready', 0)}  Esperando: {s.get('waiting', 0)}  Bloqueados: {s.get('blocked', 0)}")
            return 0

        if args.queue_command == "list":
            filters: dict = {}
            if getattr(args, "status", None):
                filters["status"] = args.status
            if getattr(args, "action", None):
                filters["action"] = args.action
            if getattr(args, "item_type", None):
                filters["item_type"] = args.item_type
            limit = getattr(args, "limit", 50)
            items = list_operational_queue(conn, filters=filters, limit=limit)
            if not items:
                print("Sin items en la cola. Ejecuta: python3 emuwarez_uploader.py queue refresh")
                return 0
            rows = []
            for item in items:
                status_label = _STATUS_LABELS.get(item.get("status", ""), item.get("status", ""))
                rows.append([
                    item["id"],
                    status_label,
                    item.get("action", ""),
                    item.get("item_type", ""),
                    (item.get("title") or "")[:50],
                ])
            _print_table(["ID", "Estado", "Acción", "Tipo", "Título"], rows)
            return 0

        if args.queue_command == "show":
            item = get_operational_queue_item(args.id, conn)
            if not item:
                print(f"✗ Item {args.id} no encontrado")
                return 1
            print(f"\n── Item #{item['id']} ─────────────────────────────────")
            print(f"  Clave:     {item.get('queue_key')}")
            print(f"  Tipo:      {item.get('item_type')} / {item.get('entity_type')}")
            print(f"  Título:    {item.get('title')}")
            print(f"  Subtítulo: {item.get('subtitle')}")
            print(f"  Estado:    {_STATUS_LABELS.get(item.get('status', ''), item.get('status', ''))}")
            print(f"  Acción:    {item.get('action')}")
            if item.get("blockers"):
                print(f"  Bloqueado por:")
                for b in item["blockers"]:
                    print(f"    · {b}")
            if item.get("reasons"):
                print(f"  Razones:")
                for r in item["reasons"]:
                    print(f"    · {r}")
            if item.get("request_item_id"):
                print(f"  request_item_id: {item['request_item_id']}")
            if item.get("library_item_id"):
                print(f"  library_item_id: {item['library_item_id']}")
            if item.get("upload_job_id"):
                print(f"  upload_job_id:   {item['upload_job_id']}")
            return 0

        if args.queue_command == "resolve":
            result = mark_queue_item_resolved(args.id, conn, reason=getattr(args, "reason", None))
            if result.get("ok"):
                print(f"✓ Item #{args.id} marcado como resuelto")
            else:
                print(f"✗ {result.get('error', 'Error desconocido')}")
                return 1
            return 0

        if args.queue_command == "ignore":
            result = ignore_queue_item(args.id, conn, reason=getattr(args, "reason", None))
            if result.get("ok"):
                print(f"✓ Item #{args.id} marcado como ignorado")
            else:
                print(f"✗ {result.get('error', 'Error desconocido')}")
                return 1
            return 0

        if args.queue_command == "actions":
            from .services.operational_actions import list_available_queue_actions
            actions = list_available_queue_actions(args.id, conn)
            if not actions:
                print(f"✗ Item {args.id} no encontrado")
                return 1
            print(f"\n── Acciones disponibles para item #{args.id} ──────────────")
            for a in actions:
                inline = "✓ inline" if a.get("safe_to_execute_inline") else "⚠ requiere flujo guiado"
                token = f"  token: {a['confirmation_token']}" if a.get("confirmation_token") else ""
                primary = " [PRINCIPAL]" if a.get("primary") else ""
                print(f"  {a['action']:<25} {inline}{primary}")
                print(f"    → {a['label']}  |  flow: {a['flow']}{token}")
            return 0

        if args.queue_command == "action-plan":
            from .services.operational_actions import get_queue_action_plan
            result = get_queue_action_plan(args.id, conn)
            if not result.get("ok"):
                print(f"✗ {result.get('error', 'Item no encontrado')}")
                return 1
            plan = result["plan"]
            print(f"\n── Plan de acción para item #{args.id} ─────────────────────")
            print(f"  Acción:       {plan['action']}")
            print(f"  Flow:         {plan['flow']}")
            print(f"  Título:       {plan.get('title') or '–'}")
            print(f"  Tipo:         {plan.get('item_type') or '–'}")
            print(f"  Estado:       {plan.get('status')}")
            ui = plan.get("ui", {})
            print(f"  UI:           {ui.get('route', '–')}  modal: {ui.get('modal') or '–'}")
            print(f"  Label:        {ui.get('label', '–')}")
            inline = plan.get("safe_to_execute_inline", False)
            print(f"  Inline:       {'✓ sí (safe)' if inline else '✗ no — flujo guiado requerido'}")
            if plan.get("requires_confirmation"):
                print(f"  Confirmación: sí  |  token: {plan.get('confirmation_token')}")
            else:
                print(f"  Confirmación: no")
            if plan.get("blockers"):
                print(f"  Bloqueado por:")
                for b in plan["blockers"]:
                    print(f"    · {b}")
            if plan.get("reasons"):
                print(f"  Razones:")
                for r in plan["reasons"]:
                    print(f"    · {r}")
            target = plan.get("target", {})
            if target:
                print(f"  Target:       {target}")
            return 0

        if args.queue_command == "execute-safe":
            from .services.operational_actions import execute_safe_queue_action
            action_req = getattr(args, "action", None)
            result = execute_safe_queue_action(args.id, conn, action=action_req)
            if result.get("blocked"):
                print(f"✗ Bloqueado: {result.get('message', '')}")
                print(f"  Flujo guiado requerido: {result.get('guided_flow', '–')}")
                ui_route = result.get("ui_route")
                if ui_route:
                    print(f"  Ruta UI: {ui_route}")
                token = result.get("confirmation_token")
                if token:
                    print(f"  Token de confirmación: {token}")
                return 1
            if not result.get("ok"):
                print(f"✗ {result.get('error', 'Error desconocido')}")
                return 1
            print(f"✓ Acción '{result.get('action')}' ejecutada")
            if result.get("result"):
                r = result["result"]
                if "file_exists" in r:
                    found = r.get("file_exists")
                    print(f"  Archivo: {'encontrado' if found else 'NO encontrado'}")
                    if r.get("file_size_on_disk"):
                        size = r["file_size_on_disk"]
                        print(f"  Tamaño: {size:,} bytes ({size // 1024 // 1024:.1f} MB)" if size >= 1024*1024 else f"  Tamaño: {size:,} bytes")
            return 0

        if args.queue_command == "events":
            from .services.operational_actions import get_queue_action_events
            limit = getattr(args, "limit", 20)
            events = get_queue_action_events(args.id, conn, limit=limit)
            if not events:
                print(f"Sin eventos registrados para item #{args.id}")
                return 0
            print(f"\n── Eventos de acción para item #{args.id} ──────────────────")
            for ev in events:
                status_icon = "✓" if ev.get("status") == "ok" else ("⚠" if ev.get("status") == "warning" else "✗")
                print(f"  {status_icon} [{ev.get('created_at', '')[:19]}] {ev.get('event_type')} — {ev.get('message') or '–'}")
            return 0

    return 1


def _print_nomenclature_proposal(proposal: dict) -> None:
    import json as _json
    warnings = []
    errors_list = []
    try:
        warnings = _json.loads(proposal.get("warnings_json") or "[]")
    except Exception:
        pass
    try:
        errors_list = _json.loads(proposal.get("errors_json") or "[]")
    except Exception:
        pass
    print("\n── Nomenclatura / Propuesta ─────────────────────────────")
    print(f"\nTítulo actual:     {proposal.get('current_name') or '–'}")
    print(f"Título propuesto:  {proposal.get('proposed_title') or '–'}")
    print(f"Archivo propuesto: {proposal.get('proposed_filename') or '–'}")
    print(f"Carpeta propuesta: {proposal.get('proposed_folder') or '–'}")
    print(f"Resolución:        {proposal.get('resolution') or '–'}")
    print(f"Source:            {proposal.get('source') or '–'}")
    print(f"Vídeo:             {proposal.get('video_codec') or '–'}")
    print(f"\nEstado: {proposal.get('status', '–')}")
    if warnings:
        print("\nAvisos:")
        for w in warnings:
            print(f"  - {w}")
    if errors_list:
        print("\nErrores:")
        for e in errors_list:
            print(f"  ✗ {e}")
    print("\nAcción: No se ha modificado ningún archivo.")


def cmd_nomenclature(args) -> int:
    from .services.nomenclature import (
        build_nomenclature_proposal, get_latest_nomenclature_proposal
    )
    with _open_conn(args) as conn:
        if args.nomenclature_command == "preview":
            proposal = build_nomenclature_proposal(args.id, force_refresh=args.force, conn=conn)
            _print_nomenclature_proposal(proposal)
            return 0
        if args.nomenclature_command == "show":
            proposal = get_latest_nomenclature_proposal(args.id, conn=conn)
            if not proposal:
                print("No hay propuesta de nomenclatura generada. Usa 'nomenclature preview' para generar una.")
                return 1
            _print_nomenclature_proposal(proposal)
            return 0
        if args.nomenclature_command == "apply":
            from .services.nomenclature import apply_nomenclature_proposal, CONFIRMATION_TOKEN
            do_apply = getattr(args, "nom_apply", False)
            dry_run = getattr(args, "dry_run", False) or not do_apply
            confirmation = getattr(args, "confirm_token", None)
            result = apply_nomenclature_proposal(
                args.id,
                dry_run=dry_run,
                apply=do_apply,
                confirmation=confirmation,
                conn=conn,
            )
            mode = "Previsualización" if result.get("dry_run") else "Aplicar"
            print(f"\n── Nomenclatura / {mode} ─────────────────────────────")
            print(f"\nArchivo original:\n  {result.get('source_path') or '–'}")
            print(f"\nArchivo preparado:\n  {result.get('destination_path') or '–'}")
            print(f"\nEstado:\n  {result.get('status', '–')}")
            if result.get("warnings"):
                print("\nAvisos:")
                for w in result["warnings"]:
                    print(f"  - {w}")
            if result.get("errors"):
                print("\nErrores:")
                for e in result["errors"]:
                    print(f"  ✗ {e}")
            if result.get("message"):
                print(f"\nMensaje:\n  {result['message']}")
            print("\nSeguridad:")
            print("  ✓ El archivo original no se ha renombrado.")
            print("  ✓ Uploadrr no se ha ejecutado.")
            print("  ✓ mkvpropedit no se ha ejecutado.")
            return 0

        # Phase 10A subcommands
        if args.nomenclature_command == "sources":
            from .services.source_assistant import list_emu_sources
            sources = list_emu_sources()
            _print_table(["Código", "Label"], [[s["code"], s["label"]] for s in sources])
            return 0

        if args.nomenclature_command == "providers":
            from .services.source_assistant import list_emu_providers
            providers = list_emu_providers()
            _print_table(["Código", "Nombre"], [[p["code"], p["name"]] for p in providers])
            return 0

        if args.nomenclature_command == "fields":
            from .services.source_assistant import build_editable_nomenclature_fields
            result = build_editable_nomenclature_fields(args.id, conn=conn)
            if "error" in result:
                print(f"✗ {result['error']}")
                return 1
            fields = result.get("fields", {})
            print(f"Título:           {fields.get('title')}")
            print(f"Año:              {fields.get('year')}")
            print(f"Resolución:       {fields.get('resolution')}")
            print(f"Source:           {fields.get('source')}")
            print(f"Provider:         {fields.get('provider')}")
            print(f"Códec:            {fields.get('video_codec')}")
            print(f"Audio:            {fields.get('audio_summary')}")
            print(f"Subs:             {fields.get('subs')}")
            print(f"Tag:              {fields.get('tag')}")
            print(f"Torrent name:     {result.get('torrent_name')}")
            print(f"MKV title:        {result.get('internal_mkv_title')}")
            tmdb_avail = result.get("tmdb_available_providers", [])
            if tmdb_avail:
                print(f"Providers TMDb:   {', '.join(tmdb_avail)}")
            return 0

        if args.nomenclature_command == "preview-fields":
            from .services.source_assistant import update_nomenclature_fields_preview
            import json as _json
            fields_json = getattr(args, "fields_json", None) or "{}"
            try:
                fields = _json.loads(fields_json)
            except Exception:
                print("✗ JSON de campos inválido")
                return 1
            result = update_nomenclature_fields_preview(args.id, fields, conn=conn)
            print(f"Torrent name:  {result.get('torrent_name')}")
            print(f"MKV title:     {result.get('internal_mkv_title')}")
            return 0

    return 1


def cmd_mkv_title(args) -> int:
    from .services.mkv_title import (
        preview_internal_title_update,
        apply_internal_title_update,
        MKV_CONFIRMATION_TOKEN,
    )
    with _open_conn(args) as conn:
        if args.mkv_command == "preview":
            result = preview_internal_title_update(args.id, conn=conn)
            print(f"Status:         {result.get('status')}")
            print(f"Prepared path:  {result.get('prepared_path')}")
            print(f"Torrent name:   {result.get('torrent_name')}")
            print(f"Internal title: {result.get('internal_mkv_title')}")
            print(f"mkvpropedit:    {'disponible' if result.get('mkvpropedit_available') else 'no instalado'}")
            if result.get("command_preview"):
                print(f"Comando:        {result['command_preview']}")
            for e in result.get("errors", []):
                print(f"  ✗ {e}")
            for w in result.get("warnings", []):
                print(f"  ⚠ {w}")
            return 0 if result.get("status") != "blocked" else 1

        if args.mkv_command == "apply":
            do_apply = getattr(args, "mkv_apply", False)
            dry_run = not do_apply
            confirm = getattr(args, "mkv_confirm", None)
            result = apply_internal_title_update(
                args.id,
                dry_run=dry_run,
                apply=do_apply,
                confirmation=confirm,
                conn=conn,
            )
            print(f"Status: {result.get('status')}")
            if result.get("status") == "applied":
                print(f"  ✓ Título MKV aplicado: {result.get('internal_mkv_title')}")
            elif dry_run:
                print(f"  [dry-run] Se aplicaría: {result.get('internal_mkv_title')}")
                print(f"  Comando: {result.get('command_preview')}")
            for e in result.get("errors", []):
                print(f"  ✗ {e}")
            if not do_apply:
                print(f"  ✓ mkvpropedit no se ha ejecutado (dry-run).")
            return 0 if result.get("status") not in ("blocked", "error") else 1
    return 1


def cmd_upload_modern(args) -> int:
    from .services.upload_preflight import (
        build_upload_preflight,
    )
    from .services.upload_execution import (
        get_upload_job, list_upload_jobs, get_upload_job_logs,
        get_upload_job_artifacts, start_upload_job, cancel_upload_job,
        retry_upload_job, CONFIRMATION_TOKEN,
    )
    with _open_conn(args) as conn:
        if args.upload_command == "preflight":
            result = build_upload_preflight(args.id, request_id=args.request_id, conn=conn)
            print(f"\n── Upload Preflight (library_item {args.id}) ──────────────")
            print(f"Estado: {result['status']}")
            cmd = result.get("command_preview", {})
            if cmd:
                print(f"Tracker:    {cmd.get('tracker', '–')}")
                print(f"Categoría:  {cmd.get('category', '–')}")
                print(f"TMDb:       {cmd.get('tmdb_id', '–')}")
                print(f"Resolución: {cmd.get('resolution', '–')}")
                print(f"Origen:     {cmd.get('source_path', '–')}")
                if cmd.get("command_preview"):
                    print(f"\nComando previsto:")
                    print(f"  {cmd['command_preview']}")
            if result.get("warnings"):
                print("\nAvisos:")
                for w in result["warnings"]:
                    print(f"  - {w}")
            if result.get("errors"):
                print("\nErrores:")
                for e in result["errors"]:
                    print(f"  ✗ {e}")
            print("\nNota: No se ha ejecutado Uploadrr ni subido ningún archivo.")
            return 0

        if args.upload_command in ("job", "status"):
            job = get_upload_job(args.id, conn=conn)
            if not job:
                print(f"✗ Job {args.id} no encontrado")
                return 1
            fields = [
                "id", "library_item_id", "status", "stage", "title",
                "source_path", "prepared_path", "exit_code", "duration_seconds",
                "result_url", "result_torrent_id", "error_message",
                "retry_count", "retry_of_job_id",
                "started_at", "finished_at", "created_at",
            ]
            for key in fields:
                val = job.get(key)
                if val is not None:
                    print(f"{key:28} {val}")
            return 0

        if args.upload_command == "jobs":
            status_filter = getattr(args, "status", None)
            filters = {"limit": 200}
            if status_filter:
                filters["status"] = status_filter
            jobs = list_upload_jobs(filters=filters, conn=conn)
            if not jobs:
                msg = f"No hay jobs con estado '{status_filter}'." if status_filter else "No hay preflights de subida registrados."
                print(msg)
                return 0
            _print_table(
                ["ID", "Estado", "Duración", "Exit", "Resultado", "Título"],
                [
                    [
                        j["id"],
                        j.get("status"),
                        f"{j['duration_seconds']}s" if j.get("duration_seconds") is not None else "–",
                        j.get("exit_code") if j.get("exit_code") is not None else "–",
                        j.get("result_url", "")[:40] if j.get("result_url") else "–",
                        j.get("title"),
                    ]
                    for j in jobs
                ],
            )
            return 0

        if args.upload_command == "logs":
            result = get_upload_job_logs(args.id, limit=args.limit, conn=conn)
            logs = result.get("logs", [])
            if not logs:
                print(f"No hay logs para el job {args.id}.")
                return 0
            print(f"\n── Logs / Job {args.id} ({result['total']} entradas) ──────────")
            for entry in logs:
                ts = entry.get("created_at", "")[:19].replace("T", " ")
                stream = entry.get("stream", "system")
                level = entry.get("level", "info")
                msg = entry.get("message", "")
                print(f"[{ts}] [{stream}/{level}] {msg}")
            return 0

        if args.upload_command == "artifacts":
            artifacts = get_upload_job_artifacts(args.id, conn=conn)
            if not artifacts:
                print(f"No hay artefactos para el job {args.id}.")
                return 0
            print(f"\n── Artefactos / Job {args.id} ─────────────────────────")
            for a in artifacts:
                parts = [f"[{a['artifact_type']}]"]
                if a.get("name"):
                    parts.append(a["name"])
                if a.get("url"):
                    parts.append(f"url={a['url']}")
                if a.get("path"):
                    parts.append(f"path={a['path']}")
                if a.get("value"):
                    parts.append(f"value={a['value']}")
                print("  " + "  ".join(parts))
            return 0

        if args.upload_command == "start":
            do_apply = getattr(args, "up_apply", False)
            confirmation = getattr(args, "up_confirm", None)
            dry_run = not do_apply
            result = start_upload_job(
                args.id,
                dry_run=dry_run,
                start=do_apply,
                confirmation=confirmation,
                conn=conn,
                wait=do_apply,
            )
            action = result.get("action", "unknown")
            if dry_run or action == "dry_run":
                print(f"\n── Uploadrr / Start dry-run ─────────────────────────────")
                print(f"\nJob:\n  {args.id}")
                print(f"\nEstado:\n  {result.get('status', '–')}")
                print(f"\nComando previsto:\n  {result.get('command_preview', '–')}")
                if result.get("warnings"):
                    print("\nAvisos:")
                    for w in result["warnings"]:
                        print(f"  - {w}")
                if result.get("errors"):
                    print("\nErrores:")
                    for e in result["errors"]:
                        print(f"  ✗ {e}")
                print(f"\nAcción:\n  {result.get('message', 'No se ha ejecutado Uploadrr.')}")
                return 0 if result.get("valid", True) else 1
            if action == "blocked":
                print(f"\n── Uploadrr / Bloqueado ─────────────────────────────")
                for e in result.get("errors", []):
                    print(f"  ✗ {e}")
                return 1
            if action == "started":
                print(f"\n── Uploadrr / Ejecución ─────────────────────────────")
                print(f"\nJob:\n  {args.id}")
                print(f"\nEstado:\n  {result.get('status', '–')}")
                print(f"\nSeguridad:")
                print(f"  ✓ Se usa archivo preparado." if result.get("using_prepared_path") else "  ⚠ Se usa el archivo original.")
                print(f"  ✓ No se modifica Uploadrr/.")
                print(f"  ✓ No se ejecuta mkvpropedit.")
                print(f"  ✓ Secretos ocultos en logs.")
                print(f"\nMensaje:\n  {result.get('message', '–')}")
                print(f"\nUsa 'upload logs {args.id}' para ver el detalle.")
                return 0 if result.get("status") == "completed" else 1
            return 1

        if args.upload_command == "retry":
            do_apply = getattr(args, "up_apply", False)
            confirmation = getattr(args, "up_confirm", None)
            dry_run = not do_apply
            result = retry_upload_job(
                args.id,
                dry_run=dry_run,
                start=do_apply,
                confirmation=confirmation,
                wait=do_apply,
            )
            if dry_run or result.get("action") == "dry_run":
                print(f"\n── Retry dry-run ────────────────────")
                original = get_upload_job(args.id, conn=conn)
                orig_status = original.get("status", "–") if original else "–"
                print(f"Job original: {args.id} ({orig_status})")
                print(f"Job nuevo (simulado): no creado")
                print(f"Reintentos previstos: {result.get('retry_count_would_be', '–')}")
                if result.get("command_preview"):
                    print(f"Comando previsto: {result['command_preview']}")
                print(f"No se ha ejecutado Uploadrr.")
                return 0
            if result.get("action") == "blocked":
                for e in result.get("errors") or [result.get("message") or "Bloqueado."]:
                    print(f"✗ {e}")
                return 1
            print(f"\n── Retry iniciado ────────────────────")
            new_job_id = result.get("new_job_id", "–")
            print(f"Job nuevo: {new_job_id}")
            print(f"Reintento: {result.get('retry_count', '–')}")
            print(f"Estado: {result.get('status', '–')}")
            print(f"Mensaje: {result.get('message', '–')}")
            print(f"\nUsa 'upload logs {new_job_id}' para ver el detalle.")
            return 0 if result.get("status") == "completed" else 1

        if args.upload_command == "cancel":
            result = cancel_upload_job(args.id, conn=conn)
            mark = "✓" if result.get("ok") else "✗"
            print(f"{mark} {result.get('message', '')}")
            return 0 if result.get("ok") else 1
    return 1


def cmd_upload(args) -> int:
    if getattr(args, "upload_command", None):
        return cmd_upload_modern(args)
    # Legacy upload path (no subcommand) — not reachable with new parser structure
    print("Usa: upload preflight <id> | upload job <id> | upload jobs")
    return 1


def cmd_tasks(args) -> int:
    with _open_conn(args) as conn:
        rows = task_service.list_tasks(conn, limit=args.limit)
        _print_table(
            ["ID", "Tarea", "Estado", "Inicio", "Fin", "Resumen"],
            [[r["id"], r["name"], r["status"], r["started_at"], r["finished_at"], r["summary"]] for r in rows],
        )
    return 0


def cmd_logs(args) -> int:
    log_file = LOG_DIR / "emuwarez-renamer.log"
    if not log_file.exists():
        print(f"No existe todavía: {log_file}")
        return 1
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-args.tail:]
    print("\n".join(lines))
    return 0


def cmd_web_setup_status() -> int:
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from .web.services.setup_service import get_setup_state, next_step
            state = get_setup_state(conn)
    except Exception as exc:
        print(f"✗ No se pudo leer el estado del setup: {exc}")
        return 1
    flags = [
        ("Admin configurado", state["admin_configured"]),
        ("TMDb configurado", state["tmdb_configured"]),
        ("eMuwarez configurado", state["emu_configured"]),
        ("Instancias Radarr", state["radarr_instances"]),
        ("Instancias Sonarr", state["sonarr_instances"]),
        ("Inicializado", state["initialized"]),
    ]
    for label, value in flags:
        mark = "✓" if value else "✗"
        print(f"  {mark}  {label}: {value}")
    ns = next_step(state)
    print(f"\nSiguiente paso: {ns or 'ninguno (setup completo)'}")
    return 0


def cmd_web_create_admin(args) -> int:
    import getpass
    password = os.environ.get("EMUWAREZ_ADMIN_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Contraseña para el admin: ")
            if not password:
                print("✗ La contraseña no puede estar vacía")
                return 1
            confirm = getpass.getpass("Confirmar contraseña: ")
            if password != confirm:
                print("✗ Las contraseñas no coinciden")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return 1
    from .web.security import validate_password_strength
    err = validate_password_strength(password)
    if err:
        print(f"✗ {err}")
        return 1
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from .web.services.auth_service import admin_exists, create_user
            if admin_exists(conn):
                print("✗ Ya existe un usuario administrador.")
                return 1
            uid = create_user(conn, args.username, password, role="admin")
            conn.commit()
        print(f"✓ Usuario administrador '{args.username}' creado con ID {uid}")
    except Exception as exc:
        print(f"✗ {exc}")
        return 1
    return 0


def cmd_web_reset_password(args) -> int:
    import getpass
    password = os.environ.get("EMUWAREZ_ADMIN_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Nueva contraseña: ")
            if not password:
                print("✗ La contraseña no puede estar vacía")
                return 1
            confirm = getpass.getpass("Confirmar nueva contraseña: ")
            if password != confirm:
                print("✗ Las contraseñas no coinciden")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return 1
    from .web.security import validate_password_strength
    err = validate_password_strength(password)
    if err:
        print(f"✗ {err}")
        return 1
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from .web.services.auth_service import get_user_by_username, update_password
            user = get_user_by_username(conn, args.username)
            if not user:
                print(f"✗ No existe el usuario '{args.username}'.")
                return 1
            update_password(conn, user["id"], password)
            conn.commit()
        print(f"✓ Contraseña de '{args.username}' restablecida.")
    except Exception as exc:
        print(f"✗ {exc}")
        return 1
    return 0


def cmd_web_info() -> int:
    print(
        "Backend: FastAPI\n"
        "App: eMuwarez Uploadrr\n"
        "Backend URL:    http://localhost:9494\n"
        "Frontend dev:   http://localhost:5173\n"
        "\n"
        "── Frontend ────────────────────────────────────────\n"
        "  cd frontend && npm install\n"
        "  npm run dev      # servidor de desarrollo (proxy → :9494)\n"
        "  npm run build    # construir para producción en frontend/dist\n"
        "  npm run preview  # previsualizar el build en :4173\n"
        "\n"
        "── Backend + Frontend producción ───────────────────\n"
        "  npm run build    # (en frontend/)\n"
        "  python3 emuwarez_uploader.py web serve --port 9494\n"
        "  # Sirve API en /api/* y frontend en /* desde frontend/dist\n"
        "\n"
        "── Endpoints de salud y runtime ────────────────────\n"
        "  GET  http://localhost:9494/api/health\n"
        "  GET  http://localhost:9494/api/runtime\n"
        "\n"
        "── Setup wizard ─────────────────────────────────────\n"
        "  GET  http://localhost:9494/api/setup/status\n"
        "  POST http://localhost:9494/api/setup/admin      (primer arranque, sin auth)\n"
        "  POST http://localhost:9494/api/setup/tmdb       (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/emu        (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/instances  (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/complete   (requiere Bearer token)\n"
        "\n"
        "── Autenticación ────────────────────────────────────\n"
        "  POST http://localhost:9494/api/auth/login\n"
        "  GET  http://localhost:9494/api/auth/me          (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/auth/logout      (requiere Bearer token)\n"
        "\n"
        "── Biblioteca ───────────────────────────────────────\n"
        "  POST http://localhost:9494/api/sync\n"
        "  GET  http://localhost:9494/api/library\n"
        "  GET  http://localhost:9494/api/library/{id}\n"
        "  GET  http://localhost:9494/api/missing\n"
        "  GET  http://localhost:9494/api/instances\n"
        "  GET  http://localhost:9494/api/dashboard/summary\n"
        "  GET  http://localhost:9494/api/dashboard/activity\n"
        "\n"
        "── Documentación interactiva ────────────────────────\n"
        "  http://localhost:9494/api/docs\n"
        "  http://localhost:9494/api/openapi.json\n"
        "\n"
        "── Setup desde CLI ──────────────────────────────────\n"
        "  python3 emuwarez_uploader.py web setup-status\n"
        "  python3 emuwarez_uploader.py web create-admin --username admin\n"
        "  python3 emuwarez_uploader.py web reset-password --username admin\n"
        "\n"
        "Instalar dependencias web:\n"
        "  pip install -e \".[web]\"\n"
        "\n"
        "── Docker ───────────────────────────────────────────\n"
        "  Build:    docker build -t emuwarez-uploadrr:local .\n"
        "  Compose:  docker compose -f docker-compose.example.yml up -d --build\n"
        "  URL:      http://localhost:9494\n"
        "  Config:   /config  (montar como volumen persistente)\n"
        "  Uploadrr: /opt/Uploadrr  (bind mount externo, no incluido en imagen)\n"
        "  Media:    monta tu biblioteca en el contenedor (p. ej. -v /mnt/storage:/data,\n"
        "            igual que Radarr/Sonarr) y configura esa misma ruta en\n"
        "            Ajustes > uploadrr_allowed_roots — sin ella, las subidas\n"
        "            reales se bloquean."
    )
    return 0


def cmd_maintenance(args) -> int:
    import json as _json
    from emuwarez_uploadrr.services import backup_service, config_export, maintenance_service

    cmd = args.maintenance_command

    if cmd == "status":
        inv = backup_service.get_config_inventory()
        db_st = maintenance_service.get_database_maintenance_status()
        bkps = backup_service.list_config_backups()
        print(f"CONFIG_DIR:   {inv.get('config_dir')}")
        print(f"Archivos:     {len(inv.get('files', []))}")
        print(f"Tamaño total: {inv.get('total_size_bytes', 0):,} bytes")
        if db_st.get("ok"):
            print(f"\nBD: {db_st.get('size_bytes', 0):,} bytes  |  freelist: {db_st.get('freelist_count', 0)}")
        else:
            print(f"\nBD: {db_st.get('error')}")
        print(f"\nBackups:      {len(bkps)}")
        if bkps:
            print(f"Último:       {bkps[0]['name']}  ({bkps[0]['size_bytes']:,} bytes)")
        return 0

    if cmd == "backup":
        result = backup_service.create_config_backup(
            include_secrets=getattr(args, "include_secrets", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(f"✓ Backup creado: {result['archive_path']}  ({result['size_bytes']:,} bytes)")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "list-backups":
        bkps = backup_service.list_config_backups()
        if not bkps:
            print("No hay backups.")
            return 0
        _print_table(
            ["Nombre", "Tamaño", "Fecha"],
            [[b["name"], f"{b['size_bytes']:,}", b["created_at"]] for b in bkps],
        )
        return 0

    if cmd == "restore":
        result = backup_service.restore_config_backup(
            args.backup_path,
            dry_run=not getattr(args, "maint_apply", False),
            apply=getattr(args, "maint_apply", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(f"✓ {result.get('message') or result.get('action')}")
            if result.get("dry_run"):
                print(f"  Archivos en el backup: {result.get('files_in_archive', 0)}")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "export-settings":
        result = config_export.export_settings(
            include_secrets=getattr(args, "include_secrets", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(_json.dumps(result.get("settings", {}), indent=2, ensure_ascii=False))
            if result.get("secrets_masked"):
                print("\n(Secretos enmascarados — usa --include-secrets --confirm EXPORTAR_SECRETOS para verlos)")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "db-integrity":
        result = maintenance_service.run_database_integrity_check()
        icon = "✓" if result.get("ok") else "✗"
        print(f"{icon} {result.get('message') or result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "db-vacuum":
        result = maintenance_service.run_database_vacuum(
            dry_run=not getattr(args, "maint_apply", False),
            apply=getattr(args, "maint_apply", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(f"✓ {result.get('message')}")
            if not result.get("dry_run"):
                print(f"  Antes: {result.get('size_bytes_before', 0):,} bytes  →  Después: {result.get('size_bytes_after', 0):,} bytes")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "cleanup-logs":
        result = maintenance_service.cleanup_old_logs(
            days=getattr(args, "days", 30),
            dry_run=not getattr(args, "maint_apply", False),
            apply=getattr(args, "maint_apply", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(f"✓ {result.get('message')}")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    return 1


def cmd_web_doctor() -> int:
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    icons = {"ok": "✓", "warning": "⚠", "error": "✗", "unknown": "?"}
    print("\nRuntime diagnostics\n")
    for check in result["checks"]:
        icon = icons.get(check["status"], "?")
        label = check["name"].replace("_", " ").title()
        print(f"{label}:")
        print(f"  {icon} {check['message']}")
        if check.get("details"):
            for k, v in check["details"].items():
                print(f"    {k}: {v}")
    if result["warnings"]:
        print(f"\nAdvertencias: {len(result['warnings'])}")
    if result["errors"]:
        print(f"\nErrores: {len(result['errors'])}")
    if result["ok"]:
        print("\n✓ Sistema listo")
    else:
        print("\n✗ Hay errores que resolver")
    return 0 if result["ok"] else 1


def cmd_web_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "✗ Faltan dependencias web. Instala el proyecto con las dependencias web:\n"
            "  pip install -e \".[web]\"\n"
            "O instala uvicorn y fastapi directamente:\n"
            "  pip install uvicorn fastapi pydantic"
        )
        return 1
    uvicorn.run(
        "emuwarez_uploadrr.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        # Al parar, uvicorn espera a que se cierren todas las conexiones, y
        # /api/eventos no se cierra mientras haya una pestaña abierta: sin
        # este tope, `docker stop` acaba siempre en SIGKILL (código 137) tras
        # el stop_grace_period entero. Pasado el tope corta lo que quede.
        timeout_graceful_shutdown=5,
    )
    return 0


def cmd_demo(args) -> int:
    from .services.demo_seed import seed_demo_data, reset_demo_data
    with _open_conn(args) as conn:
        if args.demo_command == "seed":
            try:
                result = seed_demo_data(
                    conn,
                    media_root=args.media_root,
                    prepared_root=args.prepared_root,
                    confirm_token=args.confirm_token,
                )
            except ValueError as exc:
                print(f"✗ {exc}")
                return 1
            print(f"✓ Datos demo sembrados")
            print(f"  library_item_id : {result['library_item_id']}")
            print(f"  request_item_id : {result['request_item_id']}")
            print(f"  archivo simulado: {result['media_file']}")
            return 0
        if args.demo_command == "reset":
            try:
                reset_demo_data(conn, confirm_token=args.confirm_token)
            except ValueError as exc:
                print(f"✗ {exc}")
                return 1
            print("✓ Datos demo eliminados de la BD")
            return 0
    return 1


def modern_main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "db":
            if args.db_command == "path":
                print(args.db)
                return 0
            with _open_conn(args):
                print(f"✓ SQLite lista: {args.db}")
                return 0
        if args.command == "instances":
            return cmd_instances(args)
        if args.command == "sync":
            return cmd_sync(args)
        if args.command == "library":
            return cmd_library(args)
        if args.command == "requests":
            return cmd_requests(args)
        if args.command == "missing":
            return cmd_missing(args)
        if args.command == "nomenclature":
            return cmd_nomenclature(args)
        if args.command == "upload":
            return cmd_upload(args)
        if args.command == "tasks":
            return cmd_tasks(args)
        if args.command == "logs":
            return cmd_logs(args)
        if args.command == "web":
            if args.web_command == "info":
                return cmd_web_info()
            if args.web_command == "serve":
                return cmd_web_serve(args)
            if args.web_command == "setup-status":
                return cmd_web_setup_status()
            if args.web_command == "doctor":
                return cmd_web_doctor()
            if args.web_command == "create-admin":
                return cmd_web_create_admin(args)
            if args.web_command == "reset-password":
                return cmd_web_reset_password(args)
        if args.command == "maintenance":
            return cmd_maintenance(args)
        if args.command == "arr":
            return cmd_arr(args)
        if args.command == "queue":
            return cmd_queue(args)
        if args.command == "demo":
            return cmd_demo(args)
        if args.command == "mkv-title":
            return cmd_mkv_title(args)
        parser.error("Comando no soportado")
        return 2
    except IntegrationError as exc:
        print(f"✗ {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        return 130


def main(argv: Optional[list[str]] = None) -> int:
    """Punto de entrada. Hasta el 2026-08-01, lo que no fuera un comando
    conocido caía en el CLI interactivo antiguo; ese CLI se borró (asumía un
    ./Uploadrr y un ./.venv junto al script que en el contenedor no existen, y
    su asistente escribía una segunda configuración que la aplicación no usa).
    Ahora un comando desconocido es un error, que es lo que siempre fue."""
    return modern_main(list(sys.argv[1:] if argv is None else argv))


__all__ = ["main", "modern_main", "build_parser"]
