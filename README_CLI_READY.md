# eMuwarez Uploadrr - CLI ready v2

Esta versión mantiene el uploader heredado funcionando, pero añade una CLI moderna y una capa de servicios/SQLite preparada para la futura interfaz web.

## Qué cambia respecto a `refactor_v1`

- El modo antiguo sigue funcionando:

```bash
python3 emuwarez_uploader.py "/ruta/pelicula.mkv" --dry-run
python3 emuwarez_uploader.py --configure
python3 emuwarez_uploader.py --doctor
```

- Nuevo modo CLI, espejo funcional de la futura web:

```bash
python3 emuwarez_uploader.py db init
python3 emuwarez_uploader.py instances list
python3 emuwarez_uploader.py instances add radarr --name "Radarr principal" --url http://radarr:7878 --api-key TU_KEY
python3 emuwarez_uploader.py instances add sonarr --name "Sonarr principal" --url http://sonarr:8989 --api-key TU_KEY
python3 emuwarez_uploader.py instances test
python3 emuwarez_uploader.py sync
python3 emuwarez_uploader.py sync --episodes
python3 emuwarez_uploader.py library list
python3 emuwarez_uploader.py library show 1
python3 emuwarez_uploader.py missing list
python3 emuwarez_uploader.py requests list
python3 emuwarez_uploader.py requests sync
python3 emuwarez_uploader.py tasks list
python3 emuwarez_uploader.py web-contract
```

## Conceptos cerrados para la web

Columnas principales:

- `Estado`: Disponible / Faltante / Subiendo / Subido / Error
- `Petición`: Sin petición / Compatible / Parcial / No compatible / Llena
- `Nomenclatura`: Correcta / No adaptada / N/A

Acciones equivalentes:

- `Adaptar nomenclatura` → `prepare <id>`
- `Subir` → `upload <id>`
- `Comprobar/actualizar peticiones` → `requests sync`
- `Crear petición EMU` → preparado como comando, pero desactivado hasta capturar el POST real de eMuwarez

## SQLite

La base local se crea en:

```text
~/.config/emuwarez-renamer/emuwarez_uploadrr.db
```

Contiene tablas para:

- `instances`
- `library_items`
- `request_items`
- `request_matches`
- `task_runs`
- `upload_jobs`
- `app_state`

## Peticiones eMuwarez y compatibilidad

eMuwarez usa la plataforma UNIT3D. Las peticiones (bounties/want list) se leen directamente:

```bash
python3 emuwarez_uploader.py requests sync             # sincronizar (máx 1 vez/hora)
python3 emuwarez_uploader.py requests sync --force     # forzar sin límite de tiempo
python3 emuwarez_uploader.py requests list             # listar peticiones
python3 emuwarez_uploader.py requests list --search "título"
python3 emuwarez_uploader.py requests show 42          # detalle + cruce con biblioteca
python3 emuwarez_uploader.py requests match            # recalcular todos los cruces
python3 emuwarez_uploader.py requests mark-reviewed 42 # marcar petición como revisada
```

El límite mínimo entre syncs es **1 hora**. Si intentas antes:

```text
Peticiones actualizadas hace menos de una hora. Disponible en X min.
```

### Motor de compatibilidad

Cada petición EMU se cruza automáticamente con la biblioteca local:

| Estado | Condición |
|--------|-----------|
| Compatible | Resolución y source locales ≥ lo pedido (o sin restricción) |
| Parcial | Solo uno de los dos criterios no cumple |
| No compatible | Ambos criterios fallan |
| Llena | La petición ya está satisfecha en eMuwarez |
| Sin coincidencia | Ningún ítem local coincide con la petición |

Prioridad de cruce: TMDb ID → IMDb ID → Título exacto → Similitud por palabras.

### API web de peticiones

```
GET  /api/requests                       — lista paginada + estado de compatibilidad
GET  /api/requests/sync-status           — estado de la última sync
POST /api/requests/sync                  — sincronizar ({ force: bool })
GET  /api/requests/{id}                  — detalle + mejor cruce con biblioteca
POST /api/requests/{id}/match            — re-cruzar una petición concreta
POST /api/requests/{id}/mark-reviewed    — marcar como revisada
POST /api/missing/{id}/create-emu-request — BLOQUEADO (stub seguro)
```

