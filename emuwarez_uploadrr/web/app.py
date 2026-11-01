"""FastAPI application factory for eMuwarez Uploadrr web backend."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.router import api_router
from .cabeceras import CabecerasDeSeguridad
from .errors import AppError, app_error_handler, generic_error_handler
from .runtime import get_app_version

# Phase 11D — automatic tasks scheduler tick interval (seconds). Checking
# every 60s is cheap (a couple of SQLite reads) regardless of how long the
# configured task intervals are (minimum 15 minutes).
_SCHEDULER_TICK_SECONDS = 60


async def _scheduler_loop() -> None:
    from ..services.scheduler import tick_due_tasks
    while True:
        try:
            await asyncio.to_thread(tick_due_tasks)
        except Exception:
            # A scheduler tick must never crash the app — errors from
            # individual tasks are already captured per-task by
            # run_scheduled_task(); this is a last-resort guard.
            logging.getLogger("emuwarez.web").exception("Falló un ciclo del planificador")
        await asyncio.sleep(_SCHEDULER_TICK_SECONDS)


def _backfill_spanish_flags() -> None:
    """Fill in the Castilian audio/subtitle flags on boot so an already
    populated library shows the Español column right away (and lets a season
    pack through on its subtitles) instead of waiting for the next Radarr/
    Sonarr sync. It's a handful of aggregate queries over library_items, and it
    keeps both flags correct after an upgrade even if nothing else changes.
    Best-effort: never blocks startup."""
    try:
        from emuwarez_uploadrr.database import db
        from emuwarez_uploadrr.services.library import recompute_spanish_flags
        with db() as conn:
            recompute_spanish_flags(conn)
    except Exception:
        logging.getLogger("emuwarez.web").warning(
            "No se pudo recalcular el castellano (audio/subtítulos) al arrancar", exc_info=True)


def _reconcile_interrupted_jobs() -> None:
    """Los jobs que se quedaron a medias cuando se paró la aplicación.

    Ninguno puede tener un hilo o un subproceso vivo: murieron con el proceso
    anterior. Sin esto, parar el contenedor a media subida dejaba el job
    congelado para siempre, sin ningún botón capaz de moverlo.
    Best-effort: nunca bloquea el arranque."""
    try:
        from emuwarez_uploadrr.services.upload_queue import reconcile_interrupted_jobs
        reconcile_interrupted_jobs()
    except Exception:
        logging.getLogger("emuwarez.web").warning(
            "No se pudieron reconciliar las subidas interrumpidas al arrancar", exc_info=True)


def _restore_interrupted_config() -> None:
    """El config.yaml de Uploadrr-EMU que dejó stageado (claves reales dentro)
    una subida que murió con la aplicación. Best-effort: nunca bloquea el arranque."""
    try:
        from emuwarez_uploadrr.services.upload_execution import restaurar_config_interrumpida
        if restaurar_config_interrumpida():
            logging.getLogger("emuwarez.web").warning(
                "config.yaml de Uploadrr-EMU restaurado desde el backup: lo dejó stageado una subida interrumpida")
    except Exception:
        logging.getLogger("emuwarez.web").warning(
            "No se pudo restaurar el config.yaml de Uploadrr-EMU al arrancar", exc_info=True)


def _detener_procesos() -> None:
    """Uploadrr y mkvmerge van en su propia sesión: al apagar el servidor ya no
    caen con él (antes caían con el Ctrl-C del terminal)."""
    try:
        from emuwarez_uploadrr.services.mkv_remux import detener_remuxes
        from emuwarez_uploadrr.services.upload_execution import detener_procesos_en_marcha
        detener_procesos_en_marcha()
        detener_remuxes()
    except Exception:
        logging.getLogger("emuwarez.web").warning(
            "No se pudieron detener los procesos de subida al apagar", exc_info=True)


def _preparar_base() -> None:
    """Comprueba y migra la base una sola vez, antes de atender nada. Si es de
    una versión más nueva o la migración falla, la aplicación no arranca."""
    from emuwarez_uploadrr.database import BaseMasNuevaError, preparar_base
    log = logging.getLogger("emuwarez.web")
    try:
        preparar_base()
    except BaseMasNuevaError as exc:
        log.critical("%s", exc)
        raise
    except Exception:
        log.critical("La migración de la base de datos falló; no se arranca", exc_info=True)
        raise


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _preparar_base()
    # La carpeta donde se preparan los packs para subir, creada de entrada:
    # así existe antes de la primera subida en vez de aparecer a mitad, y la
    # comprobación del asistente puede probar el enlace sin crearla ella.
    try:
        from emuwarez_uploadrr.services.carpeta_subida import asegurar_raiz
        asegurar_raiz()
    except Exception:
        logging.getLogger("emuwarez.web").warning(
            "No se pudo preparar la carpeta de subidas", exc_info=True)
    _backfill_spanish_flags()
    _reconcile_interrupted_jobs()
    _restore_interrupted_config()
    scheduler_task = None
    # EMUWAREZ_DISABLE_SCHEDULER=1 — escape hatch for scripted Docker
    # smoke/E2E runs that don't want a background scheduler tick firing
    # mid-demo. Off (scheduler enabled) by default.
    if os.environ.get("EMUWAREZ_DISABLE_SCHEDULER") != "1":
        scheduler_task = asyncio.create_task(_scheduler_loop())
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
        _detener_procesos()

_DESCRIPTION = """
**eMuwarez Uploadrr** — backend web para cruzar biblioteca Radarr/Sonarr con
peticiones de eMuwarez, detectar compatibilidad, adaptar nomenclatura y subir
contenido usando Uploadrr.

