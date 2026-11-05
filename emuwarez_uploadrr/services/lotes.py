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
    paradas = _paradas_por_el_freno(puntas)
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
        # El freno (frenar_si_fallo_sistemico): su motivo y cuántas puntas paró sin empezar. Cuentan en `canceladas`.
        "parado": paradas[0].get("error_message") if paradas else None,
        "paradas": len(paradas),
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
    paradas = _paradas_por_el_freno(puntas)
    if paradas:
        # El lote terminó porque lo paró el freno: lo dice el resumen, que con «Una por lote» es el único aviso.
        cuerpo += "\n" + _frase_de_parada(paradas[0].get("error_message") or "", len(paradas))
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
    """Reencola, en el orden del lote, cada elemento fallido o cancelado (también los que paró el freno, que quedan
    cancelados). El reintento sigue en el lote. Uno que ya tiene otra subida en marcha se salta con su motivo."""
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


# ── El freno del lote (pregunta 4 de docs/PLAN_SUBIDA_POR_LOTES.md) ───────────────────────────────────────────────
#
# Un fallo sistémico (eMuwarez caído, qBittorrent mal, una clave que ya no vale) haría fallar el resto del lote uno
# tras otro, con un aviso por subida. Cuando una punta del lote acaba `failed`, se miran las puntas ya terminadas por
# orden de fin (finished_at, y el id para desempatar): si los FALLOS_SEGUIDOS_PARA_PARAR últimos fallos que cuentan
# tienen el mismo motivo y al lote le quedan puntas en cola, esas no se lanzan. Las que se preparan o suben siguen.
#
# - Un fallo «por elemento» (MARCAS_DE_FALLO_POR_ELEMENTO) no dice nada del resto: ni cuenta ni corta la racha. Una
#   completada la corta. Las canceladas (también las que para el freno) se saltan.
# - Las paradas quedan `cancelled` con stage ETAPA_LOTE_PARADO y el motivo en error_message: no llegaron a empezar
#   (como las de «Cancelar pendientes»), «Reintentar fallidas» ya relanza las canceladas, la racha ya se las salta y
#   no salen como «Subida fallida» en «Necesita atención» del Panel.
# - Decide uno solo: «¿hay que parar?» y apuntar qué puntas se paran (app_state `lote_frenado:<lote_id>`) van en la
#   misma transacción BEGIN IMMEDIATE. Otro fallo que se evalúe a la vez solo vería como pendientes las que no están
#   apuntadas, así que no para dos veces ni avisa dos veces. Un reintento es una fila nueva, con otro id: si la
#   racha vuelve, el lote se puede parar otra vez.
# - Lo dispara _notify_upload_failed (upload_execution/estado.py), por donde pasa todo fallo de una subida: _fail de
#   la preparación y las cuatro salidas fallidas de Uploadrr-EMU. reconcile_interrupted_jobs, al arrancar, no pasa
#   por ahí, y su motivo tampoco cuenta.

FALLOS_SEGUIDOS_PARA_PARAR = 5
# La fase de las puntas que para el freno (status 'cancelled'): así se distinguen de una cancelación a mano.
ETAPA_LOTE_PARADO = "lote_parado"
_CLAVE_LOTE_FRENADO = "lote_frenado:"
_MAX_MOTIVO = 200

