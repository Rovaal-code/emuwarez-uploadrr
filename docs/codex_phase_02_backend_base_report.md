# Reporte de ejecución — Fase 2
## Backend FastAPI base

**Fecha:** 2026-06-28
**Rama:** feature/ui-phase-02-backend-base

---

## Rama usada

```
feature/ui-phase-02-backend-base
```

Creada desde `feature/ui-phase-01-contract` (commit `c409901`).

---

## Archivos creados

| Archivo | Descripción |
|---|---|
| `emuwarez_uploadrr/web/__init__.py` | Paquete web con instrucciones de instalación |
| `emuwarez_uploadrr/web/app.py` | `create_app()` + instancia `app` para uvicorn |
| `emuwarez_uploadrr/web/runtime.py` | Helpers de información runtime sin dependencia FastAPI |
| `emuwarez_uploadrr/web/schemas.py` | Modelos Pydantic para respuestas API |
| `emuwarez_uploadrr/web/errors.py` | `AppError`, handlers de error |
| `emuwarez_uploadrr/web/api/__init__.py` | Paquete de routers |
| `emuwarez_uploadrr/web/api/router.py` | Router principal `/api` que agrega todos los sub-routers |
| `emuwarez_uploadrr/web/api/health.py` | `GET /api/health`, `GET /api/runtime` |
| `emuwarez_uploadrr/web/api/setup.py` | `GET /api/setup/status` |
| `emuwarez_uploadrr/web/api/contract.py` | `GET /api/contract`, `GET /api/contract/json` |
| `emuwarez_uploadrr/web/api/placeholders.py` | ~35 endpoints placeholder para fases futuras |
| `tests/__init__.py` | Paquete de tests |
| `tests/test_web_app.py` | Suite de tests: 18 tests |
| `docs/codex_phase_02_backend_base_report.md` | Este reporte |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `pyproject.toml` | Añadidos `[project.optional-dependencies] web` y `dev` |
| `emuwarez_uploadrr/cli.py` | Añadidos `web` a `MODERN_COMMANDS`, subcomandos `web serve` / `web info`, funciones `cmd_web_serve()` / `cmd_web_info()` |
| `README_CLI_READY.md` | Añadida sección "Backend web base" con comandos y URLs |

---

## Endpoints implementados

### Funcionales

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Estado de salud, versión, estado de BD, `initialized` |
| `GET` | `/api/runtime` | Rutas, versión, CLI disponible, Uploadrr presente |
| `GET` | `/api/setup/status` | Estado del setup wizard (lee `app_state` en SQLite) |
| `GET` | `/api/contract` | Resumen del contrato UI/Backend |
| `GET` | `/api/contract/json` | Contenido completo de `docs/ui_backend_contract.json` |
| `GET` | `/api/docs` | Swagger UI (FastAPI automático) |
| `GET` | `/api/redoc` | ReDoc (FastAPI automático) |
| `GET` | `/api/openapi.json` | Schema OpenAPI |

### Placeholders (35 endpoints)

Todos devuelven `{"implemented": false, "phase": "...", "message": "..."}`.

Grupos:
- Dashboard: `summary`, `activity`, `upload-activity`, `tasks`, `events`
- Instances: `GET/POST`, `test`, `sync`
- Sync: `library`, `requests`
- Library: `list`, `detail`, `adapt-nomenclature`, `upload`
- Missing: `list`, `check-emu`, **`create-emu-request`** (stub especial con aviso)
- Requests: `list`, `sync`, `detail`, `match`, `mark-reviewed`
- Uploads: `list`, `detail`, `cancel`
- Tasks: `list`, `run`
- Logs: `get`
- Config: `get`, `general`, `tmdb`, `emu`, `uploadrr`
- Auth: `login`, `logout`, `me`

**`POST /api/missing/{id}/create-emu-request`** devuelve stub explícito:
```json
{
  "implemented": false,
  "phase": "final",
  "stub": true,
  "message": "La creación automática de peticiones eMuwarez está preparada como stub y queda bloqueada hasta capturar y validar la request real desde DevTools/Network."
}
```

---

## Comandos CLI añadidos

| Comando | Descripción |
|---|---|
| `python3 emuwarez_uploader.py web info` | Muestra URLs y comandos del servidor web |
| `python3 emuwarez_uploader.py web serve [--host] [--port] [--reload]` | Arranca uvicorn |

Modo de arranque uvicorn directo:
```bash
uvicorn emuwarez_uploadrr.web.app:app --host 0.0.0.0 --port 9494
```

---

## Dependencias añadidas

```toml
[project.optional-dependencies]
web = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.0.0",
]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
]
```

