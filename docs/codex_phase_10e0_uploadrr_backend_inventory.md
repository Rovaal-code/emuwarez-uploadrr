# Fase 10E-0 — Backend Uploadrr Contract Inventory

Auditoría interna del backend actual. **No se ha modificado código funcional. No se ha
ejecutado Uploadrr. No se ha realizado ninguna subida real. No se ha tocado `Uploadrr/`.**

## Estado del repo

| Campo | Valor |
|-------|-------|
| Ruta | `~/Descargas/emuwarez_uploadrr/emuwarez_uploadrr_cli_ready_v2` |
| Rama base | `master` (limpia, `d8103ac`, tag `emuwarez-uploadrr-external-api-test-buttons-v0`) |
| Rama de esta fase | `feature/ui-phase-10e0-uploadrr-backend-inventory` |
| Rama 10D | `feature/ui-phase-10d-uploadrr-emu-runtime-audit` (commit `d4f9dce`), no mezclada |
| Tests previos | 852 passed (confirmado de nuevo en esta fase) |

## Resumen ejecutivo

El pipeline de subida (preflight → job → ejecución controlada → logs → artifacts →
retry/cancel) está **arquitectónicamente completo y sólido**: `shell=False`, confirmación
explícita `INICIAR_UPLOADRR`, `dry_run` por defecto, redacción de secretos, resultado por
`exit_code`, estados en BD, tests de regresión. Sin embargo, se confirman y amplían los
hallazgos de la auditoría 10D, y aparecen **dos gaps nuevos no documentados en 10D**:

1. **Los flags CLI que construye `build_uploadrr_execution_command` no coinciden con el
   contrato real de Uploadrr-EMU** (`--tracker`/`--category`/`--tmdb`/`--resolution` en vez
   de `-tk`/`-mt`/`-tmdb`/`-c`/`-res`/`-ua`). Ya documentado en 10D, confirmado aquí en
   `emuwarez_uploadrr/services/upload_execution.py:239-243`.
2. **NUEVO — mismatch de namespace de settings.** El asistente de configuración real
   (`setup_uploadrr()`, `setup_tmdb()`, `setup_emu()` en
   `web/services/setup_service.py`) escribe claves con notación de puntos:
   `uploadrr.path`, `tmdb.api_key`, `emu.api_key`. Pero `upload_preflight.py` y
   `upload_execution.py` leen `uploadrr_path`, `tmdb_api_key`, `emu_api_key` (con guion
   bajo, sin punto) — **claves distintas en la misma tabla `settings`**. En producción,
   tras completar el setup real vía UI/API, `validate_upload_job_start` y
   `validate_upload_preconditions` seguirían reportando "Ruta de Uploadrr no configurada"
   y "API key de eMuwarez no configurada" indefinidamente. Los tests actuales no detectan
   esto porque insertan filas directamente con la clave equivocada (`uploadrr_path`, no
   `uploadrr.path`), replicando el bug en el fixture en vez de exponerlo.
3. **NUEVO — existe una implementación CLI-only, completamente correcta y desconectada,
   del contrato real.** `emuwarez_uploadrr/legacy.py::build_uploadrr_command` (línea 3258)
   ya construye exactamente `-tk EMU -mt <título> -tmdb <arg> -ua -c movie|tv -res <res>
   [-season/-episode]`, con `cwd=uploadrr_dir()` y `stdin=subprocess.DEVNULL`
   (`run_uploadrr_command`, línea 3868). Es la lógica portada del script monolítico
   original. Pero **nada la usa**: ni `cli.py` (que solo importa `services/upload_preflight.py`
   y `services/upload_execution.py` a través de `cmd_upload_modern`), ni el backend web.
   El módulo que la reexporta (`emuwarez_uploadrr/uploadrr_runner.py`) no tiene ningún
   importador en todo el árbol (`emuwarez_uploadrr/`, `tests/`). Es código muerto que,
   paradójicamente, contiene el contrato correcto que hace falta portar al pipeline de
   jobs.

## Módulos backend existentes

