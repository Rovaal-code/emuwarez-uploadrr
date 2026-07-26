"""Live host resource usage for the sidebar's System Status gauges."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import SystemStatsResponse, UploadConcurrencyEstimateResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/stats", response_model=SystemStatsResponse)
def system_stats(current_user: dict = Depends(require_auth)) -> SystemStatsResponse:
    from emuwarez_uploadrr.database import connect, init_db
    from ...services.system_stats import get_system_stats
    with connect(_db_path()) as conn:
        init_db(conn)
        return SystemStatsResponse(**get_system_stats(conn))


@router.get("/upload-concurrency-estimate", response_model=UploadConcurrencyEstimateResponse)
def upload_concurrency_estimate(current_user: dict = Depends(require_auth)) -> UploadConcurrencyEstimateResponse:
    """Best-effort "Subidas en paralelo" recommendation from currently
    available RAM/CPU cores — see services.system_stats.
    estimate_max_concurrent_uploads for the (rough, documented) assumptions."""
    from ...services.system_stats import estimate_max_concurrent_uploads
    return UploadConcurrencyEstimateResponse(**estimate_max_concurrent_uploads())
