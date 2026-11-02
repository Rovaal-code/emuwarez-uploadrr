"""Widget para Homepage (gethomepage.dev).

GET    /api/widget        — contadores; se abre con la clave del widget, no con una sesión
GET    /api/widget/clave  — si hay clave (requiere sesión)
POST   /api/widget/clave  — genera o regenera la clave y la devuelve esa única vez (requiere sesión)
DELETE /api/widget/clave  — desactiva el widget (requiere sesión)
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_db, require_auth, require_widget_key
from ..schemas import WidgetClaveGenerada, WidgetClaveEstado, WidgetContadores

router = APIRouter(prefix="/widget", tags=["widget"])

# Ni la clave recién generada ni los contadores se guardan en cachés intermedias.
_SIN_CACHE = {"Cache-Control": "no-store"}


@router.get("", response_model=WidgetContadores, dependencies=[Depends(require_widget_key)])
def widget(response: Response, conn: sqlite3.Connection = Depends(get_db)) -> WidgetContadores:
    from ...services.widget import contadores
    response.headers.update(_SIN_CACHE)
    return WidgetContadores(**contadores(conn))


@router.get("/clave", response_model=WidgetClaveEstado)
def clave_estado(
    current_user: dict = Depends(require_auth), conn: sqlite3.Connection = Depends(get_db),
) -> WidgetClaveEstado:
    from ...services.widget import clave_configurada
    return WidgetClaveEstado(configurada=clave_configurada(conn))


@router.post("/clave", response_model=WidgetClaveGenerada)
def clave_generar(
    response: Response, current_user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db, scope="function"),  # se confirma antes de enseñar la clave
) -> WidgetClaveGenerada:
    from ...services.widget import generar_clave
    response.headers.update(_SIN_CACHE)
    return WidgetClaveGenerada(clave=generar_clave(conn))


@router.delete("/clave", response_model=WidgetClaveEstado)
def clave_quitar(
    current_user: dict = Depends(require_auth), conn: sqlite3.Connection = Depends(get_db, scope="function"),
) -> WidgetClaveEstado:
    from ...services.widget import quitar_clave
    quitar_clave(conn)
    return WidgetClaveEstado(configurada=False)
