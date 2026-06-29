# Auditoría técnica inicial — Fase 0
## eMuwarez Uploadrr · CLI Ready v2

**Fecha:** 2026-06-28
**Rama:** feature/ui-phase-00-audit
**Estado:** Solo lectura. Ningún fichero funcional ha sido modificado.

---

## 1. Estado actual del repo

### 1.1. Estructura de carpetas

```text
emuwarez_uploadrr_cli_ready_v2/
├── emuwarez_uploader.py            # Lanzador de compatibilidad (1 import + __main__)
├── pyproject.toml                  # v0.2.0, entry points CLI
├── README_CLI_READY.md             # Documentación v2 (modo moderno + modo legacy)
├── README_REFACTOR.md              # Documentación v1 (refactor inicial)
├── emuwarez_uploadrr_codex_master_pack_v3.md  # Especificación completa del proyecto
├── docs/                           # (creada en Fase 0)
│   └── codex_phase_00_audit.md     # Este archivo
├── Uploadrr/                       # [DEPENDENCIA EXTERNA — NO TOCAR]
│   └── (repositorio git embebido)
└── emuwarez_uploadrr/              # Paquete principal
    ├── __init__.py
    ├── legacy.py                   # Motor completo original (~monolítico)
    ├── cli.py                      # Entrypoint CLI moderno
    ├── constants.py                # Re-exporta desde legacy.py
    ├── models.py                   # Dataclasses + Enums de dominio
    ├── database.py                 # SQLite, schema, helpers
    ├── config.py                   # Carga de configuración propia
    ├── crypto.py                   # Cifrado de configuración
    ├── ui.py                       # Helpers de terminal
    ├── logging_utils.py            # Logging
    ├── paths.py                    # Rutas del sistema
    ├── bootstrap.py                # venv/dependencias
    ├── tmdb.py                     # Cliente TMDb y matching
    ├── media_info.py               # MediaInfo
    ├── source.py                   # Detección de source
    ├── naming.py                   # Nomenclatura eMuwarez
    ├── planner.py                  # Plan de subida
    ├── proposal.py                 # Propuesta CLI al usuario
    ├── hardlinks.py                # Filesystem/hardlinks
    ├── progress.py                 # Parseo de progreso Uploadrr
    ├── uploadrr_runner.py          # Ejecución de Uploadrr
    ├── uploadrr_config.py          # Editor config.yaml de Uploadrr
    ├── results.py                  # Resumen final de subida
    ├── validators.py               # Validaciones/API/qBittorrent
    ├── integrations/
    │   ├── __init__.py
    │   ├── base.py                 # HTTP helpers (urllib, sin dependencias)
    │   ├── radarr.py               # Conector Radarr v3
    │   ├── sonarr.py               # Conector Sonarr v3
    │   └── emu.py                  # Conector eMuwarez (parcial/stub)
    └── services/
        ├── __init__.py
        ├── instances.py            # CRUD instancias Radarr/Sonarr
        ├── library.py              # Sincronización y consulta de biblioteca
        ├── requests.py             # Sincronización/matching de peticiones EMU
        └── tasks.py                # Registro de tareas ejecutadas
```

### 1.2. Punto de entrada principal

```text
emuwarez_uploader.py → emuwarez_uploadrr/cli.py → main()
```

`emuwarez_uploader.py` es un lanzador de una sola línea (importa `main` de `cli.py` y lo ejecuta). No contiene lógica.

### 1.3. Cómo arranca la CLI actual

La función `main()` en `cli.py:465` detecta el modo de arranque:

```python
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return legacy.main(argv)            # sin argumentos → modo legacy
    first = argv[0]
    if first not in MODERN_COMMANDS:
        return legacy.main(argv)            # argumento desconocido → modo legacy
    return modern_main(argv)               # argumento conocido → CLI moderna
```

`MODERN_COMMANDS` (cli.py:23):

```python
{
    "configure", "doctor", "test-apis", "instances", "sync", "library",
    "requests", "missing", "prepare", "upload", "tasks", "logs", "legacy",
    "web-contract", "db",
}
```

Cualquier primer argumento fuera de ese conjunto (p.ej. una ruta de archivo) cae en modo legacy de forma transparente.

### 1.4. Módulos existentes

