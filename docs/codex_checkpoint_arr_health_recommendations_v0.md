# Checkpoint — ARR Health, Verificación Filesystem y Motor de Recomendaciones (v0)

## Merge

| Campo | Valor |
|-------|-------|
| Rama mergeada | `feature/ui-phase-08a-arr-health-filesystem-recommendations` |
| Commit merge | `2e23e7f merge: ARR health filesystem recommendations milestone` |
| Commit Fase 8A | `9de3ea5 feat: add ARR health filesystem verification and recommendations` |
| Rama destino | `master` |
| Tag creado | `emuwarez-uploadrr-arr-health-recommendations-v0` |

## Validaciones pre-merge (en feature branch)

| Check | Resultado |
|-------|-----------|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" … py_compile` | OK |
| `json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py --help` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web-contract` | OK |
| `python3 emuwarez_uploader.py web info` | OK |
| `python3 emuwarez_uploader.py web setup-status` | OK |
| `python3 emuwarez_uploader.py web doctor` | OK |
| `python3 emuwarez_uploader.py maintenance status` | OK |
| `python3 emuwarez_uploader.py arr health` | OK |
| `python3 emuwarez_uploader.py library verify-files` | OK |
| `python3 emuwarez_uploader.py library recommendations` | OK |
| `python3 emuwarez_uploader.py library diagnostics` | OK |
| `python3 emuwarez_uploader.py missing diagnostics` | OK |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py library list` | OK |
| `python3 emuwarez_uploader.py missing list` | OK |
| `python3 emuwarez_uploader.py requests list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |
| pytest (pre-merge) | **563 passed, 1 warning** |
| npm run build (pre-merge) | **71 módulos, sin errores** |
| docker build checkpoint-08a (pre-merge) | OK |
| docker compose config (pre-merge) | OK |
| docker smoke test (pre-merge) | **8 OK, 0 FAIL** |

## Validaciones post-merge (en master)

| Check | Resultado |
|-------|-----------|
| `python3 -m py_compile` todos los .py | OK |
| `json.tool docs/ui_backend_contract.json` | OK |
| Todos los comandos CLI | OK |
| pytest (post-merge) | **563 passed, 1 warning** |
| npm run build (post-merge) | **71 módulos, sin errores** |
| docker build checkpoint-08a (post-merge) | OK |
| docker smoke test (post-merge) | **8 OK, 0 FAIL** |

## Funcionalidades incluidas hasta este milestone

- Radarr/Sonarr siguen siendo la fuente principal y suficiente de contenido
- Verificación filesystem read-only (`library_verification.py`)
- Columnas `file_exists`, `file_verified_at`, `file_size_on_disk`, `file_verification_error`
- Diagnóstico queue ARR (`arr_queue_status`, `arr_queue_progress`, `arr_queue_timeleft`, `arr_queue_error`)
- Diagnóstico historial ARR (`arr_history_status`, `arr_history_event_type`, `arr_history_error`)
- Tablas `library_diagnostic_runs` y `library_item_diagnostics` (preparadas para Fase 8B)
- Motor de recomendaciones (`recommendations.py`) con lógica: downloading→view_progress, queued→wait_download, pending_import/import_error→review_arr, available+no_file→fix_path, available+not_adapted→adapt_nomenclature, available+correct+prepared→upload, available+correct→run_preflight, missing→review_arr
- Campo `recommended_action` por item de biblioteca
- Endpoints protegidos `/api/arr/health`, `/api/arr/health/refresh`
- Endpoints protegidos `/api/library/verify-files`, `/api/library/{id}/verify-file`
- Endpoints protegidos `/api/library/recommendations/refresh`, `/api/library/{id}/recommendation`
- Endpoints protegidos `/api/library/diagnostics`, `/api/missing/diagnostics`
- CLI `arr health` / `arr refresh-health`
- CLI `library verify-files` / `library verify-file` / `library diagnostics` / `library recommendations` / `library recommendation`
- CLI `missing diagnostics`
- Dashboard con panel "Salud Radarr/Sonarr" (ok/warning/error y contadores Phase 8A)
- LibraryPage con columnas Archivo, Diagnóstico, Acción recomendada y detalle Phase 8A en modal
- MissingPage con columnas Queue ARR, Diagnóstico, Acción recomendada; botones Refrescar salud ARR / Verificar archivos / Recalcular recomendaciones
- InstancesPage con botón "Refrescar salud Radarr/Sonarr"
- API client `frontend/src/api/diagnostics.ts`
- Schema BBDD version 8 (22 columnas nuevas en `library_items`)
- `check_arr_health_configuration()` en runtime diagnostics
- `get_dashboard_diagnostics()` en library service
- 52 tests nuevos Phase 8A (563 total)

## Funcionalidades bloqueadas todavía

- Jellyfin — no implementado
- Seerr — no implementado
- mkvpropedit real — no implementado
- Modificación de título interno MKV — no implementada
- Creación automática de peticiones eMuwarez — no implementada
- Copia/reflink cross-device — no implementada

## Confirmaciones

- `Uploadrr/` **no fue tocado** — ningún archivo dentro del directorio fue modificado
- Jellyfin **no implementado**
- Seerr **no implementado**
- mkvpropedit **no implementado**
- Creación automática de peticiones eMuwarez **no implementada**
- Radarr/Sonarr siguen siendo la fuente principal
- Push **no realizado**

## Riesgos pendientes para Fase 8B

- Mapeo de queue/historial es a nivel película/serie; no cubre episodios individuales desde historial Sonarr
- `library_diagnostic_runs` creada pero sin registro de runs automáticos aún
- `arr_health_ok/warning/error` en dashboard requiere llamada explícita a refresh; no se actualiza en background
