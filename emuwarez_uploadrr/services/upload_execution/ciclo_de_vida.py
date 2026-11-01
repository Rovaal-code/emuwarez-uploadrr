"""Reintento, cancelación y borrado de trabajos de subida."""
from __future__ import annotations

import os
import signal

from .comun import CONFIRMATION_TOKEN, DELETE_CONFIRMATION_TOKEN, ETAPA_ESPERANDO_TURNO, _get_db_conn, _now
from .concurrencia import _upload_concurrency_gate
from .consultas import build_uploadrr_execution_command, get_upload_job
from .ejecucion import start_upload_job
from .estado import _update_job_status
from .procesos import _PROCESOS, _PROCESOS_LOCK, _detener_proceso, _pid_es_de_este_job
from .registro import append_upload_log


def retry_upload_job(
    job_id: int,
    *,
    dry_run: bool = True,
    start: bool = False,
    confirmation: str | None = None,
    wait: bool = False,
) -> dict:
    """Create a new upload_job as a retry of job_id.

    Only allowed for failed/cancelled jobs.
    Never mutates the original job.
    """
    conn = _get_db_conn()
    try:
        original = get_upload_job(job_id, conn=conn)
        if not original:
            return {
                "ok": False,
                "action": "blocked",
                "error": "not_found",
                "message": f"Job {job_id} no encontrado.",
                "job_id": job_id,
            }

        status = original.get("status", "")
        if status not in ("failed", "cancelled"):
            return {
                "ok": False,
                "action": "blocked",
                "error": "invalid_status",
                "message": (
                    f"Solo se puede reintentar un job en estado failed/cancelled. "
                    f"Estado actual: {status}"
                ),
                "job_id": job_id,
            }

        # Build command preview from original job
        cmd_preview: str | None = None
        try:
            cmd = build_uploadrr_execution_command(original, conn=conn)
            cmd_preview = cmd.get("command_preview")
        except Exception:
            pass

        if dry_run:
            return {
                "ok": True,
                "action": "dry_run",
                "dry_run": True,
                "job_id": job_id,
                "original_status": status,
                "retry_count_would_be": (original.get("retry_count") or 0) + 1,
                "command_preview": cmd_preview,
                "message": "Dry-run: no se ha creado ni ejecutado ningún job nuevo.",
                "error": None,
            }

        if not start:
            return {
                "ok": False,
                "action": "blocked",
                "dry_run": False,
                "error": "blocked",
                "job_id": job_id,
                "message": "Se requiere start=true para reintentar.",
            }

        if confirmation != CONFIRMATION_TOKEN:
            return {
                "ok": False,
                "action": "blocked",
                "dry_run": False,
                "error": "confirmation_required",
                "job_id": job_id,
                "message": f'Se requiere confirmación exacta: "{CONFIRMATION_TOKEN}".',
            }

        from ..upload_queue import trabajo_activo
        activa = trabajo_activo(conn, original.get("library_item_id"))
        if activa:
            return {
                "ok": False,
                "action": "blocked",
                "dry_run": False,
                "error": "blocked",
                "job_id": job_id,
                "message": f"Ya hay una subida en curso para este contenido (job {activa['id']}).",
            }

        # Create new job
        now = _now()
        retry_count = (original.get("retry_count") or 0) + 1
        cur = conn.execute(
            """INSERT INTO upload_jobs
               (library_item_id, request_item_id, request_title, request_url,
                title, path,
                source_path, prepared_path, uploadrr_command_json,
                status, stage, retry_of_job_id, retry_count,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', 'preflight', ?, ?, ?, ?)""",
            (
                original.get("library_item_id"),
                original.get("request_item_id"),
                original.get("request_title"),
                original.get("request_url"),
                original.get("title", ""),
                original.get("path", ""),
                original.get("source_path"),
                original.get("prepared_path"),
                original.get("uploadrr_command_json"),
                job_id,
                retry_count,
                now,
                now,
            ),
        )
        conn.commit()
        new_job_id = cur.lastrowid

        append_upload_log(
            new_job_id, "info",
            f"Retry del job {job_id} (intento {retry_count}).",
            stream="system",
        )

        # Start the new job
        result = start_upload_job(
            new_job_id,
            dry_run=False,
            start=True,
            confirmation=CONFIRMATION_TOKEN,
            conn=conn,
            wait=wait,
        )
        result["retry_of_job_id"] = job_id
        result["retry_count"] = retry_count
        result["new_job_id"] = new_job_id
        return result
    finally:
        conn.close()


