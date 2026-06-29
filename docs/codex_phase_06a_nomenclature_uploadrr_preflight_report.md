# Fase 6A — Nomenclatura eMuwarez + preflight Uploadrr seguro

**Fecha:** 2026-06-29
**Rama:** `feature/ui-phase-06a-nomenclature-uploadrr-preflight`
**Commit:** pendiente de tag/merge (ver checkpoint siguiente)
**Base:** `master` @ `e426e6a`

---

## Objetivo

Añadir previsualización de nomenclatura eMuwarez y preflight seguro de subida Uploadrr,
sin modificar archivos reales ni ejecutar Uploadrr en ningún caso.

---

## Archivos creados

| Archivo | Descripción |
|---------|-------------|
| `emuwarez_uploadrr/services/filesystem_safety.py` | Módulo read-only de filesystem |
| `emuwarez_uploadrr/services/nomenclature.py` | Servicio de propuestas de nomenclatura |
| `emuwarez_uploadrr/services/upload_preflight.py` | Servicio de preflight Uploadrr |
| `emuwarez_uploadrr/web/api/nomenclature.py` | Endpoints de nomenclatura |
| `emuwarez_uploadrr/web/api/uploads.py` | Endpoints de upload jobs |
| `frontend/src/api/nomenclature.ts` | Cliente API nomenclatura |
| `frontend/src/api/uploads.ts` | Cliente API uploads |
| `frontend/src/components/NomenclatureModal.tsx` | Modal de previsualización nomenclatura |
| `frontend/src/components/UploadPreflightModal.tsx` | Modal preflight Uploadrr |
| `tests/test_nomenclature.py` | Tests del servicio de nomenclatura |
| `tests/test_upload_preflight.py` | Tests del servicio de preflight |
| `tests/test_nomenclature_api.py` | Tests de endpoints API |

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/database.py` | Tablas `nomenclature_proposals` + migración `upload_jobs`, SCHEMA_VERSION=4 |
| `emuwarez_uploadrr/web/schemas.py` | Schemas Pydantic para nomenclatura y uploads |
| `emuwarez_uploadrr/web/api/router.py` | Registra routers de nomenclatura y uploads |
| `emuwarez_uploadrr/web/api/placeholders.py` | Eliminados stubs reemplazados por endpoints reales |
| `emuwarez_uploadrr/cli.py` | Comandos `nomenclature` y `upload` |
| `frontend/src/types/api.ts` | Tipos TypeScript para nomenclatura y uploads |
| `frontend/src/pages/LibraryPage.tsx` | Botones "Adaptar nomenclatura" y "Subir" |
| `frontend/src/pages/UploadsPage.tsx` | Pantalla real de jobs/preflights |
| `frontend/src/styles/components.css` | Clases CSS `.modal-overlay`, `.modal`, etc. |
| `tests/test_web_app.py` | Actualizado para reflejar endpoints reales |
| `README_CLI_READY.md` | Sección de nomenclatura y preflight |

---

## Endpoints añadidos

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/library/{id}/nomenclature` | Última propuesta de nomenclatura |
| `POST` | `/api/library/{id}/nomenclature/preview` | Generar/refrescar propuesta |
| `POST` | `/api/library/{id}/adapt-nomenclature` | Stub seguro (apply bloqueado) |
| `POST` | `/api/library/{id}/upload/preflight` | Validar precondiciones de subida |
| `GET` | `/api/uploads` | Listar upload jobs/preflights |
| `GET` | `/api/uploads/{job_id}` | Detalle de un job |

---

## Comandos CLI añadidos

```bash
python3 emuwarez_uploader.py nomenclature preview <library_id>
python3 emuwarez_uploader.py nomenclature show <library_id>
python3 emuwarez_uploader.py nomenclature apply <library_id> --dry-run

python3 emuwarez_uploader.py upload preflight <library_id>
python3 emuwarez_uploader.py upload job <job_id>
python3 emuwarez_uploader.py upload jobs
```

`nomenclature apply` siempre actúa como dry-run en esta fase.
`upload preflight` nunca ejecuta Uploadrr.

---

## Tablas/columnas añadidas

### Tabla nueva: `nomenclature_proposals`

