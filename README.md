# eMuwarez Uploadrr

Aplicación web (+ CLI) para gestionar subidas a **eMuwarez** (tracker UNIT3D)
a partir de tu biblioteca de **Radarr**/**Sonarr**: sincroniza tu biblioteca,
cruza peticiones abiertas en eMuwarez con lo que ya tienes, adapta la
nomenclatura, prepara el hardlink y ejecuta la subida real con
[Uploadrr-EMU](https://github.com/Rovaal-code/Uploadrr-EMU) — todo desde una
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

Requiere Docker 24+ con Compose v2.

```bash
git clone https://github.com/Rovaal-code/emuwarez-uploadrr.git
cd emuwarez-uploadrr
cp .env.example .env
nano .env   # ajusta PUID/PGID/TZ y las rutas de Uploadrr-EMU

docker compose up -d
```

Abre `http://localhost:9494` — el asistente de configuración inicial se abre
solo. `docker-compose.yml` usa la imagen ya construida en
`ghcr.io/rovaal-code/emuwarez-uploadrr`; no hace falta compilar nada.

Para construir la imagen tú mismo en vez de usar la publicada (por ejemplo,
para probar cambios locales), usa `docker-compose.example.yml`:

```bash
docker compose -f docker-compose.example.yml up -d --build
```

**Guía de despliegue completa** (mounts de Uploadrr-EMU, hardlinks/EXDEV,
primer usuario admin, troubleshooting): [`docs/DEPLOYMENT_DOCKER.md`](docs/DEPLOYMENT_DOCKER.md).

> `Uploadrr-EMU` **nunca** se empaqueta dentro de la imagen: se monta como
> directorio externo (`:ro` el código, `rw` sus `data/` y `tmp/`). Ver la
> guía de despliegue para el porqué y el mount exacto.

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
- [`docs/ui_backend_contract.md`](docs/ui_backend_contract.md) — contrato entre frontend y API.
- [`docs/source_engine.md`](docs/source_engine.md) — motor de detección de source/nomenclatura.
- [`references/`](references) — nomenclatura y guía de subida de eMuwarez.
- [`README_CLI_READY.md`](README_CLI_READY.md) — referencia extendida de la CLI y el modelo SQLite.

## Stack

- Backend: Python (FastAPI) + SQLite.
- Frontend: React + Vite + TypeScript, servido como estáticos por el backend.
- Integraciones: Radarr, Sonarr, TMDb, eMuwarez (UNIT3D), Uploadrr-EMU.

## Licencia

Uso privado/homelab. No redistribuido públicamente.
