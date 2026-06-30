# Checkpoint — Guided Operational Queue Actions v0

**Fecha:** 2026-06-30
**Tag:** `emuwarez-uploadrr-guided-queue-actions-v0`
**Commit merge:** `ab8c8c5` — merge: guided operational queue actions milestone
**Commit Fase 9A:** `feffb4b` — feat: add guided operational queue actions (Phase 9A)
**Commit doc fix:** `11a40e1` — docs: fix phase 9A report
**Rama mergeada:** `feature/ui-phase-09a-guided-queue-actions` → `master`

---

## Validaciones pre-merge (rama 9A)

| Check | Resultado |
|-------|-----------|
| `py_compile emuwarez_uploader.py` | OK |
| `py_compile emuwarez_uploadrr/**/*.py` | OK |
| `json.tool docs/ui_backend_contract.json` | OK |
| `emuwarez_uploader.py --help` | OK |
| `emuwarez_uploader.py db init` | OK |
| `emuwarez_uploader.py web-contract` | OK |
| `emuwarez_uploader.py web info` | OK |
| `emuwarez_uploader.py web setup-status` | OK |
| `emuwarez_uploader.py web doctor` | OK |
| `emuwarez_uploader.py maintenance status` | OK |
| `emuwarez_uploader.py arr health` | OK |
| `emuwarez_uploader.py library diagnostics` | OK |
| `emuwarez_uploader.py library recommendations` | OK |
| `emuwarez_uploader.py missing diagnostics` | OK |
| `emuwarez_uploader.py requests readiness` | OK |
| `emuwarez_uploader.py requests prioritized` | OK |
| `emuwarez_uploader.py queue summary` | OK |
| `emuwarez_uploader.py queue refresh` | OK |
| `emuwarez_uploader.py queue list` | OK |
| `emuwarez_uploader.py queue action-plan 1` | OK (item no encontrado — esperado) |
| `emuwarez_uploader.py queue actions 1` | OK (item no encontrado — esperado) |
| `emuwarez_uploader.py queue events 1` | OK (sin eventos — esperado) |
| `emuwarez_uploader.py instances list` | OK |
| `emuwarez_uploader.py library list` | OK |
| `emuwarez_uploader.py missing list` | OK |
| `emuwarez_uploader.py requests list` | OK |
| `emuwarez_uploader.py upload jobs` | OK |
| `pytest -q` | **681 passed** |
| `npm run build` | OK (76 módulos, 140.89 kB JS) |
| `docker build` | OK |
| `docker compose config` | OK |
| `docker-smoke-test.sh` | **8/8 OK** |

## Validaciones post-merge (master)

| Check | Resultado |
|-------|-----------|
| `py_compile` (todos) | OK |
| `json.tool ui_backend_contract.json` | OK |
| CLI (todos los comandos) | OK |
| `pytest -q` | **681 passed** |
| `npm run build` | OK |
| `docker build` | OK |
| `docker-smoke-test.sh` | **8/8 OK** |

---

## Funcionalidades incluidas en este milestone

### Schema v11

- Nueva tabla `operational_action_events` (audit trail por item de cola, con sanitización de API keys)
- Nuevas columnas en `operational_queue_items`: `last_action_at`, `last_action_status`, `last_action_message`
- Migraciones idempotentes con `try/except` sobre `ALTER TABLE`

### Backend

- `emuwarez_uploadrr/services/operational_actions.py` — servicio completo
  - `get_queue_action_plan(item_id, conn)` — plan de acción read-only por item
  - `list_available_queue_actions(item_id, conn)` — lista de acciones disponibles
  - `execute_safe_queue_action(item_id, conn, action=None)` — contrato de seguridad estricto
  - `record_queue_action_event(...)` — auditoría sanitizada
  - `get_queue_action_events(item_id, conn, limit=50)` — historial de eventos
- `emuwarez_uploadrr/web/api/operational_actions.py` — 4 endpoints API
- `emuwarez_uploadrr/web/api/router.py` — inclusión del router de acciones
- `emuwarez_uploadrr/cli.py` — 4 subcomandos nuevos en `queue`

### Acciones guiadas — action → flow mapping

| Action | Flow | Safe inline |
|--------|------|-------------|
| adapt_nomenclature | nomenclature → /library | No (409) |
| run_preflight | upload_preflight → /uploads | No (409) |
| upload | upload_execution → /uploads | No (409) |
| retry_upload | upload_retry → /uploads | No (409) |
| view_upload | upload_logs → /uploads | No (409) |
| verify_file | filesystem_verify → /library | **Sí** |
| wait_download | arr_status → /missing | No (409) |
| review_arr | arr_diagnostics → /instances | No (409) |
| manual_review | context_review → /queue | No (409) |

