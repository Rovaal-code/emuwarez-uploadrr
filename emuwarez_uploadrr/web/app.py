"""FastAPI application factory for eMuwarez Uploadrr web backend."""
from __future__ import annotations

from fastapi import FastAPI

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

    return app


app = create_app()
