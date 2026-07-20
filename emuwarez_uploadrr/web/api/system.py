"""Live host resource usage for the sidebar's System Status gauges."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import SystemStatsResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/stats", response_model=SystemStatsResponse)
def system_stats(current_user: dict = Depends(require_auth)) -> SystemStatsResponse:
    from emuwarez_uploadrr.database import connect, init_db
    from ...services.system_stats import get_system_stats
    with connect(_db_path()) as conn:
        init_db(conn)
        return SystemStatsResponse(**get_system_stats(conn))
