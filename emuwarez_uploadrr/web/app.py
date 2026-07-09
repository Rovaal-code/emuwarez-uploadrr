"""FastAPI application factory for eMuwarez Uploadrr web backend."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.router import api_router
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
            pass
        await asyncio.sleep(_SCHEDULER_TICK_SECONDS)


@asynccontextmanager
async def _lifespan(app: FastAPI):
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

_DESCRIPTION = """
**eMuwarez Uploadrr** — backend web para cruzar biblioteca Radarr/Sonarr con
peticiones de eMuwarez, detectar compatibilidad, adaptar nomenclatura y subir
contenido usando Uploadrr.

## Documentación

- [Contrato funcional JSON](/api/contract/json)
- [Health](/api/health)
- [Setup status](/api/setup/status)

## Notas

- CLI disponible: `python3 emuwarez_uploader.py --help`
- La creación de peticiones eMuwarez está preparada como stub y bloqueada
  hasta capturar la request real desde DevTools/Network.
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

    # Log every HTTP request the app handles — part of "log everything".
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
        # Skip the noisy polling of the logs endpoint itself.
        if path != "/api/logs":
            _req_log.info("%s %s → %s (%.0f ms)", request.method, path, response.status_code, dur_ms)
        return response

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    app.include_router(api_router)

    # Serve built frontend if dist exists (optional — backend works without it)
    if _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "index.html").exists():
        _assets = _FRONTEND_DIST / "assets"
        if _assets.exists():
            app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

        _favicon = _FRONTEND_DIST / "favicon.svg"
        if _favicon.exists():
            # Registered before spa_fallback below — without this, /favicon.svg
            # falls through the catch-all and gets index.html (text/html) back,
            # which browsers reject as a tab icon.
            @app.get("/favicon.svg", include_in_schema=False)
            async def favicon() -> FileResponse:
                return FileResponse(str(_favicon), media_type="image/svg+xml")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # Never intercept /api/* routes (already handled above)
            if full_path.startswith("api/") or full_path == "api":
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            index = _FRONTEND_DIST / "index.html"
            return FileResponse(str(index), media_type="text/html")

    return app


app = create_app()
