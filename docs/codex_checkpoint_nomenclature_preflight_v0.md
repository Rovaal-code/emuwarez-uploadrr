# Checkpoint: Nomenclatura + Preflight Uploadrr — v0

**Fecha:** 2026-06-29
**Rama mergeada:** `feature/ui-phase-06a-nomenclature-uploadrr-preflight`
**Commit merge:** `c764d94 merge: nomenclature and Uploadrr preflight milestone`
**Tag:** `emuwarez-uploadrr-nomenclature-preflight-v0`
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
| `python3 emuwarez_uploader.py upload jobs` | ✓ OK |
| `pytest -q` | ✓ **286 passed, 0 failed** |
| `npm run build` | ✓ **69 módulos, ~223 KB gzip** |

---

## Resultado pytest

```
286 passed, 1 warning in 47.09s
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
| `test_nomenclature.py` | 16 |
| `test_upload_preflight.py` | 11 |
| `test_nomenclature_api.py` | 22 |
| **Total** | **286** |

---

## Resultado npm build

```
vite v5.4.21 building for production...
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.39 kB
dist/assets/index-*.css          17.51 kB │ gzip:  4.09 kB
dist/assets/index-*.js           72.96 kB │ gzip: 17.13 kB
dist/assets/react-*.js          140.74 kB │ gzip: 45.79 kB
✓ built in 1.73s
```

---

## Funcionalidades incluidas en este milestone

### Milestones anteriores (heredados)

- CLI legacy completamente operativa
- Backend FastAPI: health, runtime, contrato, docs
- Setup wizard 7 pasos + autenticación local segura
- PBKDF2-SHA256 (210k iteraciones), tokens opacos, hash SHA-256 en BD
- Frontend React/Vite: Login, Setup, AppShell, Dashboard
- Sincronización Radarr/Sonarr (library, missing, instances)
- Peticiones eMuwarez read-only (UNIT3D API)
- Motor de compatibilidad (Compatible/Parcial/No compatible/Llena)
- Pantalla Peticiones con filtros, badges, panel lateral

### Añadido en Fase 6A

#### Servicio seguro de filesystem (`filesystem_safety.py`)

- `path_exists`, `is_file`, `is_video_file`, `safe_stat`
- **Contrato de seguridad**: nunca escribe, mueve, renombra ni borra nada

#### Propuestas de nomenclatura (`nomenclature.py`)

- Generación de propuesta: título + año + resolución + source + codec
- Inferencia de resolución/source desde campos Radarr/Sonarr/quality/path
- Estados: `valid`, `warning`, `blocked`, `draft`, `applied` (reservado), `expired`
- Guard contra ítems faltantes o sin ruta
- Tabla `nomenclature_proposals` en SQLite

#### Preflight Uploadrr (`upload_preflight.py`)

- Validación de precondiciones: uploadrr_path, EMU key, TMDb key
- Preview del comando Uploadrr (sin ejecutarlo jamás)
- API keys enmascaradas en el preview
- Estados de job: `draft`, `preflight`, `ready`, `blocked`
- Columnas nuevas en `upload_jobs` (migración idempotente)

#### Endpoints API protegidos

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/library/{id}/nomenclature` | Última propuesta |
| `POST` | `/api/library/{id}/nomenclature/preview` | Generar/refrescar |
| `POST` | `/api/library/{id}/adapt-nomenclature` | Stub seguro (apply bloqueado) |
| `POST` | `/api/library/{id}/upload/preflight` | Validar precondiciones |
| `GET` | `/api/uploads` | Listar jobs |
| `GET` | `/api/uploads/{id}` | Detalle job |

#### CLI extendida

```bash
python3 emuwarez_uploader.py nomenclature preview <id>
python3 emuwarez_uploader.py nomenclature show <id>
python3 emuwarez_uploader.py nomenclature apply <id> --dry-run
python3 emuwarez_uploader.py upload preflight <id>
python3 emuwarez_uploader.py upload job <id>
python3 emuwarez_uploader.py upload jobs
```

#### Frontend

- `NomenclatureModal`: título actual, propuesto, filename, carpeta, resolución, source, codec, warnings, errores; badges valid/warning/blocked; botón "Aplicar cambios" desactivado
- `UploadPreflightModal`: estado ready/blocked, tracker, categoría, TMDb, comando previsto; botón "Iniciar subida" desactivado
- `LibraryPage`: botones "Adaptar nomenclatura" y "Subir" por ítem
- `UploadsPage`: tabla de jobs/preflights reales

---

## Funcionalidades que siguen bloqueadas

- **Renombrado real de archivos** (`os.rename`) — reservado fase posterior
- **Creación real de hardlinks** (`os.link`) — reservado fase posterior
- **Modificación de título interno MKV** (mkvpropedit) — reservado fase posterior
- **Ejecución real de Uploadrr** — `POST /api/uploads/{id}/start` no implementado
- **Subida real a eMuwarez desde UI** — reservado
- **Creación automática de peticiones eMuwarez** — `POST /api/missing/{id}/create-emu-request` sigue bloqueado/stub
- **MediaInfo real** — audio/subtítulos en propuesta son `null` (MediaInfo no invocado)
- **SettingsPage real** — placeholder
- **TasksPage real** — placeholder
- **Docker** — imagen final pendiente
- **Jellyfin/Seerr** — integraciones opcionales pendientes

---

## Confirmaciones de seguridad

- `Uploadrr/` **no fue modificado** en ninguna fase. Solo inspección de lectura.
- No se hizo push a ningún remoto.
- API keys nunca expuestas en texto plano en respuestas (`masked_value`).
- Contraseñas nunca guardadas en texto plano (PBKDF2-SHA256, 210k iteraciones).
- Tokens solo como hash SHA-256 en SQLite.
- `POST /api/missing/{id}/create-emu-request` retorna `{implemented: false, stub: true}`.
- `adapt-nomenclature` con `apply=True` retorna `{blocked: true}` sin modificar nada.
- Ningún `os.rename`, `os.remove`, `shutil.move`, ni `subprocess` para Uploadrr/mkvpropedit.

---

## Historial de ramas mergeadas

| Fase | Rama | Commit |
|------|------|--------|
| Phase 00–04 | Múltiples | en master original |
| Phase 05A — Frontend | `feature/ui-phase-05a-frontend-dashboard` | `c875cbd` |
| Phase 05B — Requests | `feature/ui-phase-05b-emu-requests-compatibility` | `50bfcde` |
| Checkpoint v0 | → `master` | `1caf860` |
| Phase 06A — Nomenclatura | `feature/ui-phase-06a-nomenclature-uploadrr-preflight` | `22de9d3` |
| **Checkpoint nomenclatura** | → `master` | `c764d94` |
