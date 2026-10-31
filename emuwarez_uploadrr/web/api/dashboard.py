"""Real dashboard endpoints (Phase 4 / Phase 6D)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    DashboardActivityItem, DashboardActivityResponse,
    DashboardRecommendationItem, DashboardRecommendationsResponse,
    DashboardSummaryResponse, EmuPerfilResponse, LibraryListResponse,
)

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
        # Los contadores de peticiones y de subidas los calculan sus propios
        # servicios: el criterio de "Compatible", "Mías" y "Reclamadas" es de
        # dominio, no de HTTP (auditoría, hallazgo 6.2).
        from emuwarez_uploadrr.services.requests import dashboard_request_counters
        summary.update(dashboard_request_counters(conn))

        from emuwarez_uploadrr.services.upload_queue import dashboard_upload_counters
        summary.update(dashboard_upload_counters(conn))

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


@router.get("/recommendations", response_model=DashboardRecommendationsResponse)
def dashboard_recommendations(
    limit: int = Query(default=100, ge=0, le=100000),  # 0 = sin límite
    current_user: dict = Depends(require_auth),
) -> DashboardRecommendationsResponse:
    """Phase 11G — 'Recomendaciones': actionable content in three ranked groups
    (compatible request → unique/upload → missing/request). Replaces the old
    request-priority feed shown under 'Actividad reciente'."""
    from emuwarez_uploadrr.services.library import get_dashboard_recommendations
    with _get_conn() as conn:
        rows = get_dashboard_recommendations(conn, limit=limit)
    return DashboardRecommendationsResponse(
        items=[
            DashboardRecommendationItem(**{k: r.get(k) for k in DashboardRecommendationItem.model_fields})
            for r in rows
        ]
    )


@router.get("/emu-perfil", response_model=EmuPerfilResponse)
def dashboard_emu_perfil(current_user: dict = Depends(require_auth)) -> EmuPerfilResponse:
    """Tu cuenta de eMuwarez; se vuelve a leer del tracker como mucho una vez por hora."""
    from emuwarez_uploadrr.services.emu_perfil import perfil_emu
    with _get_conn() as conn:
        return EmuPerfilResponse(**perfil_emu(conn))


@router.post("/emu-perfil/actualizar", response_model=EmuPerfilResponse)
def dashboard_emu_perfil_actualizar(current_user: dict = Depends(require_auth)) -> EmuPerfilResponse:
    """«Actualizar»: la vuelve a leer si la última vez fue hace más de un minuto."""
    from emuwarez_uploadrr.services.emu_perfil import perfil_emu
    with _get_conn() as conn:
        return EmuPerfilResponse(**perfil_emu(conn, actualizar=True))


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
