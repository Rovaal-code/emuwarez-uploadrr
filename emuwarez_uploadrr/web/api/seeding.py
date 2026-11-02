"""La salud del seeding de las subidas, leída de qBittorrent. Solo lectura."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...database import db
from ...services.seeding_qbit import salud_del_seeding
from ..dependencies import require_auth
from ..runtime import _db_path

router = APIRouter(tags=["uploads"])


@router.get("/uploads/seeding")
def seeding_de_las_subidas(refresh: bool = False, current_user: dict = Depends(require_auth)) -> dict:
    """Estado, ratio y bytes subidos en qBittorrent de cada subida completada. Si qBittorrent no está configurado
    o no responde es un 200 con `disponible: false`, nunca un error: el resto de Subidas no depende de esto.
    `refresh` se salta la caché de ~60 s."""
    with db(_db_path()) as conn:
        return salud_del_seeding(conn, refrescar=refresh)
