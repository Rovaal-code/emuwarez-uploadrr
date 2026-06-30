# Fase 8B — Request Readiness, Priorización y Candidatos Locales

## Rama

```
feature/ui-phase-08b-request-readiness-prioritization
```

## Archivos creados

| Archivo | Descripción |
|---------|-------------|
| `emuwarez_uploadrr/services/request_readiness.py` | Motor de readiness por petición |
| `emuwarez_uploadrr/web/api/request_readiness.py` | Router Phase 8B |
| `frontend/src/api/requestReadiness.ts` | API client readiness |
| `tests/test_request_readiness.py` | Tests servicio readiness |
| `tests/test_request_readiness_api.py` | Tests endpoints API |
| `tests/test_request_readiness_cli.py` | Tests CLI |

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/database.py` | +migraciones Phase 8B (tablas request_readiness, request_candidates, columnas request_items), schema v9 |
| `emuwarez_uploadrr/web/schemas.py` | +RequestReadinessResponse, RequestCandidateResponse, campos readiness en RequestItemResponse y DashboardSummaryResponse |
| `emuwarez_uploadrr/web/api/router.py` | Incluye request_readiness_router antes de requests_router |
| `emuwarez_uploadrr/web/api/requests.py` | `_row_to_item` incluye campos readiness Phase 8B |
| `emuwarez_uploadrr/web/api/dashboard.py` | Dashboard incluye get_dashboard_readiness_counts |
| `emuwarez_uploadrr/cli.py` | +subcomandos readiness, readiness-refresh, candidates, prioritized |
| `frontend/src/types/api.ts` | +RequestReadinessResponse, RequestCandidateResponse, readiness fields en RequestItemResponse, readiness counts en DashboardSummaryResponseV2 |
| `frontend/src/pages/RequestsPage.tsx` | +columnas readiness/acción/prioridad/candidato, +panel detalle readiness, +candidatos panel, +botón recalcular, +vista priorizada |
| `frontend/src/pages/DashboardPage.tsx` | +panel "Peticiones accionables" (Phase 8B) |
| `README_CLI_READY.md` | +sección Readiness y priorización de peticiones eMuwarez |

## Tablas añadidas a BD (schema v9)

### `request_readiness`

```
id, request_item_id (UNIQUE), best_library_item_id, status, recommended_action,
priority_score, priority_bucket, compatibility_score, upload_readiness_score,
blockers_json, reasons_json, candidate_summary_json, last_evaluated_at,
created_at, updated_at
```

Índices: request_item_id, best_library_item_id, status, recommended_action, priority_bucket

### `request_candidates`

```
id, request_item_id, library_item_id, candidate_rank, match_status, match_score,
compatibility_status, compatibility_score, readiness_status, readiness_score,
blockers_json, reasons_json, created_at, updated_at
```

Índices: request_item_id, library_item_id, candidate_rank, readiness_status

## Columnas añadidas a `request_items`

```
readiness_status, readiness_action, readiness_priority_score,
readiness_priority_bucket, readiness_best_library_item_id, readiness_updated_at
```

## Servicio `services/request_readiness.py`

| Función | Descripción |
|---------|-------------|
| `evaluate_request_readiness(id, conn)` | Evalúa y persiste readiness de una petición |
| `refresh_request_readiness(conn, limit)` | Recalcula readiness batch |
| `get_request_readiness(id, conn)` | Lee readiness almacenado |
| `list_request_readiness(conn, filters, limit, offset)` | Lista con filtros |
| `list_prioritized_requests(conn, limit)` | Ordenado high→medium→low→blocked |
| `build_request_candidates(id, conn)` | Busca y puntúa candidatos |
| `score_request_candidate(req, lib)` | Puntuación individual |
| `select_best_candidate(candidates)` | Elige mejor candidato |
| `get_candidates_for_request(id, conn)` | Lee candidatos almacenados |
| `get_dashboard_readiness_counts(conn)` | Contadores para dashboard |

## Endpoints añadidos

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/requests/readiness/refresh` | Recalcular readiness |
| GET | `/api/requests/readiness` | Listar con filtros |
| GET | `/api/requests/prioritized` | Ordenados por prioridad |
| GET | `/api/requests/{id}/readiness` | Readiness de una petición |
| POST | `/api/requests/{id}/readiness/evaluate` | Evaluar una petición |
| GET | `/api/requests/{id}/candidates` | Candidatos de una petición |

Todos requieren Bearer token. Sin token: 401.

Nota técnica: `request_readiness_router` se registra antes de `requests_router` para evitar colisión de rutas `/requests/readiness` con `/requests/{request_id}`.

## CLI añadida

```bash
python3 emuwarez_uploader.py requests readiness-refresh
python3 emuwarez_uploader.py requests readiness
python3 emuwarez_uploader.py requests readiness <id>
python3 emuwarez_uploader.py requests candidates <id>
python3 emuwarez_uploader.py requests prioritized
```

## UI añadida

- **RequestsPage**: columnas Readiness, Acción, Prioridad, Candidato; panel detalle con bloque readiness (score, blockers); panel de candidatos; botón "Recalcular readiness"; vista "Ver priorizados"; filtro por readiness status
- **DashboardPage**: panel "Peticiones accionables" con contadores ready_to_upload, prioridad alta, necesitan nomenclatura, esperando descarga, bloqueadas