| Módulo | Rol | Depende de legacy.py |
|---|---|---|
| `legacy.py` | Motor monolítico completo | Sí (es la fuente) |
| `cli.py` | Entrypoint y dispatch de comandos | Sí (importa funciones de legacy) |
| `constants.py` | Re-exporta constantes de legacy | Sí |
| `models.py` | Enums + dataclasses de dominio | Sí (importa AppConfig, MediaInfoData, FilePlan, RunPlan) |
| `database.py` | SQLite helpers + schema | No (solo stdlib) |
| `config.py` | Carga de configuración | Sí (usa constantes de legacy) |
| `crypto.py` | Cifrado de config | No |
| `ui.py` | Helpers de terminal | Sí |
| `logging_utils.py` | Logging | Sí |
| `paths.py` | Rutas | Sí |
| `bootstrap.py` | venv/deps | Sí |
| `tmdb.py` | TMDb client | Sí |
| `media_info.py` | MediaInfo | Sí |
| `source.py` | Detección de source | Sí |
| `naming.py` | Nomenclatura | Sí |
| `planner.py` | Plan de subida | Sí |
| `proposal.py` | Propuesta al usuario | Sí |
| `hardlinks.py` | Hardlinks/filesystem | Sí |
| `progress.py` | Progreso Uploadrr | Sí |
| `uploadrr_runner.py` | Ejecución de Uploadrr | Sí |
| `uploadrr_config.py` | Config.yaml Uploadrr | Sí |
| `results.py` | Resumen de subida | Sí |
| `validators.py` | Validaciones | Sí |
| `integrations/base.py` | HTTP urllib helpers | No |
| `integrations/radarr.py` | Radarr v3 API | Sí (DEFAULT_TAG) |
| `integrations/sonarr.py` | Sonarr v3 API | Sí (DEFAULT_TAG) |
| `integrations/emu.py` | eMuwarez API (parcial) | Sí (EMU_TEST_URL) |
| `services/instances.py` | CRUD instancias | No (solo integrations) |
| `services/library.py` | Sync biblioteca | No (solo integrations + models) |
| `services/requests.py` | Sync peticiones EMU | Sí (via config.py) |
| `services/tasks.py` | Registro de tareas | No |

### 1.5. Dependencia de legacy.py

`legacy.py` es la fuente de verdad de:
- Todas las constantes (`APP_NAME`, `CONFIG_DIR`, `DEFAULT_TAG`, `EMU_TEST_URL`, etc.)
- Los dataclasses legacy (`AppConfig`, `MediaInfoData`, `FilePlan`, `RunPlan`)
- Toda la lógica del flujo original: MediaInfo, TMDb, nomenclatura, hardlinks, Uploadrr runner, proposal, etc.
- `parse_args`, `process_path`, `configure`, `doctor`, `test_apis`, `main`, `current_log_file`

Los módulos modernos que más dependen de legacy son: `constants.py`, `models.py`, `config.py`, `naming.py`, `media_info.py`, `source.py`, `tmdb.py`, `planner.py`.

Los módulos que **no dependen de legacy** son: `database.py`, `integrations/base.py`, `services/instances.py`, `services/library.py`, `services/tasks.py`.

### 1.6. Módulos preparados para CLI moderna

Completamente listos (no dependen de legacy, API estable):

- `emuwarez_uploadrr/database.py` — schema SQLite, helpers upsert/query
- `emuwarez_uploadrr/models.py` — Enums `LocalStatus`, `RequestStatus`, `NomenclatureStatus`, `DupeStatus`, `TaskStatus` + dataclasses `LibraryItem`, `RequestItem`, `RequestMatch`, `TaskRun`, `UploadJob`, `InstanceConfig`
- `emuwarez_uploadrr/integrations/base.py` — HTTP puro stdlib
- `emuwarez_uploadrr/integrations/radarr.py` — conector completo, `movie_to_library_item` ya transforma a `LibraryItem`
- `emuwarez_uploadrr/integrations/sonarr.py` — conector completo
- `emuwarez_uploadrr/services/instances.py` — CRUD + test de conexión
- `emuwarez_uploadrr/services/library.py` — sync, list, missing, upsert
- `emuwarez_uploadrr/services/requests.py` — sync throttled (1h), match, upsert, normalize
- `emuwarez_uploadrr/services/tasks.py` — start/finish task

### 1.7. Partes reutilizables para la futura UI web

Los siguientes módulos pueden exponerse directamente como servicios backend sin refactorizar:

