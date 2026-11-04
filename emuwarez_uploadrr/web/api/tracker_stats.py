"""Las estadísticas que eMuwarez da del torrent de una subida completada. Solo lectura."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...database import db
from ...services.emu_torrent_stats import estadisticas_de_la_subida
from ..dependencies import require_auth
from ..runtime import _db_path

router = APIRouter(tags=["uploads"])


@router.get("/uploads/{job_id}/tracker-stats")
def estadisticas_del_tracker(job_id: int, refresh: bool = False, current_user: dict = Depends(require_auth)) -> dict:
    """Seeders, leechers y veces completado del torrent en eMuwarez. Si eMuwarez no responde es un 200 con
    `disponible: false`, nunca un error; una subida sin ficha (no completada) es un 404. `refresh` se salta la caché de
    5 minutos (la clave de eMuwarez se comparte con otras aplicaciones, con 30 peticiones por minuto)."""
    with db(_db_path()) as conn:
        datos = estadisticas_de_la_subida(conn, job_id, refrescar=refresh)
    if not datos["aplica"]:
        raise HTTPException(status_code=404, detail="Esta subida no tiene ficha en eMuwarez")
    return datos
