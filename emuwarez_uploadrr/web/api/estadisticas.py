"""Estadísticas: la evolución de tu cuenta de eMuwarez a partir de las instantáneas diarias."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_db, require_auth
from ..schemas import EstadisticasCuentaResponse

router = APIRouter(prefix="/estadisticas", tags=["estadisticas"])


@router.get("/cuenta", response_model=EstadisticasCuentaResponse)
def estadisticas_cuenta(
    dias: int = Query(default=90, ge=1, le=730),
    current_user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
) -> EstadisticasCuentaResponse:
    """Ratio, subido, bajado y bonus, una instantánea por día, de la más antigua a la más reciente."""
    from emuwarez_uploadrr.services.perfil_historial import serie_cuenta
    return EstadisticasCuentaResponse(dias=dias, puntos=serie_cuenta(conn, dias))
