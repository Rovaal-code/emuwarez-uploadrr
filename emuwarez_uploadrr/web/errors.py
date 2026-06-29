"""Error handlers and exception types for the web API."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


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


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc), "status_code": 500},
    )
