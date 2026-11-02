"""Historial de tu cuenta de eMuwarez: una instantánea al día, para dibujar su evolución en Estadísticas.

Sale de lo que ya trae el perfil horario (emu_perfil): sin llamadas nuevas a eMuwarez. El día es el local del
servidor (TZ del contenedor, la misma que usan las tareas programadas): así «hoy» es el día del usuario y no el UTC.
Cada lectura sobrescribe la fila del día, de modo que gana el último valor.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

RETENCION_DIAS = 730
MAX_DIAS = 730

_POTENCIA = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5}
_TAMANO = re.compile(r"^\s*(\d[\d,]*(?:\.\d+)?)\s*([KMGTP]?)i?B\s*$", re.I)


def bytes_de_texto(texto: Any) -> Optional[int]:
    """«1.2 TiB» (como lo escribe UNIT3D) a bytes; None si no es un tamaño."""
    m = _TAMANO.match(texto) if isinstance(texto, str) else None
    if not m:
        return None
    return round(float(m.group(1).replace(",", "")) * 1024 ** _POTENCIA[m.group(2).upper()])


def _numero(valor: Any) -> Optional[float]:
    """«4.1» o «12345.50» a número; None si no lo es (el ratio puede ser «∞»)."""
    try:
        n = float(str(valor).replace(",", ""))
    except ValueError:
        return None
    return n if n == n and abs(n) != float("inf") else None


def _entero(valor: Any) -> Optional[int]:
    n = _numero(valor)
    return None if n is None else int(n)


def guardar_instantanea(conn: sqlite3.Connection, datos: dict[str, Any], ahora: Optional[datetime] = None) -> None:
    """Escribe la instantánea de hoy con el perfil recién leído y poda lo que pase de la retención.
    No hace commit (lo hace quien guarda el perfil) y nunca lanza: el historial no puede romper la lectura."""
    try:
        ahora = ahora or datetime.now()
        valores = (_numero(datos.get("ratio")), bytes_de_texto(datos.get("uploaded")),
                   bytes_de_texto(datos.get("downloaded")), _numero(datos.get("seedbonus")),
                   _entero(datos.get("hit_and_runs")))
        conn.execute(
            """INSERT INTO perfil_historial (dia, ratio, subido_bytes, bajado_bytes, bonus, hit_and_runs, actualizado_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(dia) DO UPDATE SET ratio = excluded.ratio, subido_bytes = excluded.subido_bytes,
                   bajado_bytes = excluded.bajado_bytes, bonus = excluded.bonus,
                   hit_and_runs = excluded.hit_and_runs, actualizado_at = excluded.actualizado_at""",
            (ahora.strftime("%Y-%m-%d"), *valores, ahora.isoformat(timespec="seconds")),
        )
        conn.execute("DELETE FROM perfil_historial WHERE dia < ?",
                     ((ahora - timedelta(days=RETENCION_DIAS)).strftime("%Y-%m-%d"),))
    except Exception:
        logger.warning("No se pudo guardar la instantánea de la cuenta", exc_info=True)


def serie_cuenta(conn: sqlite3.Connection, dias: int, ahora: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Las instantáneas de los últimos `dias` días (hoy incluido), de la más antigua a la más reciente."""
    desde = ((ahora or datetime.now()) - timedelta(days=dias - 1)).strftime("%Y-%m-%d")
    filas = conn.execute(
        """SELECT dia, ratio, subido_bytes, bajado_bytes, bonus, hit_and_runs
           FROM perfil_historial WHERE dia >= ? ORDER BY dia""", (desde,))
    return [dict(f) for f in filas]
