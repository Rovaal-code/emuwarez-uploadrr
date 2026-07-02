# Fase 10F — Controlled Uploadrr-EMU execution, runtime settings and progress UI

Cierra los gaps restantes documentados en 10E/10E-0: settings de runtime sin
UI, mount Docker `:ro` incompatible con escritura de Uploadrr-EMU, ejecución
real desconectada del runtime `uploadrr_emu`, sin polling de progreso, y sin
un Uploadrr-EMU fake para validar la ejecución. **En ningún momento se ha
ejecutado un Uploadrr-EMU real, no se ha subido ningún torrent real, no se ha
llamado a eMuwarez para subir nada, no se ha tocado `Uploadrr/` (no existe en
este repo, intencionadamente externo), no se ha hecho push.**

## Estado del repo

| Campo | Valor |
|-------|-------|
| Ruta | `~/Descargas/emuwarez_uploadrr/emuwarez_uploadrr_cli_ready_v2` |
| Rama base | `master` (limpia, `45fdf51`, tag `emuwarez-uploadrr-uploadrr-emu-contract-preflight-v0`) |
| Rama de esta fase | `feature/ui-phase-10f-controlled-uploadrr-emu-execution` |
| Tests previos | 911 passed (confirmados de nuevo al inicio de esta fase) |
| Tests tras esta fase | 975 passed, 0 fallos (911 + 64 nuevos: 58 en 6 ficheros nuevos + 6 ampliando `test_docker_e2e_script.py`) |

## Gaps cerrados (de la lista pendiente de 10E/10E-0)

1. **SettingsPage sin editar los settings Uploadrr** → nueva tarjeta "Uploadrr" en Configuración.
2. **Docker `:ro` incompatible con escritura real** → `data/` y `tmp/` montados aparte en `rw`.
3. **Ejecución real desconectada del runtime `uploadrr_emu`** → conectada, con bloqueo explícito para `uploadrr_generic`.
4. **Sin polling de progreso** → `UploadsPage`/`LogsPanel` hacen polling cada ~2.5s mientras el job está `running`.
5. **Sin fake Uploadrr-EMU** → `tests/fixtures/fake_uploadrr_emu.py`, usado en tests backend y en el E2E Docker.

## Cambios por área

### 1. Settings Uploadrr en UI/API

- `emuwarez_uploadrr/web/api/settings.py`: `SettingsResponse`/`SettingsUpdateRequest` exponen `uploadrr_path`, `uploadrr_runtime_type`, `uploadrr_python_path`, `uploadrr_timeout`, `uploadrr_allowed_roots`. Validación: `runtime_type` ∈ {`uploadrr_emu`, `uploadrr_generic`} (422 si no), `timeout` entero positivo (422 si ≤ 0), `allowed_roots` acepta `list[str]` o CSV y siempre se normaliza a lista. Las escrituras usan solo la forma dotted (canónica); la forma legacy sigue funcionando como fallback de lectura vía `get_setting_canonical`.
- `frontend/src/pages/SettingsPage.tsx`: nueva tarjeta "Uploadrr" (ruta, runtime, python, timeout, allowed roots como textarea CSV) + botón **Probar configuración**.
- `frontend/src/api/settings.ts`, `frontend/src/api/integrationTests.ts`: tipos y llamada nuevos.
- **Nuevo endpoint** `POST /api/integrations/test/uploadrr` (`emuwarez_uploadrr/services/integration_tests.py::test_uploadrr_connection` + `web/api/integration_tests.py`): comprobación **solo de filesystem** (ruta existe, `upload.py` existe, `python_path` existe, `data/config.yaml` existe) — nunca ejecuta `upload.py`, nunca abre un subproceso, nunca lee secretos de `config.yaml`.

### 2. Docker mount strategy

- `docker-compose.example.yml`: `/opt/Uploadrr` (código) sigue en `:ro`; nuevos mounts `/opt/Uploadrr/data:rw` y `/opt/Uploadrr/tmp:rw` vía `${UPLOADRR_DATA_PATH}`/`${UPLOADRR_TMP_PATH}`.
- `.env.example`: nuevas variables `UPLOADRR_PATH`, `UPLOADRR_DATA_PATH`, `UPLOADRR_TMP_PATH`.
- `docs/DEPLOYMENT_DOCKER.md` (sección 7b reescrita) y `README_CLI_READY.md`: documentan por qué `data/`/`tmp/` deben ser `rw` (staging/restore de `config.yaml`, temporales del fork) y que **Uploadrr-EMU nunca se vendoriza** dentro de la imagen principal.

### 3. Fake Uploadrr-EMU