El endpoint `create-emu-request` permanece bloqueado hasta capturar y validar el POST real desde DevTools → Network.

## Pruebas recomendadas

```bash
python3 -m py_compile emuwarez_uploader.py
find emuwarez_uploadrr -name "*.py" -print0 | xargs -0 python3 -m py_compile
python3 emuwarez_uploader.py --help
python3 emuwarez_uploader.py db init
python3 emuwarez_uploader.py web-contract
python3 emuwarez_uploader.py "/ruta/a/prueba.mkv" --dry-run
```

## Backend web base

Instalar dependencias web:

```bash
pip install -e ".[web]"
# o con el venv del proyecto:
.venv/bin/pip install -e ".[web]"
```

Arrancar servidor:

```bash
python3 emuwarez_uploader.py web serve --port 9494
python3 emuwarez_uploader.py web info
```

URLs disponibles:

```
http://localhost:9494/api/health
http://localhost:9494/api/setup/status
http://localhost:9494/api/runtime
http://localhost:9494/api/contract/json
http://localhost:9494/api/docs
```

Ejecutar tests:

```bash
.venv/bin/pytest tests/ -q
```

## Frontend web

Instalar y arrancar el frontend en desarrollo (proxy a `:9494`):

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

Construir para producción (sirve desde el backend en `:9494`):

```bash
cd frontend
npm run build
cd ..
python3 emuwarez_uploader.py web serve --port 9494
# → http://localhost:9494 sirve API + frontend
```

Páginas implementadas:

```
Login          — autenticación contra /api/auth/login
Setup wizard   — asistente 7 pasos: admin → base → uploadrr → tmdb → emu → instancias → completar
Dashboard      — tarjetas resumen + actividad reciente (datos reales de /api/dashboard/*)
Biblioteca     — tabla filtrable y paginada desde /api/library
Faltantes      — tabla desde /api/missing con estados de cola
Instancias     — gestión con test y sync por instancia
Peticiones     — tabla real con motor de compatibilidad, filtros y panel lateral de detalle
Subidas/Tareas/Logs/Configuración — placeholders preparados
```

Ver más comandos con:

```bash
python3 emuwarez_uploader.py web info
```

## Sincronización Radarr/Sonarr y biblioteca

Añadir instancias y sincronizar biblioteca:

```bash
python3 emuwarez_uploader.py instances list
python3 emuwarez_uploader.py instances add radarr --name "Radarr principal" --url http://radarr:7878 --api-key TU_KEY
python3 emuwarez_uploader.py instances add sonarr --name "Sonarr principal" --url http://sonarr:8989 --api-key TU_KEY
python3 emuwarez_uploader.py instances test
python3 emuwarez_uploader.py sync --episodes
python3 emuwarez_uploader.py library list
python3 emuwarez_uploader.py library show 1
python3 emuwarez_uploader.py missing list
```

Estados locales detectados automáticamente:

```
Disponible        — el archivo existe en Radarr/Sonarr
Faltante          — no hay archivo
En cola           — esperando en el cliente de descarga
Descargando       — descarga activa
Pendiente de importar — descarga completa, esperando importación
Error de importación — falló la importación
Error de búsqueda — Sonarr/Radarr no encontró fuentes
```

API web real (requiere Bearer token):

```
GET  /api/instances                    — listar instancias (sin API key completa)
POST /api/instances                    — añadir instancia
POST /api/instances/{id}/test         — test de conexión real
POST /api/instances/{id}/sync         — sincronizar esa instancia
POST /api/sync                        — sincronizar todas las instancias
GET  /api/dashboard/summary           — contadores reales de biblioteca
GET  /api/dashboard/activity          — últimas tareas ejecutadas
GET  /api/library                     — biblioteca filtrada/paginada
GET  /api/library/{id}                — detalle de ítem
GET  /api/missing                     — faltantes/en cola/con error
```

## Setup wizard y autenticación

Setup desde CLI:

