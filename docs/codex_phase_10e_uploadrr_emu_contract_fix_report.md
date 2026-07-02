# Fase 10E — Uploadrr-EMU contract fix and safe preflight

Cierra los gaps identificados en la auditoría 10D
(`docs/codex_phase_10d_uploadrr_emu_runtime_audit.md`) y el inventario 10E-0
(`docs/codex_phase_10e0_uploadrr_backend_inventory.md`): flags CLI
incorrectos y mismatch de namespace de settings. **No se ha ejecutado
Uploadrr real, no se ha subido ningún torrent, no se ha tocado `Uploadrr/`
(no existe en este repo, intencionadamente externo), no se ha hecho push.**

## Estado del repo

| Campo | Valor |
|-------|-------|
| Ruta | `~/Descargas/emuwarez_uploadrr/emuwarez_uploadrr_cli_ready_v2` |
| Rama base | `master` (limpia, `d8103ac`, tag `emuwarez-uploadrr-external-api-test-buttons-v0`) |
| Rama de esta fase | `feature/ui-phase-10e-uploadrr-emu-contract-fix` |
| Rama 10D | `feature/ui-phase-10d-uploadrr-emu-runtime-audit` (commit `d4f9dce`), no mezclada — copiado el documento a esta rama |
| Rama 10E-0 | `feature/ui-phase-10e0-uploadrr-backend-inventory` (commit `f12601b`), no mezclada — copiado el documento a esta rama |
| Tests previos | 852 passed (confirmados de nuevo al inicio de esta fase) |
| Tests tras esta fase | 911 passed (852 + 59 nuevos), 0 fallos |

## Bugs corregidos

### 1. Mismatch de namespace de settings (bug activo, no cosmético)

El setup wizard / API (`web/services/setup_service.py`) escribe claves con
puntos (`uploadrr.path`, `tmdb.api_key`, `emu.api_key`), pero
`upload_preflight.py`/`upload_execution.py` leían únicamente las claves con
guion bajo (`uploadrr_path`, `tmdb_api_key`, `emu_api_key`). Tras un setup
real vía UI, el pipeline de subida reportaba "no configurado"
indefinidamente. Los tests existentes no lo detectaban porque sus fixtures
insertaban directamente la clave con guion bajo, replicando el bug en vez de
exponerlo.

**Corrección:** `database.get_setting_canonical(conn, dotted_key, default)`
(`emuwarez_uploadrr/database.py`) resuelve la clave dotted y, si no existe o
está vacía, cae automáticamente a su alias legacy (tabla
`CANONICAL_SETTING_ALIASES`). La clave dotted gana siempre si ambas existen.
Expuesto también como wrapper en `web/services/settings_service.py`
(`get_setting_canonical`, `set_setting_canonical`, `get_secret_setting`,
`set_secret_setting`), y usado en `upload_preflight.py`,
`upload_execution.py` y `services/uploadrr_contract.py`. `get_configured()` y
`get_settings_status()` también se corrigieron para usar la resolución
canónica (antes, `get_settings_status()` podía reportar `configured=true`
pero `masked_value=None` si solo existía la clave legacy).

### 2. Flags CLI incorrectos para Uploadrr-EMU

`build_uploadrr_execution_command` (`upload_execution.py`) y
`build_uploadrr_command_preview` (`upload_preflight.py`) construían
`--tracker EMU --category ... --tmdb ... --resolution ...` — flags que **no
existen** en el CLI real de Uploadrr-EMU (`--tracker` singular no existe; es
`-tk`/`--trackers` plural). Faltaban `-mt` (título forzado) y `-ua`
(no-interactivo), y no se fijaba `stdin` explícito.

**Corrección:** nuevo módulo `emuwarez_uploadrr/services/uploadrr_contract.py`
con `build_uploadrr_emu_command(...)`, que construye exactamente:

```bash
<python_path> <uploadrr_path>/upload.py <prepared_path> \
  -tk EMU -mt "<título>" -tmdb <id> -ua -c movie|tv -res <resolución> \
  [-season Sxx] [-episode Exx]
```