- `tests/fixtures/fake_uploadrr_emu.py`: acepta el contrato de flags real (`-tk/-mt/-tmdb/-ua/-c/-res/-season/-episode`), imprime logs deterministas (`[EMU] Preparando subida` … `[EMU] Torrent creado correctamente`), soporta `--fake-fail`/`FAKE_UPLOADRR_FAIL=1` y `--fake-sleep`/`FAKE_UPLOADRR_SLEEP=N`. No importa `urllib`/`requests`/`socket`; nunca lee secretos reales; solo imprime y devuelve exit code.
- `tests/conftest.py`: fixtures `fake_uploadrr_emu_dir` (copia el fixture como `upload.py` + `data/config.yaml` placeholder en un `tmp_path`) y `fake_uploadrr_python_path` (usa `sys.executable`).
- `scripts/docker-e2e-demo.sh`: copia el mismo fixture como `upload.py` en el mount `:ro`, y un `data/config.yaml` placeholder en el mount `rw` de `data/`.

### 4. Ejecución controlada Uploadrr-EMU

- `emuwarez_uploadrr/services/upload_execution.py`:
  - `start_upload_job()` bloquea el inicio real (`error="unsupported_runtime"`) si `uploadrr.runtime_type != "uploadrr_emu"` — sigue exigiendo `apply=true`, `dry_run=false` y `confirmation=INICIAR_UPLOADRR` como antes.
  - Config staging conectado: `_stage_uploadrr_config()` hace backup + stage de `DEFAULT.tmdb`/`TRACKERS.EMU.api_key` en `data/config.yaml` (usando los helpers ya existentes de `uploadrr_config_staging.py`, Fase 10E, hasta ahora desconectados) justo antes del `subprocess.Popen`; `_restore_uploadrr_config()` restaura siempre desde el backup en un `finally` que envuelve toda la ejecución — éxito, fallo, timeout **o cancelación**. Si `data/config.yaml` no existe todavía, el staging se salta con un warning en los logs (no se crea un config.yaml desde cero).
  - **Bug de concurrencia corregido**: la implementación original habría sobreescrito un job recién cancelado con `failed`/`completed` cuando el subproceso, ya matado por `SIGTERM`, terminaba de forma asíncrona. `_finalize_job_status()` ahora hace un único `UPDATE upload_jobs SET ... WHERE id = ? AND status != 'cancelled'` atómico (no un read-then-write) — SQLite serializa escritores, así que no hay ventana de carrera posible entre este UPDATE y el de `cancel_upload_job()`. Reproducido y verificado con un runner fake real (no mockeado) cancelado a mitad de ejecución, en tests y en varias repeticiones (incluida la suite completa).
  - `compute_progress_phase(status, stage)`: mapea a `queued`/`preflight`/`config_staging`/`running`/`finalizing`/`succeeded`/`failed`/`cancelled`/`timeout` — nunca un porcentaje inventado.
- `emuwarez_uploadrr/services/upload_preflight.py`: nueva advertencia (no bloqueante) si `data/config.yaml` no existe para `runtime_type=uploadrr_emu`.
- `emuwarez_uploadrr/web/api/uploads.py`: `UploadJobDetail` expone `runtime_type`, `command_preview` (redactado, prioriza el capturado en ejecución real) y `progress_phase`. `POST /uploads/{id}/start` devuelve 400 para `error="unsupported_runtime"`.
- `emuwarez_uploadrr/web/schemas.py`: campos nuevos en `UploadJobDetail`; nuevo `TestUploadrrRequest`.
- `emuwarez_uploadrr/cli.py`: nuevo alias `upload status <job_id>` (idéntico a `upload job <job_id>`). El resto de subcomandos (`preflight`/`start --dry-run|--apply --confirm`/`logs`/`cancel`/`retry`) ya existían.

### 5. Progreso/logs en UI

- `frontend/src/pages/UploadsPage.tsx`: polling cada 2.5s mientras algún job está `running` (recarga silenciosa, sin parpadeo del spinner); columna "Progreso" con `progress_phase`; badge de estado con `title` = `command_preview` redactado; indicador "● actualizando en vivo". `LogsPanel` recibe `autoRefresh` y hace polling mientras el job abierto está `running`.
- `frontend/src/types/api.ts`: `UploadJob` gana `runtime_type`, `command_preview`, `progress_phase`.

## Tests

Nuevos archivos (58 tests):

