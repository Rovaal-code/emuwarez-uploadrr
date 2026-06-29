"""Health and runtime endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from ..runtime import get_app_version, get_runtime_info, _db_path
from ..schemas import HealthResponse, RuntimeInfoResponse

router = APIRouter(tags=["health"])


def _db_ok() -> bool:
    try:
        from emuwarez_uploadrr.database import connect, init_db
        with connect(_db_path()) as conn:
            init_db(conn)
        return True
    except Exception:
        return False


def _is_initialized() -> bool:
    try:
        from emuwarez_uploadrr.database import connect, init_db, get_state
        with connect(_db_path()) as conn:
            init_db(conn)
            return get_state(conn, "initialized") == "true"
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app="eMuwarez Uploadrr",
        version=get_app_version(),
        database="ok" if _db_ok() else "error",
        initialized=_is_initialized(),
    )


@router.get("/runtime", response_model=RuntimeInfoResponse)
def runtime_info() -> RuntimeInfoResponse:
    info = get_runtime_info()
    return RuntimeInfoResponse(**info)
