# Fase 8A — ARR Health, Verificación Filesystem y Motor de Recomendaciones

## Rama

```
feature/ui-phase-08a-arr-health-filesystem-recommendations
```

## Archivos creados

| Archivo | Descripción |
|---------|-------------|
| `emuwarez_uploadrr/services/library_verification.py` | Verificación read-only de archivos en disco |
| `emuwarez_uploadrr/services/arr_health.py` | Lectura de queue/historial ARR, mapeo a biblioteca |
| `emuwarez_uploadrr/services/recommendations.py` | Motor de recomendaciones por item |
| `emuwarez_uploadrr/web/api/arr_health.py` | Router Phase 8A: ARR health, verify-files, recommendations, diagnostics |
| `frontend/src/api/diagnostics.ts` | API client para endpoints Phase 8A |
| `tests/test_library_verification.py` | Tests verificación filesystem |
| `tests/test_arr_health.py` | Tests ARR health service |
| `tests/test_recommendations.py` | Tests motor de recomendaciones |
| `tests/test_arr_diagnostics_api.py` | Tests endpoints API |
| `tests/test_arr_diagnostics_cli.py` | Tests CLI |
| `docs/codex_checkpoint_config_maintenance_v0.md` | Checkpoint Fase 7C |

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/database.py` | +migraciones Phase 8A (columnas library_items, tablas diagnostic_runs e item_diagnostics), schema v8 |
| `emuwarez_uploadrr/services/runtime_diagnostics.py` | +`check_arr_health_configuration()` |
| `emuwarez_uploadrr/services/library.py` | +`get_dashboard_diagnostics()` |
| `emuwarez_uploadrr/web/api/router.py` | Incluye `arr_health_router` antes de `library_router` |
| `emuwarez_uploadrr/web/schemas.py` | +campos Phase 8A en LibraryItemResponse, MissingItemResponse, DashboardSummaryResponse |
| `emuwarez_uploadrr/web/api/library.py` | `_to_lib_response` y `_to_missing_response` incluyen campos Phase 8A |
| `emuwarez_uploadrr/web/api/dashboard.py` | Dashboard incluye contadores Phase 8A |
| `emuwarez_uploadrr/cli.py` | +comando `arr`, +subcomandos `library verify-files/verify-file/recommendations/recommendation/diagnostics`, +`missing diagnostics` |
| `frontend/src/types/api.ts` | +campos Phase 8A en LibraryItemResponse, MissingItemResponse, DashboardSummaryResponseV2 |
| `frontend/src/pages/DashboardPage.tsx` | +panel Salud Radarr/Sonarr |
| `frontend/src/pages/LibraryPage.tsx` | +columnas Archivo/Diagnóstico/Acción, +detalle Phase 8A |
| `frontend/src/pages/MissingPage.tsx` | +columnas Queue/Diagnóstico/Acción, +botones refresh ARR / verificar / recalcular |
| `frontend/src/pages/InstancesPage.tsx` | +botón Refrescar salud ARR |
| `README_CLI_READY.md` | +sección Diagnóstico Radarr/Sonarr y verificación filesystem |

## Tablas / columnas añadidas a BD

### `library_items` — columnas nuevas

```
file_exists, file_is_video, file_size_on_disk, file_verified_at, file_verification_error
arr_queue_status, arr_queue_title, arr_queue_progress, arr_queue_timeleft, arr_queue_error, arr_queue_raw_json
arr_history_status, arr_history_event_type, arr_history_error, arr_history_source_title, arr_history_raw_json
diagnostic_status, diagnostic_summary, diagnostic_reasons_json
recommended_action, recommendation_reasons_json, recommendation_updated_at
```

### Tablas nuevas

- `library_diagnostic_runs` (run_type, status, items_checked/updated, warnings/errors, started_at, finished_at, summary_json)
- `library_item_diagnostics` (library_item_id, run_id, severity, code, message, details_json)

## Servicios añadidos

### `services/library_verification.py`

- `verify_library_item_file(item_id, conn)` — verifica existencia y tipo de un archivo
- `verify_library_files(conn, filters, limit)` — verificación batch
- `update_library_item_file_status(item_id, result, conn)` — persiste resultado

### `services/arr_health.py`

- `collect_arr_health(conn)` — salud de todas las instancias habilitadas
- `collect_instance_health(instance_id, conn)` — salud de una instancia
- `refresh_arr_queue_diagnostics(conn, instance_id)` — lee queue y actualiza biblioteca
- `refresh_arr_history_diagnostics(conn, instance_id, page_size)` — lee historial y actualiza
- `map_queue_to_library_items / map_history_to_library_items` — helpers de mapeo

### `services/recommendations.py`

- `build_recommendation_for_item(item_id, conn)` — calcula y persiste recomendación
- `refresh_recommendations(conn, filters)` — recalcula batch
- `get_recommendation_for_item(item_id, conn)` — lee recomendación almacenada

## Endpoints añadidos

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/arr/health` | Salud de instancias ARR |
| POST | `/api/arr/health/refresh` | Refrescar queue e historial |
| POST | `/api/library/verify-files` | Verificar archivos en disco (batch) |
| POST | `/api/library/{id}/verify-file` | Verificar archivo de un item |
| POST | `/api/library/recommendations/refresh` | Recalcular recomendaciones |
| GET | `/api/library/{id}/recommendation` | Recomendación de un item |
| GET | `/api/library/diagnostics` | Diagnósticos de biblioteca con filtros |
| GET | `/api/missing/diagnostics` | Faltantes enriquecidos |

