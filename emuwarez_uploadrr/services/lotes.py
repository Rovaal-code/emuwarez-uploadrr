"""Lotes de subidas: varias subidas lanzadas de una vez (una tanda del asistente, y más adelante el modal «Subir por
lotes»). Un lote no es una tabla: es la etiqueta `upload_jobs.lote_id`, y lo que se sabe de él se deduce de sus filas.
Pertenece al lote la punta de cada cadena de reintentos que lleva esa etiqueta (ver docs/PLAN_SUBIDA_POR_LOTES.md).

Todo el SQL de los lotes vive aquí o en upload_execution/consultas.py: web/ no habla SQL."""

from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timezone
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


def _puntas(conn: sqlite3.Connection, lote_id: str) -> list[dict]:
    """Los elementos del lote: la punta de cada cadena que lleva su etiqueta, en orden de id (el de la cola)."""
    from ..database import rows_to_dicts
    return rows_to_dicts(conn.execute(
        f"SELECT * FROM upload_jobs WHERE lote_id = ? AND {CONDICION_PUNTA} ORDER BY id", (lote_id,),
    ).fetchall())


def resumen_de_lote(conn: sqlite3.Connection, lote_id: str) -> dict | None:
    """Cuántos elementos del lote hay en cada estado y qué se puede hacer con él. None si no hay ninguno.
    Solo BD local: nunca llama a eMuwarez ni a qBittorrent."""
    from .upload_states import ACTIVE_JOB_STATUSES, RETRYABLE_STATUSES
    puntas = _puntas(conn, lote_id)
    if not puntas:
        return None
    estados = [p.get("status") for p in puntas]
    en_cola = estados.count("queued")
    en_marcha = sum(1 for e in estados if e in ACTIVE_JOB_STATUSES and e != "queued")
    reintentables = sum(1 for e in estados if e in RETRYABLE_STATUSES)
    return {
        "lote_id": lote_id,
        "total": len(puntas),
        "en_cola": en_cola,
        "en_marcha": en_marcha,
        "completadas": estados.count("completed"),
        "fallidas": estados.count("failed"),
        "canceladas": estados.count("cancelled"),
        "creado": min((p.get("created_at") or "") for p in puntas) or None,
        "terminado": en_cola + en_marcha == 0,
        "puede_cancelar": en_cola + en_marcha > 0,
        "puede_reintentar": reintentables > 0,
    }


def cancelar_lote(conn: sqlite3.Connection, lote_id: str, *, solo_pendientes: bool = True) -> dict:
    """Cancela lo que queda del lote. Primero los que esperan en la cola, todos de una vez y antes de sacarlos de la
    puerta: así ninguno toma la plaza que deja otro. Un trabajo que ya había arrancado entre la lectura y la
    escritura no se toca (cancel_upload_job lo cancelaría como lo que es ahora, y eso ya no es «pendiente»).
    Con `solo_pendientes=False`, después también los que se preparan o suben, por el camino de siempre."""
    from .upload_execution import append_upload_log, cancel_upload_job
    from .upload_queue import retirar_de_la_cola
    from .upload_states import ACTIVE_JOB_STATUSES, escribir_estado

    ahora = datetime.now(timezone.utc).isoformat()
    puntas = _puntas(conn, lote_id)
    canceladas: list[int] = []
    intactas = 0
    for job in puntas:
        if job.get("status") != "queued":
            continue
        if escribir_estado(job["id"], desde={"queued"}, status="cancelled", stage="cancelled", finished_at=ahora,
                           conn=conn):
            canceladas.append(job["id"])
        else:
            intactas += 1
    for job_id in canceladas:
        retirar_de_la_cola(job_id)
        append_upload_log(job_id, "info", "Subida cancelada con el resto del lote mientras esperaba turno.",
                          stream="system")

    if not solo_pendientes:
        # Las que ya estaban en marcha y también las que arrancaron entre la lectura y la escritura de arriba.
        intactas = 0
        hechas = set(canceladas)
        for job in puntas:
            if job["id"] in hechas or job.get("status") not in ACTIVE_JOB_STATUSES:
                continue
            # cancel_upload_job relee el estado: una que acaba de terminar ya no se toca.
            if cancel_upload_job(job["id"], conn=conn).get("ok"):
                canceladas.append(job["id"])
            else:
                intactas += 1
    return {"canceladas": len(canceladas), "intactas": intactas}


def reintentar_fallidas(conn: sqlite3.Connection, lote_id: str, *, desde_el_principio: bool = False) -> dict:
    """Reencola, en el orden del lote, cada elemento fallido o cancelado. El reintento sigue en el lote. Uno que ya
    tiene otra subida en marcha se salta con su motivo."""
    from .upload_queue import queue_retry_for_job
    from .upload_states import RETRYABLE_STATUSES

    encoladas: list[int] = []
    saltadas: list[dict] = []
    for job in _puntas(conn, lote_id):
        if job.get("status") not in RETRYABLE_STATUSES:
            continue
        resultado = queue_retry_for_job(job["id"], conn=conn, desde_el_principio=desde_el_principio)
        if resultado.get("status") == "queued" and resultado.get("job"):
            encoladas.append(resultado["job"]["id"])
        else:
            saltadas.append({"job_id": job["id"], "title": job.get("title"),
                             "errors": resultado.get("errors") or ["No se pudo reintentar."]})
    return {"reintentadas": len(encoladas), "saltadas": saltadas}
