# Checkpoint — Uploadrr Controlled Execution v0

**Fecha:** 2026-06-29
**Rama mergeada:** `feature/ui-phase-06c-uploadrr-controlled-execution`
**Commit de feature:** `e96881f feat: add controlled Uploadrr execution`
**Commit de merge:** `ad4230b merge: controlled Uploadrr execution milestone`
**Tag creado:** `emuwarez-uploadrr-controlled-execution-v0`
**Tags existentes tras este checkpoint:**
- `emuwarez-uploadrr-controlled-execution-v0`
- `emuwarez-uploadrr-nomenclature-apply-v0`
- `emuwarez-uploadrr-nomenclature-preflight-v0`
- `emuwarez-uploadrr-ui-requests-v0`

---

## Validaciones ejecutadas

### Pre-merge (en `feature/ui-phase-06c-uploadrr-controlled-execution`)

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
372 passed, 1 warning in 60.82s
```

### npm build pre-merge

```
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-BmbIeSxJ.css   17.51 kB │ gzip:  4.09 kB
dist/assets/index-BTa8mdLo.js    85.45 kB │ gzip: 19.70 kB
dist/assets/react-SIwY82C9.js   140.74 kB │ gzip: 45.79 kB
✓ built in 1.18s
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
372 passed, 1 warning in 62.59s
```

### npm build post-merge

```
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-BmbIeSxJ.css   17.51 kB │ gzip:  4.09 kB
dist/assets/index-BTa8mdLo.js    85.45 kB │ gzip: 19.70 kB
dist/assets/react-SIwY82C9.js   140.74 kB │ gzip: 45.79 kB
✓ built in 740ms
```

---

## Funcionalidades incluidas en este milestone

- Ejecución controlada de Uploadrr desde `upload_job` preparado (`status=ready`)
- Confirmación exacta `INICIAR_UPLOADRR` obligatoria para ejecución real
- `dry_run=True` por defecto en todos los puntos de entrada
- Bloqueo si job no está en estado `ready`
- Bloqueo si faltan precondiciones (paths, configuración, job inexistente)
- Ejecución mediante `subprocess.Popen` sin `shell=True`
- Captura de stdout/stderr en tiempo real guardada en `upload_job_logs`
- Redacción de `api_token`, `api_key` y claves conocidas antes de guardar logs
- Estados de job: `ready → queued → running → completed/failed/cancelled`
- Tabla `upload_job_logs`: historial saneado por job
- Endpoints protegidos con Bearer token:
  - `GET /api/uploads` — lista de jobs
  - `GET /api/uploads/{id}` — detalle sin secretos
  - `GET /api/uploads/{id}/logs` — logs paginados saneados
  - `POST /api/uploads/{id}/start` — dry-run o ejecución real
  - `POST /api/uploads/{id}/cancel` — cancelación controlada
- CLI: `upload jobs`, `upload job <id>`, `upload logs <id>`, `upload start <id> [--dry-run | --apply --confirm INICIAR_UPLOADRR]`, `upload cancel <id>`
- Frontend `UploadsPage`: lista de jobs con estados visuales por color, panel de logs
- Frontend `UploadPreflightModal`: flujo de confirmación con input exacto `INICIAR_UPLOADRR` y advertencias de seguridad
- 43 tests nuevos: `test_upload_execution.py` (25), `test_upload_execution_api.py` (18), `test_upload_logs_redaction.py` (10). Total: 372 tests

---

## Funcionalidades bloqueadas (pendientes de fases posteriores)

- Creación automática de peticiones eMuwarez (requiere capturar POST real desde DevTools)
- Modificación de título interno MKV
- Integración real de `mkvpropedit`
- Copia / reflink entre dispositivos distintos
- Docker final
- Jellyfin real
- Seerr real
- `SettingsPage` con formularios de configuración real

---

## Confirmaciones

- `Uploadrr/` no fue tocado en ningún momento de esta fase
- No se hizo push a ningún remoto
- El merge fue `--no-ff` sin conflictos (estrategia `ort`)
- El árbol de trabajo queda limpio en `master`
- `shell=True` no se usa en ninguna ruta de código nueva
- Las API keys no aparecen en logs ni en respuestas de API
