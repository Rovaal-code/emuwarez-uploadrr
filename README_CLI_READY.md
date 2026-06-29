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

## Peticiones EMU

El límite manual queda preparado a 1 vez por hora. Si intentas refrescar antes:

```text
Peticiones actualizadas hace menos de una hora. Disponible en X min.
```

La lectura real de peticiones EMU necesita capturar el endpoint. Mientras tanto puedes guardarlo cuando lo tengas:

```bash
python3 emuwarez_uploader.py requests set-endpoint "https://..."
```

O usar variable de entorno:

```bash
EMUWAREZ_REQUESTS_URL="https://..." python3 emuwarez_uploader.py requests sync
```

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

Pendiente para fases posteriores:

- Capturar endpoint real de peticiones EMU.
- Crear peticiones EMU desde la app.
- Mejorar cruce por detalle TMDb/IMDb de la petición.
- Frontend React.
- Docker.
