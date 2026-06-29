# FASE 6B — Aplicación segura de nomenclatura mediante hardlink preparado

## Objetivo

Permitir aplicar una propuesta de nomenclatura creando un hardlink del archivo original hacia la ruta propuesta, sin renombrar el archivo original, sin ejecutar Uploadrr ni mkvpropedit, y sin realizar ninguna modificación de contenido.

## Contrato de seguridad

- El archivo original (`library_items.path`) **nunca** se renombra, mueve ni elimina.
- Las únicas escrituras permitidas en filesystem real son `os.makedirs` + `os.link`.
- No se ejecuta Uploadrr. No se ejecuta mkvpropedit.
- Los hardlinks cross-device (EXDEV) se bloquean con error claro; sin fallback a copia.
- No se permiten symlinks como origen.
- El destino debe estar siempre bajo `hardlink_base` (validación con `Path.relative_to`).
- Para writes reales se requiere: `dry_run=False`, `apply=True`, `confirmation="APLICAR_NOMENCLATURA"`.
- `dry_run=True` tiene precedencia absoluta sobre `apply=True`.

## Cambios de base de datos (schema v5)

### Tabla nueva: `filesystem_operations`

| columna | tipo | descripción |
|---|---|---|
| id | INTEGER PK | autoincrement |
| operation_type | TEXT | `'nomenclature_hardlink'` |
| status | TEXT | `planned / ready / applied / blocked / failed` |
| library_item_id | INTEGER | FK library_items |
| proposal_id | INTEGER | FK nomenclature_proposals |
| source_path | TEXT | ruta origen |
| destination_path | TEXT | ruta destino (hardlink) |
| base_path | TEXT | hardlink_base usado |
| dry_run | INTEGER | 1=dry_run, 0=real |
| warnings_json | TEXT | JSON array |
| errors_json | TEXT | JSON array |
| result_json | TEXT | resultado completo JSON |
| created_at / updated_at / applied_at | TEXT | ISO timestamps |

### Columnas nuevas en `nomenclature_proposals`

- `applied_path TEXT` — ruta donde se creó el hardlink
- `applied_at TEXT` — timestamp de aplicación
- `operation_id INTEGER` — FK filesystem_operations

### Columnas nuevas en `library_items`

- `prepared_path TEXT` — ruta del hardlink creado (preferida sobre `path` para uploads)
- `nomenclature_applied_at TEXT` — timestamp de aplicación

## Nuevos archivos

### `emuwarez_uploadrr/services/filesystem_apply.py`

- `ensure_path_under_base(path, base) → bool` — valida containment sin traversal
- `build_safe_apply_plan(source, dest, base) → dict` — construye plan con validaciones completas, nunca escribe
- `apply_hardlink_plan(plan, *, dry_run, overwrite) → dict` — ejecuta o simula; en real: `os.makedirs` + `os.link`

### Tests nuevos

| archivo | tests |
|---|---|
| `tests/test_filesystem_apply.py` | 19 tests (plan, dry-run, apply real, overwrite, EXDEV) |
| `tests/test_nomenclature_apply.py` | 13 tests (confirmation, db updates, path preservation) |
| `tests/test_nomenclature_apply_api.py` | 11 tests (auth, schema, operations history, real apply) |

**Total: 329 tests pasando** (antes: 286).

## Archivos modificados

