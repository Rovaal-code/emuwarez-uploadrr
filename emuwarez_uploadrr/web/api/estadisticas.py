"""Estadísticas: la evolución de tu cuenta de eMuwarez a partir de las instantáneas diarias."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import EstadisticasCuentaResponse

router = APIRouter(prefix="/estadisticas", tags=["estadisticas"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


@router.get("/cuenta", response_model=EstadisticasCuentaResponse)
def estadisticas_cuenta(
    dias: int = Query(default=90, ge=1, le=730),
    current_user: dict = Depends(require_auth),
) -> EstadisticasCuentaResponse:
    """Ratio, subido, bajado, bonus y H&R, una instantánea por día, de la más antigua a la más reciente."""
    from emuwarez_uploadrr.services.perfil_historial import serie_cuenta
    with _get_conn() as conn:
        return EstadisticasCuentaResponse(dias=dias, puntos=serie_cuenta(conn, dias))