# Fallos que solo dicen algo del propio elemento. Se buscan sin distinguir mayúsculas en la primera línea de
# error_message; un mensaje que junta varios motivos con «; » solo es «por elemento» si lo son todos (el que junta
# una clave que falta con la nomenclatura bloqueada sí cuenta). No hay una categoría guardada del fallo: es el texto.
#
# Los nuestros: los que escribe la preparación (upload_queue._fail, a veces con lo que devuelven upload_preflight y
# season_pack). test_freno_de_lote.py comprueba que cada uno sigue apareciendo en el código: si cambias el mensaje,
# cambia la marca.
_MARCAS_DE_LA_APP: tuple[str, ...] = (
    "no tiene un elemento de biblioteca asociado",
    "ya no existe en la biblioteca",
    "El ítem no está disponible localmente",
    "El ítem no tiene ruta de archivo registrada",
    "La temporada no tiene ningún episodio disponible",
    "no es accesible",  # el archivo, o el de un capítulo del pack
    "MediaInfo no pudo leer",
    "mkvtoolnix no pudo leer",
    "Hay errores en la propuesta de nomenclatura",
    "Error aplicando la nomenclatura",
    "No se pudo aplicar la nomenclatura",
    " es de la subida #",  # su carpeta en subidas es de otra subida que la siembra
    # reconcile_interrupted_jobs: la aplicación se paró; no habla de eMuwarez ni del resto del lote.
    "Interrumpido al pararse la aplicación",
)
# Los de Uploadrr-EMU, tal como los imprime (son la primera línea que deja upload_result_parser.build_error_summary):
# los títulos de panel de sus comprobaciones previas (src/utils/checks.py) y lo que eMuwarez rechaza por el propio
# torrent. Contrato con Uploadrr-EMU: si cambia el texto allí, cambia aquí.
_MARCAS_DE_UPLOADRR: tuple[str, ...] = (
    "Potential duplicate on",
    "Exact size match",
    "Banned group on",
    "Banned content on",
    "TMDb ID not found",
    "has already been taken",  # el nombre ya está en eMuwarez
    "trump",  # eMuwarez rechaza una copia peor que la que ya tiene
)
MARCAS_DE_FALLO_POR_ELEMENTO: tuple[str, ...] = _MARCAS_DE_LA_APP + _MARCAS_DE_UPLOADRR
_MARCAS_PLEGADAS = tuple(m.casefold() for m in MARCAS_DE_FALLO_POR_ELEMENTO)


def motivo_de_fallo(error_message: str | None) -> str | None:
    """El motivo con el que se comparan los fallos del lote: la primera línea no vacía de error_message, recortada.
    None si es un fallo por elemento (no cuenta para el freno) o no hay motivo."""
    primera = next((linea.strip() for linea in (error_message or "").splitlines() if linea.strip()), "")
    if not primera:
        return None
    partes = [p.strip().casefold() for p in primera.split("; ") if p.strip()]
    if all(any(m in parte for m in _MARCAS_PLEGADAS) for parte in partes):
        return None
    return primera[:_MAX_MOTIVO]


def texto_de_parada(motivo: str) -> str:
    """El error_message de cada punta que para el freno."""
    return f"Lote parado: {FALLOS_SEGUIDOS_PARA_PARAR} fallos seguidos por «{motivo}»"


def _frase_de_parada(texto: str, paradas: int) -> str:
    """La línea del aviso (y del resumen del lote) que dice que se paró, cuántas no empezaron y cómo relanzarlas."""
    return (f"{texto}. " + (f"{paradas} subida no llegó a empezar; «Reintentar fallidas» la relanza." if paradas == 1
                            else f"{paradas} subidas no llegaron a empezar; «Reintentar fallidas» las relanza."))


def _paradas_por_el_freno(puntas: list[dict]) -> list[dict]:
    return [p for p in puntas if p.get("status") == "cancelled" and p.get("stage") == ETAPA_LOTE_PARADO]


def _racha_de_fallos(puntas: list[dict]) -> str | None:
    """El motivo si los últimos FALLOS_SEGUIDOS_PARA_PARAR fallos que cuentan, por orden de fin, lo comparten y
    ninguna completada los corta. None si no."""
    terminadas = sorted((p for p in puntas if p.get("status") in ("completed", "failed")),
                        key=lambda p: (p.get("finished_at") or "", p["id"]))
    motivos: list[str] = []
    for p in reversed(terminadas):
        if p.get("status") == "completed":
            break
        motivo = motivo_de_fallo(p.get("error_message"))
        if motivo is None:
            continue
        motivos.append(motivo)
        if len(motivos) == FALLOS_SEGUIDOS_PARA_PARAR:
            break
    if len(motivos) == FALLOS_SEGUIDOS_PARA_PARAR and len(set(motivos)) == 1:
        return motivos[0]
    return None


