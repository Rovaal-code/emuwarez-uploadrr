# eMuwarez Uploadrr

[![CI](https://github.com/Kisnov/emuwarez-uploadrr/actions/workflows/ci.yml/badge.svg)](https://github.com/Kisnov/emuwarez-uploadrr/actions/workflows/ci.yml)
[![Imagen](https://github.com/Kisnov/emuwarez-uploadrr/actions/workflows/imagen.yml/badge.svg)](https://github.com/Kisnov/emuwarez-uploadrr/actions/workflows/imagen.yml)

Aplicación web autoalojada (+ CLI) para subir a **[eMuwarez](https://emu-warez.com)** (tracker UNIT3D) desde tu
biblioteca de **Radarr**/**Sonarr**. Sincroniza la biblioteca, la cruza con las peticiones abiertas de eMuwarez,
genera el nombre con la nomenclatura del tracker, enlaza los ficheros en una carpeta de subidas y lanza la subida
con [Uploadrr-EMU](https://github.com/Kisnov/Uploadrr-EMU), que va dentro de la imagen. Todo desde la interfaz web.

## Qué hace

- **Panel**: recomendaciones de qué subir y las últimas tareas ejecutadas.
- **Biblioteca**: películas y series de Radarr/Sonarr con su estado (Disponible, Faltante, Subiendo, Subido,
  Error) y si llevan castellano (Ambos, Audio, Subs, No). Filtros por columna con varias opciones a la vez.
  En la ficha de cada ítem: MediaInfo, pistas, temporadas y capítulos.
- **Peticiones**: las peticiones abiertas de eMuwarez cruzadas con lo que ya tienes (compatible, parcial, no
  compatible), con prioridad y candidato sugerido.
- **Subidas**: un asistente comprueba el contenido, genera el nombre (también para packs de temporada) y lanza
  Uploadrr-EMU. Opcionalmente renombra y reordena las pistas (cuatro modos, apagado por defecto). Progreso en
  directo, límite de subidas en paralelo y varios grupos de subida guardados para el tag.
- **Guía**: cada campo de la nomenclatura de eMuwarez, con ejemplos y de dónde lo saca la aplicación.
- **Tareas**: sincronización periódica de biblioteca y peticiones, y aviso de versión nueva en la campana.
- **Instancias**: tus Radarr y Sonarr.
- **Logs**: registros de la aplicación y de cada subida, con los secretos redactados.
- **Configuración**: claves de TMDb, eMuwarez y hosts de imágenes (se comprueban contra el proveedor),
  mapeo de rutas, notificaciones (Discord, Telegram, webhook), diagnóstico, backup y mantenimiento.

## Arranque rápido (Docker Compose)

Requiere Docker 24+ con Compose v2. No hace falta clonar el repo: copia esto en un `docker-compose.yml`, ajusta
las rutas de los volúmenes y levántalo. Usa la imagen publicada en `ghcr.io/kisnov/emuwarez-uploadrr`, así que no
compila nada.

```yaml
services:
  emuwarez-uploadrr:
    image: ghcr.io/kisnov/emuwarez-uploadrr:${EMUWAREZ_UPLOADRR_TAG:-latest}
    container_name: emuwarez-uploadrr
    restart: unless-stopped

    ports:
      - "${EMUWAREZ_UPLOADRR_PORT:-9494}:9494"

    # Ajusta PUID/PGID al UID/GID del usuario propietario de los archivos de media
    user: "${PUID:-1000}:${PGID:-1000}"

    # Límite de recursos del contenedor. Ajusta a lo que tenga disponible tu
    # equipo: es lo que marca cuántas "Subidas en Paralelo" (Configuración)
    # se sostienen de verdad, porque cada subida activa puede llegar a saturar
    # un núcleo entero (hasheo del torrent) y usar ~0.8 GB de RAM
    # (capturas/remux/transferencia). Con estos 2 núcleos y 2 GB caben
    # teóricamente 2 subidas en paralelo reales. Si quieres más, sube los dos
    # valores a la vez: subir "Subidas en Paralelo" sin darle más CPU y RAM al
    # contenedor no acelera nada.
    cpus: "2"
    mem_limit: "2g"

    environment:
      TZ: ${TZ:-Europe/Madrid}
      CONFIG_DIR: /config
      # Carpeta donde se enlaza lo que se sube. Uploadrr-EMU se la da a
      # qBittorrent como ruta de guardado, así que tiene que estar en el mismo
      # sistema de ficheros que la media (para que sea un enlace duro) y
      # qBittorrent tiene que verla en esta misma ruta.
      UPLOADRR_UPLOADS_DIR: /data/uploads/emu

    volumes:
      # Configuración persistente: base de datos SQLite, settings, y el
      # config.yaml/temporales de Uploadrr-EMU (bajo /config/Uploadrr).
      - /srv/emuwarez-uploadrr/config:/config

      # Raíz de datos compartida: media de Radarr/Sonarr y carpeta de subidas.
      - /srv/data:/data
```

Opcionalmente, crea al lado un `.env` para no editar el compose:

```env
PUID=1000
PGID=1000
TZ=Europe/Madrid
EMUWAREZ_UPLOADRR_PORT=9494
```

Y levanta el contenedor:

```bash
docker compose up -d
```

Abre `http://localhost:9494`: el asistente de configuración inicial se abre solo.

> Las API keys (TMDb, eMuwarez, Radarr/Sonarr…) se configuran desde el asistente web o desde Configuración, nunca
> en el compose ni en el `.env`.

### Rutas: lo único delicado

- **La carpeta de subidas** (`UPLOADRR_UPLOADS_DIR`) tiene que estar en el mismo sistema de ficheros que la media.
  Cuando no se puede crear un enlace duro (otro sistema de ficheros, un montaje CIFS o NFS que no los admite, o el
  límite de enlaces del fichero), la aplicación crea uno simbólico, y solo se siembra si qBittorrent puede resolver
  a dónde apunta. Sin la variable, la carpeta es `/config/Uploadrr/uploads`, normalmente en otro disco.
- **Créala antes de arrancar**, con el mismo dueño que `PUID:PGID`: si `/srv/data` es de root, el contenedor no
  puede crearla y las subidas se quedan sin preparar.

  ```bash
  mkdir -p /srv/data/uploads/emu
  chown 1000:1000 /srv/data/uploads/emu
  ```
- **qBittorrent** tiene que ver la carpeta de subidas en la misma ruta que este contenedor.
- **Si Radarr/Sonarr ven la media en otra ruta** que este contenedor, añade una regla en Configuración →
  *Mapeo de rutas (biblioteca remota)*.

### Versiones y volver atrás

La imagen se publica con varias etiquetas, y `EMUWAREZ_UPLOADRR_TAG` (en el `.env`) elige cuál usa el compose:

- `latest` (sin la variable): la última de `master`. Se actualiza con `docker compose pull && docker compose up -d`.
- `0.11.0`: una versión concreta, de las que tienen etiqueta `v0.11.0` en el repo. Sirve para quedarte en ella o
  para volver atrás si la nueva falla.
- El sha de un commit de `master`: cada commit de `master` tiene su imagen.

```bash
EMUWAREZ_UPLOADRR_TAG=0.11.0 docker compose up -d
```

### Construir la imagen tú mismo

```bash
git clone https://github.com/Kisnov/emuwarez-uploadrr.git
cd emuwarez-uploadrr
cp .env.example .env
docker compose -f docker-compose.example.yml up -d --build
```

> Uploadrr-EMU va empaquetado dentro de la imagen: no hay que montar ni configurar nada aparte para él. Su
> `config.yaml` y sus temporales persisten bajo el volumen `/config`.

## Uso sin Docker

Necesita Python 3.10+, Node 20, `mediainfo`, `ffmpeg`, `mkvtoolnix` y una copia de Uploadrr-EMU (ruta en el ajuste
`uploadrr.path`, por defecto `/opt/Uploadrr`).

```bash
pip install -e ".[web]"
(cd frontend && npm ci && npm run build)
python3 emuwarez_uploader.py web serve --host 0.0.0.0 --port 9494
```

La CLI también tiene un comando para cada acción de la web (sincronizar, listar biblioteca y peticiones, generar
la nomenclatura, subir…): ver [`README_CLI_READY.md`](README_CLI_READY.md).

## Desarrollo

```bash
# Backend, en Linux (hardlinks, mediainfo, mkvtoolnix): ~2180 tests, ~7 min
pip install -e ".[web,dev]"
python -m pytest tests -q -p no:cacheprovider

# Frontend
cd frontend && npm ci && npx tsc --noEmit && npx vitest run && npx vite build
```

El CI pasa lo mismo y las reglas graves de `ruff` en cada PR. `CLAUDE.md` recoge las reglas de arquitectura y el
contrato con Uploadrr-EMU (argumentos, claves de `config.yaml` y líneas de salida que se leen): si cambias uno de
los dos lados, cambia el otro a la vez.

## Documentación

- [`docs/DEPLOYMENT_DOCKER.md`](docs/DEPLOYMENT_DOCKER.md): despliegue Docker paso a paso y troubleshooting.
  **Desactualizada:** aún describe `hardlink_base` y pasos que ya no existen; para las rutas vale lo de arriba.
- [`docs/source_engine.md`](docs/source_engine.md): motor de detección de source y nomenclatura.
- [`README_CLI_READY.md`](README_CLI_READY.md): referencia de la CLI y del modelo SQLite.

## Stack

- Backend: Python (FastAPI) + SQLite.
- Frontend: React + Vite + TypeScript, servido como estáticos por el backend.
- Integraciones: Radarr, Sonarr, TMDb, eMuwarez (UNIT3D), Uploadrr-EMU, qBittorrent.

## Licencia

Uso privado/homelab. No redistribuido públicamente.