Este mapeo es el mismo que ya existía, correcto pero desconectado, en
`emuwarez_uploadrr/legacy.py::build_uploadrr_command` (línea 3258) —
**no se reescribió desde cero**, se portó el contrato de flags a un servicio
moderno y se conectó a `upload_preflight.py`/`upload_execution.py` según
`runtime_type`.

**Flags eliminados del runtime `uploadrr_emu`:** `--tracker`, `--category`,
`--resolution` (siguen existiendo, sin cambios, para el runtime
`uploadrr_generic`, mantenido como perfil best-effort para forks
desconocidos — no validado contra un contrato real).

Ejemplo de `command_preview` real generado end-to-end (capturado del E2E
Docker de esta fase, `scripts/docker-e2e-demo.sh`):

```text
/usr/local/bin/python /path/to/Uploadrr/upload.py "/data/media/movies/Demo Movie (2024)/Demo Movie (2024) WEBDL-1080p.mkv" -tk EMU -mt "Demo Movie" -tmdb tt0000001 -ua -c movie -res 1080p
```

## Settings añadidas (con defaults idempotentes)

| Setting | Default | Notas |
|---|---|---|
| `uploadrr.runtime_type` | `uploadrr_emu` | Acepta `uploadrr_generic`/`uploadrr_emu`. |
| `uploadrr.python_path` | `/usr/local/bin/python` | Asume imagen Docker; en host/manual debe apuntar al venv real de Uploadrr-EMU. **Ya no se usa `sys.executable`** (el Python del backend), que era el bug original de 10D. |
| `uploadrr.timeout` | `7200` (segundos) | Aplicado al subproceso de ejecución real (ver más abajo). |
| `uploadrr.allowed_roots` | `[]` (JSON) | Vacío → usa `hardlink_base` como fallback (`services/uploadrr_contract.py::get_allowed_roots`). |

Todas se leen con fallback legacy automático (`uploadrr_runtime_type`,
`uploadrr_python_path`, `uploadrr_timeout`, `uploadrr_allowed_roots`), igual
que el resto del namespace.

## Command builder final (`services/uploadrr_contract.py`)

- `build_uploadrr_emu_command(...)` → `list[str]`, nunca string de shell.
  Solo acepta `prepared_path` (no existe parámetro `source_path` en la
  firma — estructuralmente no se puede pasar el archivo original por error).
- `validate_uploadrr_emu_contract(...)` → valida `prepared_path` dentro de
  `allowed_roots`, `torrent_name` no vacío, `category` en `movie|tv`,
  `python_path` y `uploadrr_script_path` existentes en disco. Nunca ejecuta
  nada.
- `path_within_allowed_roots(path, roots)` → reutiliza
  `filesystem_apply.ensure_path_under_base` (ya usado para `hardlink_base`
  en nomenclatura) — protección de path traversal incluida (`Path.resolve()`
  + `relative_to`). `roots` vacío nunca concede acceso.
- `redact_uploadrr_command(...)` / `render_command_preview(...)` — segunda
  capa de redacción (Uploadrr-EMU nunca recibe API keys por CLI; esto cubre
  el caso de que un secreto acabe, por error, en otro campo como
  `torrent_name`).

`upload_preflight.py::build_uploadrr_command_preview` expone, para
`runtime_type=uploadrr_emu`: `runtime_type`, `command_args`,
`command_preview`, `contract_valid`, `contract_errors`, `contract_warnings`,
`can_execute` (**siempre `false`** en esta fase), `requires_confirmation`
(`INICIAR_UPLOADRR`), `safe_to_execute` (**siempre `false`**).

`upload_execution.py::build_uploadrr_execution_command` usa el mismo
builder para la ejecución real (todavía no habilitada end-to-end contra un
proceso real — ver gaps), fijando `stdin=subprocess.DEVNULL` explícito
(antes no se fijaba) y aplicando el timeout configurable: si el proceso no
termina en `uploadrr.timeout` segundos, se le envía `kill()` y el job pasa a
`status=failed`, `stage=timeout`.