```bash
python3 emuwarez_uploader.py web setup-status
python3 emuwarez_uploader.py web create-admin --username admin
# o con contraseña en variable de entorno:
EMUWAREZ_ADMIN_PASSWORD="MiPass1!segura" python3 emuwarez_uploader.py web create-admin --username admin
```

Flujo de setup vía API (requiere servidor arrancado):

```
POST /api/setup/admin      ← primer paso, sin auth
POST /api/auth/login       ← obtener token
POST /api/setup/base       ← nombre y zona horaria (requiere token)
POST /api/setup/uploadrr   ← ruta de Uploadrr (requiere token)
POST /api/setup/tmdb       ← API key TMDb (requiere token)
POST /api/setup/emu        ← API key eMuwarez (requiere token)
POST /api/setup/instances  ← añadir Radarr/Sonarr (requiere token)
POST /api/setup/complete   ← finalizar (requiere token)
```

Todas las rutas sensibles de la API (dashboard, biblioteca, faltantes, peticiones,
subidas, tareas, logs, config) requieren `Authorization: Bearer <token>`.

Reglas de contraseña: mínimo 12 caracteres, al menos minúscula, mayúscula, dígito y símbolo.

## Estado de implementación

Implementado:

- CLI moderna con subcomandos.
- SQLite y modelos internos (schema v3).
- Gestión de instancias Radarr/Sonarr (add/list/test/sync/update).
- Clientes reales Radarr/Sonarr con jerarquía de errores (`ArrClientError`, `ArrConnectionError`, `ArrAuthError`, `ArrApiError`).
- Detección de estado por cola: descargando / en cola / pendiente de importar / error de importación.
- Sincronización completa de biblioteca con queue maps.
- Listado/detalle de biblioteca con filtros y paginación.
- Faltantes (todos los estados no disponibles).
- Dashboard: resumen de contadores + actividad reciente.
- Tareas.
- Preparar/subir por ID usando el motor heredado.
- Contrato funcional para web (`docs/ui_backend_contract.md`).
- Estructura para peticiones EMU y coincidencias.
- Límite de 1 hora para refresco manual de peticiones.
- Stubs seguros para crear peticiones EMU.
- Backend FastAPI base (`emuwarez_uploadrr/web/`).
- Endpoints: `/api/health`, `/api/runtime`, `/api/setup/status`, `/api/contract/json`.
- Setup wizard completo: `POST /api/setup/admin`, `/base`, `/uploadrr`, `/tmdb`, `/emu`, `/instances`, `/complete`.
- Autenticación local con tokens opacos: `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`.
- Todos los endpoints sensibles protegidos con `Authorization: Bearer <token>`.
- Seguridad: PBKDF2-SHA256 (210k iteraciones), `hmac.compare_digest`, tokens solo como hash en BD.
- Schema SQLite v3: tablas `users`, `auth_sessions`, `settings`.
- Comandos CLI: `web setup-status`, `web create-admin`.
- Suite de tests completa: 140 tests (web_app, setup_auth, arr_integrations, library_sync, dashboard_library_api).

Implementado en Fase 5B:

- Motor de compatibilidad (`services/compatibility.py`): normalización, cruce por TMDb/IMDb/título, clasificación Compatible/Parcial/No compatible/Llena.
- Cliente UNIT3D para eMuwarez: `emu_get_requests`, `emu_fetch_all_pages` con paginación automática, auth `?api_token=`.
- Endpoints reales: `GET /api/requests`, `POST /api/requests/sync`, detalle, re-cruce, marcar revisada.
- Pantalla Peticiones real en frontend con filtros, badges de compatibilidad y panel lateral.
- CLI: `requests mark-reviewed <id>`.
- Rate limit 1 hora con `--force` override.
- Dashboard summary enriquecido con estadísticas EMU.

## Ejecución controlada de Uploadrr

La ejecución real de Uploadrr requiere confirmación explícita. Por defecto siempre es dry-run.

