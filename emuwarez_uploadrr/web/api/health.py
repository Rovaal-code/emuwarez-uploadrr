"""Health endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from ..runtime import get_app_version, _db_path
from ..schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def _estado_db() -> tuple[bool, bool]:
    """(la base responde, está inicializada)."""
    try:
        from emuwarez_uploadrr.database import db, get_state
        with db(_db_path()) as conn:
            return True, get_state(conn, "initialized") == "true"
    except Exception:
        logger.warning("health: la base de datos no responde", exc_info=True)
        return False, False


@router.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    db_ok, initialized = _estado_db()
    if not db_ok:
        # El HEALTHCHECK de Docker y los monitores solo miran el código.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if db_ok else "error",
        app="eMuwarez Uploadrr",
        version=get_app_version(),
        database="ok" if db_ok else "error",
        initialized=initialized,
    )