| Módulo | Líneas | Rol |
|---|---|---|
| `emuwarez_uploadrr/services/upload_execution.py` | 867 | Ejecución controlada de jobs (dry-run, start real, cancel, retry, logs, artifacts) |
| `emuwarez_uploadrr/services/upload_preflight.py` | 278 | Preflight: valida precondiciones y construye preview de comando antes de crear el job |
| `emuwarez_uploadrr/services/upload_result_parser.py` | ~90 | `classify_upload_result`/`build_error_summary` — interpreta stdout/stderr/exit_code |
| `emuwarez_uploadrr/services/filesystem_apply.py` | 209 | Aplica plan de nomenclatura (hardlink/rename), fuerza destino dentro de `hardlink_base` |
| `emuwarez_uploadrr/services/filesystem_safety.py` | 56 | Utilidades read-only (`safe_stat`, detección de vídeo). Sin concepto de `allowed_roots` |
| `emuwarez_uploadrr/services/mkv_title.py` | 273 | Edición controlada de título interno MKV, opera solo sobre `prepared_path`/`applied_path` |
| `emuwarez_uploadrr/services/nomenclature.py` | 589 | Genera y aplica propuestas de nomenclatura; escribe `applied_path` en `nomenclature_proposals` |
| `emuwarez_uploadrr/services/operational_actions.py` | 432 | Acciones guiadas de cola (marcar, aplicar, etc.) |
| `emuwarez_uploadrr/services/operational_queue.py` | 704 | Cola operacional unificada |
| `emuwarez_uploadrr/services/demo_seed.py` | 173 | Seed de datos demo |
| `emuwarez_uploadrr/web/services/settings_service.py` | ~90 | CRUD de `settings` — **usa namespace con puntos** (`tmdb.api_key`, `emu.api_key`, `uploadrr.path`) |
| `emuwarez_uploadrr/web/services/setup_service.py` | — | Wizard de setup inicial; escribe con el mismo namespace de puntos |
| `emuwarez_uploadrr/database.py` | 732 | Esquema SQLite, incluye tablas `upload_jobs`, `upload_job_logs`, `upload_artifacts` |
| `emuwarez_uploadrr/cli.py` | 1876 | CLI unificado; subcomando `upload` delega en los servicios de arriba |
| `emuwarez_uploader.py` | 8 | Entry point fino |
| `emuwarez_uploadrr/legacy.py` | 4446 | **Script monolítico original portado tal cual**, con lógica correcta de Uploadrr-EMU pero desconectada del pipeline de jobs |
| `emuwarez_uploadrr/uploadrr_config.py`, `uploadrr_runner.py`, `planner.py`, `validators.py`, `constants.py` | pequeños | Shims que reexportan símbolos de `legacy.py`; `uploadrr_runner.py` no tiene importadores |

No existe `emuwarez_uploadrr/services/settings_service.py` (la ruta pedida en el encargo);
el servicio de settings real vive en `emuwarez_uploadrr/web/services/settings_service.py`.

## Endpoints API existentes

`emuwarez_uploadrr/web/api/uploads.py`:

- `POST /api/library/{item_id}/upload/preflight`
- `GET /api/uploads`
- `GET /api/uploads/{job_id}`
- `GET /api/uploads/{job_id}/logs`
- `GET /api/uploads/{job_id}/artifacts`
- `POST /api/uploads/{job_id}/start` (dry_run/start/confirmation)
- `POST /api/uploads/{job_id}/retry`
- `POST /api/uploads/{job_id}/cancel`

Settings/setup: `emuwarez_uploadrr/web/api/settings.py`, `emuwarez_uploadrr/web/api/setup.py`
(incluye `POST /api/setup/uploadrr`).

## CLI existente

`cli.py` subcomando `upload` (`cmd_upload_modern`): `preflight`, `job`, `jobs`, `start`,
`logs`, `artifacts` (según `DEPLOYMENT_DOCKER.md`: `upload start <id> --apply --confirm
INICIAR_UPLOADRR`). Reutiliza exactamente los mismos servicios que la API web
(`services/upload_preflight.py`, `services/upload_execution.py`) — comparte, por tanto,
tanto el bug de flags como el mismatch de namespace de settings.

