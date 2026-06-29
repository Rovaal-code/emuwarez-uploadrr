"""Real dashboard endpoints (Phase 4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import DashboardActivityItem, DashboardActivityResponse, DashboardSummaryResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(current_user: dict = Depends(require_auth)) -> DashboardSummaryResponse:
    from emuwarez_uploadrr.services.library import get_dashboard_summary
    with _get_conn() as conn:
        summary = get_dashboard_summary(conn)
    return DashboardSummaryResponse(**summary)


@router.get("/activity", response_model=DashboardActivityResponse)
def dashboard_activity(current_user: dict = Depends(require_auth)) -> DashboardActivityResponse:
    from emuwarez_uploadrr.services.library import get_recent_activity
    with _get_conn() as conn:
        items = get_recent_activity(conn, limit=20)
    return DashboardActivityResponse(
        items=[DashboardActivityItem(**{k: i.get(k) for k in DashboardActivityItem.model_fields}) for i in items]
    )