Instalación:
```bash
pip install -e ".[web]"    # solo dependencias web
pip install -e ".[web,dev]" # + pytest/httpx
# o con el venv del proyecto:
.venv/bin/pip install -e ".[web,dev]"
```

Nota: El sistema operativo bloqueó `pip install --user` por PEP 668. Se creó `.venv/` local en el proyecto. `.venv/` está cubierto por `.gitignore`.

---

## Validaciones ejecutadas

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | ✓ OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | ✓ OK (42 archivos) |
| `python3 -m json.tool docs/ui_backend_contract.json` | ✓ JSON válido |
| `python3 emuwarez_uploader.py --help` | ✓ Legacy mode intacto |
| `python3 emuwarez_uploader.py db init` | ✓ `SQLite lista` |
| `python3 emuwarez_uploader.py web-contract` | ✓ Contrato mostrado |
| `python3 emuwarez_uploader.py web info` | ✓ URLs mostradas |
| `python3 emuwarez_uploader.py instances list` | ✓ Tabla vacía OK |
| TestClient — 7 endpoints clave | ✓ Todos 200/404 según esperado |
| `.venv/bin/pytest tests/test_web_app.py -q` | ✓ **18/18 passed** |

---

## Estado de Uploadrr

- No se tocó ningún archivo dentro de `Uploadrr/`.
- `Uploadrr/` sigue ignorado por `.gitignore`.
- El helper `_uploadrr_present()` en `runtime.py` solo comprueba si `Uploadrr/upload.py` existe; no ejecuta nada.

---

## Riesgos pendientes

| Riesgo | Detalle | Fase |
|---|---|---|
| Dependencias web no en PATH del sistema | PEP 668 bloquea `pip --user`. Usar `.venv/` o Docker. | 9 |
| `CONFIG_DIR` hardcoded en legacy | En Docker usar `CONFIG_DIR` env var. Pendiente de implementar. | 9 |
| `_REPO_ROOT` en `contract.py` calculado con `parents[3]` | Asume que el paquete está en el repositorio. En instalación pip global podría diferir. | 3 |
| Schema SQLite v2 incompleto | Faltan tablas `users`, `queue_items`, `history_items`, `upload_events`, `event_log`. | 3-4 |
| Endpoint de peticiones EMU no configurado | Stub explícito. Sin cambios. | 5 |
| Endpoint de creación de petición EMU | Stub bloqueado explícitamente. Sin cambios. | final |
| Warning `httpx` vs `httpx2` en TestClient | Deprecación interna de Starlette. No afecta a tests ni a runtime. Seguir con `httpx` hasta que FastAPI lo requiera. | - |

---

## Siguiente fase recomendada — Fase 3: Setup wizard + Auth

**Objetivo:** Completar el ciclo de primer arranque y proteger la API.

**Tareas principales:**
1. `POST /api/setup/admin` — crear usuario admin con hash bcrypt/argon2.
2. `POST /api/setup/general`, `/tmdb`, `/emu`, `/uploadrr`, `/instances`, `/complete`.
3. `POST /api/auth/login` / `GET /api/auth/me` — JWT o sesión simple.
4. Middleware de autenticación para todas las rutas salvo `/api/health` y `/api/setup/*`.
5. Guardar `initialized=true` en `app_state` al completar setup.
6. Ampliar schema SQLite a v3: añadir tabla `users` y campos faltantes en `library_items` / `upload_jobs`.
7. Tests para el flujo de setup y auth.

**Archivos previstos en Fase 3:**
```text
emuwarez_uploadrr/web/api/auth.py
emuwarez_uploadrr/web/api/setup_write.py   (endpoints POST de setup)
emuwarez_uploadrr/web/middleware.py         (auth middleware)
emuwarez_uploadrr/database.py              (schema_version = 3)
tests/test_setup_flow.py
tests/test_auth.py
```

**Rama:** `feature/ui-phase-03-setup-wizard`
**Commit final:** `feat: add setup wizard and auth`

---

## Criterios de aceptación de Fase 2

```text
[x] CLI legacy sigue funcionando
[x] CLI moderna sigue funcionando (db init, web-contract, instances list)
[x] emuwarez_uploadrr/web/ existe con todos los archivos
[x] create_app() definida en app.py
[x] uvicorn puede apuntar a emuwarez_uploadrr.web.app:app
[x] GET /api/health responde 200 con status=ok
[x] GET /api/setup/status responde 200 con initialized
[x] GET /api/contract/json responde 200 con contrato
[x] Endpoints futuros existen como placeholders seguros
[x] POST /api/missing/{id}/create-emu-request sigue bloqueado como stub
[x] Uploadrr/ no se tocó
[x] git status termina limpio
[x] 18/18 tests pasan
[ ] Commit final feat: add FastAPI backend base  ← pendiente paso de commit
```