```sql
CREATE TABLE IF NOT EXISTS nomenclature_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_item_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    current_name TEXT,
    current_path TEXT,
    proposed_title TEXT,
    proposed_filename TEXT,
    proposed_folder TEXT,
    proposed_path TEXT,
    media_type TEXT,
    tmdb_id TEXT,
    imdb_id TEXT,
    resolution TEXT,
    source TEXT,
    video_codec TEXT,
    audio_summary TEXT,
    subtitle_summary TEXT,
    release_tag TEXT,
    warnings_json TEXT,
    errors_json TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Estados: `draft`, `valid`, `warning`, `blocked`, `applied` (reservado), `expired`.

### Columnas nuevas en `upload_jobs` (migración idempotente)

```text
request_item_id  INTEGER
stage            TEXT
source_path      TEXT
prepared_path    TEXT
uploadrr_command_json  TEXT
preflight_json   TEXT
progress_json    TEXT
error_message    TEXT
started_at       TEXT
finished_at      TEXT
```

---

## Qué se implementó

- **`filesystem_safety.py`**: `path_exists`, `is_file`, `is_video_file`, `safe_stat` — solo lectura, nunca escribe
- **`nomenclature.py`**: propuesta completa con título, año, resolución, source, codec, warnings, errores; estados `valid`/`warning`/`blocked`; guard contra ítems faltantes o sin ruta
- **`upload_preflight.py`**: validación de uploadrr_path, EMU key, TMDb key; preview de comando; creación de `upload_jobs` con estado `preflight`/`ready`/`blocked`
- **API endpoints**: todos protegidos con `require_auth`; `adapt-nomenclature` con `apply=True` devuelve `blocked=true`
- **Frontend**: `NomenclatureModal` y `UploadPreflightModal`; botón "Aplicar cambios" desactivado; botón "Iniciar subida" desactivado; `UploadsPage` muestra jobs reales
- **CLI**: subcomandos `nomenclature {preview,show,apply}` y `upload {preflight,job,jobs}`

---

## Qué sigue bloqueado por seguridad

- `POST /api/library/{id}/adapt-nomenclature` con `apply=True` → HTTP 200 con `blocked=true` (sin renombrado real)
- Renombrado real de archivos
- Creación de hardlinks
- Modificación de títulos MKV con mkvpropedit
- Ejecución de Uploadrr desde web o CLI
- Subida real a eMuwarez
- `POST /api/missing/{id}/create-emu-request` permanece stub bloqueado
- `POST /api/uploads/{id}/start` no implementado

---

## Validaciones ejecutadas

| Validación | Resultado |
|-----------|-----------|
| `py_compile emuwarez_uploader.py` | ✓ OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs py_compile` | ✓ OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | ✓ JSON válido |
| `python3 emuwarez_uploader.py --help` | ✓ OK |
| `python3 emuwarez_uploader.py db init` | ✓ SQLite lista |
| `python3 emuwarez_uploader.py nomenclature --help` | ✓ OK |
| `python3 emuwarez_uploader.py upload --help` | ✓ OK |
| `python3 emuwarez_uploader.py requests list` | ✓ OK |
| `python3 emuwarez_uploader.py library list` | ✓ OK |
| `pytest -q` | ✓ **286 passed, 0 failed** |
| `npm run build` | ✓ **69 módulos, ~222 KB gzip** |

---

## Resultado pytest

```
286 passed, 1 warning in 48.37s
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
| **Total** | **284** |

*(+2 en otros archivos)*

---

## Resultado npm build

```
vite v5.4.21 building for production...
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.39 kB
dist/assets/index-*.css          17.51 kB │ gzip:  4.09 kB
dist/assets/index-*.js           72.96 kB │ gzip: 17.13 kB
dist/assets/react-*.js          140.74 kB │ gzip: 45.79 kB
✓ built in 1.75s
```

---

## Confirmaciones de seguridad

- `Uploadrr/` no fue modificado. Solo inspección de lectura para entender argumentos.
- No se hizo push a ningún remoto.
- API keys nunca en texto plano en respuestas.
- No se ejecuta `os.rename`, `os.remove`, `shutil.move`, `subprocess` con Uploadrr.
- `adapt-nomenclature` con `apply=True` devuelve `blocked=true`, no modifica nada.
- `POST /api/missing/{id}/create-emu-request` sigue retornando `{implemented: false, stub: true}`.

---

## Riesgos pendientes

- MediaInfo no se invoca (requiere subprocess controlado); propuestas sin audio/subtitle info son parciales.
- `upload_jobs.path` era `NOT NULL` en schema original; se proporciona `source_path` o cadena vacía como fallback.
- Resolución y source se infieren de campos de Radarr/Sonarr; sin ellos el título propuesto es incompleto.

---

## Siguiente fase recomendada (Fase 6B o 7)

- Adaptar nomenclatura real con hardlink + rename seguro (con confirmación explícita)
- Ejecutar Uploadrr desde UI con SSE progress
- SettingsPage real (formularios de configuración)
- TasksPage real con datos de `task_runs`
- Docker: imagen final con backend + frontend built