def cancel_upload_job(job_id: int, conn=None) -> dict:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        job = get_upload_job(job_id, conn=conn)
        if not job:
            return {"ok": False, "message": f"Job {job_id} no encontrado.", "job_id": job_id}

        status = job.get("status", "")

        if status == "queued":
            # En cola: aún no se ha tocado ningún fichero. Primero la fila, y
            # luego se saca de la cola; si justo le tocaba plaza, su hilo ve
            # el 'cancelled' al empezar y la suelta sin hacer nada. La escritura
            # solo cae si sigue en 'queued': si avanzó entre la lectura y aquí,
            # se cancela como lo que es ahora (un 'running' necesita matar el proceso).
            from ..upload_states import escribir_estado
            if not escribir_estado(job_id, desde={"queued"}, status="cancelled", stage="cancelled",
                                   finished_at=_now(), conn=conn):
                return cancel_upload_job(job_id, conn=conn)
            from ..upload_queue import retirar_de_la_cola
            retirar_de_la_cola(job_id)
            append_upload_log(job_id, "info", "Subida cancelada mientras esperaba turno en la cola.", stream="system")
            return {"ok": True, "message": "Subida cancelada.", "job_id": job_id}

        if status == "ready" and job.get("stage") == ETAPA_ESPERANDO_TURNO:
            # Arranque directo esperando plaza: aún no hay proceso. La escritura
            # solo cae si sigue en 'ready'; si justo entró y ya está en marcha,
            # se cancela como lo que es ahora.
            from ..upload_states import escribir_estado
            if not escribir_estado(job_id, desde={"ready"}, status="cancelled", stage="cancelled",
                                   finished_at=_now(), conn=conn):
                return cancel_upload_job(job_id, conn=conn)
            _upload_concurrency_gate.retirar_si_espera(job_id)
            append_upload_log(job_id, "info", "Subida cancelada mientras esperaba turno; no se lanza.",
                              stream="system", conn=conn)
            return {"ok": True, "message": "Subida cancelada.", "job_id": job_id}

        if status == "staging":
            # Nada que señalar (ni subproceso ni temporizador), solo se marca
            # la fila. Ya no se crean jobs en 'staging' (era del modo
            # Automático, retirado), pero una base anterior puede tener alguno
            # atascado ahí y tiene que poder cancelarse.
            _update_job_status(job_id, "cancelled", stage="cancelled", finished_at=_now())
            append_upload_log(job_id, "info", "Subida automática cancelada mientras se preparaba.", stream="system")
            return {"ok": True, "message": "Subida cancelada.", "job_id": job_id}

        if status == "preparing":
            # Preparando: puede estar renombrando ficheros o remuxeando, y
            # abortar a media faena dejaría un .tmp suelto o un fichero a
            # medio renombrar. Así que no se interrumpe: se marca la fila y el
            # trabajo se rinde en el siguiente punto limpio, entre fases
            # (upload_queue._mark comprueba el estado antes de avanzar).
            #
            # Y si el proceso YA no existe —la aplicación se paró a mitad—
            # esto es lo único que desatasca el job: antes se quedaba en
            # 'preparing' para siempre, sin botón que lo tocara.
            _update_job_status(job_id, "cancelled", stage="cancelled", finished_at=_now())
            append_upload_log(
                job_id, "info",
                "Cancelación solicitada durante la preparación. Si el proceso sigue vivo, "
                "terminará el paso en curso y se detendrá; si ya no existe, el job queda "
                "cancelado y se puede reintentar.",
                stream="system",
            )
            return {
                "ok": True,
                "message": "Subida cancelada. Se detendrá al terminar el paso en curso.",
                "job_id": job_id,
            }

        if status != "running":
            return {
                "ok": False,
                "message": f"El job no está en ejecución (status={status}). No hay proceso que cancelar.",
                "job_id": job_id,
            }

        pid = job.get("process_id")
        cancelled = False
        with _PROCESOS_LOCK:
            proc = _PROCESOS.get(job_id)
        if proc is not None:
            cancelled = _detener_proceso(proc)
            if cancelled:
                append_upload_log(
                    job_id, "info",
                    f"SIGTERM enviado al grupo del proceso {proc.pid}.",
                    stream="system",
                    conn=conn,
                )
        elif pid and not _pid_es_de_este_job(pid, job):
            append_upload_log(
                job_id, "warning",
                f"No se señala el PID {pid}: no se puede comprobar que siga siendo el Uploadrr de este job.",
                stream="system",
                conn=conn,
            )
        elif pid:
            # Lo lanzó otro proceso (el CLI): solo se conoce su PID, que es el de su grupo.
            try:
                os.killpg(pid, signal.SIGTERM)
                cancelled = True
                append_upload_log(
                    job_id, "info",
                    f"SIGTERM enviado al grupo del proceso {pid}.",
                    stream="system",
                    conn=conn,
                )
            except (ProcessLookupError, PermissionError) as exc:
                append_upload_log(
                    job_id, "warning",
                    f"No se pudo enviar SIGTERM al PID {pid}: {exc}",
                    stream="system",
                    conn=conn,
                )

        _update_job_status(
            job_id, "cancelled",
            stage="cancelled",
            finished_at=_now(),
        )
        append_upload_log(job_id, "info", "Job marcado como cancelado.", stream="system")

        return {
            "ok": True,
            "message": "Job cancelado." + (
                " Señal enviada al proceso." if cancelled else " El proceso puede no estar activo."
            ),
            "job_id": job_id,
        }
    finally:
        if own:
            conn.close()


