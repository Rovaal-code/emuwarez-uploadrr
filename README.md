# eMuwarez Uploadrr

Aplicación web (+ CLI) para gestionar subidas a **eMuwarez** (tracker UNIT3D)
a partir de tu biblioteca de **Radarr**/**Sonarr**: sincroniza tu biblioteca,
cruza peticiones abiertas en eMuwarez con lo que ya tienes, adapta la
nomenclatura, prepara el hardlink y ejecuta la subida real con
[Uploadrr-EMU](https://github.com/Kisnov/Uploadrr-EMU) — todo desde una
interfaz web, sin tocar la terminal.

## Características principales

- **Biblioteca**: sincroniza películas y series desde Radarr/Sonarr, con
  estado (Disponible/Faltante/Subiendo/Subido/Error) y nomenclatura por ítem.
- **Peticiones**: importa las peticiones abiertas de eMuwarez y calcula
  automáticamente qué tienes ya listo para cubrirlas (compatible, parcial,
  no compatible), con prioridad y candidato sugerido.
- **Subidas**: preflight, nomenclatura, hardlink y ejecución controlada de
  Uploadrr-EMU (`shell=False`, argv como lista, secretos siempre redactados
  en logs), con límite configurable de subidas simultáneas.
- **Mantenimiento**: backups de configuración, VACUUM de la base de datos,
  logs centralizados, diagnóstico (`web doctor`).
- **Tareas automáticas**: sincronización periódica de biblioteca y
  peticiones, sin intervención manual.

## Arranque rápido (Docker Compose)

Requiere Docker 24+ con Compose v2. No hace falta clonar el repo: copia esto
en un `docker-compose.yml`, ajusta las rutas de los volúmenes a tu entorno y
levántalo. Usa la imagen ya publicada en
`ghcr.io/kisnov/emuwarez-uploadrr`, así que no compila nada.

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

    volumes:
      # Configuración persistente: base de datos SQLite, settings, y el
      # config.yaml/temporales de Uploadrr-EMU (bajo /config/Uploadrr —
      # Uploadrr-EMU va empaquetado en la imagen, no es un mount aparte).
      - /srv/emuwarez-uploadrr/config:/config

      # Raíz de datos compartida para media + uploads — una sola raíz evita
      # el error EXDEV al crear hardlinks entre origen y destino.
      # Configura en el setup web: Raíz media → /data/media,
      # hardlink_base → /data/uploads/emu
      - /srv/data:/data
```

Opcionalmente, junto a él crea un `.env` para no editar el compose directamente:

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

Abre `http://localhost:9494` — el asistente de configuración inicial se abre
solo.

> API keys (TMDb, eMuwarez, Radarr/Sonarr...) se configuran desde el propio
> asistente web o desde Configuración — nunca en el compose ni en el `.env`.

Si prefieres clonar el repo (por ejemplo para construir la imagen tú mismo
en vez de usar la publicada), usa `docker-compose.example.yml`:

```bash
git clone https://github.com/Kisnov/emuwarez-uploadrr.git
cd emuwarez-uploadrr
cp .env.example .env
docker compose -f docker-compose.example.yml up -d --build
```

**Guía de despliegue completa** (hardlinks/EXDEV, primer usuario admin,
troubleshooting): [`docs/DEPLOYMENT_DOCKER.md`](docs/DEPLOYMENT_DOCKER.md).

> `Uploadrr-EMU` va empaquetado dentro de la imagen — no hay que montar ni
> configurar nada aparte para él. Su `config.yaml` y sus temporales de subida
> persisten automáticamente bajo el propio volumen `/config`.

## Uso sin Docker (CLI local)

```bash
pip install -e ".[web]"
python3 emuwarez_uploader.py web serve --host 0.0.0.0 --port 9494
```

La CLI también expone comandos equivalentes a cada acción de la web
(sincronizar, listar biblioteca/peticiones, preparar nomenclatura, subir…) —
ver [`README_CLI_READY.md`](README_CLI_READY.md) para el listado completo y
el modelo de datos en SQLite.

## Documentación

- [`docs/DEPLOYMENT_DOCKER.md`](docs/DEPLOYMENT_DOCKER.md) — despliegue Docker paso a paso y troubleshooting.
- [`docs/source_engine.md`](docs/source_engine.md) — motor de detección de source/nomenclatura.
- [`references/`](references) — nomenclatura y guía de subida de eMuwarez.
- [`README_CLI_READY.md`](README_CLI_READY.md) — referencia extendida de la CLI y el modelo SQLite.

## Stack

- Backend: Python (FastAPI) + SQLite.
- Frontend: React + Vite + TypeScript, servido como estáticos por el backend.
- Integraciones: Radarr, Sonarr, TMDb, eMuwarez (UNIT3D), Uploadrr-EMU.

## Licencia

Uso privado/homelab. No redistribuido públicamente.
