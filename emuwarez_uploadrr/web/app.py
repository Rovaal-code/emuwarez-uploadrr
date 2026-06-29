"""FastAPI application factory for eMuwarez Uploadrr web backend."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.router import api_router
from .errors import AppError, app_error_handler, generic_error_handler
from .runtime import get_app_version

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
    app = FastAPI(
        title="eMuwarez Uploadrr",
        version=get_app_version(),
        description=_DESCRIPTION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    app.include_router(api_router)

    # Serve built frontend if dist exists (optional — backend works without it)
    if _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "index.html").exists():
        _assets = _FRONTEND_DIST / "assets"
        if _assets.exists():
            app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

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