def retry_chain_ids(job_id: int, conn) -> list[int]:
    """Todos los intentos de la misma subida, entrando por cualquiera de ellos.

    Se sube por retry_of_job_id hasta el intento original y luego se baja
    recogiendo todo lo que cuelga de él. El control de visitados no es
    decorativo: una fila que se apuntara a sí misma, o un ciclo por datos
    corruptos, colgaría el bucle.
    """
    visto: set[int] = {job_id}
    raiz = job_id
    while True:
        fila = conn.execute("SELECT retry_of_job_id FROM upload_jobs WHERE id = ?", (raiz,)).fetchone()
        padre = fila["retry_of_job_id"] if fila else None
        if padre is None or padre in visto:
            break
        visto.add(padre)
        raiz = padre

    ids: list[int] = []
    pendientes = [raiz]
    while pendientes:
        actual = pendientes.pop()
        if actual in ids:
            continue
        ids.append(actual)
        for fila in conn.execute("SELECT id FROM upload_jobs WHERE retry_of_job_id = ?", (actual,)).fetchall():
            pendientes.append(fila["id"])
    return ids


def delete_upload_job(job_id: int, confirmation: str | None = None, conn=None) -> dict:
    """Permanently remove a job and everything registered about it (logs,
    artifacts) — never the real media file, which lives in Radarr/Sonarr's own
    library and this app never touches.

    Only allowed for a TERMINAL status: 'cancelled', 'failed' or 'completed'.
    A job still queued/staging/preparing/running has to be cancelled first
    (there's a live subprocess/timer to stop, which this never does).

    'completed' entra porque borrar el registro de una subida que salió bien
    no deshace nada: el torrent ya está en eMuwarez y el archivo sigue en su
    sitio. Lo que se borra es el historial en esta aplicación.
    Borra la CADENA DE INTENTOS entera, no solo el job que se le pasa: cada
    "Reintentar" crea una fila nueva que apunta a la anterior, así que una
    subida con 5 reintentos son 6 filas. Antes se borraban de una en una,
    empezando obligatoriamente por la última (borrar una con un reintento
    posterior se rechazaba), así que quitar del historial una subida que
    había costado varios intentos pedía pulsar Borrar seis veces. La tabla
    ya las enseña como una sola fila con sus intentos anidados, y eso es lo
    que se borra: la fila que se ve.

    Da igual por qué intento de la cadena se entre, se resuelve entera. Si
    alguno sigue vivo (en cola, preparando o subiendo) no se borra nada:
    hay un proceso en marcha que esto no sabe parar, y hacerlo a medias
    dejaría la cadena rota.
    """
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        job = get_upload_job(job_id, conn=conn)
        if not job:
            return {"ok": False, "error": "not_found", "message": f"Job {job_id} no encontrado.", "job_id": job_id}

        if confirmation != DELETE_CONFIRMATION_TOKEN:
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": f"Confirmación requerida: {DELETE_CONFIRMATION_TOKEN}",
                "job_id": job_id,
            }

        chain = retry_chain_ids(job_id, conn=conn)

        vivos = conn.execute(
            f"SELECT id, status FROM upload_jobs WHERE id IN ({','.join('?' * len(chain))}) "
            "AND status NOT IN ('cancelled', 'failed', 'completed')",
            chain,
        ).fetchall()
        if vivos:
            estados = ", ".join(sorted({str(r["status"]) for r in vivos}))
            return {
                "ok": False,
                "error": "invalid_status",
                "message": f"Solo se pueden borrar subidas terminadas: completadas, "
                           f"canceladas o fallidas (status={estados}).",
                "job_id": job_id,
            }

        # Las carpetas de enlaces de los packs, antes de perder sus rutas. Solo
        # borra enlaces: los ficheros de verdad siguen en la carpeta de Sonarr,
        # que es la gracia de todo esto (ver services/carpeta_subida.py). Y
        # solo si la ruta está dentro de la carpeta de subidas, así que un
        # prepared_path que apunte a la biblioteca no se toca.
        #
        # Se quedan los que usa cualquier subida completada (qBittorrent siembra
        # de ahí, también si se canceló o falló después de subir el torrent: eso
        # lo dice `torrent_subido`) o todavía viva (se está preparando o
        # subiendo), sea de esta cadena o de otra: los intentos fallidos suelen
        # apuntar al mismo enlace.
        from ..carpeta_subida import ENLACES, borrar_de_subidas
        marcas = ",".join("?" * len(chain))
        filas = conn.execute(
            f"SELECT prepared_path, status FROM upload_jobs WHERE id IN ({marcas})", chain).fetchall()
        with ENLACES:
            en_uso = {f["prepared_path"] for f in conn.execute(
                "SELECT prepared_path FROM upload_jobs WHERE prepared_path IS NOT NULL "
                "AND (status NOT IN ('cancelled', 'failed') OR torrent_subido = 1)")}
            for fila in filas:
                ruta = fila["prepared_path"]
                # El archivo de un elemento que vive en la carpeta de subidas (instancias «Up») no es un enlace.
                propio = ruta and conn.execute(
                    "SELECT 1 FROM library_items WHERE path = ? OR prepared_path = ? LIMIT 1", (ruta, ruta)).fetchone()
                if ruta not in en_uso and not propio:
                    borrar_de_subidas(ruta)
        conn.execute(f"DELETE FROM upload_artifacts WHERE upload_job_id IN ({marcas})", chain)
        conn.execute(f"DELETE FROM upload_job_logs WHERE upload_job_id IN ({marcas})", chain)
        conn.execute(f"UPDATE filesystem_operations SET upload_job_id = NULL WHERE upload_job_id IN ({marcas})", chain)
        conn.execute(f"UPDATE operational_queue_items SET upload_job_id = NULL WHERE upload_job_id IN ({marcas})", chain)
        conn.execute(f"DELETE FROM upload_jobs WHERE id IN ({marcas})", chain)
        conn.commit()

        mensaje = ("Subida eliminada." if len(chain) == 1
                   else f"Subida eliminada, con sus {len(chain) - 1} reintento(s).")
        return {"ok": True, "message": mensaje, "job_id": job_id, "deleted_job_ids": chain}
    finally:
        if own:
            conn.close()
