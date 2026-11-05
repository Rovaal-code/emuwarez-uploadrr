"""Lotes de subidas: varias subidas lanzadas de una vez (una tanda del asistente, y más adelante el modal «Subir por
lotes»). Un lote no es una tabla: es la etiqueta `upload_jobs.lote_id`, y lo que se sabe de él se deduce de sus filas.
Pertenece al lote la punta de cada cadena de reintentos que lleva esa etiqueta (ver docs/PLAN_SUBIDA_POR_LOTES.md).

Todo el SQL de los lotes vive aquí o en upload_execution/consultas.py: web/ no habla SQL."""

from __future__ import annotations

import logging
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
# Lo que se sube por lotes: una serie se elige por temporadas.
TIPOS_DE_LOTE = ("movie", "season", "episode")

logger = logging.getLogger("emuwarez.upload")


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


# ── El aviso de fin de lote (Ajustes → Notificaciones → «Una por lote») ──────────────────────────────────────────
#
# Con «Una por lote», las subidas de un lote no avisan una a una (_notify_upload_completed/_failed): cuando la última
# punta del lote llega a un estado final se emite una sola notificación `upload_batch_done` con el resumen. Un lote
# que se ha quedado en un elemento (se subió otra vez fuera de él) avisa como una suelta, igual que Subidas solo
# agrupa con más de uno.
#
# Que avise una sola vez: «¿soy el último?» y apuntar que ya se avisó van en la misma transacción BEGIN IMMEDIATE, y
# lo apuntado (app_state `lote_avisado:<lote_id>`) es la FIRMA del lote, los ids de sus puntas. Cada trabajo escribe
# su estado final antes de llamar aquí, así que el último en escribir siempre ve el lote entero terminado; si dos
# terminan a la vez y los dos lo ven, el segundo encuentra la firma ya apuntada y no avisa. «Reintentar fallidas»
# cambia las puntas (los reintentos son filas nuevas), así que cuando terminan los reintentos la firma es otra y el
# lote vuelve a avisar, con el resumen del lote entero. Reiniciar la aplicación no avisa: reconcile_interrupted_jobs
# marca los trabajos como fallidos sin pasar por aquí.

_CLAVE_LOTE_AVISADO = "lote_avisado:"
# Cuántos títulos de fallidas caben en el aviso; el resto se cuenta.
_MAX_TITULOS_FALLIDAS = 5


def avisa_por_lote(conn: sqlite3.Connection) -> bool:
    """Si Ajustes → Notificaciones dice «Una por lote»."""
    from .ajustes_registro import AVISO_LOTE_POR_LOTE
    from .settings import leer_ajuste
    return leer_ajuste(conn, "notify_lote_modo") == AVISO_LOTE_POR_LOTE


def aviso_va_en_el_lote(conn: sqlite3.Connection, job: dict | None) -> bool:
    """Si el aviso de fin de este trabajo lo sustituye el resumen de su lote: es de un lote de más de un elemento y
    el ajuste dice «Una por lote». Una subida suelta (sin lote) avisa siempre como siempre."""
    lote_id = (job or {}).get("lote_id")
    if not lote_id or not avisa_por_lote(conn):
        return False
    return contar_por_lote(conn, [lote_id]).get(lote_id, 0) > 1


def _apuntar_si_terminado(conn: sqlite3.Connection, lote_id: str) -> list[dict] | None:
    """Las puntas del lote si acaba de terminar y nadie ha avisado de él con estas mismas puntas; apunta su firma en
    la misma transacción. None si no toca avisar."""
    from ..database import get_state, set_state
    from .upload_states import TERMINAL_STATUSES

    previo = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            puntas = _puntas(conn, lote_id)
            firma = ",".join(str(p["id"]) for p in puntas)
            clave = _CLAVE_LOTE_AVISADO + lote_id
            if (len(puntas) <= 1 or any(p.get("status") not in TERMINAL_STATUSES for p in puntas)
                    or get_state(conn, clave) == firma):
                conn.execute("ROLLBACK")
                return None
            set_state(conn, clave, firma)
            conn.execute("COMMIT")
            return puntas
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = previo