```bash
# Ver todos los jobs de subida
python3 emuwarez_uploader.py upload jobs

# Ver detalle de un job
python3 emuwarez_uploader.py upload job 1

# Previsualizar el comando sin ejecutar nada
python3 emuwarez_uploader.py upload start 1 --dry-run

# Iniciar ejecución real (requiere confirmación exacta)
python3 emuwarez_uploader.py upload start 1 --apply --confirm INICIAR_UPLOADRR

# Ver logs de ejecución (sin secretos)
python3 emuwarez_uploader.py upload logs 1

# Cancelar un job en ejecución
python3 emuwarez_uploader.py upload cancel 1
```

Advertencias de seguridad:

```text
- start sin --apply equivale a --dry-run (no ejecuta nada).
- Se requiere --confirm INICIAR_UPLOADRR exacto para ejecución real.
- Los logs nunca muestran API keys ni secrets.
- No se crea ninguna petición EMU automáticamente.
- No se modifica el archivo original ni el título MKV.
- No se modifica nada dentro de Uploadrr/.
```

Implementado en Fase 6B — Aplicación segura de nomenclatura:

- Servicio `filesystem_apply.py`: planificación y ejecución de hardlinks con contrato de seguridad estricto (sin modificación del archivo original, sin ejecución de Uploadrr/mkvpropedit, sin copia cross-device).
- `build_safe_apply_plan()`: valida origen, destino, path traversal, EXDEV, sin symlinks como origen.
- `apply_hardlink_plan()`: crea directorio padre + `os.link()` en modo real; solo previsualización en `dry_run=True`.
- `apply_nomenclature_proposal()` con token de confirmación `APLICAR_NOMENCLATURA`: requiere `dry_run=False, apply=True, confirmation="APLICAR_NOMENCLATURA"` para writes reales.
- `dry_run=True` siempre tiene precedencia sobre `apply=True`.
- Tabla `filesystem_operations`: historial de operaciones con estado, rutas y resultado JSON.
- Columnas nuevas: `nomenclature_proposals.(applied_path, applied_at, operation_id)`, `library_items.(prepared_path, nomenclature_applied_at)`.
- Schema SQLite v5.
- Endpoint `POST /api/library/{id}/adapt-nomenclature` actualizado con resultado real (`NomenclatureApplyResult`).
- Endpoint `GET /api/library/{id}/nomenclature/operations`: historial de operaciones.
- `upload_preflight`: prefiere `prepared_path` sobre `path`; avisa si no se ha aplicado nomenclatura; añade `using_prepared_path` al preview de comando.
- CLI `nomenclature apply <id> [--dry-run] [--apply --confirm APLICAR_NOMENCLATURA]`.
- Frontend: NomenclatureModal con sección de confirmación y creación de hardlink. UploadPreflightModal con indicador "preparado"/"original".
- 43 tests nuevos (filesystem_apply, nomenclature_apply, nomenclature_apply_api). Total: 329 tests.

Implementado en Fase 6C — Ejecución controlada de Uploadrr:

- Servicio `upload_execution.py` con contrato de seguridad estricto.
- Ejecución de Uploadrr mediante `subprocess.Popen` sin `shell=True`.
- Token de confirmación `INICIAR_UPLOADRR` requerido para ejecución real.
- `dry_run=True` por defecto; siempre prevalece.
- Tabla `upload_job_logs`: logs línea a línea con `stream` (stdout/stderr/system) y `level`.
- Columnas nuevas en `upload_jobs`: `exit_code`, `process_id`. Schema SQLite v6.
- Redacción de secretos antes de guardar en logs (`api_token`, `api_key`, `emu_api_key`, `tmdb_api_key`).
- API: `GET /api/uploads`, `GET /api/uploads/{id}`, `GET /api/uploads/{id}/logs`, `POST /api/uploads/{id}/start`, `POST /api/uploads/{id}/cancel`. Todos protegidos con Bearer token.
- CLI: `upload jobs`, `upload job <id>`, `upload logs <id>`, `upload start <id> [--dry-run|--apply --confirm INICIAR_UPLOADRR]`, `upload cancel <id>`.
- Frontend: `UploadPreflightModal` con botón activo, input de confirmación y dry-run.
- Frontend: `UploadsPage` con tabla completa, panel de logs y modal de inicio.
- 43 tests nuevos (upload_execution, upload_execution_api, upload_logs_redaction). Total: 372 tests.

