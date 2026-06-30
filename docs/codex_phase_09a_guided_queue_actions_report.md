# Phase 9A — Ejecución guiada desde la cola operativa

**Rama:** `feature/ui-phase-09a-guided-queue-actions`
**Schema version:** 11 (anterior: 10)
**Fecha:** 2026-06-30

---

## Objetivo

Añadir ejecución guiada por item desde la cola operativa. Cada item expone un plan de acción que indica exactamente dónde y cómo ejecutar la acción necesaria. Nada se ejecuta de forma automática ni sin confirmación explícita del usuario.

---

## Contrato de seguridad (inmutable)

- `execute_safe_queue_action` **nunca** ejecuta Uploadrr.
- `execute_safe_queue_action` **nunca** aplica nomenclatura.
- `execute_safe_queue_action` **nunca** crea hardlinks.
- `execute_safe_queue_action` **nunca** crea peticiones eMuwarez.
- `execute_safe_queue_action` **nunca** modifica Radarr/Sonarr ni archivos de media.
- Acciones inline permitidas: `verify_file`, `refresh_queue_item`, `view_plan`.
- Todas las demás devuelven respuesta bloqueada con `guided_flow` y `ui_route`.

---

## Cambios de base de datos (schema v11)

### Nueva tabla: `operational_action_events`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | INTEGER PK | |
| queue_item_id | INTEGER | FK → operational_queue_items |
| action | TEXT | Nombre del evento/acción |
| event_type | TEXT | blocked / plan_viewed / safe_action_executed / error |
| status | TEXT | ok / warning / blocked / error |
| message | TEXT | Mensaje descriptivo |
| details_json | TEXT | JSON sanitizado (sin api_key / token / password / secret) |
| created_at | TEXT | ISO UTC |

Índices: `idx_oae_queue_item`, `idx_oae_created`.

### Nuevas columnas en `operational_queue_items`

- `last_action_at TEXT` — timestamp de la última acción
- `last_action_status TEXT` — ok / warning / blocked / error
- `last_action_message TEXT` — mensaje de la última acción

Migraciones idempotentes con `try/except` sobre `ALTER TABLE`.

---

## Archivos nuevos / modificados

### Backend

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/database.py` | SCHEMA_VERSION 10→11, `_migrate_operational_actions_tables()` |
| `emuwarez_uploadrr/services/operational_actions.py` | **NUEVO** — servicio completo |
| `emuwarez_uploadrr/web/api/operational_actions.py` | **NUEVO** — 4 endpoints API |
| `emuwarez_uploadrr/web/api/router.py` | Include `operational_actions_router` |
| `emuwarez_uploadrr/cli.py` | 4 subcomandos: `queue actions/action-plan/execute-safe/events` |

### Frontend

| Archivo | Cambio |
|---------|--------|
| `frontend/src/types/api.ts` | Interfaces Phase 9A |
| `frontend/src/api/operationalQueue.ts` | 4 nuevas funciones de API |
| `frontend/src/components/QueueActionPanel.tsx` | **NUEVO** — panel de acción guiada |
| `frontend/src/pages/QueuePage.tsx` | Botón "Plan" por fila + render de `QueueActionPanel` |
| `frontend/src/pages/DashboardPage.tsx` | Botón "Acción →" en panel "Qué hacer ahora" |
| `frontend/src/components/AppShell.tsx` | `onNavigate` threading a QueuePage y DashboardPage |

### Tests

| Archivo | Tests |
|---------|-------|
| `tests/test_operational_actions.py` | 22 tests — servicio |
| `tests/test_operational_actions_api.py` | 12 tests — endpoints API |
| `tests/test_operational_actions_cli.py` | 9 tests — CLI |

---

## Endpoints API

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/operational-queue/{id}/actions` | Bearer | Listar acciones disponibles |
| GET | `/api/operational-queue/{id}/action-plan` | Bearer | Plan completo guiado |
| POST | `/api/operational-queue/{id}/execute-safe-action` | Bearer | Ejecutar acción segura |
| GET | `/api/operational-queue/{id}/action-events` | Bearer | Historial de eventos |

Sin token: 401. Item no encontrado: 404. Acción bloqueada: 409.

---

## Action → flow mapping

| Action | Flow | Ruta UI | Modal | Confirmación | Safe inline |
|--------|------|---------|-------|-------------|-------------|
| adapt_nomenclature | nomenclature | /library | nomenclature | APLICAR_NOMENCLATURA | No |
| run_preflight | upload_preflight | /uploads | preflight | — | No |
| upload | upload_execution | /uploads | upload_confirmation | INICIAR_UPLOADRR | No |
| retry_upload | upload_retry | /uploads | retry_upload | INICIAR_UPLOADRR | No |
| view_upload | upload_logs | /uploads | upload_detail | — | No |
| verify_file | filesystem_verify | /library | — | — | **Sí** |
| wait_download | arr_status | /missing | — | — | No |
| review_arr | arr_diagnostics | /instances | — | — | No |
| manual_review | context_review | /queue | — | — | No |

---

## CLI (queue subcomandos nuevos)

```bash
# Ver acciones disponibles
python3 emuwarez_uploader.py queue actions <id>

# Ver plan completo
python3 emuwarez_uploader.py queue action-plan <id>

# Ejecutar acción segura
python3 emuwarez_uploader.py queue execute-safe <id> [--action verify_file]

# Ver historial de eventos
python3 emuwarez_uploader.py queue events <id> [--limit 20]
```

---

## UI — QueuePage

Cada fila de la tabla tiene botón **Plan** (azul) que:
1. Abre `QueueActionPanel` para ese item.
2. Si ya está abierto para ese item, lo cierra.

El panel muestra:
- Resumen: acción, flow, prioridad (color), estado.
- Dónde ejecutar: ruta UI + modal + token de confirmación si aplica.
- Botón "Abrir en X →" si `onNavigate` está disponible.
- Bloqueadores y razones.
- Botones de acción segura inline (verde, sin confirmación).
- Historial de eventos colapsable.

El panel "Qué hacer ahora" del Dashboard tiene botón **Acción →** por item que navega a `/queue`.

---

## Validaciones

| Check | Resultado |
|-------|-----------|
| `py_compile` (todos los .py) | OK |
| `pytest -q` | **681 passed** |
| `npm run build` | OK (76 módulos) |
| `docker build` | OK |
| Docker smoke (import service) | OK |