| archivo | cambio |
|---|---|
| `emuwarez_uploadrr/database.py` | schema v5, `_migrate_filesystem_operations`, `_migrate_library_items_phase6b`, columnas nomenclature_proposals |
| `emuwarez_uploadrr/services/nomenclature.py` | `CONFIRMATION_TOKEN`, `_get_hardlink_base`, `build_nomenclature_apply_plan`, `apply_nomenclature_proposal` |
| `emuwarez_uploadrr/services/upload_preflight.py` | `validate_upload_preconditions` avisa si no hay `prepared_path`; `build_uploadrr_command_preview` prefiere `prepared_path`, añade `using_prepared_path` |
| `emuwarez_uploadrr/web/schemas.py` | `AdaptNomenclatureBody` (confirmation, overwrite, proposal_id), `NomenclatureApplyResult`, `CommandPreviewResponse.using_prepared_path` |
| `emuwarez_uploadrr/web/api/nomenclature.py` | `adapt_nomenclature` usa `apply_nomenclature_proposal` real; nuevo `GET /nomenclature/operations` |
| `emuwarez_uploadrr/cli.py` | argparser `--apply --confirm TOKEN`; handler `cmd_nomenclature` llama `apply_nomenclature_proposal` |
| `frontend/src/types/api.ts` | `NomenclatureApplyResult`, `CommandPreview.using_prepared_path` |
| `frontend/src/api/nomenclature.ts` | `adaptNomenclature` acepta `confirmation`, `overwrite`, `proposalId` |
| `frontend/src/components/NomenclatureModal.tsx` | sección de apply con input de confirmación, dry-run, badges de resultado |
| `frontend/src/components/UploadPreflightModal.tsx` | badge "preparado"/"original" junto al archivo origen |
| `tests/test_nomenclature_api.py` | actualizado `test_adapt_nomenclature_apply_blocked` para schema Phase 6B |
| `README_CLI_READY.md` | sección "Implementado en Fase 6B" |

## API

### `POST /api/library/{id}/adapt-nomenclature`

**Body:**
```json
{
  "dry_run": true,
  "apply": false,
  "confirmation": null,
  "overwrite": false,
  "proposal_id": null
}
```

**Response (`NomenclatureApplyResult`):**
```json
{
  "dry_run": true,
  "apply": false,
  "status": "ready",
  "source_path": "/media/film.mkv",
  "destination_path": "/uploads/prepared/Film 2020/Film 2020 1080p BluRay.mkv",
  "operation_id": 1,
  "proposal": {...},
  "warnings": [],
  "errors": [],
  "message": "Dry-run: se crearía hardlink..."
}
```

Para apply real: `dry_run=false, apply=true, confirmation="APLICAR_NOMENCLATURA"`.

### `GET /api/library/{id}/nomenclature/operations`

Devuelve lista de `filesystem_operations` para el ítem (últimas 20, orden DESC).

## CLI

```bash
# Previsualización segura
emuwarez-uploadrr nomenclature apply 42 --dry-run

# Previsualización (default sin --apply)
emuwarez-uploadrr nomenclature apply 42

# Aplicar hardlink real
emuwarez-uploadrr nomenclature apply 42 --apply --confirm APLICAR_NOMENCLATURA
```

## Flujo de apply

```
apply_nomenclature_proposal(item_id, dry_run=False, apply=True, confirmation="APLICAR_NOMENCLATURA")
  → build_nomenclature_apply_plan(item_id)
      → get_library_item (path original)
      → get/build nomenclature_proposal
      → _get_hardlink_base() (settings o app_state)
      → destination = hardlink_base / folder / filename + ext
      → build_safe_apply_plan(source, destination, base)
  → confirmación == APLICAR_NOMENCLATURA? OK
  → apply_hardlink_plan(plan, dry_run=False)
      → os.makedirs(parent_dir)
      → os.link(source, destination)
  → INSERT filesystem_operations
  → UPDATE nomenclature_proposals SET status='applied', applied_path, applied_at, operation_id
  → UPDATE library_items SET prepared_path, nomenclature_applied_at, nomenclature_status='Correcta'
  → NUNCA modifica library_items.path
```

## Lo que NO se implementa en esta fase

- Ejecución real de Uploadrr
- Modificación de título interno MKV (mkvpropedit)
- Subida real a eMuwarez desde la UI
- Creación automática de peticiones eMuwarez
- Docker
- Configuración de `hardlink_base` desde la UI (requiere SettingsPage)