Pendiente para fases posteriores:

- Crear peticiones EMU desde la app (requiere capturar POST real desde DevTools).
- SettingsPage con formularios de configuración real (incluyendo `hardlink_base`, `uploadrr_path`, API keys).
- TasksPage con datos reales.
- Modificación de título interno MKV (`mkvpropedit`).

## Docker / despliegue homelab

### Inicio rápido

```bash
cp .env.example .env
docker compose -f docker-compose.example.yml up -d --build
```

La interfaz web estará disponible en `http://localhost:9494`.

### Volúmenes

| Ruta en contenedor | Descripción |
|---|---|
| `/config` | Configuración persistente (SQLite, settings). Montar como volumen. |
| `/opt/Uploadrr` | Directorio de Uploadrr externo (bind mount). **Nunca va dentro de la imagen.** |
| `/data` | Raíz de datos (media + uploads). Usar raíz común para evitar EXDEV. |

### Hardlinks y EXDEV

Para que la creación de hardlinks funcione, el directorio fuente (`/data/media`) y
el `hardlink_base` (`/data/uploads/emu`) deben estar en el **mismo filesystem**.

Si montas media y uploads en dispositivos distintos, la creación de hardlinks fallará
con error `EXDEV (cross-device link)`. Configura `hardlink_base` en el setup web
apuntando dentro del mismo montaje que el media.

### Configuración de Uploadrr

Monta Uploadrr como bind mount externo en `/opt/Uploadrr` y configura la ruta
desde el setup web o CLI tras el primer arranque. Uploadrr nunca se incluye en la imagen Docker.

### Gestión del contenedor

```bash
# Ver logs
docker compose -f docker-compose.example.yml logs -f

# Parar
docker compose -f docker-compose.example.yml down

# Actualizar y relanzar
docker compose -f docker-compose.example.yml up -d --build
```

## Smoke test Docker y diagnóstico

### Smoke test completo

```bash
bash scripts/docker-smoke-test.sh
```

Construye la imagen, arranca el contenedor con directorios temporales, valida
todos los endpoints HTTP, verifica que Uploadrr no está dentro de la imagen
y limpia automáticamente al terminar.

### Diagnóstico de runtime

```bash
python3 emuwarez_uploader.py web doctor
```

Muestra el estado del CONFIG_DIR, base de datos, frontend, montaje de Uploadrr,
`hardlink_base` y variables de entorno, sin mostrar secretos.

### Guía de despliegue completa

Ver: [docs/DEPLOYMENT_DOCKER.md](docs/DEPLOYMENT_DOCKER.md)

---

## Diagnóstico Radarr/Sonarr y verificación filesystem

> Radarr/Sonarr son la fuente principal de biblioteca.
> Jellyfin no es necesario para determinar qué contenido está disponible para el flujo de subida.
> La verificación filesystem solo comprueba que el archivo exista y sea utilizable; no modifica archivos.

### ARR health

```bash
# Mostrar estado de instancias ARR (solo lectura)
python3 emuwarez_uploader.py arr health

# Refrescar queue e historial ARR y actualizar diagnósticos en BD
python3 emuwarez_uploader.py arr refresh-health
python3 emuwarez_uploader.py arr refresh-health --no-history   # sin historial
python3 emuwarez_uploader.py arr refresh-health --history-size 200
```

### Verificación de archivos

```bash
# Verificar todos los archivos en disco (solo lectura, no modifica nada)
python3 emuwarez_uploader.py library verify-files

# Verificar con filtros
python3 emuwarez_uploader.py library verify-files --status Disponible --limit 100

# Verificar un archivo concreto
python3 emuwarez_uploader.py library verify-file 42
```

### Recomendaciones

```bash
# Recalcular recomendaciones para toda la biblioteca
python3 emuwarez_uploader.py library recommendations

# Ver recomendación de un item concreto
python3 emuwarez_uploader.py library recommendation 42
```

### Diagnósticos

```bash
# Ver diagnósticos de biblioteca (estado, archivo, queue, acción recomendada)
python3 emuwarez_uploader.py library diagnostics
python3 emuwarez_uploader.py library diagnostics --status Disponible --limit 100

# Faltantes enriquecidos con queue/history/recomendación
python3 emuwarez_uploader.py missing diagnostics
```