def _contar(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _emitir_resumen(conn: sqlite3.Connection, lote_id: str, puntas: list[dict]) -> None:
    from .notification_center import emit

    estados = [p.get("status") for p in puntas]
    completadas, fallidas, canceladas = (estados.count(e) for e in ("completed", "failed", "cancelled"))
    cuerpo = (f"{_contar(len(puntas), 'subida', 'subidas')}, {_contar(completadas, 'completada', 'completadas')}, "
              f"{_contar(fallidas, 'fallida', 'fallidas')}, {_contar(canceladas, 'cancelada', 'canceladas')}.")
    titulos = [f"«{p.get('title') or 'Subida'}»" for p in puntas if p.get("status") == "failed"]
    if titulos:
        resto = len(titulos) - _MAX_TITULOS_FALLIDAS
        cuerpo += ("\nFallidas: " + ", ".join(titulos[:_MAX_TITULOS_FALLIDAS])
                   + (f" y {resto} más" if resto > 0 else "") + ".")
    cuerpo += f"\nLote {lote_id}."
    if completadas == len(puntas):
        nivel = "success"
    elif fallidas and not completadas:
        nivel = "error"
    elif fallidas or (canceladas and completadas):
        nivel = "warning"
    else:
        nivel = "info"
    # La campana abre Subidas filtrada por el lote: el lote_id (12 hexadecimales) cabe entero en entity_id, que es un
    # entero (48 bits, por debajo de los 53 que un número de JavaScript guarda sin perder nada).
    emit(conn, "upload_batch_done", "Lote terminado", cuerpo, level=nivel,
         entity_type="upload_lote", entity_id=int(lote_id, 16))


def avisar_si_lote_terminado(lote_id: str | None) -> bool:
    """Con «Una por lote», si el lote acaba de terminar (ninguna punta en cola, preparándose ni subiendo), emite su
    único aviso. Lo llama quien acaba de dejar una punta del lote en un estado final (terminar, fallar, cancelar),
    DESPUÉS de escribirlo. Se puede llamar de más: solo avisa una vez por juego de puntas. Nunca lanza.
    True si ha avisado."""
    if not lote_id_valido(lote_id):
        return False
    try:
        from ..database import connect
        conn = connect()
        try:
            if not avisa_por_lote(conn):
                return False
            puntas = _apuntar_si_terminado(conn, lote_id)
            if puntas is None:
                return False
            _emitir_resumen(conn, lote_id, puntas)
            return True
        finally:
            conn.close()
    except Exception:
        logging.getLogger("emuwarez.notifications").exception("No se pudo emitir el aviso del lote %s", lote_id)
        return False


def avisar_si_termina_su_lote(job_id: int) -> bool:
    """avisar_si_lote_terminado para el lote del trabajo `job_id`, si es de uno. Nunca lanza."""
    try:
        from ..database import connect
        conn = connect()
        try:
            fila = conn.execute("SELECT lote_id FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
    except Exception:
        logging.getLogger("emuwarez.notifications").exception("No se pudo leer el lote de la subida %s", job_id)
        return False
    return avisar_si_lote_terminado(fila["lote_id"] if fila else None)


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
    if canceladas:
        # Si con esto no queda nada en marcha, el lote ha terminado (también si se ha cancelado entero).
        avisar_si_lote_terminado(lote_id)
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


def borrar_lote(conn: sqlite3.Connection, lote_id: str) -> dict:
    """«Borrar lote»: borra cada elemento terminado del lote (completado, fallido o cancelado) por el mismo camino que
    «Borrar» en una fila suelta (delete_upload_job), así que se va la cadena de intentos entera del elemento, también
    los de otros lotes o sueltos (D5), y sus enlaces en la carpeta de subidas si nadie más los usa. Los que siguen en
    cola, preparándose o subiendo no se tocan: se cuentan en `en_curso`. Nunca toca el fichero de la biblioteca."""
    from .upload_execution import DELETE_CONFIRMATION_TOKEN, delete_upload_job
    from .upload_states import ACTIVE_JOB_STATUSES

    borradas = intentos = en_curso = 0
    for job in _puntas(conn, lote_id):
        if job.get("status") in ACTIVE_JOB_STATUSES:
            en_curso += 1
            continue
        resultado = delete_upload_job(job["id"], confirmation=DELETE_CONFIRMATION_TOKEN, conn=conn)
        if resultado.get("ok"):
            borradas += 1
            intentos += len(resultado.get("deleted_job_ids") or [])
        elif resultado.get("error") == "invalid_status":
            # Algún intento de su cadena volvió a la cola entre la lectura y el borrado: se deja, como en una suelta.
            en_curso += 1
        # not_found: otra cadena ya se la llevó (o un borrado a la vez); no queda nada que contar.
    return {"borradas": borradas, "intentos": intentos, "en_curso": en_curso}


class LoteRechazado(Exception):
    """El lote entero no se puede encolar (falta una clave, Uploadrr-EMU no está): cada elemento fallaría igual."""

    def __init__(self, motivos: list[str]):
        super().__init__("; ".join(motivos))
        self.motivos = motivos


def _bloqueado(item_id: int, *motivos: str) -> dict:
    return {"item_id": item_id, "status": "blocked", "job_id": None, "errors": list(motivos)}


def _primer_fallo(comprobaciones: dict) -> str:
    for c in comprobaciones.get("checks") or []:
        if c.get("status") == "fail":
            return f"{c.get('label')}: {c.get('message')}" if c.get("message") else str(c.get("label"))
    return "No pasó las comprobaciones previas."


def _peticion_de(conn: sqlite3.Connection, item_id: int) -> int | None:
    """Sin petición elegida (un lote desde Biblioteca): la abierta que cubre el elemento, si hay una sola. Enlazarla es
    un extra: si falla la búsqueda, el elemento se sube igual, sin petición."""
    from .requests import peticion_que_enlazar
    try:
        return peticion_que_enlazar(conn, item_id)
    except Exception:
        logger.exception("No se pudo buscar la petición del elemento %s; se sube sin enlazar", item_id)
        return None


def _encolar_uno(conn: sqlite3.Connection, el: dict, lote_id: str, vistos: set[int], temporadas: set[int]) -> dict:
    """Un elemento del lote. Todo lo que puede saltarlo va antes de escribir nada: guardar `campos` caduca la
    propuesta vigente del elemento, y hacerlo para uno que luego se salta cambiaría el nombre de su subida en marcha."""
    from .source_assistant import update_nomenclature_fields_preview
    from .nomenclature import save_manual_nomenclature_fields
    from .upload_checks import run_upload_checks
    from .upload_queue import queue_upload_for_item, trabajo_activo

    item_id = int(el["item_id"])
    if item_id in vistos:
        return _bloqueado(item_id, "Repetido en el lote.")
    vistos.add(item_id)
    fila = conn.execute("SELECT id, item_type, parent_id FROM library_items WHERE id = ?", (item_id,)).fetchone()
    if not fila:
        return _bloqueado(item_id, "El elemento ya no está en la biblioteca.")
    tipo = fila["item_type"]
    if tipo not in TIPOS_DE_LOTE:
        return _bloqueado(item_id, "Elige sus temporadas." if tipo == "series" else f"No se sube por lotes ({tipo}).")
    if tipo == "episode" and fila["parent_id"] in temporadas:
        return _bloqueado(item_id, "Su temporada ya va en el lote.")
    checks = el.get("checks") or {}
    if not checks.get("ready"):
        return _bloqueado(item_id, _primer_fallo(checks))
    if tipo != "season":
        # El castellano de una película o un capítulo no se vuelve a mirar al correr el trabajo (solo los packs):
        # no basta con lo que dice el navegador. Es barato: abrir el fichero y leer columnas.
        contenido = run_upload_checks(conn, item_id, scope="content")
        if not contenido.get("ready"):
            return _bloqueado(item_id, _primer_fallo(contenido))
    if trabajo_activo(conn, item_id):
        return _bloqueado(item_id, "Ya hay una subida en curso para este contenido.")

    request_item_id = el.get("request_item_id")
    if request_item_id is None:
        request_item_id = _peticion_de(conn, item_id)
    campos = el.get("campos")
    if campos and tipo != "season":
        preview = update_nomenclature_fields_preview(item_id, campos, conn=conn)
        save_manual_nomenclature_fields(item_id, campos, preview, conn=conn)
    resultado = queue_upload_for_item(
        item_id, request_item_id=request_item_id, checks=checks,
        # El proveedor solo cuenta en un pack; el de una película va dentro de `campos`.
        provider_override=el.get("provider") if tipo == "season" else None,
        lote_id=lote_id, conn=conn,
    )
    job = resultado.get("job") or {}
    if resultado.get("status") != "queued":
        return _bloqueado(item_id, *(resultado.get("errors") or ["No se pudo encolar."]))
    return {"item_id": item_id, "status": "queued", "job_id": job.get("id"), "errors": []}


def encolar_lote(conn: sqlite3.Connection, elementos: list[dict]) -> dict:
    """Encola varias subidas como un lote, en el orden dado (el de la cola). Cada elemento es
    `{item_id, request_item_id?, checks, campos?, provider?}`: `request_item_id` la petición que cubre (la que eligió
    el Panel; sin ella, la abierta del elemento si hay una sola, ver requests.peticion_que_enlazar), `checks` el
    resultado de las comprobaciones que vio el
    usuario, `campos` el juego completo de campos de nomenclatura (película o capítulo, solo si la interfaz sugirió
    un proveedor), `provider` el proveedor elegido para un pack. Un elemento que no se puede subir se salta con su
    motivo y el resto sigue. Si no se encola ninguno, no queda lote (`lote_id` None)."""
    from .upload_queue import _season_upload_preconditions

    if not 1 <= len(elementos) <= MAX_ELEMENTOS_LOTE:
        raise ValueError(f"Un lote lleva entre 1 y {MAX_ELEMENTOS_LOTE} elementos.")
    # Lo que haría fallar a todos en segundos, mirado una vez antes de crear nada.
    motivos = _season_upload_preconditions(conn)
    if motivos:
        raise LoteRechazado(motivos)

    ids = sorted({int(e["item_id"]) for e in elementos})
    temporadas = {fila[0] for fila in conn.execute(
        f"SELECT id FROM library_items WHERE item_type = 'season' AND id IN ({','.join('?' * len(ids))})", ids)}
    lote_id = nuevo_lote_id()
    vistos: set[int] = set()
    resultados: list[dict] = []
    for el in elementos:
        try:
            resultado = _encolar_uno(conn, el, lote_id, vistos, temporadas)
            conn.commit()
        except Exception:
            logger.exception("Lote %s: no se pudo encolar el elemento %s", lote_id, el.get("item_id"))
            conn.rollback()
            resultado = _bloqueado(int(el["item_id"]), "Error inesperado al encolarlo; mira el registro.")
        resultados.append(resultado)
    encolados = sum(1 for r in resultados if r["status"] == "queued")
    return {"lote_id": lote_id if encolados else None, "encolados": encolados,
            "saltados": len(resultados) - encolados, "resultados": resultados}