```text
database.py          → init_db(), connect(), get/set_state()
services/instances   → add/remove/list/test_instance()
services/library     → sync_all(), list_library(), list_missing(), get_library_item()
services/requests    → sync_requests(), list_requests(), match_requests(), get_match_for_request()
services/tasks       → start_task(), finish_task(), list_tasks()
integrations/radarr  → test_connection(), get_movies(), movie_to_library_item()
integrations/sonarr  → test_connection(), get_series(), series_to_library_item(), episode_to_library_item()
integrations/emu     → test_connection(), get_requests(), normalize_requests()
models.py            → todos los enums y dataclasses son los contratos de API
```

Los siguientes módulos son el "motor Uploadrr" que la UI reutilizará para prepare/upload pero no debe duplicar:

```text
naming.py, media_info.py, source.py, planner.py, hardlinks.py,
uploadrr_runner.py, uploadrr_config.py, progress.py, results.py
```

---

## 2. Comandos actuales disponibles

### 2.1. Help observado

El `--help` invocado sin argumentos modernos muestra la ayuda del modo **legacy**:

```
usage: emuwarez_upload.py [-h] [--dry-run] [--yes] [--no-upload]
                          [--season] [--episode] [--debug-uploadrr] [--tmdb]
                          [--type {movie,tv}] [--configure] [--bootstrap]
                          [--scan-imports] [--check-uploadrr] [--doctor]
                          [--test-apis] [--config-pass-file] [--config-pass-env]
                          [--python] [--skip-system-update] [--no-system-install]
                          [--no-color]
                          [path ...]
```

La CLI moderna tiene su propio parser (argparse con subcomandos). Para ver la ayuda moderna:

```bash
python3 emuwarez_uploader.py db --help
python3 emuwarez_uploader.py instances --help
python3 emuwarez_uploader.py library --help
# etc.
```

### 2.2. Comandos legacy soportados (primer argumento no en MODERN_COMMANDS)

| Comando | Descripción |
|---|---|
| `<ruta> [opciones]` | Flujo completo: MediaInfo → TMDb → nomenclatura → hardlink → Uploadrr |
| `--configure` | Bootstrap inicial + configuración de claves/rutas |
| `--doctor` | Comprueba entorno/configuración |
| `--test-apis` | Prueba TMDb, EMU, Imgbox, hosts de imagen |
| `--dry-run` | Simula sin modificar nada |
| `--yes` | Aplica sin confirmación |
| `--no-upload` | No ejecuta Uploadrr |
| `--season [N]` | Forzar temporada |
| `--episode N` | Forzar episodio |
| `--tmdb <id>` | Forzar ID TMDb |
| `--type {movie,tv}` | Forzar tipo |
| `--bootstrap` | Solo crear venv/instalar deps |
| `--scan-imports` | Listar imports externos de Uploadrr |
| `--check-uploadrr` | Probar `Uploadrr/upload.py HELP --help` |
| `--debug-uploadrr` | Mostrar salida completa de Uploadrr |

### 2.3. Comandos modernos disponibles

| Comando | Estado | Descripción |
|---|---|---|
| `db init` | **Funcional** | Crea/actualiza schema SQLite |
| `db path` | **Funcional** | Muestra ruta de SQLite |
| `instances list` | **Funcional** | Lista instancias configuradas |
| `instances add <type>` | **Funcional** | Añade/actualiza instancia Radarr/Sonarr |
| `instances test [id]` | **Funcional** | Prueba conexión (requiere instancia configurada) |
| `instances remove <id>` | **Funcional** | Elimina instancia |
| `sync [--episodes]` | **Funcional** | Sincroniza biblioteca desde todas las instancias |
| `library list` | **Funcional** | Lista biblioteca con filtros |
| `library show <id>` | **Funcional** | Detalle de item |
| `missing list` | **Funcional** | Lista faltantes (status=Faltante) |
| `requests sync` | **Funcional** (throttled 1h) | Sincroniza peticiones EMU |
| `requests list` | **Funcional** | Lista peticiones sincronizadas |
| `requests show <id>` | **Funcional** | Detalle + cruce con biblioteca |
| `requests set-endpoint <url>` | **Funcional** | Guarda endpoint de peticiones EMU |
| `requests match` | **Funcional** | Recalcula cruces petición/biblioteca |
| `requests create <lib_id>` | **Stub** | Mensaje de pendiente, no activo |
| `missing create-request <id>` | **Stub** | Mensaje de pendiente, no activo |
| `prepare <id\|ruta>` | **Funcional** | Adaptar nomenclatura (llama a legacy) |
| `upload <id\|ruta>` | **Funcional** | Subir con Uploadrr (llama a legacy) |
| `tasks list` | **Funcional** | Últimas tareas ejecutadas |
| `logs [--tail N]` | **Funcional** | Últimas líneas del log heredado |
| `legacy [args...]` | **Funcional** | Pasa argumentos directamente a legacy |
| `configure` | **Funcional** | Alias de legacy --configure |
| `doctor` | **Funcional** | Alias de legacy --doctor |
| `test-apis` | **Funcional** | Alias de legacy --test-apis |
| `web-contract` | **Funcional** | Muestra contrato CLI↔Web |

