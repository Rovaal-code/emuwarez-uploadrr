# Checkpoint Fase 7C — Config Backup, Restore y Mantenimiento

## Último commit de Fase 7C

```
2f1bf22 merge: config backup and maintenance milestone
f419dd4 feat: add config backup and maintenance tools
```

Tag: `emuwarez-uploadrr-config-backup-maintenance-v0`

## Estado de tests

- **511/511 pasando**, 0 fallidos

## Frontend build

- **OK** — `npm run build` completado, 70 módulos, sin errores

## Funcionalidades incluidas

### CLI — grupo `maintenance`

```bash
python3 emuwarez_uploader.py maintenance status
python3 emuwarez_uploader.py maintenance backup
python3 emuwarez_uploader.py maintenance list-backups
python3 emuwarez_uploader.py maintenance restore <path> [--apply --confirm RESTAURAR_CONFIG]
python3 emuwarez_uploader.py maintenance export-settings [--include-secrets --confirm EXPORTAR_SECRETOS]
python3 emuwarez_uploader.py maintenance db-integrity
python3 emuwarez_uploader.py maintenance db-vacuum [--apply --confirm MANTENIMIENTO_DB]
python3 emuwarez_uploader.py maintenance cleanup-logs [--days N] [--apply --confirm LIMPIAR_LOGS]
```

### Backup / Restore

- Creación de backup `.tar.gz` del directorio de configuración
- Listado de backups existentes con metadatos
- Restauración con `dry_run=True` por defecto + token de confirmación `RESTAURAR_CONFIG`

### Export / Import settings

- Export de ajustes con secretos enmascarados (`***MASKED***`) por defecto
- Export con secretos reales requiere token `EXPORTAR_SECRETOS`
- Import rechaza valores `***MASKED***` (no sobreescribe secretos enmascarados)
- Import con `dry_run=True` por defecto + token `IMPORTAR_CONFIG`

### Mantenimiento SQLite

- `PRAGMA integrity_check` vía CLI y API
- `VACUUM` con `dry_run=True` por defecto + token `MANTENIMIENTO_DB`

### Limpieza de logs

- `cleanup-logs` con `dry_run=True` por defecto + token `LIMPIAR_LOGS`
- Parámetro `--days N` para definir antigüedad máxima

### Endpoints `/api/maintenance/*`

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/maintenance/status` | Estado general: inventario, BD, backups |
| GET | `/api/maintenance/export-settings` | Exportar ajustes (secretos enmascarados) |
| POST | `/api/maintenance/import-settings` | Importar ajustes (dry_run por defecto) |
| POST | `/api/maintenance/backup` | Crear backup .tar.gz |
| GET | `/api/maintenance/backups` | Listar backups existentes |
| POST | `/api/maintenance/restore` | Restaurar backup (dry_run por defecto) |
| POST | `/api/maintenance/db/integrity-check` | PRAGMA integrity_check |
| POST | `/api/maintenance/db/vacuum` | VACUUM (dry_run por defecto) |
| POST | `/api/maintenance/logs/cleanup` | Limpiar logs antiguos (dry_run por defecto) |

Todos protegidos con Bearer token.

### UI Settings/Maintenance

- Panel de mantenimiento en frontend con estado, backups y operaciones

## Garantías de seguridad

- Los secretos (`tmdb_api_key`, `emu_api_key`) nunca aparecen en export sin confirmación explícita
- Todas las operaciones destructivas requieren `dry_run=True` por defecto + token de confirmación
- Los checks de diagnóstico no exponen nombres ni valores de claves secretas

## Confirmaciones

- `Uploadrr/` **no tocado** — ningún archivo dentro del directorio fue modificado
- Push **no realizado** — rama `master` local únicamente

## Archivos modificados en Fase 7C

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/services/runtime_diagnostics.py` | +2 checks: `check_required_secrets()`, `check_arr_instances_configuration()` |
| `emuwarez_uploadrr/web/schemas.py` | +5 schemas de mantenimiento |
| `emuwarez_uploadrr/web/api/router.py` | Incluye `maintenance_router` |
| `emuwarez_uploadrr/cli.py` | +`maintenance` en MODERN_COMMANDS, parser completo, `cmd_maintenance()` |
| `emuwarez_uploadrr/services/config_export.py` | Nuevo servicio de exportación de configuración |
| `emuwarez_uploadrr/services/maintenance.py` | Nuevo servicio de mantenimiento |
| `emuwarez_uploadrr/web/api/maintenance.py` | Nuevo router de mantenimiento |
| `tests/test_config_export.py` | 9 tests del servicio de exportación |
| `tests/test_maintenance_service.py` | 9 tests del servicio de mantenimiento |
| `tests/test_maintenance_api.py` | 23 tests de los endpoints API |
