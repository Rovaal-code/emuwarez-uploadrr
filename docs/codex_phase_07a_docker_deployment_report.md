# Fase 7A — Docker Deployment Report

**Fecha:** 2026-06-29
**Rama:** `feature/ui-phase-07a-docker-deployment`

---

## Archivos creados

| Archivo | Descripción |
|---|---|
| `Dockerfile` | Multi-stage: Node 20 Alpine → Python 3.12 slim |
| `.dockerignore` | Excluye Uploadrr/, .venv/, node_modules/, *.db, .env, etc. |
| `docker-compose.example.yml` | Ejemplo homelab con bind mount Uploadrr externo |
| `.env.example` | Variables sin secretos: PUID, PGID, TZ, PORT |
| `tests/test_docker_runtime.py` | 12 tests de compatibilidad runtime sin Docker real |
| `docs/codex_phase_07a_docker_deployment_report.md` | Este reporte |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `emuwarez_uploadrr/cli.py` | Añadida sección Docker en `cmd_web_info()` |
| `README_CLI_READY.md` | Añadida sección "Docker / despliegue homelab" |

## Dockerfile — diseño multi-stage

```
Stage 1 (frontend-builder): node:20-alpine
  - COPY frontend/package.json + lockfile
  - npm ci / npm install
  - COPY frontend/
  - npm run build  →  /build/frontend/dist

Stage 2 (runtime): python:3.12-slim
  - COPY pyproject.toml, emuwarez_uploader.py, emuwarez_uploadrr/
  - pip install -e ".[web]"
  - COPY --from=frontend-builder /build/frontend/dist ./frontend/dist
  - ENV CONFIG_DIR=/config TZ=Europe/Madrid PYTHONUNBUFFERED=1
  - VOLUME ["/config"]
  - EXPOSE 9494
  - HEALTHCHECK  (urllib.request, sin curl)
  - CMD python3 emuwarez_uploader.py web serve --host 0.0.0.0 --port 9494
```

### Cómo se sirve el frontend

`app.py` resuelve la ruta del frontend con:
```python
_REPO_ROOT = Path(__file__).parent.parent.parent
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"
```

Con `WORKDIR=/app` y `app.py` en `/app/emuwarez_uploadrr/web/app.py`:
- `_REPO_ROOT` = `/app`
- `_FRONTEND_DIST` = `/app/frontend/dist`

El Dockerfile copia el dist del stage 1 a `./frontend/dist` (= `/app/frontend/dist`).
Si el directorio no existe, la app arranca sin frontend (solo API) — comportamiento ya existente.

## Variables de entorno soportadas

| Variable | Por defecto | Descripción |
|---|---|---|
| `CONFIG_DIR` | `/config` | Directorio de configuración (SQLite + settings) |
| `TZ` | `Europe/Madrid` | Zona horaria del contenedor |
| `PYTHONUNBUFFERED` | `1` | Logs en tiempo real |
| `PUID` / `PGID` | `1000` / `1000` | UID/GID (configurado en compose, no en la imagen) |

`CONFIG_DIR` ya era respetado en `database.py` vía `db_path()` con `os.environ.get("CONFIG_DIR")`.

## Volúmenes recomendados

| Ruta en contenedor | Uso |
|---|---|
| `/config` | Persistencia (SQLite, settings). Siempre montar. |
| `/opt/Uploadrr` | Uploadrr externo (bind mount `:ro`). Configurar ruta en setup. |
| `/data` | Raíz común de media + uploads. Necesario para hardlinks sin EXDEV. |

## Advertencia hardlink / EXDEV

Si el directorio fuente (Radarr/Sonarr media) y `hardlink_base` están en distintos
dispositivos o montajes dentro del contenedor, `os.link()` fallará con `EXDEV`.

**Solución:** montar una raíz de datos común (`/data`) que contenga tanto el media
(`/data/media`) como el hardlink_base (`/data/uploads/emu`), garantizando que
ambas rutas comparten el mismo filesystem real del host.

## Validaciones ejecutadas

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| CLI: db init, instances list, library list, etc. | OK |
| `web info` — sección Docker | OK |
| `pytest -q` | **434 passed** (422 + 12 nuevos) |
| `npm run build` | 69 módulos, sin errores |
| `docker build -t emuwarez-uploadrr:phase-07a .` | **OK** (imagen construida exitosamente) |
| `docker compose -f docker-compose.example.yml config` | **OK** (configuración válida) |

## Confirmaciones de seguridad

- `Uploadrr/` no fue tocado ni incluido en la imagen Docker (`.dockerignore` lo excluye explícitamente)
- No se hizo push a ningún remoto
- La imagen no contiene secretos ni API keys
- `.env.example` no contiene secretos

## Riesgos pendientes

- La imagen no tiene `curl` para healthcheck — se usa `urllib.request` de Python stdlib (solución válida)
- `user: PUID:PGID` puede causar problemas si el usuario del host no tiene permisos sobre `/config` — el usuario debe crear y chown el directorio previamente
- Si Uploadrr requiere paquetes del sistema adicionales (ej. `mkvtoolnix`), deben añadirse al Dockerfile en la siguiente fase que implemente mkvpropedit

## Siguiente fase recomendada

- **Fase 7B** — SettingsPage real: formularios de configuración web para `hardlink_base`, `uploadrr_path`, API keys de Radarr/Sonarr/TMDb/eMuwarez, editable sin tocar archivos de configuración manualmente
- O bien: Fase 8 — integración con pruebas de despliegue real (smoke test con contenedor levantado en CI/CD local)
