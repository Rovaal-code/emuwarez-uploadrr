"""Construcción del parser de argumentos (`build_parser`)."""
from __future__ import annotations

import argparse

from ..database import db_path


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

    p_nomenclature = sub.add_parser("nomenclature", help="Nomenclatura eMuwarez: `apply` renombra el archivo original, el resto no modifica archivos")
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
    p_up_start.add_argument("--confirm", metavar="TOKEN", dest="up_confirm", help="Token de confirmación: INICIAR_UPLOADRR")
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

    maint_sub.add_parser("db-integrity", help="PRAGMA integrity_check (solo lectura)")

    p_vacuum = maint_sub.add_parser("db-vacuum", help="VACUUM en la BD SQLite")
    p_vacuum.add_argument("--dry-run", action="store_true", default=True, help="Solo previsualización (por defecto)")
    p_vacuum.add_argument("--apply", action="store_true", dest="maint_apply", help="Ejecutar VACUUM real")
    p_vacuum.add_argument("--confirm", metavar="TOKEN", dest="confirm", help="Token: MANTENIMIENTO_DB")

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