def _decidir_parada(conn: sqlite3.Connection, lote_id: str, job_id: int) -> tuple[str, list[int]] | None:
    """(motivo, ids de las puntas en cola que hay que parar) si el fallo de `job_id` completa la racha y nadie ha
    decidido ya parar esas mismas; apunta la decisión en la misma transacción. None si no toca parar."""
    from ..database import get_state, set_state

    previo = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            puntas = _puntas(conn, lote_id)
            por_id = {p["id"]: p for p in puntas}
            propio = por_id.get(job_id)
            clave = _CLAVE_LOTE_FRENADO + lote_id
            # Solo las que siguen siendo puntas: un id viejo ya no es del lote.
            ya = {int(i) for i in (get_state(conn, clave) or "").split(",") if i.isdigit()} & por_id.keys()
            pendientes = [p["id"] for p in puntas if p.get("status") == "queued" and p["id"] not in ya]
            motivo = None
            # El fallo que dispara tiene que contar: uno por elemento no cambia la racha.
            if (len(puntas) > 1 and propio and propio.get("status") == "failed" and pendientes
                    and motivo_de_fallo(propio.get("error_message")) is not None):
                motivo = _racha_de_fallos(puntas)
            if motivo is None:
                conn.execute("ROLLBACK")
                return None
            set_state(conn, clave, ",".join(str(i) for i in sorted(ya | set(pendientes))))
            conn.execute("COMMIT")
            return motivo, pendientes
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = previo


def _parar_pendientes(conn: sqlite3.Connection, pendientes: list[int], motivo: str) -> list[int]:
    """Como «Cancelar pendientes»: todas de una vez y antes de sacarlas de la puerta, así ninguna toma la plaza que
    deja otra. Una que arrancó entre la decisión y la escritura sigue su curso."""
    from .upload_execution import append_upload_log
    from .upload_queue import retirar_de_la_cola
    from .upload_states import escribir_estado

    ahora = datetime.now(timezone.utc).isoformat()
    texto = texto_de_parada(motivo)
    paradas = [j for j in pendientes
               if escribir_estado(j, desde={"queued"}, status="cancelled", stage=ETAPA_LOTE_PARADO, finished_at=ahora,
                                  error_message=texto, conn=conn)]
    for job_id in paradas:
        retirar_de_la_cola(job_id)
        append_upload_log(job_id, "warning",
                          f"{texto}. No llegó a empezar: «Reintentar fallidas» en el lote la relanza.", stream="system")
    return paradas


def _avisar_parada(conn: sqlite3.Connection, lote_id: str, motivo: str, paradas: int) -> None:
    """Un solo aviso. Con «Una por lote», la parada hace terminar el lote (o terminará con la última en marcha) y lo
    cuenta su resumen. Con «Una por subida», un aviso «Lote parado» del tipo de las subidas fallidas: lo reciben los
    canales que reciben esas, y abre Subidas filtrada por el lote. Las paradas no avisan una a una."""
    from .notification_center import emit

    if avisa_por_lote(conn):
        avisar_si_lote_terminado(lote_id)
        return
    emit(conn, "upload_failed", "Lote parado",
         _frase_de_parada(texto_de_parada(motivo), paradas) + f"\nLote {lote_id}.",
         level="error", entity_type="upload_lote", entity_id=int(lote_id, 16))


def frenar_si_fallo_sistemico(job_id: int) -> int:
    """El freno del lote, tras escribir el `failed` de `job_id` (ver arriba). Devuelve cuántas puntas en cola ha
    parado. Nunca lanza."""
    try:
        from ..database import connect
        conn = connect()
        try:
            fila = conn.execute("SELECT lote_id FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
            lote_id = fila["lote_id"] if fila else None
            if not lote_id_valido(lote_id):
                return 0
            decision = _decidir_parada(conn, lote_id, job_id)
            if decision is None:
                return 0
            motivo, pendientes = decision
            paradas = _parar_pendientes(conn, pendientes, motivo)
            logger.warning("Lote %s parado tras %d fallos seguidos por «%s»: %d subida(s) en cola no se lanzan",
                           lote_id, FALLOS_SEGUIDOS_PARA_PARAR, motivo, len(paradas))
            if paradas:
                try:
                    _avisar_parada(conn, lote_id, motivo, len(paradas))
                except Exception:
                    logging.getLogger("emuwarez.notifications").exception(
                        "No se pudo avisar de la parada del lote %s", lote_id)
            return len(paradas)
        finally:
            conn.close()
    except Exception:
        logger.exception("No se pudo comprobar el freno del lote de la subida %s", job_id)
        return 0


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