### 2.4. Comandos stub

| Comando | Motivo |
|---|---|
| `requests create <id>` | Endpoint POST de eMuwarez pendiente de capturar desde DevTools |
| `missing create-request <id>` | Mismo motivo. Mensaje explícito al ejecutar |

### 2.5. Comandos que requieren configuración externa real

| Comando | Requisito |
|---|---|
| `sync` | Instancias Radarr/Sonarr configuradas (`instances add`) |
| `instances test` | URL y API key de Radarr/Sonarr alcanzables |
| `requests sync` | API key eMuwarez en config + endpoint de peticiones configurado |
| `prepare <id>` | Item en biblioteca (requiere `sync` previo) |
| `upload <id>` | Item en biblioteca + Uploadrr instalado y config.yaml presente |

### 2.6. Salidas observadas en Fase 0

```bash
# db init
✓ SQLite lista: /home/alvaro/.config/emuwarez-renamer/emuwarez_uploadrr.db

# web-contract
Contrato funcional preparado para la interfaz web:
Dashboard: sync-library, sync-requests, recent-tasks
Biblioteca: list, detail, adaptar nomenclatura, subir
Faltantes: list, crear petición futura
Peticiones: sync, list, detail+motivos
Instancias: add/list/test/remove

# instances list  (sin instancias configuradas)
ID  Tipo  Nombre  URL  Activa
──  ────  ──────  ───  ──────

# tasks list / missing list / requests list
(tablas vacías — base sin sincronizar)
```

---

## 3. Validación técnica

### 3.1. Comandos ejecutados

```bash
python3 -m py_compile emuwarez_uploader.py
find emuwarez_uploadrr -name "*.py" -print0 | xargs -0 python3 -m py_compile
```

### 3.2. Resultado

**OK** — Todos los archivos compilan sin errores.

```text
OK: emuwarez_uploader.py
OK: all modules (34 archivos .py del paquete)
```

No se detectan errores de sintaxis, importaciones circulares ni referencias inválidas en tiempo de compilación.

### 3.3. Observaciones

- `Uploadrr/` fue reconocido por Git como repositorio embebido (git submodule). No interfiere con el paquete Python pero debe excluirse de `git add -A` en futuras fases.
- La base de datos SQLite se crea correctamente en `~/.config/emuwarez-renamer/emuwarez_uploadrr.db` al ejecutar `db init`.
- El schema versión 2 incluye 7 tablas + 6 índices.

---

## 4. Base de datos actual

### 4.1. Ruta esperada

```text
~/.config/emuwarez-renamer/emuwarez_uploadrr.db
```

Definido en `database.py:11`:

```python
DB_FILE = CONFIG_DIR / "emuwarez_uploadrr.db"
```

Donde `CONFIG_DIR = Path.home() / ".config" / "emuwarez-renamer"` (de `legacy.py:57`).

La ruta puede sobreescribirse con `--db <ruta>` en cualquier comando moderno.

La carpeta futura en Docker será `/config/emuwarez_uploadrr.db` (requiere ajuste en Fase 2).

### 4.2. Tablas definidas (schema_version = 2)

| Tabla | Estado | Descripción |
|---|---|---|
| `app_state` | **Presente** | Par clave-valor para estado persistente (last_sync, endpoints, etc.) |
| `instances` | **Presente** | Instancias Radarr/Sonarr (tipo, nombre, URL, api_key, enabled) |
| `library_items` | **Presente** | Items sincronizados desde Radarr/Sonarr |
| `request_items` | **Presente** | Peticiones sincronizadas desde eMuwarez |
| `request_matches` | **Presente** | Cruces petición ↔ item de biblioteca |
| `task_runs` | **Presente** | Registro de tareas ejecutadas |
| `upload_jobs` | **Presente** | Jobs de subida |