### Endpoints API (Phase 8A)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/arr/health` | Salud de instancias ARR |
| POST | `/api/arr/health/refresh` | Refrescar queue e historial ARR |
| POST | `/api/library/verify-files` | Verificar archivos en disco |
| POST | `/api/library/{id}/verify-file` | Verificar archivo de un item |
| POST | `/api/library/recommendations/refresh` | Recalcular recomendaciones |
| GET | `/api/library/{id}/recommendation` | Recomendación de un item |
| GET | `/api/library/diagnostics` | Diagnósticos de biblioteca |
| GET | `/api/missing/diagnostics` | Faltantes enriquecidos |

Todos requieren Bearer token.

---

## Readiness y priorización de peticiones eMuwarez

Fase 8B añade un motor de readiness por petición que responde:
- ¿Tengo algo local que sirva para esta petición?
- ¿Está disponible en disco?
- ¿Cumple calidad/source/resolución?
- ¿Necesita nomenclatura? ¿Preflight? ¿Listo para subir?
- ¿Cuál es la acción recomendada? ¿Y la prioridad?

**Readiness no crea peticiones. Readiness no sube contenido automáticamente. Solo calcula la mejor acción recomendada usando datos locales, ARR y eMuwarez read-only.**

```bash
# Recalcular readiness para todas las peticiones
python3 emuwarez_uploader.py requests readiness-refresh

# Ver lista de readiness ordenada por prioridad
python3 emuwarez_uploader.py requests readiness

# Ver readiness de una petición concreta
python3 emuwarez_uploader.py requests readiness 31

# Ver peticiones priorizadas (high > medium > low > blocked)
python3 emuwarez_uploader.py requests prioritized

# Ver candidatos locales para una petición
python3 emuwarez_uploader.py requests candidates 31
```

Salida ejemplo:

```
ID    Título              Estado readiness   Acción              Prioridad   Score
31    Movie A             ready_to_upload    upload              high        91
32    Serie B S01          needs_nomenclature adapt_nomenclature  high        84
33    Movie C             downloading        wait_download       medium      61
34    Movie D             import_error       review_arr          blocked     0
```

### Endpoints API (Phase 8B)

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/requests/readiness/refresh` | Recalcular readiness (todas las peticiones) |
| GET | `/api/requests/readiness` | Listar readiness con filtros |
| GET | `/api/requests/prioritized` | Peticiones ordenadas por prioridad |
| GET | `/api/requests/{id}/readiness` | Readiness de una petición |
| POST | `/api/requests/{id}/readiness/evaluate` | Evaluar readiness de una petición |
| GET | `/api/requests/{id}/candidates` | Candidatos locales para una petición |

Todos requieren Bearer token. Sin token: 401.

---

## Cola operativa unificada (Phase 8C)

Fase 8C añade una cola operativa que responde a: **¿Qué hago ahora?** La cola agrega items de readiness, biblioteca, subidas ARR y jobs de upload en una única vista priorizada.

**La cola NO ejecuta acciones. NO sube contenido. NO crea peticiones. Es read-only sobre todas las fuentes.**

Prioridades: `critical` > `high` > `medium` > `low` > `blocked`

```bash
# Refrescar la cola desde todas las fuentes
python3 emuwarez_uploader.py queue refresh

# Ver resumen de la cola
python3 emuwarez_uploader.py queue summary

# Listar items pendientes (por defecto excluye resolved/ignored)
python3 emuwarez_uploader.py queue list
python3 emuwarez_uploader.py queue list --bucket critical
python3 emuwarez_uploader.py queue list --status ready

# Ver detalle de un item
python3 emuwarez_uploader.py queue show <id>

# Marcar item como resuelto manualmente
python3 emuwarez_uploader.py queue resolve <id>

