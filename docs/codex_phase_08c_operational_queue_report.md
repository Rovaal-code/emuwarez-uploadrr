# Phase 8C — Cola Operativa Unificada · Informe de implementación

**Fecha:** 2026-06-30
**Rama:** `feature/ui-phase-08c-unified-operational-queue`
**Schema SQLite:** versión 10 (SCHEMA_VERSION = 10)
**Tests:** 641 passed (12 servicio + 17 API + 7 CLI + ~605 previos)

---

## Objetivo

Responder a la pregunta operativa: **¿Qué hago ahora?**

La cola agrega en una única vista priorizada todos los items que requieren atención humana:

- Peticiones con readiness calculado (request_readiness)
- Recomendaciones de biblioteca que no están cubiertas por readiness
- Jobs de upload en estado activo (upload_jobs)
- Issues de ARR detectados en diagnósticos (arr_diagnostics)

La cola **no ejecuta acciones**. No sube contenido. No crea peticiones. No modifica estado externo.

---

## Tablas nuevas (SCHEMA v10)

### `operational_queue_items`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | INTEGER PK | |
| `queue_key` | TEXT UNIQUE | Clave determinista: `request:{id}:readiness`, `library:{id}:recommendation`, `upload:{id}:status`, `arr:{id}:issue:{code}` |
| `item_type` | TEXT | `request_readiness`, `library_recommendation`, `upload_job`, `arr_issue` |
| `entity_type` | TEXT | `request`, `library`, `upload`, `arr` |
| `status` | TEXT | `open`, `ready`, `waiting`, `blocked`, `running`, `resolved`, `ignored`, `completed` |
| `action` | TEXT | `upload`, `adapt_nomenclature`, `run_preflight`, `wait_download`, `review_arr`, `retry_upload`, `verify_file`, `none` |
| `priority_score` | INTEGER | 0–100 heredado de fuente |
| `priority_bucket` | TEXT | `critical`, `high`, `medium`, `low`, `blocked` |
| `blockers_json` | TEXT | JSON lista de bloqueantes |
| `reasons_json` | TEXT | JSON lista de razones |
| `context_json` | TEXT | JSON contexto adicional |
| `last_seen_at` | TEXT | Última vez que apareció en un refresh |
| `resolved_at` | TEXT | Timestamp de resolución |

### `operational_queue_runs`

Registro de cada ejecución de `refresh_operational_queue`: timestamp, items_built, items_open, items_ready, items_blocked, summary_json.

---

## Lógica de prioridad

| Fuente / estado | Bucket | Condición extra |
|-----------------|--------|-----------------|
| `ready_to_upload` | `critical` | `priority_score >= 90` |
| `ready_to_upload` | `high` | `score < 90` |
| `needs_nomenclature` | `high` | — |
| `preflight_needed` | `medium` | — |
| `downloading` | `medium` → `waiting` | status=waiting |
| `uploading` | `medium` → `running` | status=running |
| `no_local_match` | `low` | — |
| `import_error`, `file_missing`, etc. | `blocked` | — |

---

## Servicio (`operational_queue.py`)

| Función | Descripción |
|---------|-------------|
| `upsert_queue_item(item, conn)` | INSERT OR REPLACE by queue_key; resetea resolved_at si re-aparece |
| `build_items_from_request_readiness(limit, conn)` | Mapea request_readiness → queue items |
| `build_items_from_library_recommendations(limit, conn)` | Salta library items ya cubiertos por request_readiness |
| `build_items_from_upload_jobs(limit, conn)` | Excluye completed/cancelled |
| `build_items_from_arr_diagnostics(limit, conn)` | import_error, pending_import, history errors |
| `refresh_operational_queue(conn, ...)` | Reconstruye cola, marca desaparecidos como resolved, registra run |
| `list_operational_queue(conn, ...)` | Ordenado: bucket rank ASC, priority_score DESC, updated_at DESC |
| `get_operational_queue_summary(conn)` | Conteos por status y bucket |
| `mark_queue_item_resolved(item_id, conn, reason)` | Marca resolved_at |
| `ignore_queue_item(item_id, conn, reason)` | Marca ignored |
| `get_dashboard_queue_counts(conn)` | 6 claves `operational_queue_*` para el dashboard |

---

## API (`/api/operational-queue/*`)

Todos los endpoints requieren `Authorization: Bearer <token>`. Sin token: 401.

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/operational-queue/refresh` | Reconstruir cola |
| GET | `/api/operational-queue` | Listar items (filtros: status, action, priority_bucket, item_type, search, limit, offset) |
| GET | `/api/operational-queue/summary` | Resumen por status y bucket |
| GET | `/api/operational-queue/{id}` | Detalle de un item; 404 si no existe |
| POST | `/api/operational-queue/{id}/resolve` | Marcar resolved |
| POST | `/api/operational-queue/{id}/ignore` | Marcar ignored |

---

## CLI (`queue`)

```bash
python3 emuwarez_uploader.py queue refresh
python3 emuwarez_uploader.py queue summary
python3 emuwarez_uploader.py queue list [--bucket critical|high|medium|low|blocked] [--status ready|open|waiting|blocked]
python3 emuwarez_uploader.py queue show <id>
python3 emuwarez_uploader.py queue resolve <id>
python3 emuwarez_uploader.py queue ignore <id>
```

---

## Frontend

### Nuevos ficheros

- `frontend/src/api/operationalQueue.ts` — 6 funciones API
- `frontend/src/pages/QueuePage.tsx` — Página completa con tabla, filtros, panel detalle, resolve/ignore

### Cambios en ficheros existentes

- `frontend/src/components/AppShell.tsx` — Importa `QueuePage`, añade `queue` en `PAGE_TITLE` y `PageContent`
- `frontend/src/components/Sidebar.tsx` — Añade icono SVG para `queue`
- `frontend/src/types/domain.ts` — Añade `{ id: 'queue', label: 'Cola', icon: 'queue' }` en `NAV_ITEMS`
- `frontend/src/types/api.ts` — Añade 6 campos Phase 8C en `DashboardSummaryResponseV2` y 7 nuevas interfaces
- `frontend/src/pages/DashboardPage.tsx` — Panel "Qué hacer ahora" con top 5 items + botón Refrescar

---

## Reglas de seguridad respetadas

- No push
- No modificaciones dentro de `Uploadrr/`
- No subidas reales
- No ejecución de Uploadrr real
- No Jellyfin / Seerr / mkvpropedit
- No creación automática de peticiones eMuwarez
- La cola no ejecuta ninguna acción automáticamente
- Radarr/Sonarr siguen siendo la fuente principal

---

## Resultados de validación

```
pytest: 641 passed, 0 failed
npm run build: ✓ built in 1.98s (133 kB JS gzip 30 kB)
CLI smoke: queue summary / refresh / list → OK (respuestas vacías esperadas)
```
