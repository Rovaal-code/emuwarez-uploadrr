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
- Contrato funcional para web.
- Estructura para peticiones EMU y coincidencias.
- Límite de 1 hora para refresco manual de peticiones.
- Stubs seguros para crear peticiones EMU.

Pendiente para fases posteriores:

- Capturar endpoint real de peticiones EMU.
- Crear peticiones EMU desde la app.
- Mejorar cruce por detalle TMDb/IMDb de la petición.
- API web FastAPI.
- Frontend.
- Docker.
