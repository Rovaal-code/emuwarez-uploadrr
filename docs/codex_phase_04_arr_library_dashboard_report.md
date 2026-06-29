# Codex Phase 04 — Radarr/Sonarr Library Sync & Dashboard API

**Rama:** `feature/ui-phase-04-arr-library-dashboard`
**Fecha:** 2026-06-28
**Tests:** 140 passed, 0 failed

---

## Archivos creados

| Archivo | Descripción |
|---------|-------------|
| `emuwarez_uploadrr/integrations/arr_base.py` | Jerarquía de errores, `arr_request`, `join_api_path`, `normalize_base_url`, `safe_api_key` |
| `emuwarez_uploadrr/services/quality.py` | Extracción de resolución, fuente y calidad desde metadatos Radarr/Sonarr |
| `emuwarez_uploadrr/web/api/instances.py` | Endpoints reales GET/POST /api/instances, test, sync por instancia |
| `emuwarez_uploadrr/web/api/dashboard.py` | Endpoints reales GET /api/dashboard/summary y /activity |
| `emuwarez_uploadrr/web/api/library.py` | Endpoints reales POST /api/sync, GET /api/library, /library/{id}, /missing |
| `tests/test_arr_integrations.py` | 40 tests de clientes Radarr/Sonarr y utilidades |
| `tests/test_library_sync.py` | Tests de sincronización de biblioteca con SQLite en memoria |
| `tests/test_dashboard_library_api.py` | Tests de API completos con auth y mocks HTTP |

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/models.py` | Añadidos `QUEUED`, `DOWNLOADING`, `PENDING_IMPORT`, `IMPORT_ERROR`, `SEARCH_ERROR` a `LocalStatus`; método `not_available()` |
| `emuwarez_uploadrr/integrations/radarr.py` | Funciones instance-dict: `radarr_test_connection`, `radarr_get_movies`, `radarr_get_queue`, `radarr_get_history`, `radarr_get_quality_profiles`, `radarr_get_root_folders`, `radarr_get_system_status`, `build_queue_map`, `movie_to_library_item` |
| `emuwarez_uploadrr/integrations/sonarr.py` | Funciones instance-dict: `sonarr_test_connection`, `sonarr_get_series`, `sonarr_get_episodes`, `sonarr_get_queue`, `sonarr_get_quality_profiles`, `build_episode_queue_map`, `build_series_queue_map`, `series_to_library_item`, `episode_to_library_item` |
| `emuwarez_uploadrr/services/instances.py` | Añadidos `update_instance`, `instance_to_dict_safe`, `test_instance_safe`, `mark_instance_test_result` |
| `emuwarez_uploadrr/services/library.py` | `sync_instance` con queue maps; `list_library` con filtros/paginación; `list_missing` con `_MISSING_STATUSES`; `get_dashboard_summary`; `get_recent_activity`; `count_library` |
| `emuwarez_uploadrr/web/schemas.py` | Añadidos `InstanceSafeResponse`, `InstanceTestResponse`, `AddInstanceRequest`, `SyncRequest`, `SyncResponse`, `DashboardSummaryResponse`, `DashboardActivityItem`, `DashboardActivityResponse`, `LibraryItemResponse`, `LibraryListResponse`, `MissingItemResponse`, `MissingListResponse` |
| `emuwarez_uploadrr/web/api/router.py` | Incluidos routers de instances, dashboard, library |
| `emuwarez_uploadrr/web/api/placeholders.py` | Eliminados stubs de instances/dashboard/library/missing/sync; mantenidos los de requests/uploads/tasks/logs/config |
| `tests/test_web_app.py` | Separados tests de endpoints reales vs stubs; añadidos auth_headers en tests protegidos |
| `tests/test_setup_auth.py` | Actualizado `test_protected_endpoints_accessible_with_token` para respuesta real de dashboard |
| `README_CLI_READY.md` | Sección de sincronización Radarr/Sonarr; estado de implementación actualizado |

---

## Endpoints reales implementados

### Instancias

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/instances` | Bearer | Lista instancias (api_key enmascarada) |
| POST | `/api/instances` | Bearer | Añade instancia |
| POST | `/api/instances/{id}/test` | Bearer | Test de conexión real, guarda resultado |
| POST | `/api/instances/{id}/sync` | Bearer | Sincroniza solo esa instancia |

### Sincronización

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/sync` | Bearer | Sincroniza todas las instancias habilitadas |

### Dashboard

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/dashboard/summary` | Bearer | Contadores reales de biblioteca |
| GET | `/api/dashboard/activity` | Bearer | Últimas tareas ejecutadas |

