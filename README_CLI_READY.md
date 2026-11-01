# Referencia de la CLI

Generada con `python3 scripts/referencia_cli.py` a partir de `build_parser()`: no se edita a mano.

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py <comando>
```

Sin Docker, `python3 emuwarez_uploader.py <comando>`. La opción global `--db RUTA` elige otra base SQLite.
Los argumentos entre corchetes son opcionales. El historial de la CLI anterior está en [`docs/historial_cli.md`](docs/historial_cli.md).

## `db` — Operaciones de base de datos local

| Comando | Qué hace |
|---|---|
| `db init` | Crear/actualizar tablas SQLite |
| `db path` | Mostrar ruta de SQLite |

## `instances` — Gestionar instancias Radarr/Sonarr

| Comando | Qué hace |
|---|---|
| `instances list` | Listar instancias |
| `instances add {radarr,sonarr} --name NAME --url URL --api-key API_KEY` | Añadir o actualizar instancia |
| `instances test [ID]` | Probar conexión |
| `instances remove ID` | Eliminar instancia |

## `sync` — Sincronizar biblioteca desde Radarr/Sonarr

| Comando | Qué hace |
|---|---|
| `sync [--episodes]` | Sincronizar biblioteca desde Radarr/Sonarr. `--episodes`: En Sonarr, importar también episodios |

## `library` — Biblioteca local sincronizada

| Comando | Qué hace |
|---|---|
| `library list [--status STATUS] [--request REQUEST] [--nomenclature NOMENCLATURE] [--type TYPE] [--search SEARCH] [--limit LIMIT]` | Listar biblioteca |
| `library show ID` | Ver detalle de item |
| `library verify-files [--limit LIMIT] [--status STATUS]` | Verificar existencia de archivos en disco (solo lectura). `--limit`: Máximo de items a verificar; `--status`: Filtrar por estado (ej: Disponible) |
| `library verify-file ID` | Verificar un archivo concreto |
| `library recommendations` | Recalcular recomendaciones para toda la biblioteca |
| `library recommendation ID` | Ver recomendación de un item |
| `library diagnostics [--limit LIMIT] [--status STATUS]` | Listar diagnósticos de biblioteca |

## `requests` — Peticiones EMU

| Comando | Qué hace |
|---|---|
| `requests sync [--force]` | Sincronizar peticiones EMU. Mínimo 1 vez/hora salvo --force. `--force`: Forzar sincronización ignorando el límite de una hora |
| `requests list [--search SEARCH] [--limit LIMIT]` | Listar peticiones sincronizadas |
| `requests show ID` | Detalle de petición y cruce con biblioteca |
| `requests match` | Recalcular cruces petición/biblioteca |
| `requests mark-reviewed ID` | Marcar petición como revisada |
| `requests create LIBRARY_ID [--dry-run]` | Preparado para futuro: crear petición EMU |
| `requests readiness [ID] [--limit LIMIT]` | Listar readiness de peticiones o detalle de una. `id`: ID de petición (opcional) |
| `requests readiness-refresh` | Recalcular readiness para todas las peticiones |
| `requests candidates ID` | Candidatos locales para una petición |

## `missing` — Contenido faltante

| Comando | Qué hace |
|---|---|
| `missing list [--limit LIMIT]` | Listar faltantes |
| `missing create-request LIBRARY_ID [--dry-run]` | Preparado para futuro: crear petición EMU desde faltante |
| `missing diagnostics [--limit LIMIT]` | Faltantes enriquecidos con queue/history/recomendación |

## `arr` — Diagnóstico avanzado Radarr/Sonarr

| Comando | Qué hace |
|---|---|
| `arr health` | Mostrar salud de instancias ARR |
| `arr refresh-health [--no-queue] [--no-history] [--history-size HISTORY_SIZE]` | Refrescar queue e historial ARR y actualizar diagnósticos. `--no-queue`: Omitir lectura de queue; `--no-history`: Omitir lectura de historial; `--history-size`: Número de entradas de historial (default: 100) |

## `nomenclature` — Nomenclatura eMuwarez: `apply` renombra el archivo original, el resto no modifica archivos

| Comando | Qué hace |
|---|---|
| `nomenclature preview ID [--force]` | Generar propuesta de nomenclatura para un item. `id`: ID del library_item; `--force`: Forzar regeneración aunque ya exista propuesta |
| `nomenclature show ID` | Mostrar última propuesta de nomenclatura. `id`: ID del library_item |
| `nomenclature apply ID [--dry-run] [--apply] [--confirm TOKEN]` | Adaptar nomenclatura renombrando el archivo original. `id`: ID del library_item; `--dry-run`: Solo previsualización (no escribe nada); `--apply`: Aplicar cambios reales; `--confirm`: Token de confirmación: APLICAR_NOMENCLATURA |
| `nomenclature sources` | Listar sources eMuwarez disponibles |
| `nomenclature providers` | Listar providers eMuwarez disponibles |
| `nomenclature fields ID` | Ver campos editables de nomenclatura para un item |
| `nomenclature preview-fields ID [--fields-json FIELDS_JSON]` | Previsualizar nombre con campos dados (JSON). `--fields-json`: JSON de campos editables |

## `mkv-title` — Título interno MKV (Phase 10A)

| Comando | Qué hace |
|---|---|
| `mkv-title preview ID` | Previsualizar título interno MKV sin modificar nada. `id`: ID del library_item |
| `mkv-title apply ID [--dry-run] [--apply] [--confirm TOKEN]` | Aplicar título interno MKV a prepared_path. `id`: ID del library_item; `--confirm`: Token de confirmación: APLICAR_TITULO_MKV |

## `upload` — Subir contenido / preflight Uploadrr

| Comando | Qué hace |
|---|---|
| `upload preflight ID [--request-id REQUEST_ID]` | Validar precondiciones de subida (no ejecuta Uploadrr). `id`: ID del library_item; `--request-id`: ID opcional de request_item vinculada |
| `upload job ID` | Ver detalle de un upload job/preflight. `id`: ID del upload job |
| `upload status ID` | Alias de 'job': ver detalle/estado de un upload job. `id`: ID del upload job |
| `upload jobs [--status STATUS]` | Listar upload jobs/preflights. `--status`: Filtrar por estado (ready, running, completed, failed, cancelled) |
| `upload logs ID [--limit LIMIT]` | Ver logs de un upload job. `id`: ID del upload job; `--limit`: Número máximo de entradas |
| `upload start ID [--dry-run] [--apply] [--confirm TOKEN]` | Iniciar/previsualizar ejecución de Uploadrr. `id`: ID del upload job; `--dry-run`: Solo previsualización (por defecto); `--apply`: Iniciar ejecución real; `--confirm`: Token de confirmación: INICIAR_UPLOADRR |
| `upload cancel ID` | Cancelar un upload job en ejecución. `id`: ID del upload job |
| `upload artifacts ID` | Ver artefactos de un upload job. `id`: ID del upload job |
| `upload retry ID [--dry-run] [--apply] [--confirm TOKEN]` | Reintentar un upload job failed/cancelled. `id`: ID del upload job original; `--dry-run`: Solo previsualización (por defecto); `--apply`: Crear job nuevo y ejecutar; `--confirm`: Token: INICIAR_UPLOADRR |

## `tasks` — Tareas ejecutadas

| Comando | Qué hace |
|---|---|
| `tasks list [--limit LIMIT]` | Listar últimas tareas |

## `logs` — Logs del uploader heredado

| Comando | Qué hace |
|---|---|
| `logs [--tail TAIL]` | Logs del uploader heredado |

## `web` — Servidor web backend FastAPI

| Comando | Qué hace |
|---|---|
| `web info` | Mostrar información del servidor web |
| `web serve [--host HOST] [--port PORT] [--reload]` | Arrancar servidor web. `--host`: Host (default: 0.0.0.0); `--port`: Puerto (default: 9494); `--reload`: Recarga automática (solo desarrollo) |
| `web setup-status` | Mostrar estado del asistente de configuración |
| `web doctor` | Diagnóstico del runtime de la aplicación |
| `web create-admin --username USERNAME` | Crear usuario administrador web. `--username`: Nombre de usuario admin |
| `web reset-password --username USERNAME` | Restablecer la contraseña de un usuario existente (requiere acceso al servidor). `--username`: Nombre de usuario a restablecer |

## `maintenance` — Mantenimiento: backup, configuración, BD y logs

| Comando | Qué hace |
|---|---|
| `maintenance status` | Estado general: inventario config, BD y backups |
| `maintenance backup [--include-secrets] [--confirm TOKEN]` | Crear backup comprimido del directorio de configuración. `--include-secrets`: Incluir las claves (sin esto van vacías, y sin el config.yaml ni las cookies de Uploadrr-EMU); `--confirm`: Token de confirmación para incluir secretos: RESTAURAR_CONFIG |
| `maintenance list-backups` | Listar backups existentes |
| `maintenance restore BACKUP_PATH [--dry-run] [--apply] [--confirm TOKEN]` | Restaurar un backup. `backup_path`: Ruta del archivo .tar.gz a restaurar; `--dry-run`: Solo previsualización (por defecto); `--apply`: Aplicar restauración real; `--confirm`: Token: RESTAURAR_CONFIG |
| `maintenance db-integrity` | PRAGMA integrity_check (solo lectura) |
| `maintenance db-vacuum [--dry-run] [--apply] [--confirm TOKEN]` | VACUUM en la BD SQLite. `--dry-run`: Solo previsualización (por defecto); `--apply`: Ejecutar VACUUM real; `--confirm`: Token: MANTENIMIENTO_DB |

## `demo` — [DEV] Datos demo para E2E controlado. Requiere confirmación explícita.

| Comando | Qué hace |
|---|---|
| `demo seed --media-root MEDIA_ROOT --prepared-root PREPARED_ROOT --confirm TOKEN` | Sembrar datos demo en una BD temporal (requiere --confirm DEMO_SEED). `--media-root`: Raíz de media simulada (ej: /data/media o tmpdir/data/media); `--prepared-root`: Raíz de archivos preparados (ej: /data/uploads/emu); `--confirm`: Token de seguridad obligatorio: DEMO_SEED |
| `demo reset --confirm TOKEN` | Eliminar datos demo de la BD (requiere --confirm DEMO_RESET). `--confirm`: Token de seguridad obligatorio: DEMO_RESET |
