# Checkpoint — Uploadrr EMU contract and safe preflight (v0)

Checkpoint de integración de la Fase 10E: valida, mergea a `master` y tagea
el milestone. **No se implementó ninguna funcionalidad nueva en este
checkpoint** — solo validación, merge y documentación. No se modificó
`Uploadrr/`, no se ejecutó Uploadrr real, no hubo subida real, no se hizo
push.

## Rama y commits

| Campo | Valor |
|---|---|
| Rama de feature | `feature/ui-phase-10e-uploadrr-emu-contract-fix` |
| Commit de Fase 10E | `98f15a5` — "fix: align Uploadrr EMU contract and settings" |
| Rama destino | `master` |
| Commit base (master antes del merge) | `d8103ac` (tag `emuwarez-uploadrr-external-api-test-buttons-v0`) |
| Merge commit | `f94b5e7` — "merge: Uploadrr EMU contract and safe preflight milestone" (`--no-ff`, sin conflictos) |
| Tag creado | `emuwarez-uploadrr-uploadrr-emu-contract-preflight-v0` (sobre `f94b5e7`) |

## Validaciones ejecutadas (antes y después del merge)

Ambas rondas (en `feature/ui-phase-10e-uploadrr-emu-contract-fix` y de nuevo
en `master` tras el merge) dieron el mismo resultado:

```
python3 -m py_compile emuwarez_uploader.py                → OK
find emuwarez_uploadrr -name "*.py" | xargs py_compile     → OK (todos compilan)
python3 -m json.tool docs/ui_backend_contract.json         → OK (JSON válido)

emuwarez_uploader.py --help                                → exit 0
emuwarez_uploader.py db init                                → exit 0
emuwarez_uploader.py web-contract                           → exit 0
emuwarez_uploader.py web info                               → exit 0
emuwarez_uploader.py web setup-status                       → exit 0
emuwarez_uploader.py web doctor                             → exit 0
emuwarez_uploader.py nomenclature sources                   → exit 0
emuwarez_uploader.py nomenclature providers                 → exit 0

pytest -q                                                   → 911 passed, 4 warnings
                                                                (pre-merge: 179.12s; post-merge: 159.36s)

cd frontend && npm install && npm run build                → OK (tsc + vite build;
                                                                único warning benigno preexistente
                                                                de import dinámico/estático mixto
                                                                en requestReadiness.ts)

docker build -t emuwarez-uploadrr:checkpoint-10e .          → OK (pre-merge y post-merge)
docker compose -f docker-compose.example.yml config         → OK
bash scripts/docker-smoke-test.sh                            → PASADO — 8 OK, 0 FAIL (ambas rondas)
bash scripts/docker-e2e-demo.sh                               → PASSED — 25 OK, 0 FAIL (ambas rondas)
```

Docker estuvo disponible en todo momento (daemon reachable, build funcionó
sin intervención). No hubo fallos en ninguna validación; por eso se procedió
con el merge.

## Bugs corregidos (Fase 10E, confirmados en este checkpoint)

1. **Namespace de settings desalineado.** El setup wizard/UI escribía claves
   dotted (`uploadrr.path`, `tmdb.api_key`, `emu.api_key`) mientras el
   pipeline de subida solo leía las claves legacy con guion bajo
   (`uploadrr_path`, `tmdb_api_key`, `emu_api_key`), dejando el flujo de
   subida bloqueado indefinidamente tras un setup real vía UI.
2. **Flags CLI incompatibles con Uploadrr-EMU real.** Se construía
   `--tracker`/`--category`/`--resolution` — flags que no existen (o no
   coinciden) en el CLI real, sin `-mt`/`-ua`, sin `stdin` fijado.

## Settings namespace fix

`emuwarez_uploadrr/database.py::get_setting_canonical(conn, dotted_key, default)`
resuelve la clave dotted primero; si está vacía o ausente, cae al alias
legacy (`CANONICAL_SETTING_ALIASES`). **La clave dotted gana siempre** si
ambas existen. Expuesto también en `web/services/settings_service.py`
(`get_setting_canonical`, `set_setting_canonical`, `get_secret_setting`,
`set_secret_setting`) y usado por `upload_preflight.py`,
`upload_execution.py` y `services/uploadrr_contract.py`.

## Settings nuevas (con defaults idempotentes)

| Setting | Default |
|---|---|
| `uploadrr.runtime_type` | `uploadrr_emu` (alternativa: `uploadrr_generic`) |
| `uploadrr.python_path` | `/usr/local/bin/python` (pensado para Docker; sobrescribir en host/manual) |
| `uploadrr.timeout` | `7200` segundos |
| `uploadrr.allowed_roots` | `[]` (vacío → usa `hardlink_base` como fallback) |

## Command builder final

