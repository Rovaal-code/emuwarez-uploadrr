# Fase 6C — Ejecución controlada de Uploadrr

**Rama:** `feature/ui-phase-06c-uploadrr-controlled-execution`
**Fecha:** 2026-06-29
**Basada en:** `master` @ `9fc38f7`

---

## Archivos creados

- `emuwarez_uploadrr/services/upload_execution.py` — servicio principal de ejecución
- `tests/test_upload_execution.py` — 25 tests del servicio
- `tests/test_upload_execution_api.py` — 18 tests de los endpoints
- `tests/test_upload_logs_redaction.py` — 10 tests de redacción de secretos
- `docs/codex_phase_06c_uploadrr_controlled_execution_report.md` — este informe

## Archivos modificados

- `emuwarez_uploadrr/database.py` — schema v6, nuevas migraciones
- `emuwarez_uploadrr/web/schemas.py` — nuevos schemas de ejecución
- `emuwarez_uploadrr/web/api/uploads.py` — nuevos endpoints start/cancel/logs
- `emuwarez_uploadrr/cli.py` — nuevos subcomandos upload start/logs/cancel
- `frontend/src/types/api.ts` — nuevos tipos UploadJobLog, UploadStartRequest, etc.
- `frontend/src/api/uploads.ts` — nuevas funciones startUploadJob, getUploadJobLogs, cancelUploadJob
- `frontend/src/components/UploadPreflightModal.tsx` — botón Iniciar subida activado
- `frontend/src/pages/UploadsPage.tsx` — tabla completa con logs, start, cancel
- `README_CLI_READY.md` — sección nueva de ejecución controlada

---

## Endpoints añadidos

```
GET  /api/uploads                     → lista jobs con detalle completo
GET  /api/uploads/{job_id}            → detalle de job (sin secretos)
GET  /api/uploads/{job_id}/logs       → logs paginados saneados
POST /api/uploads/{job_id}/start      → dry-run o inicio real
POST /api/uploads/{job_id}/cancel     → cancelar job en ejecución
```

Todos requieren `Authorization: Bearer <token>`. Sin token: 401.

---

## Comandos CLI añadidos

```bash
python3 emuwarez_uploader.py upload jobs
python3 emuwarez_uploader.py upload job <id>
python3 emuwarez_uploader.py upload logs <id> [--limit 200]
python3 emuwarez_uploader.py upload start <id> --dry-run
python3 emuwarez_uploader.py upload start <id> --apply --confirm INICIAR_UPLOADRR
python3 emuwarez_uploader.py upload cancel <id>
```

---

## Tablas / columnas añadidas

### `upload_jobs` — columnas nuevas (fase 6C)
- `exit_code INTEGER` — código de salida del proceso
- `process_id INTEGER` — PID del proceso Uploadrr

### `upload_job_logs` — tabla nueva
```sql
CREATE TABLE upload_job_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_job_id INTEGER NOT NULL,
    level TEXT NOT NULL,          -- info / warning / error / debug
    message TEXT NOT NULL,
    stream TEXT,                  -- stdout / stderr / system
    created_at TEXT NOT NULL,
    raw_json TEXT,
    FOREIGN KEY (upload_job_id) REFERENCES upload_jobs(id)
)
```

**Schema version:** 5 → 6

---

## Modelo de ejecución

1. `start_upload_job()` valida todas las precondiciones.
2. Si `dry_run=True`: devuelve el comando previsto sin ejecutar nada.
3. Si `dry_run=False, start=True, confirmation="INICIAR_UPLOADRR"`: lanza `_run_uploadrr_subprocess` en un `threading.Thread` daemon.
4. El thread actualiza el job a `running`, ejecuta `subprocess.Popen` y registra stdout/stderr en `upload_job_logs` línea a línea.
5. Al terminar: `completed` (exit 0) o `failed` (exit != 0).
6. `cancel_upload_job` envía `SIGTERM` al PID registrado y marca el job como `cancelled`.

---

## Cómo se evita shell=True

`subprocess.Popen` se invoca siempre como:
```python
subprocess.Popen(
    [executable] + args,   # lista explícita, nunca string
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=cwd,
    env=env,
)
```

El parámetro `shell` nunca se pasa, por lo que su valor es `False` por defecto. Los tests verifican explícitamente que `call_kwargs.get("shell", False) is False`.

---

## Cómo se redactan los secretos

`redact_secrets(value, secrets)`:
1. Reemplaza cada valor de la lista `secrets` directamente en el string.
2. Aplica expresiones regulares para patrones comunes:
   - `api_token=<valor>`
   - `api_key=<valor>`
   - `token=<valor>`
   - `key=<valor>`