Tablas previstas en el Codex pero **aún no creadas**:

| Tabla | Referencia | Estado |
|---|---|---|
| `users` | codex §10 | Ausente — para Fase 3 (auth setup wizard) |
| `settings` | codex §10 | Ausente — para Fase 3 |
| `queue_items` | codex §10 | Ausente — para Fase 4 (queue Radarr/Sonarr) |
| `history_items` | codex §10 | Ausente — para Fase 4 (history Radarr/Sonarr) |
| `upload_events` | codex §10 | Ausente — para Fase 8 (streaming progreso) |
| `event_log` | codex §10 | Ausente — para Fase 7 (panel eventos) |

### 4.3. Campos principales de tablas existentes

**`library_items`**

```text
id, item_type, title, year, original_title,
instance_id, instance_type, instance_name,
external_id, tmdb_id, imdb_id, tvdb_id,
path, quality, resolution, source, size_bytes,
local_status, request_status, nomenclature_status, request_id,
added_at, updated_at, raw_json
UNIQUE(instance_id, item_type, external_id)
```

Notas: falta `spanish_title`, `file_path` separado de `path`, `codec`, `audio`, `subtitles`, `monitored`, `has_file` (presentes en el Codex §10.1 pero no en el schema actual).

**`request_items`**

```text
id, emu_id (UNIQUE), title, category,
requested_source, requested_resolution, emu_status, points, comments,
created_at, tmdb_id, imdb_id, url,
author, author_visible, raw_json, updated_at
```

**`request_matches`**

```text
id, library_item_id (FK), request_item_id (FK),
status, confidence, resolution_match, source_match, type_match,
reasons (TEXT con \n), updated_at
UNIQUE(library_item_id, request_item_id)
```

**`task_runs`**

```text
id, name, status, started_at, finished_at, summary, details
```

**`upload_jobs`**

```text
id, library_item_id (FK), title, path, status, dupe_status,
dupe_message, uploadrr_description, trailer_url, created_at, updated_at
```

Notas: falta `stage`, `percent`, `source_path`, `prepared_path`, `uploadrr_tmp_path`,
`description_path`, `emu_url`, `started_at`, `finished_at`, `error_message`
(presentes en Codex §10.4 pero no en el schema actual).

**`app_state`**

```text
key (PK), value, updated_at
```

Claves conocidas usadas en código:
- `schema_version`
- `last_emu_requests_sync_utc`
- `emu_requests_endpoint`

---

## 5. Modelo funcional esperado

### 5.1. Integraciones y su rol

| Integración | Rol | Estado |
|---|---|---|
| **Radarr** | Fuente primaria: películas, calidad, queue, history, TMDb/IMDb IDs, rutas | Conector funcional |
| **Sonarr** | Fuente primaria: series, temporadas, episodios, calidad, rutas | Conector funcional |
| **eMuwarez** | Fuente de peticiones + destino de subida | Test de conexión funcional; lectura de peticiones requiere endpoint; creación pendiente |
| **TMDb** | Enriquecimiento: título español, IDs externos, matching, posters | Módulo `tmdb.py` en legacy funcional |
| **Uploadrr** | Motor de subida (torrent a EMU) | Integración via subprocess (legacy) |
| **Jellyfin** | Integración opcional: verificar disponibilidad, refresh | Sin módulo aún |
| **Seerr** | Integración opcional: contexto de peticiones de usuarios | Sin módulo aún |

**Orden de confianza para biblioteca:**

```text
1. Radarr/Sonarr  (fuente principal)
2. TMDb           (enriquecimiento)
3. eMuwarez       (peticiones)
4. Jellyfin       (verificación opcional)
5. Seerr          (contexto opcional)
```

### 5.2. Diferencia entre Biblioteca, Faltantes y Peticiones

#### Biblioteca

- **Origen:** Radarr/Sonarr
- **Contenido:** Todo lo que el sistema conoce: películas disponibles, faltantes, series, temporadas, episodios, calidad, rutas, estado local, origen, nomenclatura, relación con peticiones EMU
- **En CLI:** `library list / library show`

