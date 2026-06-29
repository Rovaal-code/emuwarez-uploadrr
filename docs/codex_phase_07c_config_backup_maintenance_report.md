# Fase 7C — Endurecimiento de configuración, backup/restore, mantenimiento runtime y validación de secretos

**Fecha:** 2026-06-29
**Rama:** `feature/ui-phase-07c-config-backup-maintenance`

---

## Resumen

Esta fase añade herramientas de mantenimiento, backup/restore y exportación de configuración, tanto en el backend (API + servicios) como en la CLI y la UI.

---

## Archivos creados

| Archivo | Descripción |
|---|---|
| `emuwarez_uploadrr/services/backup_service.py` | Inventario de CONFIG_DIR, creación de backups .tar.gz, listado y restauración |
| `emuwarez_uploadrr/services/config_export.py` | Exportar/importar ajustes con enmascaramiento de secretos |
| `emuwarez_uploadrr/services/maintenance_service.py` | Estado BD, integrity_check, VACUUM, ANALYZE, limpieza de logs |
| `emuwarez_uploadrr/web/api/maintenance.py` | 9 endpoints REST protegidos con Bearer token |
| `frontend/src/api/maintenance.ts` | API client TypeScript para todos los endpoints de mantenimiento |
| `frontend/src/pages/SettingsPage.tsx` | UI con 4 pestañas: Configuración, Diagnóstico, Backup, Mantenimiento |
| `tests/test_backup_service.py` | 10 tests del servicio de backup |
| `tests/test_config_export.py` | 9 tests del servicio de exportación |
| `tests/test_maintenance_service.py` | 9 tests del servicio de mantenimiento |
| `tests/test_maintenance_api.py` | 23 tests de los endpoints API |

---

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `emuwarez_uploadrr/services/runtime_diagnostics.py` | +2 checks: `check_required_secrets()`, `check_arr_instances_configuration()` |
| `emuwarez_uploadrr/web/schemas.py` | +5 schemas: BackupRequest, RestoreRequest, ImportSettingsRequest, VacuumRequest, CleanupLogsRequest |
| `emuwarez_uploadrr/web/api/router.py` | Incluye `maintenance_router` |
| `emuwarez_uploadrr/cli.py` | +`maintenance` en MODERN_COMMANDS, parser completo, `cmd_maintenance()` |

---

## Endpoints nuevos (`/api/maintenance/*`)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/maintenance/status` | Estado general: inventario, BD, backups |
| GET | `/api/maintenance/export-settings` | Exportar ajustes (secretos enmascarados) |
| POST | `/api/maintenance/import-settings` | Importar ajustes (dry_run por defecto) |
| POST | `/api/maintenance/backup` | Crear backup .tar.gz |
| GET | `/api/maintenance/backups` | Listar backups existentes |
| POST | `/api/maintenance/restore` | Restaurar backup (dry_run por defecto) |
| POST | `/api/maintenance/db/integrity-check` | PRAGMA integrity_check |
| POST | `/api/maintenance/db/vacuum` | VACUUM (dry_run por defecto) |
| POST | `/api/maintenance/logs/cleanup` | Limpiar logs antiguos (dry_run por defecto) |

Todos requieren Bearer token.

---

## Tokens de confirmación

| Operación | Token |
|---|---|
| Restaurar backup | `RESTAURAR_CONFIG` |
| Exportar secretos | `EXPORTAR_SECRETOS` |
| Importar ajustes (apply) | `IMPORTAR_CONFIG` |
| VACUUM BD | `MANTENIMIENTO_DB` |
| Limpiar logs (apply) | `LIMPIAR_LOGS` |

---

## CLI — grupo `maintenance`

```
python3 emuwarez_uploader.py maintenance status
python3 emuwarez_uploader.py maintenance backup
python3 emuwarez_uploader.py maintenance list-backups
python3 emuwarez_uploader.py maintenance restore <path> [--apply --confirm RESTAURAR_CONFIG]
python3 emuwarez_uploader.py maintenance export-settings [--include-secrets --confirm EXPORTAR_SECRETOS]
python3 emuwarez_uploader.py maintenance db-integrity
python3 emuwarez_uploader.py maintenance db-vacuum [--apply --confirm MANTENIMIENTO_DB]
python3 emuwarez_uploader.py maintenance cleanup-logs [--days N] [--apply --confirm LIMPIAR_LOGS]
```

---

## Garantías de seguridad

- Los secretos (`tmdb_api_key`, `emu_api_key`) **nunca** aparecen en las respuestas de export sin confirmación explícita.
- El endpoint `export-settings` devuelve `***MASKED***` para secretos por defecto.
- El import rechaza valores `***MASKED***` (no sobreescribe secretos enmascarados).
- Los checks de diagnóstico no exponen nombres ni valores de claves secretas.
- Todas las operaciones destructivas requieren `dry_run=True` por defecto + token de confirmación para ejecutar.

---

## Validaciones

| Validación | Resultado |
|---|---|
| `python3 -m py_compile` (todos los archivos) | OK |
| `pytest` (511 tests) | 511 passed, 0 failed |
| `npm run build` | ✓ 70 módulos, sin errores |
| CLI `maintenance status/db-integrity/db-vacuum/export-settings/backup/list-backups` | OK |
