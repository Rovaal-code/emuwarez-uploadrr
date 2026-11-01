"""Transiciones de estado de un trabajo de subida, comprobación del tráiler y avisos de fin de subida."""
from __future__ import annotations

import json
import logging

from ..uploadrr_contract import get_runtime_settings
from .comun import _get_db_conn, logger
from .consultas import get_upload_job
from .registro import append_upload_log, create_upload_artifact, get_upload_job_artifacts


def _update_job_status(job_id: int, status: str, **kwargs) -> None:
    """Escribe el estado sin condiciones. Solo para Cancelar, que es la
    decisión del usuario. Para arrancar usa _avanzar_job y para terminar un
    trabajo _finalize_job_status: los dos protegen la cancelación."""
    from ..upload_states import escribir_estado
    escribir_estado(job_id, status=status, **kwargs)


def _avanzar_job(job_id: int, status: str, **kwargs) -> bool:
    """Escribe el estado salvo que el usuario ya haya cancelado el trabajo.
    False significa cancelado: quien llama no debe seguir."""
    from ..upload_states import escribir_estado
    return escribir_estado(job_id, salvo=("cancelled",), status=status, **kwargs)


def _finalize_job_status(job_id: int, desired_status: str, **kwargs) -> None:
    """Atomically set the terminal status of a job, unless it was already
    cancelled — as a single conditional UPDATE, not a read-then-write, so
    there is no race window with cancel_upload_job() running concurrently
    on another connection/thread.

    cancel_upload_job() sends SIGTERM and unconditionally writes status
    "cancelled" while the subprocess is still running. When that subprocess
    then exits (killed by the signal), this function tries to record
    "failed"/"completed" — but only if the row is not already "cancelled".
    SQLite serializes writers, so this single UPDATE either lands before or
    after cancel_upload_job()'s UPDATE, never interleaved with it: if it
    lands first, cancel_upload_job()'s later unconditional write still wins
    (status ends as "cancelled" either way); if it lands after, the WHERE
    clause here blocks clobbering an already-cancelled job, and only the
    non-status bookkeeping fields (exit_code/finished_at/duration) are kept.
    """
    from ..upload_states import escribir_estado

    escrito = escribir_estado(job_id, salvo=("cancelled",),
                              status=desired_status, **kwargs)
    conn = _get_db_conn()
    try:
        if not escrito:
            # Already cancelled — keep status/stage, but still record the
            # bookkeeping fields (exit_code, finished_at, duration_seconds…)
            # for observability.
            extra = {k: v for k, v in kwargs.items() if k != "stage"}
            if extra:
                escribir_estado(job_id, conn=conn, **extra)
    finally:
        conn.close()


def _check_trailer_and_log(job_id: int) -> None:
    """Best-effort post-upload check: does the description Uploadrr-EMU just
    sent to eMuwarez actually include a [youtube] trailer tag? Never blocks
    or fails the job either way — just logs to Actividad, and records a
    "trailer_url" artifact when found so _notify_upload_completed() (and the
    job detail page) can tell. See services/trailer_check.py for why reading
    Uploadrr-EMU's own generated file is a reliable signal, not a guess."""
    try:
        from ..trailer_check import check_trailer_for_job

        conn = _get_db_conn()
        try:
            job = get_upload_job(job_id, conn=conn)
            if not job:
                return
            uploadrr_path = get_runtime_settings(conn)["uploadrr_path"]
            snapshot = {}
            try:
                snapshot = json.loads(job.get("nomenclature_snapshot_json") or "{}") or {}
            except (TypeError, ValueError):
                pass
            candidate_names = [n for n in (snapshot.get("proposed_torrent_name"), snapshot.get("proposed_filename"), snapshot.get("proposed_title")) if n]

            result = check_trailer_for_job(uploadrr_path, candidate_names, desde=job.get("started_at"))
            if result["found"]:
                create_upload_artifact(job_id, "trailer_url", name="Trailer", url=result["url"], conn=conn)
                append_upload_log(job_id, "info", f"Trailer incluido en la descripción: {result['url']}", stream="system", conn=conn)
            elif result["checked"]:
                append_upload_log(
                    job_id, "warning",
                    "No se encontró un trailer en la descripción generada por Uploadrr "
                    "(TMDb podría no tener uno para este contenido).",
                    stream="system", conn=conn,
                )
            else:
                append_upload_log(
                    job_id, "warning",
                    "No se pudo localizar el archivo de descripción de Uploadrr para comprobar el trailer.",
                    stream="system", conn=conn,
                )
        finally:
            conn.close()
    except Exception:
        logger.exception("Error comprobando el trailer (job %s)", job_id)