### API endpoints (Phase 9A)

| Método | Ruta | Auth | Bloqueado |
|--------|------|------|-----------|
| GET | `/api/operational-queue/{id}/actions` | Bearer 401 | — |
| GET | `/api/operational-queue/{id}/action-plan` | Bearer 401 | — |
| POST | `/api/operational-queue/{id}/execute-safe-action` | Bearer 401 | 409 si bloqueada |
| GET | `/api/operational-queue/{id}/action-events` | Bearer 401 | — |

### CLI nuevos subcomandos

- `queue actions <id>` — lista acciones con etiqueta inline/guiada
- `queue action-plan <id>` — plan completo con flow, route, token, blockers
- `queue execute-safe <id> [--action X]` — ejecuta acción segura o muestra guía
- `queue events <id> [--limit N]` — historial de eventos con iconos de estado

### Frontend

- `QueueActionPanel.tsx` — panel de acción guiada con navegación, acciones inline, historial
- `QueuePage.tsx` — botón "Plan" por fila que abre/cierra `QueueActionPanel`
- `DashboardPage.tsx` — botón "Acción →" por item en panel "Qué hacer ahora"
- `AppShell.tsx` — `onNavigate` threading a QueuePage y DashboardPage

### Tests nuevos (40 tests)

- `tests/test_operational_actions.py` — 22 tests de servicio
- `tests/test_operational_actions_api.py` — 12 tests de API
- `tests/test_operational_actions_cli.py` — 9 tests de CLI (nota: 9 tests = 9 funciones, 1 warning = deprecation de httpx no crítico)

---

## Funcionalidades bloqueadas (no implementadas)

| Funcionalidad | Estado |
|---------------|--------|
| Jellyfin | No implementado |
| Seerr | No implementado |
| mkvpropedit real | No implementado |
| Modificación de título interno MKV | No implementado |
| Creación automática de peticiones eMuwarez | No implementado |
| Subida automática sin confirmación | No implementado |
| Ejecución inline de Uploadrr desde cola | Bloqueada — devuelve 409 + flujo guiado |
| Aplicación inline de nomenclatura desde cola | Bloqueada — devuelve 409 + flujo guiado |
| Copia/reflink cross-device | No implementado |

---

## Confirmaciones de seguridad

| Punto de control | Estado |
|-----------------|--------|
| `Uploadrr/` tocado en este milestone | **No** |
| Push realizado a remoto | **No** |
| Jellyfin implementado | **No** |
| Seerr implementado | **No** |
| Subida automática sin confirmación | **No** |
| Petición eMuwarez automática | **No** |
| Uploadrr ejecutable inline desde cola | **No — bloqueado con 409** |
| Nomenclatura aplicable inline desde cola | **No — bloqueado con 409** |
| Docker smoke: Uploadrr/ dentro de imagen | **No** (verificado en smoke test) |

---

## Historial de milestones hasta este punto

| Tag | Descripción |
|-----|-------------|
| emuwarez-uploadrr-nomenclature-preflight-v0 | Preflight Uploadrr |
| emuwarez-uploadrr-nomenclature-apply-v0 | Aplicación segura de nomenclatura |
| emuwarez-uploadrr-controlled-execution-v0 | Ejecución controlada Uploadrr |
| emuwarez-uploadrr-lifecycle-results-v0 | Resultados y retry Uploadrr |
| emuwarez-uploadrr-docker-deployment-v0 | Despliegue Docker |
| emuwarez-uploadrr-docker-smoke-runtime-v0 | Smoke test Docker |
| emuwarez-uploadrr-config-backup-maintenance-v0 | Backup y mantenimiento |
| emuwarez-uploadrr-arr-health-recommendations-v0 | Salud ARR y recomendaciones |
| emuwarez-uploadrr-request-readiness-v0 | Readiness y priorización de peticiones |
| emuwarez-uploadrr-ui-requests-v0 | UI peticiones eMuwarez |
| emuwarez-uploadrr-operational-queue-v0 | Cola operativa unificada (Phase 8C) |
| **emuwarez-uploadrr-guided-queue-actions-v0** | **Ejecución guiada desde cola (Phase 9A)** |