# Ignorar item
python3 emuwarez_uploader.py queue ignore <id>
```

Salida ejemplo (`queue list`):

```
#   Prioridad   Estado    Acción           Tipo                 Título
1   CRITICAL    ready     upload           request_readiness    Movie A
2   HIGH        ready     adapt_nomenclature request_readiness  Serie B S01
3   MEDIUM      waiting   wait_download    request_readiness    Movie C
4   MEDIUM      open      run_preflight    upload_job           Movie D
5   BLOCKED     blocked   review_arr       arr_issue            Movie E
```

### Endpoints API (Phase 8C)

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/operational-queue/refresh` | Reconstruir cola desde todas las fuentes |
| GET | `/api/operational-queue` | Listar items con filtros |
| GET | `/api/operational-queue/summary` | Resumen por estado y bucket |
| GET | `/api/operational-queue/{id}` | Detalle de un item |
| POST | `/api/operational-queue/{id}/resolve` | Marcar como resuelto |
| POST | `/api/operational-queue/{id}/ignore` | Ignorar item |

Todos requieren Bearer token. Sin token: 401.

El dashboard incluye un panel "Qué hacer ahora" con los 5 items más urgentes de la cola.

---

## Ejecución guiada desde la cola (Phase 9A)

Fase 9A añade ejecución guiada por item de la cola. Cada item de la cola expone un plan de acción que indica exactamente **dónde y cómo** ejecutar la acción correspondiente, sin ejecutar nada automáticamente ni sin confirmación.

### Contrato de seguridad

- `execute_safe_queue_action` solo ejecuta: `verify_file`, `refresh_queue_item`, `view_plan`.
- Nunca ejecuta Uploadrr, aplica nomenclatura, crea hardlinks, crea peticiones eMuwarez ni modifica Radarr/Sonarr.
- Las acciones bloqueadas devuelven `409 Conflict` con la ruta exacta del flujo guiado donde ejecutarlas.

### CLI — queue actions

```bash
# Listar acciones disponibles para un item
python3 emuwarez_uploader.py queue actions <id>

# Ver plan de acción completo
python3 emuwarez_uploader.py queue action-plan <id>

# Ejecutar acción segura (verify_file, view_plan)
python3 emuwarez_uploader.py queue execute-safe <id> [--action verify_file]

# Ver historial de eventos de un item
python3 emuwarez_uploader.py queue events <id> [--limit 20]
```

Ejemplo (`queue action-plan 3`):

```
Item #3 — Plan de acción
  Action : upload
  Flow   : upload_execution
  Route  : /uploads  →  modal: upload_confirmation
  Token  : INICIAR_UPLOADRR  (requiere confirmación)
  Bucket : HIGH
  Estado : ready
```

### Endpoints API (Phase 9A)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/operational-queue/{id}/actions` | Listar acciones disponibles |
| GET | `/api/operational-queue/{id}/action-plan` | Plan completo de acción guiada |
| POST | `/api/operational-queue/{id}/execute-safe-action` | Ejecutar acción segura (body: `{"action": str}`) |
| GET | `/api/operational-queue/{id}/action-events` | Historial de eventos del item |

Todos requieren Bearer token. Sin token: 401. Acción bloqueada: 409.

### UI — QueuePage

Cada fila de la cola muestra botón **Plan** que abre el `QueueActionPanel` con:
- Resumen del plan (acción, flow, prioridad, estado)
- Ruta UI donde ejecutar la acción y, si aplica, modal y token de confirmación
- Botones de acción segura inline (verde) — solo `verify_file` y `view_plan`
- Historial de eventos colapsable

El panel "Qué hacer ahora" del Dashboard incluye botón **Acción →** que navega a la Cola.

---

## E2E controlado en Docker (Phase 9B)

Valida el flujo completo de la app en Docker con datos simulados, sin tocar servicios reales.

### Uso

```bash
# E2E completo (construye imagen, arranca contenedor, siembra datos, valida flujo, limpia)
bash scripts/docker-e2e-demo.sh

# Mantener el contenedor y el tmpdir al terminar (para depuración)
KEEP_CONTAINER=1 bash scripts/docker-e2e-demo.sh

# Usar un puerto diferente
PORT=9595 bash scripts/docker-e2e-demo.sh
```

### Qué valida

