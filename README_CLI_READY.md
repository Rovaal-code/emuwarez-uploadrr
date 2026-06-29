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
- Docker.
- SettingsPage con formularios de configuración real (incluyendo `hardlink_base`, `uploadrr_path`, API keys).
- TasksPage con datos reales.
- Modificación de título interno MKV (`mkvpropedit`).
