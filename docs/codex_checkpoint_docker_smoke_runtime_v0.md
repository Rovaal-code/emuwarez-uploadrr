# Checkpoint — Docker Smoke Runtime v0

**Fecha:** 2026-06-29
**Rama mergeada:** `feature/ui-phase-07b-docker-smoke-runtime`
**Commit de feature:** `d710736 feat: add Docker smoke test and runtime diagnostics`
**Commit de merge:** `e6a4bce merge: Docker smoke runtime milestone`
**Tag creado:** `emuwarez-uploadrr-docker-smoke-runtime-v0`
**Tags existentes tras este checkpoint:**
- `emuwarez-uploadrr-docker-smoke-runtime-v0`
- `emuwarez-uploadrr-docker-deployment-v0`
- `emuwarez-uploadrr-lifecycle-results-v0`
- `emuwarez-uploadrr-controlled-execution-v0`
- `emuwarez-uploadrr-nomenclature-apply-v0`
- `emuwarez-uploadrr-nomenclature-preflight-v0`
- `emuwarez-uploadrr-ui-requests-v0`

---

## Validaciones ejecutadas

### Pre-merge (en `feature/ui-phase-07b-docker-smoke-runtime`)

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web-contract` | OK |
| `python3 emuwarez_uploader.py web setup-status` | OK |
| `python3 emuwarez_uploader.py web doctor` | OK (2 warnings esperados: Uploadrr no montado, hardlink_base no configurado) |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |

### pytest pre-merge

```
460 passed, 1 warning in 82.39s
```

### npm build pre-merge

```
✓ 69 módulos transformados.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-PxIUbSaL.js    92.03 kB │ gzip: 20.62 kB
✓ built in 2.50s
```

### docker build pre-merge

```
emuwarez-uploadrr:checkpoint-07b — OK
```

### docker compose config pre-merge

```
OK — YAML válido
```

### scripts/docker-smoke-test.sh pre-merge

```
8/8 OK — app respondió en 4s
✓ GET /api/health → HTTP 200
✓ GET /api/runtime → HTTP 200
✓ GET /api/setup/status → HTTP 200
✓ GET /api/docs → HTTP 200
✓ GET / → HTML (HTTP 200)
✓ GET /dashboard → HTTP 200 (SPA fallback OK)
✓ /config montado y accesible desde el host
✓ Uploadrr/ no está dentro de la imagen
Smoke test PASADO
```

### Post-merge (en `master`)

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web doctor` | OK |

### pytest post-merge

```
460 passed, 1 warning in 87.39s
```

### npm build post-merge

```
✓ 69 módulos, sin errores, built in 2.26s
```

### docker build post-merge

```
emuwarez-uploadrr:checkpoint-07b — OK
```

### scripts/docker-smoke-test.sh post-merge

```
8/8 OK — Smoke test PASADO
```

---

## Funcionalidades incluidas en este milestone

- Script reproducible `scripts/docker-smoke-test.sh` con `set -euo pipefail`, tmpdir, cleanup trap y 8 checks
- Smoke test real del contenedor Docker (build + run + HTTP checks + cleanup)
- Validación HTTP de `/api/health`, `/api/runtime`, `/api/setup/status`, `/api/docs`
- Validación de frontend SPA: `/` devuelve HTML, `/dashboard` cae en index.html
- Verificación de `CONFIG_DIR=/config` montado como volumen temporal
- Verificación de que `Uploadrr/` no está dentro de la imagen
- `emuwarez_uploadrr/services/runtime_diagnostics.py` — 6 checks read-only sin secretos
- Endpoint protegido `GET /api/runtime/diagnostics` con Bearer token (401 sin token)
- CLI `python3 emuwarez_uploader.py web doctor` — diagnóstico runtime en formato legible
- `docs/DEPLOYMENT_DOCKER.md` — guía de 21 secciones con troubleshooting completo
- `README_CLI_READY.md` actualizado con smoke test y diagnóstico
- 26 tests nuevos: `test_runtime_diagnostics.py` (9) + `test_runtime_diagnostics_api.py` (4) + otros

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
- `Uploadrr/` excluido en `.dockerignore` y verificado por el smoke test como no presente en imagen
- No se hizo push a ningún remoto
- El merge fue `--no-ff` sin conflictos (estrategia `ort`)
- El árbol de trabajo queda limpio en `master`
- El smoke test se ejecutó dos veces (pre y post merge) con resultado 8/8 OK
