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
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN LOWER(COALESCE(emu_status,'')) IN ('filled','llena','1') THEN 1 ELSE 0 END) AS filled
                FROM request_items
                """
            ).fetchone()
            summary["requests_total"] = int(row["total"] or 0) if row else 0
            summary["requests_filled"] = int(row["filled"] or 0) if row else 0
            compatible_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM request_matches WHERE status = 'Compatible'"
            ).fetchone()
            summary["requests_compatible"] = int(compatible_row["cnt"] or 0) if compatible_row else 0
            from emuwarez_uploadrr.database import get_state
            summary["requests_last_sync_at"] = get_state(conn, "last_emu_requests_sync_utc")
        except Exception:
            summary.setdefault("requests_total", 0)
            summary.setdefault("requests_filled", 0)
            summary.setdefault("requests_compatible", 0)
            summary.setdefault("requests_last_sync_at", None)
    return DashboardSummaryResponse(**summary)


@router.get("/activity", response_model=DashboardActivityResponse)
def dashboard_activity(current_user: dict = Depends(require_auth)) -> DashboardActivityResponse:
    from emuwarez_uploadrr.services.library import get_recent_activity
    with _get_conn() as conn:
        items = get_recent_activity(conn, limit=20)
    return DashboardActivityResponse(
        items=[DashboardActivityItem(**{k: i.get(k) for k in DashboardActivityItem.model_fields}) for i in items]
    )
