"""Error handlers and exception types for the web API."""
from __future__ import annotations

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..integrations.base import texto_de_error


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "detail": exc.detail, "status_code": exc.status_code},
    )


# Pydantic repite en cada error el valor recibido (`input`) y, a veces, la excepción que lo
# provocó (`ctx`). En esta API ese valor puede ser una URL con la clave en la query, una API
# key, un token o una contraseña: el 422 los devolvería a quien los escribió y quedarían en
# cualquier registro de respuestas. Se conservan `type`, `loc` y `msg`, que es lo que lee el
# frontend (api/client.ts).
_CAMPOS_QUE_REPITEN_EL_VALOR = ("input", "ctx")


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errores = [
        {k: v for k, v in error.items() if k not in _CAMPOS_QUE_REPITEN_EL_VALOR}
        for error in jsonable_encoder(exc.errors())
    ]
    return JSONResponse(status_code=422, content={"detail": errores})


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": texto_de_error(exc), "status_code": 500},
    )
