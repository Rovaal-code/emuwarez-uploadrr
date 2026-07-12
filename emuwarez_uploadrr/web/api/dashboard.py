"""Real dashboard endpoints (Phase 4 / Phase 6D)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    DashboardActivityItem, DashboardActivityResponse, DashboardSummaryResponse,
    LibraryListResponse,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _get_upload_counts(conn) -> dict:
    """Return upload job status counts for the dashboard summary."""
    try:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS cnt FROM upload_jobs GROUP BY status
            """
        ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = int(row["cnt"] or 0)

        last_row = conn.execute(
            "SELECT MAX(updated_at) AS last_at FROM upload_jobs"
        ).fetchone()
        last_at = last_row["last_at"] if last_row else None

        return {
            "uploads_ready": counts.get("ready", 0),
            "uploads_running": counts.get("running", 0),
            "uploads_completed": counts.get("completed", 0),
            "uploads_failed": counts.get("failed", 0),
            "last_upload_at": last_at,
        }
    except Exception:
        return {
            "uploads_ready": 0,
            "uploads_running": 0,
            "uploads_completed": 0,
            "uploads_failed": 0,
            "last_upload_at": None,
        }


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
                    SUM(CASE WHEN LOWER(COALESCE(emu_status,'')) IN ('filled','llena','lleno','1') THEN 1 ELSE 0 END) AS filled
                FROM request_items
                """
            ).fetchone()
            summary["requests_total"] = int(row["total"] or 0) if row else 0
            summary["requests_filled"] = int(row["filled"] or 0) if row else 0
            # Count requests whose BEST match is Compatible (same criterion as
            # the Peticiones list), not every Compatible match row.
            compatible_row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM request_items ri
                WHERE (
                    SELECT rm.status FROM request_matches rm
                    WHERE rm.request_item_id = ri.id
                    ORDER BY rm.confidence DESC LIMIT 1
                ) = 'Compatible'
                """
            ).fetchone()
            summary["requests_compatible"] = int(compatible_row["cnt"] or 0) if compatible_row else 0
            from emuwarez_uploadrr.database import get_state
            summary["requests_last_sync_at"] = get_state(conn, "last_emu_requests_sync_utc")

        except Exception:
            summary.setdefault("requests_total", 0)
            summary.setdefault("requests_filled", 0)
            summary.setdefault("requests_compatible", 0)
            summary.setdefault("requests_last_sync_at", None)

        # "Mis peticiones" (Phase 5 of the 12-part batch) — requests authored
        # by the user's own eMuwarez account (new emu.username setting, no
        # migration needed since `settings` is already a flexible key-value
        # table). author_visible gates whether `author` is meaningfully
        # populated at all (same convention services/requests.py already
        # uses when exposing it in API responses) — an invisible-author row
        # never counts as "mine" even if it happens to match by coincidence.
        try:
            from emuwarez_uploadrr.web.services.settings_service import get_setting
            my_username = get_setting(conn, "emu.username")
            if my_username:
                mine_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM request_items WHERE author_visible = 1 AND author = ?",
                    (my_username,),
                ).fetchone()
                summary["requests_mine"] = int(mine_row["cnt"] or 0) if mine_row else 0
            else:
                summary["requests_mine"] = 0
        except Exception:
            summary["requests_mine"] = 0

        # Phase 6D: upload counts
        upload_counts = _get_upload_counts(conn)
        summary.update(upload_counts)

        # Phase 8A: diagnostic counts
        try:
            from emuwarez_uploadrr.services.library import get_dashboard_diagnostics
            diag_counts = get_dashboard_diagnostics(conn)
            summary.update(diag_counts)
        except Exception:
            pass

        # Phase 8B: request readiness counts
        try:
            from emuwarez_uploadrr.services.request_readiness import get_dashboard_readiness_counts
            readiness_counts = get_dashboard_readiness_counts(conn)
            summary.update(readiness_counts)
        except Exception:
            pass

        # Phase 8C: operational queue counts
        try:
            from emuwarez_uploadrr.services.operational_queue import get_dashboard_queue_counts
            queue_counts = get_dashboard_queue_counts(conn)
            summary.update(queue_counts)
        except Exception:
            pass

    return DashboardSummaryResponse(**summary)


@router.get("/activity", response_model=DashboardActivityResponse)
def dashboard_activity(current_user: dict = Depends(require_auth)) -> DashboardActivityResponse:
    from emuwarez_uploadrr.services.library import get_recent_activity
    with _get_conn() as conn:
        items = get_recent_activity(conn, limit=20)
    return DashboardActivityResponse(
        items=[DashboardActivityItem(**{k: i.get(k) for k in DashboardActivityItem.model_fields}) for i in items]
    )


@router.get("/library-activity", response_model=LibraryListResponse)
def dashboard_library_activity(
    limit: int = Query(default=50, ge=1, le=300),
    current_user: dict = Depends(require_auth),
) -> LibraryListResponse:
    """Phase 11F — 'Actividad reciente': library items prioritized by EMU
    request satisfaction (filled > compatible/partial > everything else),
    replacing the old task_runs feed of the same name (that data is still
    available, unchanged, at GET /dashboard/activity)."""
    from emuwarez_uploadrr.services.library import get_dashboard_library_activity
    from .library import _to_lib_response
    with _get_conn() as conn:
        rows = get_dashboard_library_activity(conn, limit=limit)
        items = [_to_lib_response(row, conn) for row in rows]
    return LibraryListResponse(
        items=items,
        total=len(rows),
        limit=limit,
        offset=0,
    )