## Config staging (`services/uploadrr_config_staging.py`)

Servicio nuevo para preparar cambios en `Uploadrr/data/config.yaml` sin
tocar nunca una instalación real: toda función recibe un `config_path: Path`
explícito (en tests, siempre `tmp_path`). Reutiliza los helpers puros ya
existentes en `legacy.py` (`set_block_key`, `set_emu_config`,
`get_block_key`, `yaml_scalar` — operan solo sobre `lines: list[str]`, sin
I/O) en vez de reescribirlos.

Funciones: `read_config_lines`, `backup_config` (crea `.bak` si no existe,
nunca lo sobrescribe), `restore_config_from_backup`, `write_staged_config`
(backup automático antes de escribir), `stage_tmdb_key` (`DEFAULT.tmdb`),
`stage_emu_config` (`TRACKERS.EMU.api_key`/`anon`), `build_redacted_preview`
y `diff_staged_changes` (diff unificado con secretos redactados a un hash
corto no reversible — así el diff muestra que hubo un cambio sin revelar
ninguno de los dos valores).

No se implementó el resto de campos del encargo original (`SCREENS.*`,
`TORRENT_CLIENTS.*`, `emu_anon` fuera del bloque EMU) — la auditoría 10D ya
recomendaba que esos siguan siendo responsabilidad exclusiva del operador
editando `config.yaml` directamente, para no duplicar gestión de secretos;
se documenta como alcance pendiente, no como omisión.

## Allowed roots / protección de `source_path`

- `prepared_path` dentro de `allowed_roots` → contrato válido.
- `prepared_path` fuera de `allowed_roots` → `contract_valid=false`,
  error explícito.
- Si no se ha aplicado nomenclatura (solo existe el `path` original) y ese
  path está fuera de `allowed_roots`, también bloquea — cubre el caso
  "source_path pasado por error", ya que el builder nunca distingue un
  `source_path` con privilegios especiales: cualquier ruta pasa por el mismo
  chequeo de `allowed_roots`.
- Path traversal bloqueado por `Path.resolve()` + `relative_to()` (ya
  existente en `filesystem_apply.ensure_path_under_base`, reutilizado sin
  duplicar).
- `allowed_roots` vacío (sin configurar ni `uploadrr.allowed_roots` ni
  `hardlink_base`) nunca concede acceso implícito.

## UI

`UploadPreflightModal.tsx`: nueva fila "Runtime" con badge de
contrato válido/inválido, y bloques de "Errores/Avisos de contrato
Uploadrr-EMU" cuando `contract_valid=false` o hay `contract_warnings`. Sin
progreso/timeline avanzado (fuera de alcance, ver gaps). `types/api.ts` y
`web/schemas.py` (`CommandPreviewResponse`) ampliados con los mismos campos
nuevos del backend.

## Tests ejecutados

Nuevos (59 tests):

- `tests/test_uploadrr_contract.py` (28) — command builder, flags,
  season/episode, redacción, `path_within_allowed_roots`,
  `validate_uploadrr_emu_contract`.
- `tests/test_uploadrr_settings_namespace.py` (9) — dotted gana sobre
  legacy, legacy sigue funcionando solo, setup real → pipeline lee
  correctamente, end-to-end con `validate_upload_job_start`.
- `tests/test_uploadrr_emu_preflight.py` (8) — flags reales en el preview,
  bloqueo por `allowed_roots`, bloqueo usando el `path` original sin
  preparar, `python_path`/script faltantes, `can_execute`/`safe_to_execute`
  siempre `false`, sin secretos en el preview.
- `tests/test_uploadrr_config_staging.py` (14) — backup/restore, staging en
  memoria, redacción determinista en preview/diff, nunca toca una ruta real
  de Uploadrr (guardia estructural sobre el propio código fuente del
  módulo).

Ningún test ejecuta subprocess real ni usa `shell=True`.

