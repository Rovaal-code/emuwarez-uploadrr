# Fase 7B — Docker Smoke Test y Diagnóstico Runtime

**Rama:** `feature/ui-phase-07b-docker-smoke-runtime`
**Fecha:** 2026-06-29
**Base:** `master` @ `433d63d` (tag: `emuwarez-uploadrr-docker-deployment-v0`)

---

## Archivos creados

| Archivo | Descripción |
|---|---|
| `emuwarez_uploadrr/services/runtime_diagnostics.py` | Servicio de diagnóstico read-only |
| `emuwarez_uploadrr/web/api/diagnostics.py` | Endpoint `GET /api/runtime/diagnostics` |
| `scripts/docker-smoke-test.sh` | Script reproducible de smoke test Docker |
| `docs/DEPLOYMENT_DOCKER.md` | Guía completa de primer arranque (21 secciones) |
| `tests/test_runtime_diagnostics.py` | 16 tests del servicio de diagnóstico |
| `tests/test_runtime_diagnostics_api.py` | 10 tests del endpoint de diagnóstico |
| `docs/codex_phase_07b_docker_smoke_runtime_report.md` | Este reporte |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `emuwarez_uploadrr/web/api/router.py` | Registra `diagnostics_router` |
| `emuwarez_uploadrr/web/schemas.py` | Añade `DiagnosticCheck`, `RuntimeDiagnosticsResponse` |
| `emuwarez_uploadrr/cli.py` | Añade subcomando `web doctor` y parser |
| `README_CLI_READY.md` | Añade sección "Smoke test Docker y diagnóstico" |

---

## Script smoke test (`scripts/docker-smoke-test.sh`)

- `bash strict`: `set -euo pipefail`
- Usa `mktemp -d` para directorios temporales efímeros
- Construye imagen local con `docker build`
- Arranca contenedor con bind mounts de config, data, uploads y uploadrr (read-only)
- Espera respuesta con timeout configurable (90s por defecto)
- Verifica 8 checks:
  - `GET /api/health` → 200
  - `GET /api/runtime` → 200
  - `GET /api/setup/status` → 200
  - `GET /api/docs` → 200
  - `GET /` → HTML 200
  - `GET /dashboard` → 200 (SPA fallback)
  - `/config` accesible desde el host
  - `Uploadrr/` NO está dentro de la imagen
- Limpia contenedor y tmpdir en `EXIT` (configurable con `KEEP_CONTAINER=1`)
- Variables configurables: `IMAGE_NAME`, `PORT`, `KEEP_CONTAINER`

### Resultado smoke test (2026-06-29)

```
Resultado: 8 OK, 0 FAIL
✓ Smoke test PASADO
App respondiendo tras 4s
```

---

## Servicio de diagnóstico (`runtime_diagnostics.py`)

Función `get_runtime_diagnostics()` ejecuta 6 checks read-only:

| Check | Status posible | Descripción |
|---|---|---|
| `environment` | ok | CONFIG_DIR, TZ, PYTHONUNBUFFERED |
| `config_dir` | ok/warning/error | Existe y es escribible |
| `database` | ok/warning/error | BD SQLite accesible |
| `frontend_dist` | ok/warning | frontend/dist con index.html |
| `uploadrr_mount` | ok/warning | /opt/Uploadrr accesible |
| `hardlink_base` | ok/warning | Configurado en settings |

Garantías:
- No expone secretos (API keys, tokens)
- No falla fatalmente si Uploadrr no está montado (devuelve warning)
- No crea hardlinks de prueba
- No escribe en directorios de media/uploads

---

## Endpoint `GET /api/runtime/diagnostics`

- Requiere `Authorization: Bearer <token>` → 401 sin token
- Responde `RuntimeDiagnosticsResponse` (Pydantic)
- No expone API keys ni configuración sensible
- Router registrado en `/api/runtime/diagnostics`

---

## CLI `web doctor`

```bash
python3 emuwarez_uploader.py web doctor
```

Salida con iconos ✓/⚠/✗, labels legibles, detalles sin secretos. Devuelve exit code 0 si `ok=True`, 1 si hay errores.

---

## Guía `docs/DEPLOYMENT_DOCKER.md`

21 secciones: requisitos → backup → actualización → troubleshooting.

Troubleshooting cubre: contenedor no arranca, healthcheck fallo, permisos /config, PUID/PGID, Uploadrr no montado, EXDEV, API keys no configuradas, Radarr/Sonarr, frontend, logs redactados.

---

## Validaciones ejecutadas

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web doctor` | OK (2 warnings esperados) |
| `python3 emuwarez_uploader.py upload jobs` | OK |
| `docker build -t emuwarez-uploadrr:phase-07b .` | OK |
| `docker compose -f docker-compose.example.yml config` | OK |
| `bash scripts/docker-smoke-test.sh` | **8/8 OK — PASADO** |

### pytest

```
460 passed, 1 warning in 85.78s
```

(434 anteriores + 26 nuevos)

### npm build

```
✓ 69 módulos transformados, built in 1.94s
```

---

## Confirmaciones de seguridad

- `Uploadrr/` no tocado en ningún momento
- `Uploadrr/` no está dentro de la imagen Docker (verificado por smoke test)
- Diagnóstico no expone API keys ni secretos
- No se realizó push a ningún remoto

---

## Riesgos pendientes

- El smoke test asume puerto 9494 libre; usar `PORT=XXXX bash scripts/docker-smoke-test.sh` para evitar conflictos
- El diagnóstico de `hardlink_base` lee directamente SQLite; si el schema cambia en el futuro hay que actualizarlo

---

## Siguiente fase recomendada

**Fase 7C** o **Fase 8**: según el roadmap, los siguientes candidatos son:
- `SettingsPage` completa con formularios de configuración real desde la UI
- `TasksPage` con datos reales de tareas en curso
- Integración real con Jellyfin o Seerr (si se capturan las APIs)
- Creación de peticiones eMuwarez (requiere capturar POST real desde DevTools)