Aparte, `legacy.py` es invocable como comandos `legacy` (línea 25 de `cli.py`) y contiene
su propio flujo interactivo end-to-end (detección de fuente, TMDb, construcción de
`AppConfig`, hardlinks, y `build_uploadrr_command`/`run_uploadrr_command` con el contrato
correcto) — pero es un camino completamente distinto al de `upload_jobs`.

## UI existente

- `frontend/src/pages/UploadsPage.tsx`: lista de jobs con filtro por estado, botón de
  logs (`LogsPanel`, fetch único al abrir el modal — **sin polling ni auto-refresh**),
  start/retry/cancel según estado.
- `frontend/src/pages/QueuePage.tsx`: referencia `upload_job_id` y acciones
  `upload`/`retry_upload` como parte de la cola operacional guiada, no tiene su propio
  panel de logs.
- `frontend/src/api/uploads.ts`: cliente para los 8 endpoints anteriores.

## Tests existentes

`test_upload_execution.py`, `test_upload_execution_api.py`, `test_upload_preflight.py`,
`test_upload_lifecycle.py`, `test_upload_logs_redaction.py`, `test_upload_result_parser.py`,
`test_upload_retry_api.py`. Ninguno fija literalmente los flags `--tracker`/`--category`
como cadena — solo comprueban claves de diccionario (`tracker`, `category`) y ausencia de
secretos en el preview, por lo que **cambiar los flags reales en Fase 10E tiene bajo riesgo
de romper tests existentes**. Sí fijan (indirectamente, vía fixtures) la clave de settings
`uploadrr_path`/`emu_api_key`/`tmdb_api_key` sin punto — habrá que decidir si se corrige el
namespace o se mantiene y se corrige el lado del setup wizard.

## Contrato actual de Uploadrr

`build_uploadrr_execution_command` (`upload_execution.py:208-261`):

```python
executable = sys.executable
args = [script, active_path, "--tracker", tracker, "--category", category]
if tmdb_id: args += ["--tmdb", str(tmdb_id)]
if resolution: args += ["--resolution", resolution]
```

`build_uploadrr_command_preview` (`upload_preflight.py:88-139`) construye un preview de
texto equivalente (`--tracker`, `--category`, `--tmdb`, `--resolution`, `--source`,
`--title`) — **ninguno de estos flags largos existe en el `upload.py` real** salvo
`--category`/`--resolution`/`--tmdb`, y ninguno de los dos módulos añade `-ua`/`-mt`.

## Flags actuales detectados

| Flag actual (app) | ¿Existe en Uploadrr-EMU real? | Correcto real |
|---|---|---|
| `--tracker EMU` | ❌ No existe (es plural `-tk`/`--trackers`) | `-tk EMU` |
| `--category movie/tv` | ✅ Existe como alias largo | `-c movie/tv` |
| `--tmdb <id>` | ✅ Existe como alias largo | `-tmdb <id>` |
| `--resolution 1080p` | ✅ Existe como alias largo | `-res 1080p` |
| (no se envía) | — | `-mt <título>` — falta, crítico para nomenclatura |
| (no se envía) | — | `-ua` — falta, obligatorio para no-interactivo |
| (no se fija `stdin`) | — | debería ser `DEVNULL` |

## Comparación con Uploadrr-EMU real

Ver tabla completa de compatibilidad ya construida en la auditoría 10D
(`docs/codex_phase_10d_uploadrr_emu_runtime_audit.md`, sección "Compatibilidad con
`upload_execution.py` actual"). Resumen: arquitectura de ejecución (subprocess, shell=False,
confirmación, logs, resultado por exit-code) correcta; mapeo de flags y `-ua`/`-mt`/`stdin`
son los gaps concretos a cerrar.

## Lógica legacy ya portada

Toda existe **igual, por nombre**, dentro de `emuwarez_uploadrr/legacy.py` (portado tal
cual del script monolítico original), y se reexporta sin cambios vía
`emuwarez_uploadrr/uploadrr_config.py` y `emuwarez_uploadrr/uploadrr_runner.py`:

