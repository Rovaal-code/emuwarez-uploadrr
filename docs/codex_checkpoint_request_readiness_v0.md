# Checkpoint — Request Readiness v0

## Rama mergeada

```
feature/ui-phase-08b-request-readiness-prioritization
```

## Tag creado

```
emuwarez-uploadrr-request-readiness-v0
```

Mensaje: `Milestone: request readiness, prioritization and actionable eMuwarez queue`

## Commits

| Commit | Descripción |
|--------|-------------|
| `bce39d4` | merge: request readiness prioritization milestone |
| `26209f3` | feat: add request readiness and prioritization (Fase 8B) |

## Validaciones pre-merge

| Check | Resultado |
|-------|-----------|
| `python3 -m py_compile` todos los .py | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web-contract` | OK |
| `python3 emuwarez_uploader.py web info` | OK |
| `python3 emuwarez_uploader.py web setup-status` | OK |
| `python3 emuwarez_uploader.py web doctor` | OK |
| `python3 emuwarez_uploader.py maintenance status` | OK |
| `python3 emuwarez_uploader.py arr health` | OK |
| `python3 emuwarez_uploader.py library diagnostics` | OK |
| `python3 emuwarez_uploader.py library recommendations` | OK |
| `python3 emuwarez_uploader.py missing diagnostics` | OK |
| `python3 emuwarez_uploader.py requests readiness` | OK |
| `python3 emuwarez_uploader.py requests readiness-refresh` | OK |
| `python3 emuwarez_uploader.py requests prioritized` | OK |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py library list` | OK |
| `python3 emuwarez_uploader.py missing list` | OK |
| `python3 emuwarez_uploader.py requests list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |

## Resultado pytest

```
605 passed, 1 warning in 102.77s
```

- 563 tests heredados de fases anteriores: todos pasando
- 42 tests nuevos Fase 8B:
  - `tests/test_request_readiness.py`: 14 tests
  - `tests/test_request_readiness_api.py`: 17 tests
  - `tests/test_request_readiness_cli.py`: 8 tests
  - (+3 en test de servicio)

## Resultado npm build

```
✓ built in 2.06s
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-BmbIeSxJ.css   17.51 kB │ gzip:  4.09 kB
dist/assets/index-zaxZMiPa.js   120.16 kB │ gzip: 27.46 kB
dist/assets/react-SIwY82C9.js   140.74 kB │ gzip: 45.79 kB
```

## Resultado Docker

```
docker build: OK (tag emuwarez-uploadrr:checkpoint-08b)
docker compose config: OK
docker smoke: 8 OK, 0 FAIL
```

## Validaciones post-merge

Idénticas a pre-merge. Todos los checks: **OK**. pytest: **605 passed**.

## Funcionalidades incluidas hasta este milestone

### Fase 8B — Request Readiness y Priorización

- `emuwarez_uploadrr/services/request_readiness.py` — motor de readiness
- Scoring determinista por petición:
  - `compatibility_score` (0-100): TMDb/IMDb match, título, año, tipo, resolución, source
  - `upload_readiness_score` (0-100): disponibilidad local, file_exists, cola ARR, historial ARR, nomenclatura, preflight
  - `priority_score` = compatibility×0.45 + upload_readiness×0.45 + urgency×0.10
  - `priority_bucket`: high / medium / low / blocked
- Tablas BD `request_readiness` y `request_candidates` (schema v9)
- Columnas `readiness_*` en `request_items`
- Selección de mejor candidato local por petición
- Blockers explícitos por petición
- Razones explicables en texto
- Priorización de cola de peticiones eMuwarez (high → medium → low → blocked)

### Endpoints protegidos (Bearer token)

| Método | Ruta |
|--------|------|
| POST | `/api/requests/readiness/refresh` |
| GET | `/api/requests/readiness` |
| GET | `/api/requests/prioritized` |
| GET | `/api/requests/{id}/readiness` |
| POST | `/api/requests/{id}/readiness/evaluate` |
| GET | `/api/requests/{id}/candidates` |

### CLI Phase 8B

```bash
python3 emuwarez_uploader.py requests readiness
python3 emuwarez_uploader.py requests readiness-refresh
python3 emuwarez_uploader.py requests candidates <id>
python3 emuwarez_uploader.py requests prioritized
```

### Frontend Phase 8B

- **RequestsPage**: columnas Readiness, Acción, Prioridad, Candidato; panel detalle con bloque readiness (score, blockers, recommended_action); panel de candidatos; botón "Recalcular readiness"; vista "Ver priorizados"; filtro por readiness status
- **DashboardPage**: panel "Peticiones accionables" con 5 contadores (ready to upload, prioridad alta, necesitan nomenclatura, esperando descarga, bloqueadas)

### Documentación Phase 8B

- `docs/codex_phase_08b_request_readiness_prioritization_report.md`
- `docs/ui_backend_contract.md` — endpoints Phase 8B añadidos
- `docs/ui_backend_contract.json` — endpoints Phase 8B añadidos
- `docs/DEPLOYMENT_DOCKER.md` — sección 13b: readiness de peticiones
- `README_CLI_READY.md` — sección readiness y priorización

### Acumulado en master (fases previas)

- DB migrations v1→v9 (idempotentes)
- Biblioteca Radarr/Sonarr (sync, lista, detalle, diagnósticos)
- Faltantes con diagnósticos y recomendaciones
- Peticiones eMuwarez (sync, match, mark-reviewed)
- Nomenclatura eMuwarez (adapt, hardlink, preflight)
- Subidas con Uploadrr (lifecycle, retry, logs, artifacts)
- Docker multi-stage + smoke test
- Config backup y mantenimiento
- ARR health + filesystem verification
- Library recommendations

## Funcionalidades bloqueadas todavía

| Funcionalidad | Estado |
|---------------|--------|
| Jellyfin | No implementado |
| Seerr | No implementado |
| mkvpropedit real | No implementado |
| Modificación de título interno MKV | No implementado |
| Creación automática de peticiones eMuwarez | No implementado |
| Subida automática sin confirmación explícita | No implementado |
| Copia/reflink cross-device | No implementado |

## Confirmaciones de seguridad

- `Uploadrr/` **no fue tocado**
- Jellyfin **no fue implementado**
- Seerr **no fue implementado**
- No se creó subida automática
- No se creó petición eMuwarez automática
- El cálculo de readiness es de **solo lectura** sobre Radarr/Sonarr/filesystem
- Push **no realizado**
