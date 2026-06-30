# Reporte — Fase 9B: E2E Controlado en Docker con Datos Simulados

**Fecha:** 2026-06-30
**Rama:** `feature/ui-phase-09b-controlled-e2e-docker`
**Base:** `master` @ `2c89f7e`

---

## Archivos creados

| Archivo | Descripción |
|---------|-------------|
| `emuwarez_uploadrr/services/demo_seed.py` | Servicio de seed de datos demo con contrato de seguridad |
| `scripts/docker-e2e-demo.sh` | Script E2E completo en Docker con datos simulados |
| `tests/fixtures/__init__.py` | Paquete fixtures |
| `tests/fixtures/fake_uploadrr.py` | Fake Uploadrr sin red ni API keys |
| `tests/test_demo_seed.py` | 14 tests del servicio demo_seed |
| `tests/test_docker_e2e_script.py` | 18 tests del script E2E y fake Uploadrr |
| `docs/codex_phase_09b_controlled_e2e_docker_report.md` | Este reporte |

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/cli.py` | Añadido grupo `demo` con subcomandos `seed` y `reset` |
| `README_CLI_READY.md` | Añadida sección `## E2E controlado en Docker (Phase 9B)` |
| `docs/DEPLOYMENT_DOCKER.md` | Añadida sección sobre E2E demo |
| `docs/ui_backend_contract.md` | Añadida nota sobre Phase 9B (sin nuevos endpoints) |
| `docs/ui_backend_contract.json` | Añadida clave `phase_9b_e2e` con descripción |

---

## `scripts/docker-e2e-demo.sh`

Script bash con:
- `set -euo pipefail` — modo estricto
- Variables configurables: `IMAGE_NAME`, `PORT`, `KEEP_CONTAINER`
- `mktemp -d` — tmpdir temporal para todos los datos
- `trap cleanup EXIT` — limpieza automática del contenedor y tmpdir
- Crea estructura de directorios y archivo fake `.mkv` (texto con extensión `.mkv`)
- Construye imagen Docker y arranca contenedor con volúmenes temporales
- Espera `/api/health` con timeout 90s
- Ejecuta 13 etapas de validación via `docker exec`
- Verifica que Uploadrr/ no esté dentro de la imagen
- Imprime logs del contenedor si falla

Flujo validado paso a paso:
1. Build imagen
2. Arrancar contenedor
3. Esperar `/api/health`
4. `db init`
5. `demo seed --media-root /data/media --prepared-root /data/uploads/emu --confirm DEMO_SEED`
6. `library verify-files`, `library recommendations`, `library verify-file 1`
7. `requests readiness-refresh`, `requests prioritized`
8. `queue refresh`, `queue summary`, `queue list`
9. `queue action-plan 1`, `queue execute-safe 1 --action view_plan`, `queue events 1`
10. `nomenclature preview 1`
11. `upload preflight 1` (dry-run, nunca ejecuta Uploadrr)
12. HTTP checks: `/api/health`, `/api/setup/status`, `/`, `/dashboard`, `/queue`
13. Verificación seguridad: Uploadrr/ no en imagen

---

## `emuwarez_uploadrr/services/demo_seed.py`

Servicio con dos funciones principales:

### `seed_demo_data(conn, media_root, prepared_root, confirm_token)`

- Lanza `ValueError` si `confirm_token != "DEMO_SEED"`
- Crea archivo fake `.mkv` en `{media_root}/movies/Demo Movie (2024)/Demo Movie (2024) WEBDL-1080p.mkv`
- Inserta en BD (idempotente):
  - Instancia Radarr fake (enabled=0, api_key ficticia)
  - `library_item` movie "Demo Movie" (2024), path al archivo fake, local_status="Disponible"
  - `request_item` con emu_id="demo-emu-001", emu_status="approved", TMDb/IMDb demo
  - `request_match` Compatible entre los dos
- Solo escribe en CONFIG_DIR y en las rutas pasadas como parámetro

### `reset_demo_data(conn, confirm_token)`

- Lanza `ValueError` si `confirm_token != "DEMO_RESET"`
- Elimina los registros demo de la BD (no borra archivos de disco)

**Decisión de diseño:** Se usa comprobación de existencia previa en lugar de `INSERT OR IGNORE` para `library_items` porque la restricción `UNIQUE(instance_id, item_type, external_id)` no se activa con `external_id=NULL` en SQLite (dos NULL no se consideran iguales).

---

## `tests/fixtures/fake_uploadrr.py`

Script Python que simula la salida de Uploadrr exitoso:

```
Upload completed
Torrent URL: https://emuwarez.example/torrents/12345
Torrent ID: 12345
```

- Sin red
- Sin API real
- Sin secrets
- Sin tocar `Uploadrr/`
- Acepta cualquier argumento sin error

---

## Flujo E2E validado (dentro del contenedor)