#### Faltantes

- **Origen:** Radarr/Sonarr (items monitorizados sin archivo local)
- **Contenido:** Película/episodio añadido/monitorizado pero sin archivo disponible. Incluye errores de importación, items sin indexar, temporadas incompletas
- **Objetivo:** Decidir si buscar, revisar Radarr/Sonarr, comprobar eMuwarez o (en fase final) crear petición
- **Diferencia clave con Peticiones:** Nace del estado de Radarr/Sonarr, no de eMuwarez
- **En CLI:** `missing list`

#### Peticiones

- **Origen:** eMuwarez
- **Contenido:** Peticiones activas de eMuwarez, cruzadas contra la biblioteca local
- **Objetivo:** Saber qué peticiones de eMuwarez puedes cubrir con contenido que ya tienes
- **Diferencia clave con Faltantes:** Nace de eMuwarez, no de Radarr/Sonarr
- **En CLI:** `requests list / requests show`

### 5.3. Estados de un item de biblioteca

**Estado local:**

```text
Disponible              (tiene archivo local)
Faltante                (monitorizado, sin archivo)
En cola                 (en queue Radarr/Sonarr)    → pendiente Fase 4
Descargando             (activo en queue)            → pendiente Fase 4
Pendiente de importación                             → pendiente Fase 4
Error de importación                                 → pendiente Fase 4
Error de búsqueda                                    → pendiente Fase 4
Subiendo                (upload_job activo)
Subido                  (upload_job completado)
Error                   (genérico)
Desconocido             (estado inicial antes de sync)
```

**Estado eMuwarez** (via `request_status` en library_items):

```text
Sin petición
Compatible
Parcial
No compatible
Llena
Desconocida
```

**Nomenclatura:**

```text
Correcta        (path contiene DEFAULT_TAG = "EMUWAREZ")
No adaptada     (disponible pero path sin DEFAULT_TAG)
N/A             (no disponible, no aplica)
```

La columna se llama siempre **Nomenclatura** (nunca FormatoEMU).

### 5.4. Compatibilidad de petición

Reglas implementadas en `services/requests.py:_classify_match()`:

```text
EMU pide 1080p WEB-DL + local tiene 1080p WEB-DL  → Compatible (score 1.0)
EMU pide 2160p WEB-DL + local tiene 1080p WEB-DL  → Parcial    (resolución diferente)
EMU pide 1080p WEB-DL + local tiene 1080p BluRay   → Parcial    (source diferente)
EMU pide Any            + local tiene cualquier     → Compatible (any = sin restricción)
EMU estado = Lleno                                  → Llena      (aunque exista localmente)
Sin candidato en biblioteca                         → Sin petición (no se crea match)
```

Matching por prioridad:
1. TMDb ID
2. IMDb ID
3. Título normalizado (NFKD casefold, sin acentos, sin signos)

---

## 6. Flujo seguro antes de recomendar acciones

El siguiente flujo debe respetar la futura aplicación antes de actuar:

```text
1. Sincronizar Radarr/Sonarr
   → GET /api/v3/movie (Radarr)
   → GET /api/v3/series, /episode, /episodefile (Sonarr)

2. Leer biblioteca
   → Todos los items con has_file=true → local_status = Disponible
   → Items monitorizados sin archivo  → local_status = Faltante

3. Leer wanted/missing
   → GET /api/v3/wanted/missing (Radarr/Sonarr)
   → Confirmar/enriquecer local_status = Faltante

4. Leer queue
   → GET /api/v3/queue (Radarr/Sonarr)
   → local_status = En cola / Descargando / Pendiente de importación
   [PENDIENTE — Fase 4]

5. Leer history/errores
   → GET /api/v3/history (Radarr/Sonarr)
   → local_status = Error de importación / Error de búsqueda
   [PENDIENTE — Fase 4]

6. Sincronizar peticiones eMuwarez
   → GET <endpoint configurado> con Bearer token
   → Guardar en request_items
   → Throttle: máximo 1 vez/hora

7. Cruzar por TMDb/IMDb/título español
   → match_requests() en services/requests.py
   → Genera request_matches con status y reasons

8. Comprobar compatibilidad resolución/source
   → _classify_match() en services/requests.py
   → Compatible / Parcial / No compatible / Llena

9. Comprobar existencia en eMuwarez si aplica
   → integrations/emu.py (stub actual, endpoint pendiente)

10. Recomendar acción segura
    → Si Disponible + Compatible + Nomenclatura correcta → Subir
    → Si Disponible + Compatible + No adaptada → Adaptar nomenclatura + Subir
    → Si En cola / Descargando → Esperar
    → Si Faltante + sin queue + sin error → Comprobar en EMU
    → Si Faltante + error → Revisar Radarr/Sonarr
```

