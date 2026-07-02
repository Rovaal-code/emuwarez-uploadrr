# Fase 10D Audit — Uploadrr-EMU Runtime Contract

## Estado del repo principal

| Campo | Valor |
|-------|-------|
| Ruta | `~/Descargas/emuwarez_uploadrr/emuwarez_uploadrr_cli_ready_v2` |
| Rama base | `master` (limpia, `d8103ac`) |
| Rama de auditoría | `feature/ui-phase-10d-uploadrr-emu-runtime-audit` |
| Última fase completada | 10C (`emuwarez-uploadrr-external-api-test-buttons-v0`) |
| Tests previos | 852 passed, 0 failed |

Esta fase **no modifica código funcional** del repo principal. Solo añade este documento de auditoría.

## Estado del fork auditado

| Campo | Valor |
|-------|-------|
| URL | `https://codeberg.org/ccx94/Uploadrr-EMU.git` |
| Clonado en | `/tmp/uploadrr-emu-audit` (fuera del repo principal, `--depth 1`) |
| Rama por defecto | `main` |
| Commit único | `a268edf` — "Subir archivos a "/"" (2026-05-01), autor `ccx94` |
| Historia git | **Un solo commit "flatten"**, sin ancestro común con el upstream. No es posible hacer `git diff` contra Upload-Assistant/Uploadrr original desde este clon. |
| Origen declarado | `pyproject.toml`: `name = "uploadrr"`, `version = "2.0.0"`, "Forked from L4G" (Upload-Assistant, vía Uploadrr de CvT) |
| Working tree tras clonar | Limpio, sin cambios, sin push realizado |

No se ejecutó ningún comando de Uploadrr-EMU, ni `npm install`, ni `pip install`. Solo lectura de ficheros (`find`, `grep`, `cat`/Read).

## Estructura del fork

146 ficheros (excluyendo `.git`). Piezas relevantes:

```
upload.py                          # entry point CLI real de Uploadrr
src/args.py                        # ~500 líneas, define TODOS los flags CLI
src/trackers/EMU.py                # tracker específico eMuwarez (extiende UNIT3D)
src/trackers/UNIT3D.py             # base común UNIT3D: upload()/search_existing()
src/trackers/*.py                  # ~50 trackers más (BLU, HDB, PTP, ANT, etc.)
src/utils/config.py                # load_yaml_config() — YAML puro, sin env vars
src/utils/redact.py                # Redactrr — redacción automática de secretos en consola/logs
src/utils/checks.py                # pre_upload_checks (dupe-check, etc.)
src/utils/upload.py                # upload_to_trackers()
src/prep.py, src/mediainfo.py      # análisis de medios (mediainfo, mkv, BDInfo)
src/screenshots/                   # generación/subida de capturas
data/config.yaml, config.yaml.bak  # config activa TRACKEADA EN GIT (ver riesgos)
data/backup/example_config.yaml    # plantilla de config
data/cookies/                      # cookies para trackers que las requieren (no EMU)
discordbot.py, cogs/commands.py    # bot de Discord opcional, no relevante para esta integración
bin/BDInfo/*.exe, *.dll            # binarios Windows para discos BluRay (no aplica a nuestro flujo)
Dockerfile                         # Alpine + mono + ffmpeg + mediainfo + mktorrent
```

No hay `.env.example`, ni `docker-compose*`, ni `requirements-dev`. Un único `Dockerfile`.

## Tipo de proyecto

