# Checkpoint — Nomenclature Apply v0

**Fecha:** 2026-06-29
**Rama mergeada:** `feature/ui-phase-06b-safe-nomenclature-apply`
**Commit de feature:** `a71577d feat: add safe nomenclature hardlink apply`
**Commit de merge:** `f48ba3b merge: safe nomenclature hardlink apply milestone`
**Tag creado:** `emuwarez-uploadrr-nomenclature-apply-v0`
**Tags existentes tras este checkpoint:**
- `emuwarez-uploadrr-nomenclature-apply-v0`
- `emuwarez-uploadrr-nomenclature-preflight-v0`
- `emuwarez-uploadrr-ui-requests-v0`

---

## Validaciones ejecutadas

### Pre-merge (en `feature/ui-phase-06b-safe-nomenclature-apply`)

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py --help` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web-contract` | OK |
| `python3 emuwarez_uploader.py web info` | OK |
| `python3 emuwarez_uploader.py web setup-status` | OK |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py library list` | OK |
| `python3 emuwarez_uploader.py missing list` | OK |
| `python3 emuwarez_uploader.py requests list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |

### pytest pre-merge

```
329 passed, 1 warning in 54.09s
```

### npm build pre-merge

```
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-BmbIeSxJ.css   17.51 kB │ gzip:  4.09 kB
dist/assets/index-DdcHh-VV.js    76.66 kB │ gzip: 18.03 kB
dist/assets/react-SIwY82C9.js   140.74 kB │ gzip: 45.79 kB
✓ built in 2.11s
```

### Post-merge (en `master`)

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py library list` | OK |
| `python3 emuwarez_uploader.py missing list` | OK |
| `python3 emuwarez_uploader.py requests list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |

### pytest post-merge

```
329 passed, 1 warning in 56.42s
```

### npm build post-merge

```
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-BmbIeSxJ.css   17.51 kB │ gzip:  4.09 kB
dist/assets/index-DdcHh-VV.js    76.66 kB │ gzip: 18.03 kB
dist/assets/react-SIwY82C9.js   140.74 kB │ gzip: 45.79 kB
✓ built in 660ms
```

---

## Funcionalidades incluidas en este milestone

- `filesystem_apply.py` con contrato de seguridad estricto
- Aplicación segura de nomenclatura mediante hardlink (`os.link`)
- `dry_run=True` por defecto; siempre prevalece sobre `apply=True`
- Token de confirmación exacto `APLICAR_NOMENCLATURA` requerido para writes reales
- Bloqueo de symlinks como origen
- Bloqueo de path traversal (destino fuera de `hardlink_base`)
- Bloqueo de destino ya existente (por defecto)
- Manejo controlado de `EXDEV` / cross-device link
- Tabla `filesystem_operations`: historial de todas las operaciones
- `library_items.prepared_path`: ruta del hardlink creado
- `nomenclature_proposals.(applied_path, applied_at, operation_id)`
- Schema SQLite v5
- Endpoint `POST /api/library/{id}/adapt-nomenclature` real con `NomenclatureApplyResult`
- Endpoint `GET /api/library/{id}/nomenclature/operations`: historial de operaciones
- `upload_preflight` prioriza `prepared_path` sobre `path`; avisa si nomenclatura no aplicada; añade `using_prepared_path` al preview
- CLI `nomenclature apply <id> [--dry-run] [--apply --confirm APLICAR_NOMENCLATURA]`
- Frontend: `NomenclatureModal` con sección de confirmación y creación de hardlink
- Frontend: `UploadPreflightModal` con indicador "preparado" / "original"
- 43 tests nuevos (filesystem_apply, nomenclature_apply, nomenclature_apply_api) — total 329

---

## Funcionalidades bloqueadas (pendientes de fases posteriores)

- Ejecución real de Uploadrr
- Subida real a eMuwarez desde la UI
- Modificación de título interno MKV
- Integración real de `mkvpropedit`
- Sobrescritura automática de destinos existentes
- Copia / reflink entre dispositivos distintos
- Creación automática de peticiones eMuwarez (requiere capturar POST real desde DevTools)
- Docker final
- `SettingsPage` con formularios de configuración real (incluyendo `hardlink_base`)
- `TasksPage` con datos reales
- `UploadsPage` con flujo de subida completo

---

## Confirmaciones

- `Uploadrr/` no fue tocado en ningún momento de esta fase
- No se hizo push a ningún remoto
- El merge fue `--no-ff` sin conflictos (estrategia `ort`)
- El árbol de trabajo queda limpio en `master`