### Biblioteca

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/library` | Bearer | Lista con filtros: type, status, origin, search, limit, offset |
| GET | `/api/library/{id}` | Bearer | Detalle de ítem |
| GET | `/api/missing` | Bearer | Faltantes + en cola + descargando + con error |

---

## Endpoints que siguen como placeholder

| Ruta | Razón |
|------|-------|
| `POST /api/missing/{id}/create-emu-request` | Requiere capturar endpoint real de eMuwarez |
| `GET /api/missing/{id}/check-emu` | Mismo motivo |
| `GET /api/library/{id}/adapt-nomenclature` | Lógica de adaptación pendiente |
| `POST /api/library/{id}/upload` | Motor heredado no expuesto vía web aún |
| `GET /api/requests` | Endpoint eMuwarez no capturado |
| `GET /api/uploads` | Pendiente de integración |
| `GET /api/tasks` | Stub devuelve lista vacía |
| `GET /api/logs` | Pendiente |
| `GET /api/config` | Pendiente |
| `GET /api/dashboard/upload-activity` | Pendiente estadísticas de subidas |
| `GET /api/dashboard/events` | Pendiente sistema de eventos |
| `GET /api/dashboard/tasks` | Duplicado de tasks, pendiente |

---

## Tablas/columnas añadidas o modificadas

### `instances` (columnas añadidas vía `_migrate_instances`)

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `is_4k` | INTEGER DEFAULT 0 | Marca instancia como perfil 4K |
| `is_anime` | INTEGER DEFAULT 0 | Marca instancia como perfil anime |
| `last_test_status` | TEXT | Resultado del último test ("ok" o "error: ...") |
| `last_test_at` | TEXT | Timestamp del último test |

### `LocalStatus` (nuevos valores)

```
QUEUED          → "En cola"
DOWNLOADING     → "Descargando"
PENDING_IMPORT  → "Pendiente de importar"
IMPORT_ERROR    → "Error de importación"
SEARCH_ERROR    → "Error de búsqueda"
```

---

## Decisiones técnicas

### Detección de estado por cola

La cola de Radarr/Sonarr se consulta en cada sync. Se construye un mapa `{movieId: status}` que se pasa a `movie_to_library_item`. Si el elemento tiene archivo → `AVAILABLE`; si está en la cola → estado de cola; si no → `MISSING`.

### Seguridad de API key

- `GET /api/instances` devuelve `api_key_masked` (4 chars + … + 4 chars), nunca `api_key` completa.
- `radarr_test_connection` / `sonarr_test_connection` nunca incluyen `api_key` en el resultado.
- `safe_api_key()` en `arr_base.py` centraliza el enmascaramiento.

### Slots en InstanceConfig

`InstanceConfig` usa `slots=True` (no tiene `__dict__`). Al pasar a funciones que esperan `dict`, se construye explícitamente:
```python
inst_dict = {"url": instance.url, "api_key": instance.api_key, "name": instance.name}
```

### Mock patch targets

Las funciones importadas con `from .arr_base import arr_request` crean referencias locales en cada módulo. Los tests parchean la referencia local:
```python
patch("emuwarez_uploadrr.integrations.radarr.arr_request", ...)
patch("emuwarez_uploadrr.integrations.sonarr.arr_request", ...)
```

### Filtro `?type=` en /api/library

El parámetro usa `alias="type"` en FastAPI para aceptar `?type=movie` aunque la variable Python sea `item_type` (evita conflicto con builtin `type`).

---

## Suite de tests

| Archivo | Tests |
|---------|-------|
| `tests/test_web_app.py` | 29 |
| `tests/test_setup_auth.py` | 40 |
| `tests/test_arr_integrations.py` | 40 |
| `tests/test_library_sync.py` | ~15 |
| `tests/test_dashboard_library_api.py` | ~16 |
| **Total** | **140** |

Comando para ejecutar:
```bash
.venv/bin/pytest tests/ -q
# 140 passed, 1 warning in ~21s
```

---

## Validaciones ejecutadas

```
python3 emuwarez_uploader.py instances list
python3 emuwarez_uploader.py instances test
python3 emuwarez_uploader.py sync --episodes
python3 emuwarez_uploader.py library list
python3 emuwarez_uploader.py missing list
.venv/bin/pytest tests/ -q  → 140 passed
```

---

## Limitaciones conocidas

- Los episodios de Sonarr solo se sincronizan si `include_episodes=True` y hay archivos de episodio disponibles en la API.
- `GET /api/missing` devuelve `total=len(rows)` (no paginado en el contador). Para paginación correcta usar `count_library` con `_MISSING_STATUSES`.
- Las métricas de subida (`uploading`, `completed`) en el dashboard requieren integración con el motor de subida (pendiente).

---

## Siguiente fase recomendada (Phase 5)

- Capturar endpoint real de peticiones eMuwarez.
- Implementar `POST /api/missing/{id}/create-emu-request`.
- Cruce biblioteca ↔ peticiones por TMDb/IMDb.
- Frontend React con las rutas de la API ya estables.