`emuwarez_uploadrr/services/uploadrr_contract.py::build_uploadrr_emu_command(...)`
construye:

```bash
<python_path> <uploadrr_path>/upload.py <prepared_path> \
  -tk EMU -mt "<torrent_name>" -tmdb <id> -ua -c movie|tv -res <resolution> \
  [-season Sxx] [-episode Exx]
```

Confirmado en el código (`grep` sobre `uploadrr_contract.py`): usa
`"-tk", "EMU"`, `"-mt", torrent_name`, `"-tmdb"`, `"-ua"`, `"-c"`, `"-res"` —
y **ninguno** de los flags antiguos (`--tracker`/`--category`/`--resolution`)
para el runtime `uploadrr_emu`. El runtime `uploadrr_generic` conserva el
mapeo best-effort anterior, sin validar contra un contrato real, para forks
desconocidos.

### Ejemplo real de `command_preview` (capturado del E2E Docker de esta fase)

```text
/usr/local/bin/python /path/to/Uploadrr/upload.py "/data/media/movies/Demo Movie (2024)/Demo Movie (2024) WEBDL-1080p.mkv" -tk EMU -mt "Demo Movie" -tmdb tt0000001 -ua -c movie -res 1080p
```

## Config staging

`emuwarez_uploadrr/services/uploadrr_config_staging.py` — staging en memoria
de `Uploadrr/data/config.yaml` (`DEFAULT.tmdb`, `TRACKERS.EMU.api_key/anon`)
con backup automático antes de escribir, restauración desde backup, y
diff/preview con secretos redactados a un hash corto no reversible. Reutiliza
los helpers puros ya existentes en `legacy.py` (`set_block_key`,
`set_emu_config`, etc.) — nunca toca una instalación real de Uploadrr/, todas
las funciones reciben un `config_path: Path` explícito (`tmp_path` en tests).

## Protección allowed_roots / source_path / path traversal

- `path_within_allowed_roots(path, roots)` — reutiliza
  `filesystem_apply.ensure_path_under_base` (`Path.resolve()` +
  `relative_to()`), ya usado para `hardlink_base` en nomenclatura.
- `prepared_path` dentro de `allowed_roots` → contrato válido.
- `prepared_path` fuera de `allowed_roots` → `contract_valid=false` con
  error explícito.
- El uso del `path` original sin nomenclatura aplicada pasa por el mismo
  chequeo — no hay privilegio especial para `source_path` en el builder
  (su firma ni siquiera acepta ese parámetro).
- `allowed_roots` vacío nunca concede acceso implícito.

## UI

`UploadPreflightModal.tsx`: fila "Runtime" con badge de contrato
válido/inválido, y bloques de errores/avisos de contrato Uploadrr-EMU
cuando `contract_valid=false` o hay `contract_warnings`. `types/api.ts` y
`web/schemas.py::CommandPreviewResponse` ampliados con los mismos campos.

## Garantías de seguridad

- No se ejecutó Uploadrr real en ningún momento (ni en la Fase 10E ni en
  este checkpoint).
- No se subió ningún torrent ni se hizo login real contra eMuwarez.
- `Uploadrr/` no fue tocado (no existe en este repo, es intencionadamente
  externo/bind-mount) — confirmado también por los checks de seguridad de
  los scripts de smoke/E2E ("Uploadrr/ no está dentro de la imagen").
- El command builder nunca usa `shell=True`; `stdin=subprocess.DEVNULL`
  fijado explícitamente.
- Ningún test invoca `subprocess.Popen`/`.run` real.
- Merge sin conflictos (`git merge --no-ff`, resuelto automáticamente por
  `ort`).
- No se hizo `git push` en ningún momento.

## Gaps restantes (heredados de la Fase 10E, sin cambios en este checkpoint)

- **Ejecución real controlada** de Uploadrr-EMU queda para la Fase 10F.
- **Progreso/timeline UI avanzado** (polling/streaming de logs) pendiente.
- **Mount Docker `:ro`** de Uploadrr sigue siendo incompatible con la
  escritura real en `tmp/` — deberá ajustarse en la Fase 10F.
- **SettingsPage** todavía no expone formulario para
  `uploadrr.runtime_type`/`python_path`/`timeout`/`allowed_roots` (solo
  configurables vía API/CLI/setup wizard).
- **Dependencia/runtime final de Uploadrr-EMU** (venv, versión de Python,
  instalación de `requirements.txt` del fork) pendiente de decisión de
  despliegue — fuera del alcance de este proyecto per se, es responsabilidad
  del operador.

## Estado final

```
Rama:            master
Merge commit:    f94b5e7
Tag:             emuwarez-uploadrr-uploadrr-emu-contract-preflight-v0
git status:      limpio (tras este commit de checkpoint)
Sin push.
```