```
✓ db init
✓ demo seed → library_item_id=1, request_item_id=1, archivo=/data/media/...
✓ library verify-files → Verificados: 1, Encontrados: 1, Errores: 0
✓ library recommendations → 1 recalculado
✓ library verify-file 1 → existe: sí, es vídeo: sí (extensión .mkv reconocida)
✓ requests readiness-refresh → 1 petición, needs_nomenclature, prioridad medium
✓ requests prioritized → Demo Movie | adapt_nomenclature | medium | #1
✓ queue refresh → 1 item (adapt_nomenclature, ready, medium)
✓ queue summary → Total: 1
✓ queue list → Demo Movie, adapt_nomenclature, medium
✓ queue action-plan 1 → flow: nomenclature, route: /library, token: APLICAR_NOMENCLATURA
✓ queue execute-safe 1 --action view_plan → view_plan ejecutado
✓ queue events 1 → plan_viewed registrado
✓ nomenclature preview 1 → propuesta generada (warning: codec no detectado — esperado)
✓ upload preflight 1 → preview visible, bloqueado (uploadrr_path no configurado — esperado en demo)
✓ GET /api/health → 200
✓ GET /api/setup/status → 200
✓ GET / → HTML 200
✓ GET /dashboard → 200 (SPA fallback)
✓ GET /queue → 200 (SPA fallback)
✓ Uploadrr/ no en imagen → confirmado
```

**Total: 21/21 OK**

---

## Garantías de aislamiento

| Garantía | Estado |
|----------|--------|
| Datos en tmpdir temporal | ✓ — `mktemp -d` + `trap cleanup EXIT` |
| No usa Radarr/Sonarr reales | ✓ — instancia fake deshabilitada |
| No usa eMuwarez real | ✓ — datos ficticios, sin sync |
| No ejecuta Uploadrr real | ✓ — solo preflight dry-run (siempre devuelve 0 sin ejecutar) |
| No sube contenido real | ✓ |
| No modifica `Uploadrr/` | ✓ |
| No expone API keys reales | ✓ — api_key="demo_key_fake" visible |
| Limpieza automática | ✓ — salvo KEEP_CONTAINER=1 |

---

## Validaciones ejecutadas

### Python

```
python3 -m py_compile emuwarez_uploader.py           → OK
find emuwarez_uploadrr -name "*.py" | xargs py_compile → OK
python3 -m json.tool docs/ui_backend_contract.json   → OK
python3 emuwarez_uploader.py --help                  → OK
python3 emuwarez_uploader.py db init                 → OK
python3 emuwarez_uploader.py demo --help             → OK
python3 emuwarez_uploader.py queue summary           → OK
python3 emuwarez_uploader.py queue list              → OK
```

### pytest

```
713 passed, 1 warning in 154.76s
(681 anteriores + 32 nuevos: 14 test_demo_seed + 18 test_docker_e2e_script)
```

### npm run build

```
76 módulos, dist/assets/index-*.js ~140 kB — OK
```

### Docker build

```
docker build -t emuwarez-uploadrr:phase-09b . → OK
docker compose -f docker-compose.example.yml config → OK
```

### Docker smoke test

```
bash scripts/docker-smoke-test.sh → 8/8 OK — PASADO
```

### Docker E2E demo

```
IMAGE_NAME=emuwarez-uploadrr:phase-09b bash scripts/docker-e2e-demo.sh → 21/21 OK — E2E DEMO PASSED
```

---

## Confirmaciones de seguridad

| Punto de control | Estado |
|-----------------|--------|
| `Uploadrr/` tocado en este milestone | **No** |
| Push realizado a remoto | **No** |
| Jellyfin implementado | **No** |
| Seerr implementado | **No** |
| mkvpropedit implementado | **No** |
| Subida automática sin confirmación | **No** |
| Petición eMuwarez automática | **No** |
| Uploadrr ejecutable desde cola | **No — bloqueado con 409** |
| Upload preflight ejecuta Uploadrr | **No — solo dry-run preview** |
| API keys reales en código | **No** |

---

## Riesgos pendientes

- `upload preflight` muestra "bloqueado" en el E2E porque `uploadrr_path` y las API keys no están configuradas — comportamiento esperado en demo. No es un bug.
- `nomenclature preview` emite advertencia de "codec no detectado" porque el archivo `.mkv` es texto plano y MediaInfo no está disponible. Comportamiento esperado; los verificadores solo comprueban existencia/extensión.
- La imagen Docker en el E2E siempre se reconstruye desde cero — puede tardar si no hay caché local.

---

## Siguiente fase recomendada

**Fase final — Creación real de peticiones eMuwarez**

Rama: `feature/ui-final-emu-create-request`

Implementar `emu_create_request()` usando la request capturada manualmente desde DevTools:
- URL endpoint, método, headers, payload, auth/cookie/csrf
- Validar payload antes de enviar
- Añadir dry-run y confirmación explícita
- Guardar resultado en event_log/task_runs
- No enviar sin confirmación; no enviar si prechecks fallan
- No loguear cookies/tokens

---

## Historial de milestones

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
| emuwarez-uploadrr-guided-queue-actions-v0 | Ejecución guiada desde cola (Phase 9A) |
| **emuwarez-uploadrr-e2e-demo-v0** | **E2E controlado en Docker con datos simulados (Phase 9B)** |
