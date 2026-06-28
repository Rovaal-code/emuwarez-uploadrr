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
- SQLite y modelos internos.
- Gestión de instancias Radarr/Sonarr.
- Conectores básicos Radarr/Sonarr.
- Sincronización de biblioteca.
- Listado/detalle de biblioteca.
- Faltantes.
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
- Suite de tests completa: `tests/test_web_app.py` (29 tests) + `tests/test_setup_auth.py` (40 tests).

Pendiente para fases posteriores:

- Capturar endpoint real de peticiones EMU.
- Crear peticiones EMU desde la app.
- Mejorar cruce por detalle TMDb/IMDb de la petición.
- Radarr/Sonarr sync real con queue/history.
- Auth y setup wizard completos.
- Frontend React.
- Docker.