| Función legacy pedida | Estado | Ubicación |
|---|---|---|
| `uploadrr_dir()` | existe igual | `legacy.py:715` |
| `uploadrr_py()` | existe igual | `legacy.py:722` |
| `uploadrr_config()` | existe igual | `legacy.py:726` |
| `venv_python()` | existe igual | `legacy.py:734` |
| `read_yaml_lines()` | existe igual | `legacy.py:978` |
| `write_yaml_lines()` | existe igual | `legacy.py:984` |
| `set_block_key()` | existe igual | `legacy.py:1021` |
| `set_emu_config()` | existe igual | `legacy.py:1126` |
| `set_watch_folder()` | existe igual | `legacy.py:1195` |
| `set_qbit_config()` | existe igual | `legacy.py:1206` |
| `inject_app_config_into_uploadrr()` | existe igual | `legacy.py:1347` |
| `restore_uploadrr_config_from_backup()` | existe igual | `legacy.py:1335` |
| `register_config_restore_handlers()` | existe igual | `legacy.py:1370` |
| `validate_tmdb()` | existe igual | `legacy.py:1410` |
| `validate_emu()` | existe igual | `legacy.py:1421` |
| `build_uploadrr_command()` (contrato correcto `-tk/-mt/-tmdb/-ua/-c/-res`) | existe igual | `legacy.py:3258` |
| `run_uploadrr_command()` (`cwd=uploadrr_dir()`, `stdin=DEVNULL`, pty) | existe igual | `legacy.py:3868` |

## Lógica legacy no portada

Nada falta *en código* — todo existe igual dentro de `legacy.py`. Lo que falta es
**integración**: ninguna de estas funciones es invocada por `services/upload_execution.py`,
`services/upload_preflight.py`, ni por el pipeline de `upload_jobs` (BD, API, UI). El
propio módulo puente `uploadrr_runner.py` no tiene importadores en todo el árbol —
es código muerto. Portar significa aquí "conectar lo que ya existe al pipeline de jobs",
no "reescribir desde cero".

## Settings existentes

| Setting pedido | Existe | Dónde se almacena | Notas |
|---|---|---|---|
| `uploadrr_path` | ⚠️ con otro nombre | Setup real usa `uploadrr.path` (con punto); `upload_execution.py`/`upload_preflight.py` leen `uploadrr_path` (sin punto) — **mismatch** | Ver Resumen ejecutivo, punto 2 |
| `uploadrr_command` | no existe | — | No hay setting; el comando se reconstruye en runtime |
| `uploadrr_config_path` | no existe | — | — |
| `uploadrr_python_path` | no existe | — | Gap ya señalado en 10D; hoy se usa `sys.executable` |
| `uploadrr_runtime_type` | no existe | — | Gap ya señalado en 10D (`uploadrr_generic`/`uploadrr_emu`) |
| `uploadrr_timeout` | no existe | — | Subprocess sin timeout configurable |
| `uploadrr_allowed_roots` | no existe | — | Solo existe `hardlink_base` (para nomenclatura), no reforzado en el paso de ejecución de subida |
| `uploadrr_output_dir` | no existe | — | — |
| `watch_folder` | solo en `legacy.py`/`AppConfig` | Config YAML propio de Uploadrr, gestionado por CLI legacy | No en settings de la app web |
| `torrent client` (`torrent_client`) | solo en `legacy.py`/`AppConfig` | ídem | No en settings de la app web |
| `qbit_*` (url/port/user/pass/storage/layout/verify) | solo en `legacy.py`/`AppConfig` | ídem | No en settings de la app web |
| Image host settings (`SCREENS.API_KEYS`, imgbb) | solo en `legacy.py` (`get_screen_api_keys`, `imgbb_api_key`) | ídem | No en settings de la app web |
| `emu_anon` | solo en `legacy.py`/`AppConfig` | ídem | No en settings de la app web |

En la app web (`web/services/settings_service.py`) solo existen: `tmdb.api_key`,
`emu.api_key`, `emu.endpoint_url`, `uploadrr.path`, `app.name`, `app.timezone`. Todos los
demás settings de Uploadrr-EMU (venv, torrent client, watch folder, qbit, image hosts,
emu_anon) solo existen en el flujo CLI legacy interactivo que edita el `config.yaml` de
Uploadrr directamente — no están en `SettingsPage`, ni en `.env.example`, ni documentados
para Docker.

## Settings faltantes

