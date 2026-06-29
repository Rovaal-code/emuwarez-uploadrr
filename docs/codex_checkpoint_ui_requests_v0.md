# Checkpoint: UI + Requests Compatibility — v0

**Fecha:** 2026-06-29
**Rama mergeada:** `feature/ui-phase-05b-emu-requests-compatibility`
**Commit merge:** `1caf860 merge: UI backend requests compatibility milestone`
**Tag:** `emuwarez-uploadrr-ui-requests-v0`
**Rama destino:** `master`
**Push:** No realizado

---

## Validaciones ejecutadas (antes y después del merge)

| Validación | Resultado |
|-----------|-----------|
| `python3 -m py_compile emuwarez_uploader.py` | ✓ OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs py_compile` | ✓ OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | ✓ JSON válido |
| `python3 emuwarez_uploader.py --help` | ✓ OK |
| `python3 emuwarez_uploader.py db init` | ✓ SQLite lista |
| `python3 emuwarez_uploader.py web-contract` | ✓ OK |
| `python3 emuwarez_uploader.py web info` | ✓ OK |
| `python3 emuwarez_uploader.py web setup-status` | ✓ OK |
| `python3 emuwarez_uploader.py instances list` | ✓ OK |
| `python3 emuwarez_uploader.py library list` | ✓ OK |
| `python3 emuwarez_uploader.py missing list` | ✓ OK |
| `python3 emuwarez_uploader.py requests list` | ✓ OK |
| `pytest -q` | ✓ **237 passed, 0 failed** |
| `npm run build` | ✓ **65 módulos, ~219 KB gzip** |

---

## Resultado pytest

```
237 passed, 1 warning in 25.42s
```

Desglose por archivo:

| Archivo | Tests |
|---------|-------|
| `test_web_app.py` | 16 |
| `test_setup_auth.py` | 52 |
| `test_arr_integrations.py` | 29 |
| `test_library_sync.py` | 37 |
| `test_dashboard_library_api.py` | 22 |
| `test_emu_requests.py` | 18 |
| `test_compatibility.py` | 34 |
| `test_requests_api.py` | 27 |
| **Total** | **237** |

---

## Resultado npm build

```
vite v5.4.21 building for production...
✓ 65 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.39 kB
dist/assets/index-*.css          16.86 kB │ gzip:  3.92 kB
dist/assets/index-*.js           62.42 kB │ gzip: 15.36 kB
dist/assets/react-*.js          140.74 kB │ gzip: 45.79 kB
✓ built in 2.54s
```

---

## Funcionalidades incluidas en este milestone

### CLI legacy
- Modo heredado completamente operativo: preparar, subir, configurar, doctor
- Compatible con los argumentos posicionales originales

### Backend FastAPI
- `GET /api/health`, `/api/runtime`, `/api/contract/json`
- OpenAPI docs en `/api/docs`
- Healthcheck + runtime sin auth

### Setup y autenticación local
- Wizard 7 pasos: admin → base → uploadrr → tmdb → emu → instancias → complete
- PBKDF2-SHA256 (210k iteraciones), `hmac.compare_digest`
- Tokens opacos: `secrets.token_urlsafe(48)`, solo hash SHA-256 en BD
- `Authorization: Bearer <token>` en todas las rutas protegidas
- Contraseñas: mínimo 12 caracteres, mayúsculas, minúsculas, dígito, símbolo
- API keys: nunca en respuestas completas, solo `masked_value`

### Frontend React/Vite
- Login, Setup Wizard (7 pasos), AppShell (sidebar 9 secciones + topbar)
- Dark theme, glassmorphism, CSS propio sin librerías UI externas
- `token` en `localStorage`, limpiado en logout y en 401

### Dashboard real
- `GET /api/dashboard/summary`: contadores biblioteca + estadísticas EMU
- `GET /api/dashboard/activity`: últimas tareas ejecutadas
- Tarjetas: biblioteca total, disponibles, faltantes, Radarr, Sonarr, peticiones EMU

### Biblioteca desde Radarr/Sonarr
- Clientes reales Radarr v3 y Sonarr v3
- Detección de estado por cola: Descargando, En cola, Pendiente de importar, Error
- `GET /api/library` con filtros: tipo, estado, petición, nomenclatura, búsqueda, paginación
- `GET /api/library/{id}`: detalle completo
- `POST /api/sync`: sincronización de todas las instancias

### Faltantes desde Radarr/Sonarr
- `GET /api/missing`: todos los ítems no disponibles con estados de cola

### Instancias Radarr/Sonarr
- `GET/POST /api/instances`, `POST /api/instances/{id}/test`, `/sync`
- Test de conexión real, API key enmascarada en respuestas

### Peticiones eMuwarez (read-only)
- Cliente UNIT3D: `emu_get_requests`, `emu_fetch_all_pages` con `?api_token=`
- Paginación automática de todas las páginas
- `_flatten_unit3d()` normaliza formato anidado `{attributes: {...}}`
- Autores: `author_visible=0` siempre; `anon=true` → `author=null`
- Rate limit: mínimo 3600 segundos entre syncs

### Motor de compatibilidad
- `normalize_title`, `compact_title`: sin acentos, casefold, sin artículos
- `parse_resolution`: texto → px height (`1080p` → 1080, `4K` → 2160)
- `parse_source`: texto → clave canónica (`BluRay`, `WEB-DL`, etc.)
- `compare_resolution/compare_source`: `True/False/None` (None = sin restricción)
- `match_request_to_library`: TMDb ID > IMDb ID > título exacto > similitud palabras
- `classify_request_match`: Compatible / Parcial / No compatible / Llena
- `rank_request_matches`: Compatible+Disponible+Correcta primero

### Pantalla Peticiones real (frontend)
- Tabla con filtros: búsqueda por título, filtro por compatibilidad
- Badges de compatibilidad (verde/amarillo/rojo/gris)
- Panel lateral al pulsar fila: detalle, motivos del cruce, enlace EMU
- Sync con info de throttle, botón "Forzar"
- `POST /api/requests/{id}/mark-reviewed`

### CLI extendida (peticiones)
```bash
requests sync [--force] [--endpoint-url ...]
requests list [--search X] [--limit N]
requests show <id>
requests match
requests mark-reviewed <id>
requests set-endpoint <url>
```

---

## Funcionalidades pendientes

- **Adaptar nomenclatura desde UI**: `POST /api/library/{id}/adapt-nomenclature` (stub)
- **Flujo Uploadrr desde UI**: `POST /api/library/{id}/upload` (stub) — requiere SSE para progreso
- **Progreso de subida**: `GET /api/uploads`, `POST /api/uploads/{id}/cancel` (stubs)
- **Tareas en tiempo real**: `GET /api/tasks` con datos reales (placeholder)
- **Logs del backend**: `GET /api/logs` (placeholder)
- **Configuración desde UI**: `GET/POST /api/config` (placeholder)
- **SettingsPage real**: formularios de configuración
- **Creación de peticiones EMU**: `POST /api/missing/{id}/create-emu-request` — bloqueado hasta capturar POST real
- **Docker**: imagen final con backend + frontend built
- **Jellyfin**: integración opcional pendiente
- **Seerr**: integración opcional pendiente

---

## Confirmaciones de seguridad

- `Uploadrr/` **no fue modificado** en ninguna fase. El directorio `Uploadrr/` solo fue inspeccionado en lectura para descubrir el patrón UNIT3D.
- No se hizo push a ningún remoto.
- API keys nunca expuestas en texto plano en respuestas.
- Contraseñas nunca guardadas en texto plano (PBKDF2-SHA256, 210k iteraciones).
- Tokens solo como hash SHA-256 en SQLite.
- `POST /api/missing/{id}/create-emu-request` retorna `{implemented: false, stub: true}`.

---

## Historial de ramas mergeadas

| Fase | Rama | Commit |
|------|------|--------|
| Phase 00 — Audit | `feature/ui-phase-00-audit` | en master original |
| Phase 01 — Contract | `feature/ui-phase-01-contract` | en master original |
| Phase 02 — Backend base | `feature/ui-phase-02-backend-base` | en master original |
| Phase 03 — Setup/Auth | `feature/ui-phase-03-setup-auth` | en master original |
| Phase 04 — Arr/Library/Dashboard | `feature/ui-phase-04-arr-library-dashboard` | en master original |
| Phase 05A — Frontend | `feature/ui-phase-05a-frontend-dashboard` | `c875cbd` |
| Phase 05B — Requests | `feature/ui-phase-05b-emu-requests-compatibility` | `50bfcde` |
| **Merge checkpoint** | → `master` | `1caf860` |