## Documentación

- [Health](/api/health)
- [Setup status](/api/setup/status)

## Notas

- CLI disponible: `python3 emuwarez_uploader.py --help`
- UNIT3D no permite crear peticiones por API: «Crear petición» abre el
  formulario de eMuwarez ya rellenado.
"""

# Path to the built frontend (frontend/dist relative to repo root)
_REPO_ROOT = Path(__file__).parent.parent.parent
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"


def create_app() -> FastAPI:
    import logging
    import time
    from .logging_setup import setup_app_logging

    setup_app_logging()
    _req_log = logging.getLogger("emuwarez.request")

    app = FastAPI(
        title="eMuwarez Uploadrr",
        version=get_app_version(),
        description=_DESCRIPTION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    # La lista de Biblioteca son decenas de MB de JSON. El canal de avisos
    # (text/event-stream) queda fuera: Starlette no lo comprime. Nivel 6 y no
    # el 9 por defecto: un 10 % más grande en la mitad de tiempo.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
    app.add_middleware(CabecerasDeSeguridad)

    # HTTP request logging. To keep the INFO stream meaningful (not drowned in
    # polling), we classify each request:
    #   • 5xx                     → ERROR   (server broke)
    #   • 4xx (non-benign paths)  → WARNING (bad request / auth)
    #   • mutations POST/PUT/…    → INFO    (a real state change)
    #   • GET reads, polling,     → DEBUG   (dropped: the root logs at INFO, so
    #     static assets, SPA         these never reach the buffer/file at all)
    # High-frequency pollers and static assets are always DEBUG so they never
    # clutter the stream even when they 4xx (e.g. a 401 while logged out).
    _MUTATIONS = {"POST", "PUT", "DELETE", "PATCH"}
    _SKIP_PATHS = {
        "/api/logs", "/api/notifications", "/api/auth/me", "/api/setup/status",
        "/api/library/sync-status", "/api/library/sync-progress",
        "/api/library/emu-sync-status", "/api/library/emu-sync-progress",
        "/api/requests/sync-status",
    }
    _SKIP_SUFFIXES = ("/sync-status", "/sync-progress", "/emu-sync-status", "/emu-sync-progress")

    def _level_for(method: str, path: str, status: int) -> int:
        if status >= 500:
            return logging.ERROR
        is_quiet = (
            path.startswith("/assets/")
            or not path.startswith("/api/")            # SPA fallback / static
            or path in _SKIP_PATHS
            or path.endswith(_SKIP_SUFFIXES)
        )
        if is_quiet:
            return logging.DEBUG
        if status >= 400:
            return logging.WARNING
        return logging.INFO if method in _MUTATIONS else logging.DEBUG

    @app.middleware("http")
    async def _log_requests(request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
        except Exception:
            _req_log.exception("%s %s → EXCEPCIÓN", request.method, request.url.path)
            raise
        dur_ms = (time.time() - start) * 1000
        path = request.url.path
        _req_log.log(
            _level_for(request.method, path, response.status_code),
            "%s %s → %s (%.0f ms)", request.method, path, response.status_code, dur_ms,
        )
        return response

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    app.include_router(api_router)

    # Serve built frontend if dist exists (optional — backend works without it)
    if _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "index.html").exists():
        _assets = _FRONTEND_DIST / "assets"
        if _assets.exists():
            app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

        _dist_resolved = _FRONTEND_DIST.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # Never intercept /api/* routes (already handled above)
            if full_path.startswith("api/") or full_path == "api":
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            # Any real static file sitting at the repo root of dist/ (favicon.ico,
            # the various icon PNGs, site.webmanifest, robots.txt, ...) gets
            # served directly with its real content-type — instead of only
            # favicon.svg as a one-off special case, which silently left every
            # OTHER root-level static file falling through to index.html
            # (wrong content-type: text/html for a PNG/manifest/ico is rejected
            # by browsers and any tool auto-discovering these icons).
            if full_path:
                candidate = (_FRONTEND_DIST / full_path).resolve()
                if candidate.is_file() and _dist_resolved in candidate.parents:
                    # CORS: lets a third-party dashboard (Homarr, Homepage...) on a
                    # different origin fetch this app's own icon/manifest to preview
                    # it — those tools' icon pickers commonly validate a pasted URL
                    # via a cross-origin fetch() first, which the browser silently
                    # blocks without this header (a plain curl/img tag wouldn't show
                    # the problem, since CORS is enforced by the browser, not by us).
                    return FileResponse(str(candidate), headers={"Access-Control-Allow-Origin": "*"})
            index = _FRONTEND_DIST / "index.html"
            # The SPA shell must never be cached: it points at hash-named bundles
            # in /assets, so a stale index.html leaves the browser running old
            # code (or requesting a deleted bundle). Force revalidation on every
            # load; the hashed assets themselves can still cache normally.
            return FileResponse(
                str(index),
                media_type="text/html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    return app


app = create_app()
