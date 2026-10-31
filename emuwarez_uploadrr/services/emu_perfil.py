"""Tu cuenta de eMuwarez, para el Panel y la barra superior.

Sale de GET /api/user y se guarda una hora: la clave la comparten Sonarr,
Radarr, qui, autobrr y las subidas, con 30 llamadas por minuto entre todos.
Mensajes y notificaciones no están en la API (solo en la web, con sesión), así
que de ellos la interfaz solo pone el enlace.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from ..database import get_json_state, get_setting_canonical, set_json_state
from ..integrations.base import IntegrationError
from ..integrations.emu import emu_get_user
from .settings import set_setting

logger = logging.getLogger(__name__)

PERFIL_STATE_KEY = "emu.perfil"
DURACION = timedelta(hours=1)
# «Actualizar» a mano, como mucho una vez por minuto, igual que «Probar conexión».
ESPERA_ACTUALIZAR = timedelta(minutes=1)
CAMPOS = ("username", "group", "uploaded", "downloaded", "ratio", "buffer",
          "seeding", "leeching", "seedbonus", "hit_and_runs")

# Con el Panel y la barra superior abiertos en varias pestañas, solo una va a eMuwarez.
_PIDIENDO = threading.Lock()


def perfil_emu(conn: sqlite3.Connection, *, actualizar: bool = False) -> dict[str, Any]:
    """El perfil guardado; antes lo vuelve a pedir si el último intento tiene más de una hora
    (o de un minuto, con `actualizar`). Un fallo se guarda en `error` junto al último perfil bueno."""
    clave = (get_setting_canonical(conn, "emu.api_key") or "").strip()
    guardado: dict[str, Any] = {}
    if clave:
        guardado = get_json_state(conn, PERFIL_STATE_KEY) or {}
        if _caducado(guardado, ESPERA_ACTUALIZAR if actualizar else DURACION) and _PIDIENDO.acquire(blocking=False):
            try:
                guardado = _pedir(conn, clave, guardado)
            finally:
                _PIDIENDO.release()
    perfil = guardado.get("perfil") or {}
    return {
        "configured": bool(clave),
        **{campo: perfil.get(campo) for campo in CAMPOS},
        # Sin perfil todavía, el usuario de Ajustes basta para los enlaces.
        "username": perfil.get("username") or get_setting_canonical(conn, "emu.username") or None,
        "updated_at": guardado.get("leido_at"),
        "error": guardado.get("error"),
    }


def _caducado(guardado: dict[str, Any], plazo: timedelta) -> bool:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(guardado["intento_at"]) >= plazo
    except (KeyError, TypeError, ValueError):
        return True


def _pedir(conn: sqlite3.Connection, clave: str, guardado: dict[str, Any]) -> dict[str, Any]:
    nuevo = {**guardado, "intento_at": datetime.now(timezone.utc).isoformat()}
    try:
        datos = emu_get_user(clave)
    except IntegrationError as exc:
        logger.warning("No se pudo leer el perfil de eMuwarez: %s", exc)
        nuevo["error"] = str(exc)
    else:
        nuevo.update(perfil={campo: datos.get(campo) for campo in CAMPOS}, leido_at=nuevo["intento_at"], error=None)
        # «Mis peticiones» cuenta por este nombre: si no lo has escrito en Ajustes, se pone el de la cuenta.
        if not get_setting_canonical(conn, "emu.username"):
            set_setting(conn, "emu.username", str(datos["username"]))
    set_json_state(conn, PERFIL_STATE_KEY, nuevo)
    conn.commit()
    return nuevo
