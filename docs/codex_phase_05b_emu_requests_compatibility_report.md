# Codex Phase 05B — eMuwarez Requests + Compatibility Engine

**Rama:** `feature/ui-phase-05b-emu-requests-compatibility`
**Fecha:** 2026-06-29
**Tests backend:** 237 passed, 0 failed (+96 tests respecto a fase 5A)
**Build frontend:** OK — 65 módulos, ~219 KB gzip total

---

## Resumen

Implementación completa del motor de compatibilidad EMU, cliente UNIT3D, pantalla de Peticiones real y CLI extendida. El endpoint `POST /api/missing/{id}/create-emu-request` permanece como stub bloqueado por diseño.

---

## Archivos creados

```
emuwarez_uploadrr/services/compatibility.py  — motor de normalización y cruce
emuwarez_uploadrr/web/api/requests.py        — router real de /api/requests
frontend/src/api/requests.ts                 — módulo API frontend
tests/test_emu_requests.py                   — tests integración EMU
tests/test_compatibility.py                  — tests motor de compatibilidad
tests/test_requests_api.py                   — tests endpoints /api/requests
docs/codex_phase_05b_emu_requests_compatibility_report.md
```

---

## Archivos modificados

```
emuwarez_uploadrr/integrations/emu.py        — añade funciones UNIT3D
emuwarez_uploadrr/services/requests.py       — funciones enriquecidas
emuwarez_uploadrr/database.py                — migraciones idempotentes
emuwarez_uploadrr/web/schemas.py             — esquemas Request* + dashboard EMU
emuwarez_uploadrr/web/api/router.py          — registra requests_router
emuwarez_uploadrr/web/api/placeholders.py    — elimina stubs de requests
emuwarez_uploadrr/web/api/dashboard.py       — añade estadísticas EMU
emuwarez_uploadrr/cli.py                     — añade mark-reviewed
frontend/src/types/api.ts                    — tipos Request*
frontend/src/pages/RequestsPage.tsx          — pantalla real
frontend/src/styles/components.css           — CSS detail-panel, sync-info, etc.
tests/test_web_app.py                        — /api/requests pasa de stub a real
```

---

## eMuwarez UNIT3D API

eMuwarez ejecuta la plataforma UNIT3D (`https://emuwarez.com`). Auth con `?api_token=<key>`.

| Función nueva | Endpoint UNIT3D |
|--------------|-----------------|
| `emu_test_connection(api_key)` | `GET /api/torrents/filter?api_token=…&perPage=1` |
| `emu_get_requests(api_key, page, per_page)` | `GET /api/requests?api_token=…&page=N&perPage=100` |
| `emu_get_request_detail(api_key, request_id)` | `GET /api/requests/{id}?api_token=…` |
| `emu_search_existing(api_key, query)` | `GET /api/torrents/filter?api_token=…&name=query` |
| `emu_fetch_all_pages(api_key)` | Paginación automática de requests |

La función `_flatten_unit3d(raw)` normaliza el formato anidado `{id, attributes: {...}, links: {...}}` a dict plano antes de `normalize_request()`.

Autores: `anon=true` → `author=None`, siempre `author_visible=0`.

---

## Motor de compatibilidad (`services/compatibility.py`)

| Función | Descripción |
|---------|-------------|
| `normalize_title(value)` | Sin acentos, casefold, solo alfanumérico |
| `compact_title(value)` | Sin artículos ni espacios |
| `parse_resolution(value)` | Texto → px height entero |
| `parse_source(value)` | Texto → clave canónica (`bluray`, `webdl`, …) |
| `compare_resolution(requested, local)` | `True/False/None` (None = sin restricción) |
| `compare_source(requested, local)` | `True/False/None` |
| `match_request_to_library(req, library)` | Lista de candidatos ordenados por confianza |
| `classify_request_match(req, item, ...)` | `{status, confidence, reasons, ...}` |
| `rank_request_matches(matches)` | Ordena por prioridad compatible → parcial → no compatible → llena |

### Prioridad de cruce

1. TMDb ID → confianza 1.0
2. IMDb ID → confianza 0.95
3. Título exacto (normalizado) → confianza 0.90
4. Solapamiento de palabras ≥ 75% → confianza variable

### Clasificación de compatibilidad

| Status | Condición |
|--------|-----------|
| Compatible | Resolución ≥ pedida Y source ≥ pedido (o sin restricción) |
| Parcial | Una condición no cumple |
| No compatible | Ambas condiciones fallan |
| Llena | `emu_status` contiene "filled"/"lleno"/"1" |

---

## Migraciones DB idempotentes

```sql
-- request_items (nuevas columnas)
ALTER TABLE request_items ADD COLUMN reviewed_at TEXT;
ALTER TABLE request_items ADD COLUMN last_sync_at TEXT;
```

Ejecutadas en `_migrate_requests()` dentro de `init_db()`, con `try/except OperationalError` para idempotencia.

---

## Nuevas funciones en `services/requests.py`