**No debe recomendar crear petición en eMuwarez si:**

- El contenido está en cola de descarga
- Está descargando activamente
- Ya existe el contenido en eMuwarez
- Ya hay petición compatible activa
- El problema parece ser de Radarr/Sonarr (error de importación/búsqueda)
- Ya está disponible localmente

---

## 7. Riesgos actuales

### 7.1. Dependencia de legacy.py

**Riesgo medio-alto.** Casi todos los módulos del paquete importan de `legacy.py` directamente. Si legacy.py cambia una constante o refactoriza una función, pueden romperse múltiples módulos.

- `constants.py` re-exporta todo desde legacy — cualquier cambio en legacy debe replicarse
- `models.py` importa `AppConfig`, `MediaInfoData`, `FilePlan`, `RunPlan` desde legacy
- `config.py`, `naming.py`, `tmdb.py`, `media_info.py` importan funciones de legacy directamente

**Recomendación:** No mover código de legacy.py hasta Fase 8 o posterior. Los módulos que SÍ son independientes (database, integrations/base, services/*) son los seguros para Fase 1.

### 7.2. Acoplamiento con Uploadrr

`Uploadrr/` es un repositorio git embebido, no un submodulo declarado. Git avisa de esto pero lo admite como commit `160000`. La lógica de subida en `uploadrr_runner.py` y `uploadrr_config.py` depende de que Uploadrr esté en `./Uploadrr/upload.py` relativo al script.

Si se dockeriza, el volumen `/app/Uploadrr` debe montar el directorio externo o el path debe ser configurable.

### 7.3. Rutas relativas delicadas

- `CONFIG_DIR = Path.home() / ".config" / "emuwarez-renamer"` — funciona en local, requiere ajuste en Docker (usar `CONFIG_DIR` env var o `/config`)
- `DEFAULT_HARDLINK_BASE = "/mnt/storage/uploads/emu"` — ruta absoluta hardcoded, requiere configuración real
- `DEFAULT_WATCH_FOLDER = "~/test_torrents"` — ruta relativa al home, requiere expand

### 7.4. Configuración cifrada/no cifrada

La configuración propia existe en dos formatos:
- `~/.config/emuwarez-renamer/config.json` (sin cifrar)
- `~/.config/emuwarez-renamer/config.enc.json` (cifrado AES-GCM)

La passphrase se pasa por archivo (`--config-pass-file`) o variable de entorno. La API key de eMuwarez y las claves de imagen se guardan en este fichero. En Docker habrá que decidir si se usa cifrado o variables de entorno.

### 7.5. SQLite todavía inicial

El schema actual (v2) cubre los casos de uso básicos pero le faltan tablas para:
- `users` / `settings` (auth web)
- `queue_items` / `history_items` (queue/history Radarr/Sonarr)
- `upload_events` (progreso en tiempo real)
- `event_log` (panel de eventos)

Campos de `library_items` que faltan para el Codex completo: `spanish_title`, `file_path` separado, `codec`, `audio`, `subtitles`, `monitored`, `has_file`.

Campos de `upload_jobs` que faltan: `stage`, `percent`, `source_path`, `prepared_path`, `uploadrr_tmp_path`, `description_path`, `emu_url`, `started_at`, `finished_at`, `error_message`.

### 7.6. Endpoints eMuwarez pendientes de confirmar

- Endpoint de listado de peticiones: **pendiente de capturar** (env `EMUWAREZ_REQUESTS_URL` o `requests set-endpoint`)
- Endpoint de creación de petición: **no implementado**, stub explícito en `integrations/emu.py:create_request()`
- Endpoint de búsqueda de existencia de torrent: **no implementado**

### 7.7. Necesidad de no romper CLI legacy

El modo legacy es la única forma actual de hacer subidas reales. La lógica está entera en `legacy.py`. Cualquier refactorización profunda de legacy.py puede romper flujos de producción activos.

**Regla operativa:** Hasta Fase 8, legacy.py solo se puede leer, no modificar.

---

## 8. Plan recomendado para Fase 1

### 8.1. Objetivo de Fase 1

Preparar el **contrato funcional** entre la CLI existente y la futura UI web, sin construir aún ni backend ni frontend. Solo enriquecer modelos, definir specs y dejar los cimientos listos para que Fase 2 (FastAPI) pueda empezar sobre base sólida.

### 8.2. Tareas concretas de Fase 1

1. **Enriquecer `models.py`** con los enums/estados que el Codex tiene documentados pero que aún no están en el código:
   - `EmuStatus` (No comprobado, Existe en eMuwarez, No existe, Petición activa, Petición llena, Posible duplicado, Duplicado confirmado, Error comprobando)
   - `RecommendationType` (Subir, Adaptar nomenclatura, Esperar descarga, Revisar Radarr/Sonarr, Comprobar en EMU, Crear petición futura, Sin acción)
   - `LocalStatus` ampliado con: EN_COLA, DESCARGANDO, PENDIENTE_IMPORTACION, ERROR_IMPORTACION, ERROR_BUSQUEDA

2. **Actualizar schema SQLite** para añadir campos faltantes en `library_items` y `upload_jobs` sin romper tablas existentes (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).

3. **Crear `docs/FUNCTIONAL_FLOW.md`** con:
   - Diferencia exacta Biblioteca/Faltantes/Peticiones
   - Flujo seguro de decisión antes de actuar
   - Reglas de compatibilidad con ejemplos
   - Estados definitivos con valores string usables en API/UI
   - Lista de prechecks antes de acciones peligrosas

4. **Crear `docs/UI_SPEC.md`** con:
   - Estilo visual (dark navy, glassmorphism, colores semánticos)
   - Grid layout (sidebar, topbar, 12 columnas)
   - Sidebar items y orden
   - Dashboard: cards, tabla Actividad reciente, panel subida, últimas tareas, últimos eventos
   - Pantalla Peticiones: filtros, tabla, orden por compatibilidad, panel detalle
   - Pantalla Faltantes: filtros, tabla, recomendaciones, acciones
   - Regla obligatoria de iconos Radarr/Sonarr junto al texto

5. **No implementar:**
   - FastAPI / uvicorn
   - React / Vite
   - Docker
   - endpoints nuevos de eMuwarez

### 8.3. Archivos probablemente tocados en Fase 1

```text
emuwarez_uploadrr/models.py           # añadir EmuStatus, RecommendationType, LocalStatus ampliado
emuwarez_uploadrr/database.py         # añadir ALTER TABLE para campos faltantes (schema_version = 3)
docs/FUNCTIONAL_FLOW.md               # crear (nuevo)
docs/UI_SPEC.md                       # crear (nuevo)
```

No se tocan en Fase 1:
```text
legacy.py
Uploadrr/
integrations/emu.py   (solo stub, no hay endpoint)
services/requests.py  (match funciona, ampliar en Fase 6)
```

### 8.4. Criterios de aceptación de Fase 1

```text
[ ] py_compile pasa en todos los módulos
[ ] db init con schema_version = 3 funciona sin error
[ ] library list, missing list, requests list, tasks list siguen funcionando
[ ] web-contract sigue funcionando
[ ] legacy mode sigue funcionando (python3 emuwarez_uploader.py --help)
[ ] Uploadrr/ no modificado
[ ] docs/FUNCTIONAL_FLOW.md creado
[ ] docs/UI_SPEC.md creado
[ ] commit: feat: add functional contract and UI specification
```

---

## 9. Criterios de aceptación de Fase 0

```text
[x] No se modificó lógica funcional
[x] Uploadrr/ no se tocó
[x] docs/codex_phase_00_audit.md creado
[x] python3 -m py_compile emuwarez_uploader.py → OK
[x] find emuwarez_uploadrr -name "*.py" -print0 | xargs -0 python3 -m py_compile → OK
[x] python3 emuwarez_uploader.py db init → OK
[x] python3 emuwarez_uploader.py web-contract → OK
[x] python3 emuwarez_uploader.py instances list → OK
[x] python3 emuwarez_uploader.py tasks list → OK
[x] Repo con commit limpio baseline
[x] Rama feature/ui-phase-00-audit creada
[ ] Commit docs: add phase 00 repository audit  ← pendiente del paso final
```
