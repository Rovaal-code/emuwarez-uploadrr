"""Lotes de subidas: varias subidas lanzadas de una vez (una tanda del asistente, y más adelante el modal «Subir por
lotes»). Un lote no es una tabla: es la etiqueta `upload_jobs.lote_id`, y lo que se sabe de él se deduce de sus filas.
Pertenece al lote la punta de cada cadena de reintentos que lleva esa etiqueta (ver docs/PLAN_SUBIDA_POR_LOTES.md).

Todo el SQL de los lotes vive aquí o en upload_execution/consultas.py: web/ no habla SQL."""

from __future__ import annotations

import re
import secrets
import sqlite3
from typing import Iterable

from .upload_execution.consultas import CONDICION_PUNTA

# Copia vigilada en el frontend (frontend/src/utils/lote.ts, test_copias_frontend.py).
MAX_ELEMENTOS_LOTE = 50
# 12 hexadecimales en minúscula: lo genera el servidor o, en las tandas del asistente, el navegador.
PATRON_LOTE_ID = r"^[0-9a-f]{12}$"
_LOTE_ID = re.compile(PATRON_LOTE_ID)


def nuevo_lote_id() -> str:
    return secrets.token_hex(6)


def lote_id_valido(valor: object) -> bool:
    return isinstance(valor, str) and bool(_LOTE_ID.match(valor))


def contar_por_lote(conn: sqlite3.Connection, lote_ids: Iterable[str]) -> dict[str, int]:
    """Cuántos elementos (puntas de cadena) tiene cada lote, en una sola consulta. Solo BD local."""
    ids = sorted({i for i in lote_ids if i})
    if not ids:
        return {}
    filas = conn.execute(
        f"SELECT lote_id, COUNT(*) FROM upload_jobs WHERE lote_id IN ({','.join('?' * len(ids))}) "
        f"AND {CONDICION_PUNTA} GROUP BY lote_id",
        ids,
    ).fetchall()
    return {fila[0]: fila[1] for fila in filas}