3. Resultado: cualquier coincidencia se sustituye por `***REDACTED***`.
4. Los secretos se recogen de la tabla `settings` en tiempo de ejecución (nunca del JSON almacenado).

---

## Qué se implementó

- Servicio `upload_execution.py` completo con todos los contratos de seguridad.
- Ejecución real de Uploadrr mediante `subprocess.Popen` (sin `shell=True`).
- Confirmación exacta `INICIAR_UPLOADRR` requerida para ejecución real.
- `dry_run=True` por defecto.
- Logs línea a línea guardados en `upload_job_logs` con stream y level.
- Secretos redactados antes de guardar en logs.
- API protegida con Bearer token.
- CLI completa con start/logs/cancel.
- Frontend: botón "Iniciar subida" activo con input de confirmación.
- Frontend: `UploadsPage` con tabla completa, logs panel y modal de inicio.
- 43 tests nuevos cubriendo todos los casos críticos.

---

## Qué sigue bloqueado

- Creación automática de peticiones eMuwarez (requiere POST capturado desde DevTools).
- Modificación de título interno MKV (`mkvpropedit`).
- Copia/reflink entre dispositivos distintos.
- Sobrescritura automática de destinos.
- Docker final.
- `SettingsPage` completa (incluyendo configuración de `hardlink_base` y `uploadrr_path`).
- `TasksPage` con datos reales.
- Cancelación fiable mediante proceso registrado (actualmente via SIGTERM al PID; el proceso puede haber terminado).

---

## Validaciones ejecutadas

| Validación | Resultado |
|---|---|
| `python3 -m py_compile emuwarez_uploader.py` | OK |
| `find emuwarez_uploadrr -name "*.py" \| xargs python3 -m py_compile` | OK |
| `python3 -m json.tool docs/ui_backend_contract.json` | OK |
| `python3 emuwarez_uploader.py --help` | OK |
| `python3 emuwarez_uploader.py db init` | OK |
| `python3 emuwarez_uploader.py web-contract` | OK |
| `python3 emuwarez_uploader.py web setup-status` | OK |
| `python3 emuwarez_uploader.py instances list` | OK |
| `python3 emuwarez_uploader.py library list` | OK |
| `python3 emuwarez_uploader.py missing list` | OK |
| `python3 emuwarez_uploader.py requests list` | OK |
| `python3 emuwarez_uploader.py upload jobs` | OK |

## pytest

```
372 passed, 1 warning in 57.46s
```

(329 anteriores + 43 nuevos)

## npm run build

```
✓ 69 modules transformed.
dist/index.html                   0.64 kB │ gzip:  0.38 kB
dist/assets/index-BmbIeSxJ.css   17.51 kB │ gzip:  4.09 kB
dist/assets/index-BTa8mdLo.js    85.45 kB │ gzip: 19.70 kB
dist/assets/react-SIwY82C9.js   140.74 kB │ gzip: 45.79 kB
✓ built in 1.81s
```

---

## Riesgos pendientes

- **Uploadrr CLI args**: La forma exacta de invocación de `Uploadrr/upload.py` (args posicionales vs flags) no se ha confirmado al 100% con ejecución real. El comando construido sigue la lógica de `build_uploadrr_command_preview` existente. Si Uploadrr espera una interfaz diferente, se detectará en el primer `start` real.
- **Cancelación**: `cancel_upload_job` usa `os.kill(pid, SIGTERM)`. Si el proceso terminó antes, `ProcessLookupError` se captura silenciosamente. No hay garantía de que el proceso se detenga inmediatamente.
- **Threads daemon**: El thread de ejecución es daemon, por lo que si el proceso Python termina abruptamente, el thread muere. El job quedaría en `running` en la BD. Se recomienda añadir un mecanismo de recuperación al arrancar (detectar jobs `running` sin proceso activo y marcarlos como `failed`).

---

## Confirmaciones

- `Uploadrr/` no fue modificado.
- No se hizo push.
- No se ejecutó `mkvpropedit`.
- No se crearon peticiones eMuwarez automáticamente.
- `shell=True` nunca se usa en ningún subprocess.
- API keys no aparecen en logs ni respuestas API.

---

## Siguiente fase recomendada

**Fase 7 — Settings UI + configuración real desde frontend:**
- Formulario `SettingsPage` para configurar `uploadrr_path`, `hardlink_base`, `emu_api_key`, `tmdb_api_key`.
- Conexión real de setup wizard desde frontend.
- O alternativamente: `TasksPage` con datos reales y `UploadsPage` con polling de estado.