`uploadrr_python_path`, `uploadrr_runtime_type`, `uploadrr_timeout`,
`uploadrr_allowed_roots` (o reforzar `hardlink_base` también en el paso final de
ejecución), y decidir si el resto de settings de Uploadrr (torrent client, watch folder,
qbit, image hosts, `emu_anon`) deben exponerse en la app web o seguir siendo
responsabilidad exclusiva del operador editando `config.yaml` directamente (opción
recomendada por 10D, para no duplicar gestión de secretos).

## Docker actual

- **No instala `mediainfo`** ni `mkvtoolnix`/`mkvpropedit` ni `ffmpeg`/`mono`: el
  `Dockerfile` (`RUN apt-get update && apt-get install -y --no-install-recommends \` con
  lista vacía) no añade ningún paquete de sistema.
- No incluye ninguna dependencia de Uploadrr-EMU — filosofía correcta y explícita: Uploadrr
  se monta como bind mount externo, nunca vendorizado.
- `docker-compose.example.yml` monta `/srv/Uploadrr:/opt/Uploadrr:ro` — **contradicción
  confirmada**: Uploadrr-EMU escribe en `<uploadrr_dir>/tmp/<uuid>/` (torrents,
  descripciones, capturas), lo cual fallaría con el mount actual en modo `:ro`.
- Sí hay rutas escribibles: `/config` (BD/settings, `VOLUME ["/config"]`) y `/data`
  (media + hardlink_base). No hay ninguna ruta `tmp/` de Uploadrr montada por separado.
- `.env.example` no contiene ninguna variable relacionada con Uploadrr (solo
  `PUID`/`PGID`/`TZ`/puerto) — coherente con que la config de Uploadrr vive en su propio
  `config.yaml`, no en variables de entorno de nuestra app.

## Modelo actual de progreso/logs

- Estados de `upload_jobs.status`: `draft`/`preflight`/`ready`/`running`/`completed`/
  `failed`/`blocked`/`cancelled` (confirmado en `upload_preflight.py`,
  `upload_execution.py`).
- Logs por streaming en background (hilos `stdout`/`stderr` con secuencia, tabla
  `upload_job_logs`), redactados con `redact_secrets` antes de persistir.
- Artifacts (`upload_artifacts`): `prepared_file`, `uploaded_url`, `torrent_id`.
- **No existe porcentaje ni timeline de fases** — solo `stage` (`running`/`finished`/
  `failed`/`cancelled`), sin granularidad intermedia.
- La UI (`LogsPanel` en `UploadsPage.tsx`) hace **un único fetch al abrir el modal**, sin
  `setInterval` ni polling — para ver progreso en vivo de un job `running` hay que cerrar
  y reabrir el modal manualmente. No hay streaming (SSE/WebSocket) del lado del backend
  tampoco: los endpoints son `GET` puntuales.
- El resultado final si se muestra: `result_url`/`result_torrent_id`/`error_message` en
  el job, visibles en `UploadsPage`/CLI `upload job <id>`.

## Matriz de reutilización

| Componente legacy | Módulo actual equivalente | Estado | Acción recomendada | Riesgo |
|---|---|---|---|---|
| `build_uploadrr_command` (flags correctos `-tk/-mt/-tmdb/-ua/-c/-res`) | `legacy.py:3258`, no conectado | existe pero desconectado | portar el mapeo de flags a `build_uploadrr_execution_command` por `runtime_type` | alto |
| `run_uploadrr_command` (`cwd`, `stdin=DEVNULL`, pty) | `legacy.py:3868`, no conectado | existe pero desconectado | reutilizar `stdin=DEVNULL`; pty opcional (hilos actuales con PIPE ya funcionan) | medio |
| `inject_app_config_into_uploadrr` / `restore_uploadrr_config_from_backup` | ninguno en el pipeline web | existe solo en flujo CLI legacy interactivo | **no portar** — 10D ya recomienda que el operador gestione `config.yaml` fuera de la app; mantener como está | bajo (si se respeta la recomendación) |
| `venv_python()` / gestión de venv | ninguno | no existe en Docker/web | añadir setting `uploadrr_python_path`, sin bootstrap automático de venv | medio |
| Namespace de settings (`uploadrr.path` vs `uploadrr_path`) | `web/services/settings_service.py` vs `services/upload_execution.py` | **bug activo, no documentado hasta ahora** | unificar namespace (recomendado: usar el de puntos ya expuesto en setup/API) antes de tocar flags | alto |
| Ejecución controlada (subprocess, confirmación, logs, artifacts, retry/cancel) | `upload_execution.py` | existe y es sólido | mantener sin rediseño | bajo |
| Progreso/logs UI | `UploadsPage.tsx` / `upload_job_logs` | existe pero sin auto-refresh | opcional, fuera de alcance de 10E (es UX, no contrato) | bajo |
| `allowed_root`/`hardlink_base` en paso final de ejecución | `filesystem_safety.py`/`nomenclature.py` (no invocado en `upload_execution.py`) | existe pero no reforzado en este paso | añadir check explícito antes de construir el comando | medio |

## Riesgos

1. Namespace de settings desalineado (`uploadrr.path` vs `uploadrr_path`) — riesgo alto,
   bloquea todo el flujo de subida en un despliegue real configurado solo vía UI/API, y
   los tests actuales lo enmascaran.
2. Flags CLI incorrectos (`--tracker`/`--category`/`--tmdb`/`--resolution` sin `-ua`/`-mt`)
   — con el comando actual, cualquier ejecución real fallaría con error de argparse o
   quedaría colgada esperando input interactivo (ya documentado en 10D).
3. Mount Docker `:ro` incompatible con la escritura en `tmp/` de Uploadrr-EMU — bloquea
   ejecución real hasta que se resuelva en Fase 10F.
4. Código muerto (`uploadrr_runner.py`, gran parte de `legacy.py`) con la lógica correcta
   pero desconectada — riesgo de que una futura fase reimplemente desde cero lo que ya
   existe, o de que se elimine por error creyendo que no se usa.
5. Sin timeout configurable en el subprocess — una subida real que se cuelgue (p.ej. por
   prompt interactivo sin `-ua`) dejaría el job en `running` indefinidamente.

## Recomendación para Fase 10E

1. Corregir primero el mismatch de namespace de settings (bug activo, no cosmético).
2. Añadir `runtime_type` (`uploadrr_generic`/`uploadrr_emu`) y `uploadrr_python_path` como
   settings nuevos.
3. Reescribir `build_uploadrr_execution_command` para `uploadrr_emu` portando literalmente
   el mapeo de `legacy.py::build_uploadrr_command` (`-tk`, `-mt`, `-tmdb`, `-c`, `-res`,
   `-ua`, `-season`/`-episode`), fijando `stdin=subprocess.DEVNULL`.
4. Añadir timeout configurable al subprocess y el check explícito de `prepared_path`
   dentro de `hardlink_base`/`allowed_root` antes de construir el comando.
5. Tests de regresión: ausencia de secretos en `command_preview`, y namespace de settings
   correcto end-to-end (setup → preflight → ejecución).
6. No ejecutar subida real, no tocar el mount Docker todavía.

## Recomendación para Fase 10F

Ejecución real controlada solo sobre `prepared_path`, con el mount Docker ajustado
(`tmp/` escribible), reutilizando `INICIAR_UPLOADRR`, validando retry/cancel contra un
proceso real de Uploadrr-EMU, en un entorno controlado del propio usuario (nunca en
CI/tests automatizados).

## Validaciones ejecutadas

```
python3 -m py_compile emuwarez_uploader.py                → OK
find emuwarez_uploadrr -name "*.py" | xargs py_compile     → OK (todos compilan)
python3 -m json.tool docs/ui_backend_contract.json         → OK (JSON válido)
pytest -q                                                  → 852 passed, 4 warnings, 172.58s
cd frontend && npm run build                               → OK (tsc + vite build sin errores;
                                                              1 warning benigno de import
                                                              dinámico/estático mixto en
                                                              requestReadiness.ts)
```

No se ejecutó Docker (no requerido, no se intentó). No se ejecutó Uploadrr. No se realizó
ninguna subida real. No se modificó `Uploadrr/` (no existe tal directorio en este repo,
intencionadamente externo).