def _job_poster_url(conn, job: dict | None) -> str | None:
    """upload_jobs has no poster of its own — look it up via the job's linked
    library_item, same join used elsewhere (web/api/uploads.py)."""
    item_id = (job or {}).get("library_item_id")
    if not item_id:
        return None
    row = conn.execute("SELECT poster_url FROM library_items WHERE id = ?", (item_id,)).fetchone()
    return row["poster_url"] if row else None


def _notify_upload_completed(job_id: int, result_url: str | None, aviso: str | None = None) -> None:
    """Emit a 'subida completada' notification. Best-effort: never lets a
    notification failure affect the upload result. `aviso` se añade al texto
    (p. ej. un pack de temporada incompleto)."""
    try:
        from ..notification_center import emit
        conn = _get_db_conn()
        try:
            job = get_upload_job(job_id, conn=conn)
            title = (job or {}).get("title") or "Subida"
            artifacts = get_upload_job_artifacts(job_id, conn=conn)
            has_trailer = any(a.get("artifact_type") == "trailer_url" for a in artifacts)
            body = "Se ha subido a eMuwarez correctamente."
            if job and job.get("request_title"):
                body += f" Petición: «{job['request_title']}»."
            if not has_trailer:
                body += " Requiere Trailer."
            if aviso:
                body += f" {aviso}"
            emit(
                conn, "upload_completed",
                "Subida completada",
                body,
                link=result_url,
                level="success",
                entity_type="upload_job",
                entity_id=job_id,
                poster_url=_job_poster_url(conn, job),
                content_title=title,
            )
        finally:
            conn.close()
    except Exception:
        logging.getLogger("emuwarez.notifications").exception(
            "No se pudo emitir la notificación de subida completada (job %s)", job_id
        )


def _notify_upload_failed(job_id: int, error_message: str | None, result_url: str | None = None) -> None:
    """Emit a 'subida fallida' notification. Best-effort: never lets a
    notification failure affect the upload result. Called from every
    terminal-failure branch of _run_uploadrr_subprocess (timeout, non-zero
    exit, executable not found, unexpected exception). `result_url`: la ficha
    del torrent, si llegó a subirse antes de fallar."""
    try:
        from ..notification_center import emit
        conn = _get_db_conn()
        try:
            job = get_upload_job(job_id, conn=conn)
            title = (job or {}).get("title") or "Subida"
            body = "Ha fallado al subirse a eMuwarez."
            if result_url:
                body += " El torrent sí llegó a subirse."
            if job and job.get("request_title"):
                body += f" Petición: «{job['request_title']}»."
            if error_message:
                body += "\n" + error_message.strip()[:300]
            emit(
                conn, "upload_failed",
                "Subida fallida",
                body,
                link=result_url,
                level="error",
                entity_type="upload_job",
                entity_id=job_id,
                poster_url=_job_poster_url(conn, job),
                content_title=title,
            )
        finally:
            conn.close()
    except Exception:
        logging.getLogger("emuwarez.notifications").exception(
            "No se pudo emitir la notificación de subida fallida (job %s)", job_id
        )


def _esta_cancelado(job_id: int) -> bool:
    conn = _get_db_conn()
    try:
        row = conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    return bool(row) and row["status"] == "cancelled"
