# Checkpoint — Docker Deployment v0

**Fecha:** 2026-06-29
**Rama mergeada:** `feature/ui-phase-07a-docker-deployment`
**Commit de feature:** `92682af feat: add Docker deployment support`
**Commit de merge:** `1c0a5b9 merge: Docker deployment milestone`
**Tag creado:** `emuwarez-uploadrr-docker-deployment-v0`
**Tags existentes tras este checkpoint:**
- `emuwarez-uploadrr-docker-deployment-v0`
- `emuwarez-uploadrr-lifecycle-results-v0`
- `emuwarez-uploadrr-controlled-execution-v0`
- `emuwarez-uploadrr-nomenclature-apply-v0`
- `emuwarez-uploadrr-nomenclature-preflight-v0`
- `emuwarez-uploadrr-ui-requests-v0`

---

## Validaciones ejecutadas

### Pre-merge (en `feature/ui-phase-07a-docker-deployment`)

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web-contract` | OK |
| `python3 emuwarez_uploader.py web setup-status` | OK |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py library list` | OK |
| `python3 emuwarez_uploader.py missing list` | OK |
| `python3 emuwarez_uploader.py requests list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |

### pytest pre-merge

```
434 passed, 1 warning in 74.02s
```

### npm build pre-merge

```
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-BmbIeSxJ.css   17.51 kB │ gzip:  4.09 kB
dist/assets/index-PxIUbSaL.js    92.03 kB │ gzip: 20.62 kB
dist/assets/react-SIwY82C9.js   140.74 kB │ gzip: 45.79 kB
✓ built in 1.97s
```

### docker build pre-merge

```
emuwarez-uploadrr:checkpoint-07a — OK (imagen construida exitosamente)
```

### docker compose config pre-merge

```
OK — YAML válido, configuración parseada correctamente
```

### Post-merge (en `master`)

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |

### pytest post-merge

```
434 passed, 1 warning in 70.73s
```

### npm build post-merge

```
✓ 69 módulos, sin errores, built in 2.03s
```

### docker build post-merge

```
emuwarez-uploadrr:checkpoint-07a — OK
```

### docker compose config post-merge

```
OK — YAML válido
```

---

## Funcionalidades incluidas en este milestone

- Dockerfile multi-stage (Node 20 Alpine para build frontend + Python 3.12-slim runtime)
- Build frontend con `npm ci && npm run build` en stage separado
- `frontend/dist` servido desde FastAPI en runtime Docker (`COPY --from=frontend-builder`)
- `.dockerignore` con exclusión explícita de `Uploadrr/`, `.venv/`, `node_modules/`, `*.db`
- `docker-compose.example.yml` para homelab con bind mount de Uploadrr externo en `/opt/Uploadrr`
- `.env.example` sin secretos (solo PUID, PGID, TZ, PORT)
- `CONFIG_DIR=/config` como variable de entorno documentada y soportada
- Uploadrr tratado como runtime externo — nunca incluido en imagen
- `HEALTHCHECK` nativo Python contra `/api/health`
- Sección Docker en `python3 emuwarez_uploader.py web info`
- README actualizado con sección "Docker / despliegue homelab"
- Documentación de volúmenes, PUID/PGID, red Docker opcional
- Advertencia EXDEV: media y hardlink_base deben estar en el mismo filesystem
- `tests/test_docker_runtime.py` — 12 tests sin Docker real

---

## Funcionalidades bloqueadas (pendientes de fases posteriores)

- Creación automática de peticiones eMuwarez
- Modificación de título interno MKV / `mkvpropedit` real
- Copia / reflink cross-device
- Jellyfin real
- Seerr real

---

## Confirmaciones

- `Uploadrr/` no fue tocado en ningún momento
- `Uploadrr/` excluido explícitamente en `.dockerignore`
- `Uploadrr/` montado como bind mount externo en compose example
- No se hizo push a ningún remoto
- El merge fue `--no-ff` sin conflictos (estrategia `ort`)
- El árbol de trabajo queda limpio en `master`