| Función | Descripción |
|---------|-------------|
| `sync_emu_requests(conn, *, force, passphrase)` | Sync UNIT3D con paginación |
| `list_request_items(conn, *, limit, offset, search, status)` | Lista paginada + match info |
| `get_request_item(conn, id)` | Detalle sin match |
| `get_request_detail(conn, id)` | Detalle + mejor match |
| `match_all_requests(conn)` | Recalcula todos los cruces |
| `match_single_request(conn, id)` | Re-cruza una sola petición |
| `mark_request_reviewed(conn, id)` | Actualiza `reviewed_at` |
| `get_request_sync_status(conn)` | Estado de sincronización |

Funciones antiguas (`sync_requests`, `list_requests`, `get_request`, `match_requests`) conservadas para retro-compatibilidad.

---

## Endpoints web reales

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/requests` | Lista paginada + match info |
| `GET` | `/api/requests/sync-status` | Estado de sincronización |
| `POST` | `/api/requests/sync` | Sincronizar (`force: bool`) |
| `GET` | `/api/requests/{id}` | Detalle + match |
| `POST` | `/api/requests/{id}/match` | Re-cruzar una petición |
| `POST` | `/api/requests/{id}/mark-reviewed` | Marcar revisada |
| `POST` | `/api/missing/{id}/create-emu-request` | **SIGUE BLOQUEADO** (stub) |

El dashboard (`GET /api/dashboard/summary`) añade opcionalmente:
- `requests_total`, `requests_compatible`, `requests_filled`, `requests_last_sync_at`

---

## CLI extendida

```bash
python3 emuwarez_uploader.py requests sync             # usa UNIT3D api_token
python3 emuwarez_uploader.py requests sync --force     # ignora límite de 1 hora
python3 emuwarez_uploader.py requests sync --endpoint-url https://...  # legacy Bearer
python3 emuwarez_uploader.py requests list [--search X] [--limit N]
python3 emuwarez_uploader.py requests show <id>
python3 emuwarez_uploader.py requests match
python3 emuwarez_uploader.py requests mark-reviewed <id>
```

---

## Pantalla Peticiones (frontend)

Archivo: `frontend/src/pages/RequestsPage.tsx`

- Header con estado de sync (última sync + tiempo hasta disponible)
- Botón "Sincronizar" (deshabilitado si throttled) + "Forzar" si hay espera
- Filtro de búsqueda por título
- Filtro de estado de compatibilidad
- Tabla: Título, Resolución, Source, Compatibilidad (badge), Contenido local, Estado EMU
- Paginación (50 ítems por página)
- Panel lateral al pulsar fila: detalle completo, motivos del cruce, enlace a EMU, botón "Marcar como revisada"

Módulo API: `frontend/src/api/requests.ts`
Tipos TS: añadidos en `frontend/src/types/api.ts`

---

## Seguridad

- Autor de peticiones: nunca expuesto (`author_visible=0` siempre). Si `anon=true` en UNIT3D, se guarda `author=null`.
- API key: enviada solo como `?api_token=` en la query string (UNIT3D estándar), nunca en respuestas.
- Rate limit: mínimo 3600 segundos entre syncs. `force=True` es parámetro de cuerpo en el endpoint (cualquier usuario autenticado puede forzar — en producción se restringe por rol).
- `POST /api/missing/{id}/create-emu-request` sigue retornando `{implemented: false, stub: true}`.

---

## Tests añadidos

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_emu_requests.py` | 18 | `emu.py`: flatten, normalize, fetch_all_pages, create_request blocked |
| `test_compatibility.py` | 34 | Todas las funciones de `compatibility.py` |
| `test_requests_api.py` | 27 | Todos los endpoints `/api/requests` |
| `test_web_app.py` | actualizado | `/api/requests` ahora retorna 200 real (no stub) |

**Total: 237 tests, 0 failed**

---

## Validaciones ejecutadas

```
python3 -m py_compile emuwarez_uploadrr/**/*.py      → OK
python3 emuwarez_uploader.py requests --help         → OK (incluye mark-reviewed)
pytest tests/ -q                                     → 237 passed, 0 failed
npm run build                                        → OK (65 módulos, ~219 KB)
```

---

## Criterios de aceptación

| Criterio | Estado |
|----------|--------|
| UNIT3D `?api_token=` usado para requests EMU | ✓ |
| Paginación automática de todas las páginas | ✓ |
| Motor de compatibilidad en módulo propio | ✓ |
| Migraciones DB idempotentes | ✓ |
| Rate limit 1 hora con `force` override | ✓ |
| Autores nunca expuestos | ✓ |
| `create-emu-request` sigue bloqueado | ✓ |
| `GET /api/requests` retorna datos reales | ✓ |
| `POST /api/requests/sync` con throttling | ✓ |
| `POST /api/requests/{id}/mark-reviewed` | ✓ |
| Dashboard summary con estadísticas EMU | ✓ |
| CLI `requests mark-reviewed <id>` | ✓ |
| RequestsPage real con filtros y panel lateral | ✓ |
| 237 tests passing | ✓ |
| `npm run build` OK | ✓ |
| Uploadrr/ no modificado | ✓ |
| CLI legacy sigue funcionando | ✓ |