Uploadrr-EMU es un **fork personal de Uploadrr** (a su vez fork de [Upload-Assistant](https://github.com/L4GSP1KE/Upload-Assistant)): una **herramienta CLI en Python (asyncio)** para preparar y subir torrents a trackers privados basados en UNIT3D (entre ellos, un tracker `EMU` específico para eMuwarez). No es un servicio HTTP ni un daemon: se invoca por proceso una vez por subida y termina.

Incluye además un bot de Discord opcional (`discordbot.py`) para lanzar subidas por comando de chat — no relevante para la integración con nuestra app web, que hablaría directamente con `upload.py`.

## Cómo se configura Uploadrr-EMU

- **Un único fichero YAML**: `data/config.yaml` (sin soporte de variables de entorno — confirmado, no hay `os.environ`/`getenv` en `src/utils/config.py`, `src/args.py` ni `upload.py`).
- Secciones relevantes: `DEFAULT.tmdb` (API key TMDb), `TRACKERS.EMU.api_key` / `TRACKERS.EMU.anon`, `SCREENS.API_KEYS.*` (hosts de imágenes), `TORRENT_CLIENTS.watch.watch_folder` o `TORRENT_CLIENTS.qbit.*`.
- **Riesgo de configuración detectado**: `data/config.yaml` y `data/config.yaml.bak` están **trackeados en git** en el fork (`git ls-files data/` los lista), pese a que el propio `.gitignore` del fork los excluye (`data/config.yaml` aparece en `.gitignore` pero sigue commiteado — se añadió antes de la regla o con `git add -f`). Actualmente solo contienen placeholders (`TMDB_API_KEY`, `EMU_API_KEY`), no secretos reales, pero es un patrón peligroso: si el operador rellena el YAML con claves reales y hace `git push` sin comprobar `git status`, las subiría en claro a un repo público de Codeberg. **No se debe reutilizar el `config.yaml` del fork clonado como base — debe generarse uno propio, fuera de control de versiones, en el despliegue.**

## Cómo se ejecuta Uploadrr-EMU

```bash
python upload.py [flags] <ruta_a_media>
```

- Entry point real: `upload.py` (raíz del repo), no un script `bin/`.
- No hay modo servidor/daemon ni API HTTP propia expuesta por Uploadrr-EMU.
- `cwd` importa: escribe en `<uploadrr_dir>/tmp/<uuid>/` (torrents, descripciones, MediaInfo) — confirmado en `src/prep.py:44` y `src/utils/torrentman.py:417`.
- No existe un flag `--dry-run` nativo en `upload.py`/`src/args.py`. El dry-run solo existe en el wrapper externo `emuwarez-auto-uploader_v1.0.py` (ver más abajo), que simplemente **no construye ni lanza el subprocess** cuando `--dry-run` está activo.
- Sí existe modo no interactivo: `-ua` / `--unattended` ("Run without interactive prompts"). Sin este flag, Uploadrr puede hacer preguntas por `input()`/prompts interactivos.

## Comandos detectados

### CLI real de `upload.py` (`src/args.py`)

Flags relevantes para nuestra integración (formato corto, todos con alias largo):

| Flag | Alias largo | Tipo | Notas |
|------|-------------|------|-------|
| posicional | — | path(s) | ruta de fichero/carpeta a subir |
| `-tk` | `--trackers` | `nargs="*"` | **plural**, lista de trackers (p.ej. `-tk EMU`) |
| `-c` | `--category` | choices `movie/tv/fanres/sports/music` | |
| `-t` | `--type` | choices `disc/remux/encode/webdl/web-dl/webrip/hdtv` | tipo de release |
| `--source` | — | choices `Blu-ray/BluRay/DVD/HDDVD/WEB/HDTV/UHDTV` | |
| `-res` | `--resolution` | choices `2160p/1080p/.../other` | |
| `-tmdb` | `--tmdb` | `nargs="*"` | ID TMDb, p.ej. `movie/12345` o `12345` |
| `-imdb` | `--imdb` | `nargs="*"` | |
| `-mt` | `--manual-title` | `nargs="*"` | fuerza el nombre final (crítico para nomenclatura EMU) |
| `-g` | `--tag` | str | tag de grupo (release tag) |
| `-season` / `-episode` | `--season`/`--episode` | str | `S02`, `E05` |
| `-ua` | `--unattended` | flag | sin prompts interactivos |
| `-D` / `-DD` | `--debug`/`--deep-debug` | flag | logging |
| `-ns` | `--no-seed` | flag | no añade el torrent al cliente configurado |
| `-sdc` | `--skip-dupe-check` | flag | omite comprobación de duplicados |
| `-fd` | `--full-dir` | flag | sube carpeta completa |

**No existe** `--tracker` (singular), ni `--category`/`--tmdb`/`--resolution` como únicos alias largos sin el flag corto — sí existen como alias largos, pero el nombre del argumento real que hay que emitir en `sys.argv` debe coincidir exactamente (`--trackers`, no `--tracker`).

### Wrapper opcional `emuwarez-auto-uploader_v1.0.py` (en el mismo repo del fork, ~4400 líneas)

No es parte de Uploadrr-EMU en sí — es un script adicional del mismo autor que orquesta todo el flujo manual: crea su propio venv, instala dependencias de Uploadrr, gestiona su propia config (`~/.config/emuwarez-renamer/config.json` o cifrada con scrypt+HMAC), **inyecta temporalmente** claves en `Uploadrr/data/config.yaml` (con backup/restore vía `atexit`/`signal`), analiza MediaInfo, busca en TMDb, y finalmente construye y ejecuta:

```python
cmd = [venv_python, uploadrr_py, str(target), "-tk", "EMU", "-mt", title,
       "-tmdb", tmdb_arg, "-ua", "-c", "movie"|"tv", "-res", resolution]
# + ["-season", "S02"] / ["-episode", "E05"] si aplica
```

Es un ejemplo real y funcional de cómo invocar `upload.py` de forma no interactiva para EMU: confirma `-tk EMU`, `-mt <título>`, `-tmdb <id>`, `-ua`, `-c`, `-res`. Se ejecuta con `subprocess.Popen(cmd, cwd=uploadrr_dir(), stdin=DEVNULL, stdout=pty, stderr=pty, env=...)` — sin `shell=True`, con `cwd` fijado al directorio de Uploadrr, y usa una pty para capturar el output (necesario porque `rich`/progreso interactivo cambia de comportamiento según tty).

Este wrapper **no debe copiarse ni ejecutarse** — es solo una referencia útil de contrato CLI real observado en producción por el propio autor del fork.

## Variables de entorno detectadas

**Ninguna.** Ni `upload.py`, ni `src/args.py`, ni `src/utils/config.py` leen `os.environ`. Toda la configuración es vía `data/config.yaml`. (El wrapper opcional sí usa variables de entorno propias — `CONFIG_DIR`-style — pero eso es del wrapper, no de Uploadrr-EMU.)

## Ficheros de configuración detectados

- `data/config.yaml` — activo, cargado por `upload.py` vía `yaml.safe_load`. Si no existe, `upload.py` aborta con `sys.exit(1)` ("No Config detected").
- `data/config.py` / legado — si `config.yaml` no existe pero sí `config.py`, aborta pidiendo migrar a YAML.
- `data/backup/example_config.yaml` — plantilla de referencia.
- `data/cookies/*` — solo para trackers que requieren sesión de navegador (p.ej. PTP); **EMU/UNIT3D no los usa**, autentica por `api_token`.

## Dependencias detectadas

- Python **3.9+** (recomendado 3.11 según wrapper), `asyncio`.
- Sistema: **ffmpeg**, **mediainfo**, **mono** (solo BDInfo, no aplica a WEB-DL/streaming que es el caso típico eMuwarez).
- `requirements.txt`: 27 paquetes (httpx, pymediainfo, guessit, torf, qbittorrent-api, deluge-client, rich, pyyaml, pillow, etc.). Sin versiones fijadas (sin pins), lo que es un riesgo de reproducibilidad menor.
- `pyproject.toml` declara `dependencies = []` (vacío) — la gestión real de dependencias es vía `requirements.txt`, no vía el paquete instalable.

## Entradas requeridas

Para una subida EMU mínima viable (según el wrapper y `src/args.py`):

- Ruta al fichero/carpeta preparado (positional).
- `-tk EMU`
- `-mt <título final ya validado>` (evita que Uploadrr regenere el nombre con su propio `name.py`)
- `-tmdb <id>` (o `-imdb`)
- `-c movie|tv`
- `-res <resolución>`
- `-ua` (obligatorio para uso no interactivo)
- Opcional: `-season`/`-episode` para packs de temporada/episodio.
- La API key de EMU **no se pasa por CLI**: vive en `config.yaml` → `TRACKERS.EMU.api_key`, leída internamente por `src/trackers/UNIT3D.py:211`.

## Salidas/logs detectados

- Salida por **stdout/stderr** con formato `rich` (colores/progreso si hay tty; texto plano si no — `rich` detecta automáticamente ausencia de tty).
- **Redacción propia integrada**: `upload.py:main()` instancia un `Redactrr` (`src/utils/redact.py`) que carga automáticamente como secretas las claves de config que contengan `api_key`, `password`, `token`, `pid`, etc., y también redacta rutas (`base_dir`, `$HOME`) en logs/tracebacks. Esto es una defensa adicional útil, pero **no debe ser la única capa de redacción** en nuestro lado (no cubre argumentos de `sys.argv` explícitamente, solo el logger interno).
- No hay fichero de log dedicado por defecto — todo va a stdout/stderr salvo que `-D`/`-DD` cambien el nivel.
- Artefactos generados: torrent (`.torrent`) en el `watch_folder`/cliente configurado (externo a Uploadrr, según `TORRENT_CLIENTS`); descripción `[EMU]DESCRIPTION.txt` y capturas bajo `<uploadrr_dir>/tmp/<uuid>/`.

## Señales de éxito/error

- **Sin contrato JSON de salida.** El éxito/fracaso se infiere de:
  - **Exit code del proceso** (0 = éxito, la señal más fiable).
  - Cadenas de texto en stdout (heurísticas observadas en el wrapper): `"Rejected Upload"`, `"Validation Error"`, `'"success":false'` → fallo; `"Torrent uploaded successfully"`, `"Uploaded successfully"`, `"Upload complete"` → éxito.
  - URLs de la subida y IDs de torrent, si aparecen en el texto de salida (sin formato fijo garantizado).
- `src/trackers/UNIT3D.py:upload()` devuelve `bool` internamente, pero eso es interno a la librería — no se traduce en un JSON de salida por stdout de forma garantizada; el exit code del proceso completo (`upload.py`) es la señal contractual más sólida.

## Riesgos detectados

1. **Contrato CLI asumido por la app principal está desalineado con el real.** `upload_execution.py`/`upload_preflight.py` construyen `--tracker EMU --category ... --tmdb ... --resolution ...` (flags largos, `--tracker` singular). El CLI real de Uploadrr-EMU usa `-tk/--trackers` (plural, `nargs="*"`), y no tiene ningún flag `--tracker` singular. **Con el comando actual, la ejecución real fallaría con error de argparse** (unrecognized arguments) — ver sección de compatibilidad.
2. **Falta `-ua`/`--unattended` y `-mt`/`--manual-title` en el comando construido por la app.** Sin `-ua`, Uploadrr puede intentar prompts interactivos (`input()`); como `_run_uploadrr_subprocess` no fija `stdin` explícitamente (hereda el del proceso backend, normalmente no-tty), el comportamiento ante un prompt es indefinido: puede colgarse esperando input o fallar con EOF, dejando el job en `running` indefinidamente. Sin `-mt`, Uploadrr genera su propio nombre (`name.py`) en vez de respetar la nomenclatura EMU ya validada por nuestro Fase 10A/10B.
3. **`data/config.yaml` trackeado en git en el fork** pese a estar en `.gitignore` — patrón de riesgo de fuga de secretos si el operador reutiliza ese fichero tal cual.
4. **Sin señal de éxito estructurada (JSON).** Nuestro `upload_result_parser.py` ya asume esto correctamente (basa el estado en `exit_code`, extrae URLs/IDs por regex sin inventar datos) — compatible, pero conviene documentar que la detección de URL/torrent-id es "best effort", no garantizada.
5. **`cwd` con volumen `:ro` en `docker-compose.example.yml`.** El compose actual monta Uploadrr como `/opt/Uploadrr:ro` (correcto para esta fase de solo lectura/auditoría), pero Uploadrr **escribe** en `<uploadrr_dir>/tmp/<uuid>/` (torrents temporales, descripciones, capturas) — confirmado en `src/prep.py` y `src/utils/torrentman.py`. Una ejecución real con el mount actual en modo `ro` fallaría por permisos. Habrá que decidir en Fase 10E/10F si se monta `tmp/` aparte en `rw` o se cambia el mount completo a `rw` solo durante ejecución controlada.
6. **Dependencias sin pins de versión** (`requirements.txt` sin `==`), y **binarios `.exe`/`.dll` de Windows** (`bin/BDInfo/*`) incluidos en el repo — irrelevantes para Linux/Docker pero aumentan la superficie/peso si se llegase a copiar el árbol completo (razón de más para NUNCA vendorizar Uploadrr dentro de la imagen).
7. **Historia git plana (un solo commit)** — no hay forma de diferenciar con precisión qué cambió respecto al Uploadrr original vía `git diff`; solo inferencia por comparación de árbol de ficheros (se identificó `src/trackers/EMU.py` como el cambio EMU-específico más claro).

## Compatibilidad con `upload_execution.py` actual

| Aspecto | Contrato actual de la app (`upload_execution.py`/`upload_preflight.py`) | Uploadrr-EMU real | ¿Encaja? |
|---|---|---|---|
| Ejecutable | `sys.executable` (Python del backend) | Debe ser un **venv propio de Uploadrr** con sus deps instaladas | ❌ — hace falta un `python_path` configurable, no reutilizar `sys.executable` |
| Script | `<uploadrr_path>/upload.py` | Igual | ✅ |
| `cwd` | `uploadrr_path` | Requiere ser `uploadrr_dir()` para que `tmp/` relativo funcione | ✅ (ya coincide) |
| shell | `shell=False`, lista de args | Igual | ✅ |
| Tracker | `--tracker EMU` | `-tk EMU` (o `--trackers EMU`) | ❌ flag no coincide |
| Categoría | `--category movie/tv` | `-c movie/tv` (idéntico choices) | ⚠️ flag largo correcto (`--category` sí existe), pero falta consistencia con el resto |
| TMDb | `--tmdb <id>` | `-tmdb <id>` (`nargs="*"`, acepta `movie/123`) | ⚠️ formato de valor puede diferir (`123` vs `movie/123`) |
| Resolución | `--resolution 1080p` | `-res 1080p` (choices exactos) | ✅ valor compatible, flag debe usar forma larga real `--resolution` (sí existe) |
| Título forzado | No se envía | `-mt <título>` — necesario para respetar nomenclatura EMU ya generada | ❌ gap — no implementado |
| No interactivo | No se envía | `-ua` obligatorio para uso automatizado | ❌ gap — no implementado |
| stdin | No se fija explícitamente | Debería ser `DEVNULL` para evitar cuelgues | ❌ gap |
| Confirmación previa | `INICIAR_UPLOADRR` (token propio de la app) | N/A (es un concepto de nuestra app, no de Uploadrr) | ✅ ya implementado y correcto — no reutilizar `APLICAR_TITULO_MKV` |
| Logs | Captura stdout/stderr por hilos, redacta secretos conocidos | Uploadrr ya redacta internamente sus propios secretos conocidos | ✅ complementario, doble capa está bien |
| Resultado | `classify_upload_result` por exit_code + regex de URLs/IDs, sin inventar datos | Sin contrato JSON, exit code es la señal fiable | ✅ ya es el enfoque correcto |
| Cancelación | `SIGTERM` al PID guardado | Proceso async simple, debería responder a SIGTERM | ✅ probablemente compatible, sin verificar en vivo |
| Config secretos | Espera que `Uploadrr/data/config.yaml` YA esté configurado externamente por el operador, la app solo lee ajustes para redactar/mostrar | Coincide con el modelo real (config solo YAML, sin env vars) | ✅ modelo correcto — no hace falta que la app escriba `config.yaml` |

**Resumen**: la arquitectura general (subprocess controlado, `shell=False`, confirmación explícita, logs redactados, resultado por exit-code) es sólida y no necesita rediseño. Lo que falla es el **mapeo exacto de flags** (`build_uploadrr_execution_command`) y la **falta de `-ua`/`-mt`/`stdin=DEVNULL`**, y la ausencia de un **`python_path` configurable** distinto del intérprete del backend.

## Gaps de integración

- No hay setting `uploadrr_python_path` (o equivalente) — hoy se asume `sys.executable`, que es el Python del backend web, no el venv de Uploadrr con sus dependencias.
- No hay setting para el `runtime_type` (genérico vs EMU) — la construcción de comando es única y ya asume flags que no son universales entre forks de Uploadrr.
- No se envía `-mt` con el título validado de nomenclatura (Fase 10A/10B) ni `-ua`.
- No hay gestión de `stdin` explícita en `_run_uploadrr_subprocess`.
- No hay check de "instancia venv de Uploadrr operativa" (`--check-uploadrr` / `HELP --help`, como hace el wrapper) antes de permitir marcar un job como `ready`.
- No hay verificación de que `prepared_path` esté dentro de un `allowed_root` antes de construir el comando (existe en otras partes del proyecto — `filesystem_safety.py` — pero no se ve invocada explícitamente en `upload_preflight.py`/`upload_execution.py` para este paso final).

## Uploadrr EMU Runtime Contract v0

### 7.1 Inputs permitidos

- `prepared_path` (preferido) o `applied_path` resultante de nomenclatura — **nunca** el `source_path` original.
- `torrent_name`/`internal_mkv_title` ya confirmados por el flujo de nomenclatura (Fase 10A/10B), usados para construir `-mt`.
- `category` (`movie`/`tv`), `resolution`, `tmdb_id` (o `imdb_id`) ya validados.
- `uploadrr_python_path` — Python del venv de Uploadrr-EMU (nuevo setting, distinto de `sys.executable`).
- `uploadrr_path` — ya existente.
- `dry_run` — ya existente en el contrato actual, se mantiene.
- La API key EMU/TMDb **no viaja como argumento**: sigue viviendo únicamente en `Uploadrr/data/config.yaml`, gestionado fuera de nuestra app (el operador la configura directamente en Uploadrr).

### 7.2 Inputs prohibidos

- `source_path` original (solo `prepared_path`/`applied_path`).
- Rutas fuera de `allowed_roots` (hardlink_base / prepared roots ya definidos en el proyecto).
- Cadena de comando como string (`shell=True`) — prohibido, siempre lista de argumentos.
- API keys como argumento CLI (Uploadrr-EMU no lo soporta ni lo necesita — viven en su propio `config.yaml`).
- Cualquier flag que dispare comportamiento interactivo sin `-ua` presente.

### 7.3 Ejecución

- `subprocess.Popen`/`run` con `shell=False`, lista explícita de argumentos (ya así hoy).
- `cwd` = `uploadrr_dir()` (ya así hoy).
- `stdin=subprocess.DEVNULL` explícito (gap a cerrar).
- Timeout configurable (no existe hoy — a añadir; una subida real puede tardar minutos, el timeout debe ser generoso y configurable, no fijo).
- Logs capturados por stream (ya así hoy) y saneados con `redact_secrets` (ya existe) — mantener como segunda capa sobre la redacción propia de Uploadrr.
- `dry_run=True` por defecto (ya así hoy) — se mantiene como precedencia absoluta sobre `start=True`.

### 7.4 Confirmación

Se mantiene `INICIAR_UPLOADRR` (ya implementado en `upload_execution.py`) como token exclusivo para subida real. **No reutilizar** `APLICAR_TITULO_MKV` (token de Fase 10A, ámbito distinto: edición de título interno MKV).

### 7.5 Estados

Los estados ya definidos en `upload_jobs.status` (`draft/preflight/ready/running/completed/failed/blocked/cancelled`) cubren razonablemente el ciclo. Para alinear con el pedido de esta auditoría, se recomienda incorporar explícitamente (algunos ya existen con otro nombre):

```
pending             (= draft actual)
preflight_ok        (= ready actual, tras validate_upload_job_start)
waiting_for_confirmation   (nuevo — entre preflight_ok y running, cuando dry_run=False pero aún sin confirmation)
running             (ya existe)
succeeded           (= completed actual)
failed              (ya existe)
cancelled           (ya existe)
timeout             (nuevo — requiere el timeout de 7.3)
blocked_by_policy   (nuevo — p.ej. prepared_path fuera de allowed_root, o kind inválido)
```

### 7.6 Artifacts esperados

Ya cubierto en gran parte por `upload_artifacts` (`prepared_file`, `uploaded_url`, `torrent_id`) y `upload_jobs` (`safe_command_json`, `exit_code`, `started_at`, `finished_at`, `error_message`). Falta:
- Persistir `command_preview` redactado también en `preflight` (ya se hace) y en el estado `waiting_for_confirmation` propuesto.
- Confirmar que `prepared_path`/`torrent_name` quedan en el artifact incluso si el job falla antes de arrancar el proceso (hoy `create_upload_artifact` para `prepared_file` solo se llama tras iniciar el subprocess).

## Checks seguros propuestos (sin ejecutar nada real)

- Comprobar que `uploadrr_path` existe y contiene `upload.py` y `data/` (ya existe en `validate_upload_job_start`).
- Comprobar que existe un Python de venv configurable (`uploadrr_python_path`) y que es ejecutable — nuevo check, sin ejecutar Uploadrr.
- Comprobar `<uploadrr_python_path> <uploadrr_path>/upload.py HELP --help` como smoke-check opcional y explícito (igual que hace el wrapper con `--check-uploadrr`) — **solo si el operador lo activa a propósito**, nunca automático ni en cada preflight, ya que igualmente lanza un proceso real (aunque inofensivo, con `--help` no debería tocar nada, pero requiere config.yaml válido para no abortar antes).
- Comprobar que `data/config.yaml` existe dentro de `uploadrr_path` (sin leer su contenido con fines de mostrarlo, salvo para extraer si `TRACKERS.EMU.api_key` está vacío/placeholder, de forma similar al check ya existente de `emu_api_key` en nuestra propia BD).
- Comprobar que `prepared_path` existe, no es symlink, es fichero regular y de extensión de vídeo reconocida (ya existe en `validate_upload_job_start`).
- Comprobar que `prepared_path` está dentro de un `allowed_root` conocido (hardlink_base) — reforzar explícitamente en este paso, reusando `filesystem_safety.py`.
- Comprobar que `torrent_name`/título manual está generado y no vacío antes de construir `-mt`.
- Comprobar que el `command_preview` no contiene ninguna de las secrets conocidas (`emu_api_key`, `tmdb_api_key`) — el modelo actual ya no las incluye porque no se pasan por CLI, pero un test de regresión que lo confirme (`assert secret not in command_preview`) es barato y valioso.

Ninguno de estos checks sube torrents, ejecuta Uploadrr en modo real, ni modifica `Uploadrr/`.

## Docker/deployment recomendado

- **Mantener** la filosofía actual: Uploadrr-EMU como **bind mount externo**, nunca copiado/vendorizado dentro de la imagen `emuwarez-uploadrr` (evita duplicar binarios pesados de `bin/BDInfo/`, evita gestionar su propio `requirements.txt`/venv dentro de nuestra imagen, evita acoplar su ciclo de releases al nuestro).
- **No usar el `config.yaml` del fork clonado tal cual** — el operador debe generar su propio `data/config.yaml` fuera de git, siguiendo `data/backup/example_config.yaml` como plantilla, y montarlo únicamente en su propia instancia.
- El propio venv/dependencias de Uploadrr-EMU deben instalarse **en el host o en un volumen persistente propio**, no dentro de la imagen principal — nuestra imagen solo necesita saber la ruta al Python del venv (`uploadrr_python_path`) y al `upload.py`.
- **Cambiar el mount de `:ro` a un esquema mixto** antes de cualquier ejecución real (Fase 10F): el árbol de Uploadrr puede seguir siendo `:ro` salvo el subdirectorio `tmp/` (y posiblemente `data/backup/`), que necesita ser escribible. Opciones: (a) mount adicional `rw` solo para `tmp/`, o (b) mount completo `rw` de todo `/opt/Uploadrr` aceptando que Uploadrr pueda escribir en su propio árbol (más simple, algo menos estricto). Recomendación: opción (a), más alineada con "no tocar Uploadrr/" en todo lo que no sea estrictamente necesario.
- No se recomienda un contenedor separado para Uploadrr-EMU en esta fase: al no exponer una API HTTP propia (es un CLI por proceso), separarlo en su propio contenedor añadiría complejidad de IPC (habría que exponerlo via RPC/cola) sin beneficio claro todavía. Revisar esta decisión si en el futuro se necesita paralelizar muchas subidas simultáneas.

## Recomendación: generic vs emu vs ambos

**Se recomienda la opción B: `runtime_type` configurable (`uploadrr_generic` / `uploadrr_emu`)**, confirmando la preferencia inicial planteada en el encargo.

Justificación:
- **Complejidad**: baja-media. La diferencia entre ambos perfiles se reduce a la construcción de `args` en `build_uploadrr_execution_command` (qué flags exactos usar) — se puede resolver con una tabla de mapeo por `runtime_type` sin duplicar el resto del pipeline (validación, logs, artifacts, confirmación, estados).
- **Seguridad**: igual en ambos casos — el modelo de confirmación, redacción y `shell=False` no cambia con el `runtime_type`.
- **Mantenimiento**: aceptable. Si en el futuro aparece un tercer fork con flags distintos, añadir un tercer perfil es trivial con este diseño; la opción A (solo EMU) bloquearía esa extensión y la opción C (genérico + "profile" ad-hoc) acaba reinventando lo mismo que B con más ambigüedad de nombres.
- **Configuración Docker**: sin impacto — el volumen sigue siendo "ruta externa a Uploadrr", independientemente del `runtime_type`.
- **Compatibilidad con el flujo actual**: alta. `upload_jobs` ya tiene una tabla flexible (`uploadrr_command_json`); añadir `runtime_type` como columna/setting adicional no rompe nada existente, y el valor por defecto puede ser `uploadrr_emu` dado que es el único fork verificado hasta ahora.

## Qué NO se ha ejecutado

- No se ejecutó `python upload.py` ni ningún subcomando de Uploadrr-EMU.
- No se hizo `pip install -r requirements.txt` ni `npm install` en el fork.
- No se realizó login real, ni subida de torrents, ni llamada real a `https://emuwarez.com`.
- No se lanzó ningún proceso de mkvpropedit real.
- No se modificó ningún fichero del fork clonado en `/tmp/uploadrr-emu-audit`.
- No se modificó `Uploadrr/` del repo principal (no existe tal directorio en este repo — es intencionadamente externo).
- No se hizo `git push` a ningún remoto (ni del repo principal ni del fork).
- No se creó ningún commit de código funcional en el repo principal — solo este documento.

## Siguiente fase propuesta

### FASE 10E — Uploadrr-EMU runtime integration dry-run

Objetivo:
- Añadir `runtime_type` (`uploadrr_generic` / `uploadrr_emu`) como setting configurable.
- Añadir `uploadrr_python_path` como setting distinto de `sys.executable`.
- Reescribir `build_uploadrr_execution_command` para el perfil `uploadrr_emu` con el mapeo real de flags (`-tk`, `-mt`, `-tmdb`, `-c`, `-res`, `-ua`, `-season`/`-episode`), fijando `stdin=subprocess.DEVNULL`.
- Añadir los checks seguros descritos arriba (venv existe, `config.yaml` existe, `prepared_path` dentro de `allowed_root`, sin secretos en `command_preview`).
- Añadir preview de comando redactado para el nuevo perfil, con tests que confirmen ausencia de secretos.
- Añadir timeout configurable al subprocess.
- **No** ejecutar subida real, **no** cambiar el mount Docker a `rw` todavía.

### FASE 10F — Controlled Uploadrr-EMU execution

Objetivo (futuro, posterior a 10E):
- Ejecución real controlada, solo sobre `prepared_path`.
- Confirmación exacta `INICIAR_UPLOADRR` (ya existente, reutilizar).
- Ajuste del mount Docker (`tmp/` escribible) documentado y probado.
- Logs/artifacts completos, incluyendo URL/torrent_id si aparecen.
- Retry/cancel ya existen — validarlos contra un proceso real de Uploadrr-EMU.
- Entorno controlado (staging/homelab del propio usuario), nunca como parte de CI/tests automatizados.

## Validaciones ejecutadas

Ver sección siguiente del commit (resultados reales, no simulados) — todas ejecutadas sobre el repo principal, ninguna sobre el fork.