- La imagen Docker construye correctamente
- El contenedor arranca y responde en `/api/health`
- `demo seed` crea biblioteca simulada y petición compatible
- `library verify-files` y `library recommendations` funcionan
- `requests readiness-refresh` y `requests prioritized` funcionan
- `queue refresh`, `queue summary`, `queue list` funcionan
- `queue action-plan 1` y `queue execute-safe 1` funcionan
- `nomenclature preview 1` funciona
- `upload preflight 1` (dry-run) funciona
- El frontend devuelve HTML en `/`, `/dashboard`, `/queue`
- Uploadrr/ NO está dentro de la imagen

### Garantías de aislamiento

- Todo escribe en un `tmpdir` temporal creado con `mktemp -d`, limpiado automáticamente al salir
- No usa Radarr/Sonarr reales
- No usa eMuwarez real
- No ejecuta Uploadrr real
- No sube contenido real
- No modifica `Uploadrr/`
- No expone API keys reales

### Datos demo

El comando `demo seed` siembra datos mínimos:

```bash
python3 emuwarez_uploader.py demo seed \
    --media-root /data/media \
    --prepared-root /data/uploads/emu \
    --confirm DEMO_SEED

python3 emuwarez_uploader.py demo reset --confirm DEMO_RESET
```

Crea:
- 1 instancia Radarr fake (deshabilitada, api_key ficticia)
- 1 `library_item` movie "Demo Movie (2024)" con archivo `.mkv` simulado
- 1 `request_item` compatible con TMDb/IMDb demo
- 1 `request_match` Compatible entre los anteriores

El archivo simulado es un fichero de texto con extensión `.mkv`, suficiente para que los verificadores de existencia/extensión pasen. No es un vídeo real.

---

## Nomenclatura editable, Source Assistant y título MKV interno (Phase 10A)

### Source Assistant

Catálogos de fuentes y proveedores EMU disponibles en la API y CLI:

```bash
emuwarez nomenclature sources
emuwarez nomenclature providers
```

Fórmula EMU: `[Título][Año][Resolución][Fuente][Códec][Audios+Canales][SUBS] - [Uploader]`

Solo `WEB-DL` acepta prefijo de proveedor: `AMZN WEB-DL`, `NF WEB-DL`, `DSNP WEB-DL`…

### Campos editables

```bash
# Ver campos actuales de un ítem
emuwarez nomenclature fields 42

# Previsualizar con campos modificados (sin guardar)
emuwarez nomenclature preview-fields 42 \
  --fields-json '{"title":"Dune","year":"2021","resolution":"1080p","source":"WEB-DL","provider":"AMZN","video_codec":"H.265","audio_summary":"DDP5.1","subs":"SPA","tag":"EMUWAREZ"}'
```

API equivalente:
- `GET /api/library/{id}/nomenclature/fields`
- `POST /api/library/{id}/nomenclature/preview-fields`
- `POST /api/library/{id}/nomenclature/save-fields`

### Título interno MKV

Escribe el título interno al `.mkv` en `prepared_path` usando `mkvpropedit`. Requiere token de confirmación.

```bash
# Previsualizar sin modificar nada
emuwarez mkv-title preview 42

# Aplicar (dry-run por defecto)
emuwarez mkv-title apply 42 --dry-run

# Aplicar real (requiere token)
emuwarez mkv-title apply 42 --apply --confirm APLICAR_TITULO_MKV
```

API equivalente:
- `GET /api/library/{id}/mkv-title/preview`
- `POST /api/library/{id}/mkv-title/apply` — body: `{dry_run, apply, confirmation}`

Restricciones de seguridad:
- `shell=False` en subprocess (sin interpolación de shell)
- Solo aplica a ficheros `.mkv` en `prepared_path` (nunca `source_path`)
- Token `APLICAR_TITULO_MKV` obligatorio para escritura real
- `mkvpropedit` no disponible → aviso, sin bloqueo del flujo

### Sugerencia de proveedor TMDb

Al previsualizar campos con `source=WEB-DL`, la API devuelve los proveedores disponibles en TMDb
para la región configurada (`tmdb_watch_region`, por defecto `ES`). Los proveedores disponibles
se marcan con `★` en el desplegable del frontend. El proveedor final siempre es elección del usuario.