- `tests/test_uploadrr_emu_fake_runner.py` (8): el fixture fake en sí — acepta flags reales, `--fake-fail`/`--fake-sleep`, sin red, sin secretos.
- `tests/test_uploadrr_emu_execution.py` (7): contrato de flags reales en `build_uploadrr_execution_command`, apply con fake runner (éxito/fallo), dry-run no ejecuta subprocess, `uploadrr_generic` bloquea el arranque real, cancelación marca `cancelled` bajo concurrencia real.
- `tests/test_uploadrr_config_staging_execution.py` (5): restauración de `config.yaml` en éxito/fallo/timeout, secretos nunca en logs/preview/`safe_command_json`, staging se salta sin error si no hay `config.yaml`.
- `tests/test_uploadrr_progress_logs.py` (14): mapeo de `compute_progress_phase`, campos nuevos en `GET /api/uploads/{id}`, logs visibles tras ejecución fake.
- `tests/test_uploadrr_runtime_settings_api.py` (18): guardado/validación de cada setting Uploadrr, normalización de `allowed_roots` (CSV y lista), endpoint `test/uploadrr` (not_configured/not_found/python_missing/connected_no_config/connected), nunca ejecuta `upload.py`.
- `tests/test_uploadrr_cli_execution.py` (6): `upload status` == `upload job`, `start` dry-run no ejecuta subprocess, `start --apply` sin confirm bloquea, `start --apply --confirm` con fake runner, `logs` y `cancel` desde CLI.

Ampliados: `tests/test_docker_e2e_script.py` (+6, validan estáticamente las nuevas secciones del script E2E).

**Resultado `pytest -q`:** `975 passed, 0 failed` (verificado además con varias repeticiones consecutivas completas de la suite y ~7 repeticiones de los archivos nuevos, sin fallos, para descartar flakiness de concurrencia).

**`npm run build`:** OK (`tsc && vite build`, sin errores de tipos).

## Docker

- `docker build -t emuwarez-uploadrr:phase-10f .` → OK.
- `docker compose -f docker-compose.example.yml config` → OK, refleja los 3 mounts de Uploadrr (`:ro` código, `rw` data, `rw` tmp).
- `bash scripts/docker-smoke-test.sh` → OK.
- `bash scripts/docker-e2e-demo.sh` → OK, incluye la nueva sección "Phase 10F" que: configura los settings de runtime Uploadrr apuntando al fake runner montado, ejecuta un preflight real sobre el ítem demo, arranca el job con `apply=true`+`INICIAR_UPLOADRR`, espera a que termine, y verifica: `command_preview` con flags reales (`-tk`/`-mt`/`-ua`), `action=started`, `status=completed`, `exit_code=0`, URL fake capturada como resultado, logs con `Torrent creado correctamente`, y `config.yaml` restaurado al placeholder original tras la ejecución.

## Confirmaciones de seguridad

- **No se ejecutó Uploadrr-EMU real** en ningún momento (tests, E2E o validaciones manuales) — todo contra `tests/fixtures/fake_uploadrr_emu.py`.
- **No se subió ningún torrent real. No se llamó a eMuwarez real.**
- **No se tocó `Uploadrr/`** (no existe en este repo).
- `subprocess.Popen` siempre con `shell=False`, argv como `list[str]`.
- La ejecución real exige `apply=true`, `dry_run=false` y confirmación exacta `INICIAR_UPLOADRR`; además ahora exige `runtime_type=uploadrr_emu`.
- `dry_run=true` nunca invoca `subprocess.Popen` (verificado con mock).
- `config.yaml` se restaura siempre — éxito, fallo, timeout y cancelación — vía un único `finally`.
- Secretos (`tmdb.api_key`, `emu.api_key`) nunca aparecen en `command_preview`, logs (`upload_job_logs`) ni `safe_command_json` (verificado con valores de prueba distintivos).
- Sin push en ningún momento.

## Gaps restantes

- **Prueba manual real en servidor**: esta fase solo valida contra el runner fake; la primera ejecución contra una instalación real de Uploadrr-EMU queda para el operador, bajo confirmación manual.
- **Progreso más granular**: `progress_phase` es un mapeo aproximado de `status`/`stage`, no un parsing específico del contenido real de los logs de Uploadrr-EMU (que no emite progreso estructurado).
- **Config staging limitado**: solo cubre `DEFAULT.tmdb`/`TRACKERS.EMU.api_key`/`anon` — el resto de `config.yaml` (otros trackers, clientes de torrent, hosts de capturas) sigue siendo responsabilidad del operador, por diseño (ya documentado como límite intencional desde la Fase 10E).
- **Integración con publicación final real**: queda explícitamente bajo confirmación manual del usuario en un servidor real; no se automatiza en esta fase.