Todos requieren Bearer token. Sin token: 401.

## CLI añadida

```bash
python3 emuwarez_uploader.py arr health
python3 emuwarez_uploader.py arr refresh-health [--no-queue] [--no-history] [--history-size N]
python3 emuwarez_uploader.py library verify-files [--limit N] [--status S]
python3 emuwarez_uploader.py library verify-file <id>
python3 emuwarez_uploader.py library recommendations
python3 emuwarez_uploader.py library recommendation <id>
python3 emuwarez_uploader.py library diagnostics [--limit N] [--status S]
python3 emuwarez_uploader.py missing diagnostics [--limit N]
```

## UI añadida

- **DashboardPage**: panel compacto "Salud Radarr/Sonarr" con contadores ok/warning/error y métricas de diagnóstico
- **LibraryPage**: columnas Archivo, Diagnóstico, Acción recomendada, Queue; detalle de item con bloque Phase 8A
- **MissingPage**: columnas Queue ARR, Diagnóstico, Acción recomendada; botones Refrescar salud ARR / Verificar archivos / Recalcular recomendaciones
- **InstancesPage**: botón global "Refrescar salud Radarr/Sonarr"
- **`frontend/src/api/diagnostics.ts`**: API client completo para los endpoints Phase 8A

## Reglas de recomendación implementadas

| Condición | Acción |
|-----------|--------|
| Queue=downloading | view_progress |
| Queue=queued | wait_download |
| Queue=pending_import | review_arr |
| Queue=import_error | review_arr |
| Disponible + archivo no en disco | fix_path |
| Disponible + nomenclatura no adaptada | adapt_nomenclature |
| Disponible + nomenclatura correcta + sin prepared_path | run_preflight |
| Disponible + nomenclatura correcta + prepared_path | upload |
| Faltante sin queue | review_arr |
| Error historial ARR + no disponible | review_arr |

`create_emu_request` no se recomienda cuando: en queue, descargando, pending import, ya existe petición compatible, petición llena, problema parece de ARR.

## Garantías read-only

- `library_verification.py`: sin rename, delete, move, hardlink, mkdir, subprocess
- `arr_health.py`: sin llamadas destructivas a ARR, sin búsquedas iniciadas, sin imports forzados
- CLI `arr health` y `arr refresh-health`: solo lectura de queue/historial/status
- `library verify-files`: solo `stat()`, sin modificar archivos

## Validaciones ejecutadas

| Check | Resultado |
|-------|-----------|
| `python3 -m py_compile` (todos los .py) | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
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

## Resultado pytest

```
563 passed, 1 warning in 109.93s
```

- 511 tests heredados: todos pasando
- 52 tests nuevos Phase 8A: todos pasando
  - `tests/test_library_verification.py`: 7 tests
  - `tests/test_arr_health.py`: 6 tests
  - `tests/test_recommendations.py`: 12 tests
  - `tests/test_arr_diagnostics_api.py`: 17 tests
  - `tests/test_arr_diagnostics_cli.py`: 8 tests (+ 2 en test_arr_health)

## Resultado npm build

```
✓ 71 módulos transformados, sin errores
```

## Resultado Docker smoke

```
8 OK, 0 FAIL — Smoke test PASADO
```

## Confirmaciones

- `Uploadrr/` **no tocado** — ningún archivo dentro fue modificado
- Jellyfin **no implementado**
- Seerr **no implementado**
- mkvpropedit **no implementado**
- Creación automática de peticiones eMuwarez **no implementada**
- Radarr/Sonarr siguen siendo la fuente principal
- Push **no realizado**

## Riesgos pendientes

- El mapeo de queue/historial a items de biblioteca es conservador (por movieId/seriesId). No cubre episodios individuales desde historial Sonarr (solo nivel de serie).
- `library_diagnostic_runs` y `library_item_diagnostics` están creadas pero no se usan aún para registros de runs (preparado para Fase 8B).
- Los campos `arr_health_ok/warning/error` en el dashboard requieren ejecutar explícitamente `arr refresh-health` o la API `/api/arr/health/refresh`; no se actualiza automáticamente en background.

## Siguiente fase recomendada

**Fase 8B** — Integración completa de diagnósticos: registro de runs en `library_diagnostic_runs`, alertas automáticas en sync, y panel de historial de diagnósticos en la UI.