## Scoring implementado

### compatibility_score (0-100)

| Criterio | Puntos |
|----------|--------|
| TMDb match | +40 |
| IMDb match | +38 |
| Título exacto (sin ID) | +18 |
| Título parcial | +12 |
| Año match | +10 |
| Tipo match (movie/series) | +10 |
| Resolución compatible | +10 |
| Source compatible | +10 |
| Sin restricción resolución | +10 |
| Sin restricción source | +10 |

### upload_readiness_score (0-100)

| Criterio | Puntos |
|----------|--------|
| local_status=Disponible | +20 |
| file_exists=true | +20 |
| Sin bloqueo de cola ARR | +15 |
| Sin error historial ARR | +15 |
| Nomenclatura correcta o prepared | +15 |
| Preflight listo (prepared_path) | +15 |

### priority_score

```
priority_score = compatibility_score × 0.45 + upload_readiness_score × 0.45 + urgency × 0.10
```

`urgency`: +10 si Compatible, +5 si Parcial, 0 si no.

Bloqueadores críticos → `priority_score = min(score, 30)`.

### priority_bucket

| Valor | Condición |
|-------|-----------|
| `high` | ready_to_upload, needs_nomenclature con compat≥70 |
| `medium` | downloading/queued con compat≥60, preflight con compat≥70 |
| `low` | no_local_match, downloading débil |
| `blocked` | pending_import, import_error, file_missing, already_exists, upload_error |

## Reglas de readiness implementadas

| Estado | Condición | Acción |
|--------|-----------|--------|
| `no_local_match` | Sin candidato local | `review_arr` |
| `downloading` | arr_queue_status=downloading\|queued | `wait_download` |
| `pending_import` | arr_queue_status=pending_import | `review_arr` / blocked |
| `import_error` | arr_queue_status=import_error | `review_arr` / blocked |
| `file_missing` | Disponible pero file_exists=false | `verify_file` / blocked |
| `uploading` | local_status=Subiendo | `view_upload` |
| `uploaded` | local_status=Subido | `view_upload` / blocked |
| `already_exists` | emu_existence_status=exists | `ignore_already_exists` / blocked |
| `needs_nomenclature` | file_exists + nomenclature=not_adapted | `adapt_nomenclature` |
| `preflight_needed` | nomenclature=correct, sin prepared_path | `run_preflight` |
| `ready_to_upload` | file_exists + nomenclature=correct + prepared_path | `upload` / high |

## Garantías no destructivas

- Sin modificaciones a eMuwarez
- Sin modificaciones a Radarr/Sonarr
- Sin modificaciones al filesystem
- Sin ejecución de Uploadrr
- Sin creación de hardlinks
- Solo escritura en tablas locales: `request_readiness`, `request_candidates`, `request_items` (columnas readiness_*)

## Validaciones ejecutadas

| Check | Resultado |
|-------|-----------|
| `python3 -m py_compile` todos los .py | OK |
| `json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py requests readiness` | OK |
| `python3 emuwarez_uploader.py requests readiness-refresh` | OK |
| `python3 emuwarez_uploader.py requests prioritized` | OK |
| `python3 emuwarez_uploader.py arr health` | OK |
| `python3 emuwarez_uploader.py library diagnostics` | OK |
| `python3 emuwarez_uploader.py library recommendations` | OK |
| `python3 emuwarez_uploader.py missing diagnostics` | OK |
| Todos los list commands | OK |

## Resultado pytest

```
605 passed, 1 warning
```

- 563 tests heredados: todos pasando
- 42 tests nuevos Phase 8B: todos pasando
  - `tests/test_request_readiness.py`: 14 tests
  - `tests/test_request_readiness_api.py`: 17 tests
  - `tests/test_request_readiness_cli.py`: 8 tests (+3 en service tests = 42 total)

## Resultado npm build

```
✓ 72 módulos transformados, sin errores
```

## Resultado Docker

```
docker build: OK (tag emuwarez-uploadrr:phase-08b)
docker compose config: OK
docker smoke: 8 OK, 0 FAIL
```

## Confirmaciones

- `Uploadrr/` **no tocado**
- Jellyfin **no implementado**
- Seerr **no implementado**
- mkvpropedit **no implementado**
- Creación automática de peticiones eMuwarez **no implementada**
- Radarr/Sonarr siguen siendo la fuente principal
- Push **no realizado**

## Riesgos pendientes

- `emu_existence_status` no existe aún en `library_items` → la regla `already_exists` nunca se activa (se descarta silenciosamente con `.get()`)
- Los candidatos se buscan en toda la biblioteca sin restricción de instancia; puede haber falsos positivos en entornos con múltiples instancias cruzadas
- `request_readiness` no se actualiza automáticamente al sincronizar ARR o library; requiere llamada explícita a refresh

## Siguiente fase recomendada

**Fase 8C** — Integración automática: actualización de readiness en el sync ARR, alertas en dashboard cuando peticiones pasan a `ready_to_upload`, y panel de historial de evaluaciones.