## Resultado de validaciones

```
python3 -m py_compile emuwarez_uploader.py                → OK
find emuwarez_uploadrr -name "*.py" | xargs py_compile     → OK
python3 -m json.tool docs/ui_backend_contract.json         → OK
emuwarez_uploader.py --help/db init/web-contract/web info/
  web setup-status/web doctor/nomenclature sources/providers → OK (exit 0)
pytest -q                                                  → 911 passed, 4 warnings, ~186s
cd frontend && npm run build                               → OK (tsc + vite build; mismo
                                                              warning benigno preexistente
                                                              de import dinámico/estático
                                                              mixto en requestReadiness.ts)
docker build -t emuwarez-uploadrr:phase-10e .              → OK
docker compose -f docker-compose.example.yml config        → OK
bash scripts/docker-smoke-test.sh                          → PASADO (8 OK, 0 FAIL)
bash scripts/docker-e2e-demo.sh                            → PASSED (25 OK, 0 FAIL) —
  incluye la captura real de "Comando previsto" con los flags correctos
  (-tk/-mt/-tmdb/-ua/-c/-res), confirmando el fix end-to-end en un
  contenedor real, no solo en tests unitarios.
```

## Confirmaciones de seguridad

- No se ejecutó Uploadrr real en ningún momento de esta fase.
- No se subió ningún torrent ni se hizo login real contra eMuwarez.
- `Uploadrr/` no fue tocado (no existe en este repo, es intencionadamente
  externo/bind-mount).
- El command builder nunca usa `shell=True`; `stdin=subprocess.DEVNULL`
  fijado explícitamente.
- Ningún test invoca `subprocess.Popen`/`.run` real (todo mockeado donde
  aplica).
- No se hizo `git push`.

## Gaps restantes

1. **Ejecución real controlada (Fase 10F):** el contrato de flags ya es
   correcto y se generó/verificó end-to-end en Docker, pero nunca se ha
   ejecutado contra un proceso real de Uploadrr-EMU. Esta fase no añadió un
   bloqueo arquitectónico nuevo sobre `start_upload_job` para
   `runtime_type=uploadrr_emu` más allá del ya existente (confirmación
   `INICIAR_UPLOADRR` + `validate_upload_job_start`) — añadir uno hubiera
   requerido actualizar fixtures de tests preexistentes (6C/6D) sin
   necesidad real, dado que ninguna ejecución real ocurre hasta 10F.
2. **Mount Docker `:ro`:** sigue siendo incompatible con la escritura real
   de Uploadrr-EMU en `tmp/` — documentado en `DEPLOYMENT_DOCKER.md`
   (sección 7b), sin cambios de código en esta fase (explícitamente fuera
   de alcance).
3. **SettingsPage sin exponer los settings nuevos:** `uploadrr.runtime_type`
   /`python_path`/`timeout`/`allowed_roots` solo son configurables vía
   API/CLI directa a la tabla `settings` o el setup wizard (`uploadrr.path`
   únicamente) — no hay formulario dedicado en el frontend. Se dejó fuera
   por complejidad/tiempo, tal como permite el encargo ("si complica
   demasiado, dejar para fase posterior").
4. **Config staging incompleto:** solo `DEFAULT.tmdb` y `TRACKERS.EMU.*`
   portados con tests; el resto de bloques de `config.yaml`
   (`SCREENS`, `TORRENT_CLIENTS`, `emu_anon`) siguen sin superficie en la
   app web, por diseño (ver sección Config staging).
5. **Progreso/timeline de subida:** sigue sin polling/streaming — fuera de
   alcance de 10E (es UX, no contrato).

## Siguiente fase propuesta

**Fase 10F — Controlled Uploadrr-EMU execution**: ejecución real solo sobre
`prepared_path`, ajuste del mount Docker (`tmp/` escribible), validación de
retry/cancel contra un proceso real de Uploadrr-EMU, en un entorno
controlado del propio usuario (nunca en CI/tests automatizados).
