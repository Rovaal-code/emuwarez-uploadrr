"""Ejecución del subproceso de Uploadrr-EMU y arranque de una subida."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from ..upload_result_parser import classify_upload_result
from ..uploadrr_contract import RUNTIME_EMU, get_runtime_settings
from ..uploadrr_progress import parse_uploadrr_progress
from . import procesos
from .comun import (
    CONFIRMATION_TOKEN,
    ETAPA_ESPERANDO_TURNO,
    QBIT_AÑADIDO,
    _collect_secrets,
    _get_db_conn,
    _now,
    logger,
    redact_secrets,
)
from .concurrencia import _upload_concurrency_gate
from .config import ConfigNoPreparada, _acquire_staged_config, _release_staged_config
from .consultas import build_uploadrr_execution_command, get_upload_job, validate_upload_job_start
from .estado import (
    _avanzar_job,
    _check_trailer_and_log,
    _esta_cancelado,
    _finalize_job_status,
    _notify_upload_completed,
    _notify_upload_failed,
)
from .procesos import (
    _PROCESOS,
    _PROCESOS_LOCK,
    _detener_proceso,
    _senalar_grupo,
    _terminar_y_esperar,
)
from .progreso import advance_running_phase, mark_phase_done, mark_phase_failed
from .registro import _ficha_del_torrent, append_upload_log, create_upload_artifact


# Margen a las tuberías tras salir Uploadrr (segundos).
_GRACIA_LECTORES = 15


def _run_uploadrr_subprocess(job_id: int, cmd: dict, secrets: list[str], *, pre_gated: bool = False) -> None:
    """Execute Uploadrr in a background thread. Updates job status, logs, and result artifacts.

    pre_gated=True means the caller (the queued-job pipeline, upload_queue.py's
    _run_queued_job) already holds this job's concurrency slot from before its
    own preprocessing (verificación pre-subida/nomenclatura/remux) — so this
    function must NOT acquire again (that would double-count the same job
    against the limit), only release once the real work here is done. Every
    other entry point (CLI, direct retry, the legacy direct-start endpoint)
    calls this on an already-"ready" job with no preprocessing to gate, so it
    still acquires here itself, right at the actual heavy work, same as before.
    """
    if not pre_gated and not _upload_concurrency_gate.acquire(
            job_id, cancelada=lambda: _esta_cancelado(job_id)):
        append_upload_log(job_id, "info", "Subida cancelada mientras esperaba turno; no se lanza.", stream="system")
        return
    try:
        _run_uploadrr_subprocess_body(job_id, cmd, secrets)
    finally:
        _upload_concurrency_gate.release()


def _run_uploadrr_subprocess_body(job_id: int, cmd: dict, secrets: list[str]) -> None:
    executable = cmd["executable"]
    args = cmd["args"]
    cwd = cmd.get("cwd") or "."

    # Build safe_command_json without secrets
    safe_preview = redact_secrets(cmd.get("command_preview", ""), secrets)
    safe_cmd_json = json.dumps({
        "executable": "[python]",
        "args_preview": safe_preview,
        "cwd": cwd,
        "using_prepared_path": cmd.get("using_prepared_path"),
        "source_path": cmd.get("source_path"),
    }, ensure_ascii=False)

    started_dt = datetime.now(timezone.utc)
    started_at = started_dt.isoformat()
    timeout = cmd.get("timeout") or None

    # Todo dentro del try: un fallo en cualquier paso (la base bloqueada al
    # escribir el primer estado, p. ej.) termina el job como fallido y suelta
    # el config stageado, en vez de dejarlo «en marcha» para siempre.
    staged_config_path: Path | None = None
    proc: subprocess.Popen | None = None
    try:
        def _cancelado() -> None:
            append_upload_log(job_id, "info", "Subida cancelada antes de lanzar Uploadrr; no se lanza.", stream="system")

        # Cancelar puede llegar en cualquier momento: cada escritura de estado
        # lo respeta, y si ya está cancelado no se lanza nada.
        if not _avanzar_job(
            job_id,
            "running",
            stage="running",
            started_at=started_at,
            safe_command_json=safe_cmd_json,
            last_log_at=_now(),
        ):
            _cancelado()
            return
        append_upload_log(job_id, "info", "Iniciando proceso Uploadrr…", stream="system")
        append_upload_log(
            job_id,
            "info",
            f"Comando: {safe_preview}",
            stream="system",
        )

        # Save prepared file artifact if applicable
        if cmd.get("using_prepared_path") and cmd.get("source_path"):
            create_upload_artifact(
                job_id, "prepared_file",
                name="archivo preparado",
                path=cmd["source_path"],
            )

        # Phase 10F: stage DEFAULT.tmdb / TRACKERS.EMU.api_key into Uploadrr-EMU's
        # own config.yaml before running, and always restore it afterwards
        # (success, failure, timeout, or cancellation) via the finally block.
        if cmd.get("runtime_type") == RUNTIME_EMU and os.path.isdir(cwd):
            if not _avanzar_job(job_id, "running", stage="config_staging"):
                _cancelado()
                return
            staged_config_path = _acquire_staged_config(job_id, cwd)
        if not _avanzar_job(job_id, "running", stage="running"):
            _cancelado()
            return

        env = {k: v for k, v in os.environ.items()}

        # Sesión propia: Cancelar y el timeout señalan el grupo entero (Uploadrr,
        # mkbrr, ffmpeg…) y no solo el PID de Python.
        # Lanzar y apuntar, bajo el candado con que se apaga el servidor: una vez
        # empezado el apagado no se lanza otro, y ninguno se escapa de la lista.
        with _PROCESOS_LOCK:
            # La bandera vive en procesos (la pone detener_procesos_en_marcha): se lee por el módulo, no por copia.
            if procesos._apagando:
                raise RuntimeError("El servidor se está apagando; no se lanza Uploadrr.")
            proc = subprocess.Popen(
                [executable] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                errors="replace",
                cwd=cwd if os.path.isdir(cwd) else None,
                env=env,
                start_new_session=True,
            )
            _PROCESOS[job_id] = proc

        if not _avanzar_job(job_id, "running", process_id=proc.pid):
            # Cancelar llegó entre medias y no vio el proceso: se detiene aquí.
            append_upload_log(job_id, "info", "Subida cancelada al arrancar; se detiene Uploadrr.", stream="system")
            _detener_proceso(proc)
        append_upload_log(job_id, "info", f"PID: {proc.pid}", stream="system")

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        progress_lock = threading.Lock()
        progress_state = {"phase": None, "pct": 0, "last_sig": None, "qbittorrent_add_failed": False}

        def _track_uploadrr_progress(line: str) -> None:
            parsed = parse_uploadrr_progress(line)
            if not parsed:
                return
            phase_key, pct, ok_state = parsed
            with progress_lock:
                if phase_key == progress_state["phase"] and pct < progress_state["pct"] and ok_state is not False:
                    pct = progress_state["pct"]
                sig = (phase_key, pct, ok_state)
                if sig == progress_state["last_sig"]:
                    return
                progress_state["phase"] = phase_key
                progress_state["pct"] = pct
                progress_state["last_sig"] = sig
                if phase_key == "qbittorrent_add":
                    if ok_state is False:
                        progress_state["qbittorrent_add_failed"] = True
                    elif ok_state is True:
                        progress_state["qbittorrent_add_failed"] = False
            advance_running_phase(job_id, phase_key, pct)
            # Distinct, clearly-flagged line beyond the raw stdout passthrough
            # already captured above — otherwise this only shows up as one
            # more anonymous line among hundreds in Ver Logs.
            if phase_key == "qbittorrent_add" and ok_state is True:
                append_upload_log(job_id, "info", QBIT_AÑADIDO, stream="system")
            elif phase_key == "qbittorrent_add" and ok_state is False:
                if "Torrent upload succeeded, but failed to" in line:
                    # UNIT3D.py's re-download-after-upload step 403'd (or
                    # otherwise failed) — no [tracker]{name}.torrent ever
                    # gets written, so add_to_client() has nothing to add.
                    # Not a qBittorrent problem at all; the eMuwarez upload
                    # itself did succeed.
                    append_upload_log(
                        job_id, "error",
                        "qBittorrent: no se añadió ningún torrent porque no se pudo descargar el .torrent firmado "
                        "desde eMuwarez justo después de subir (ver la línea \"Torrent upload succeeded, but failed "
                        "to...\" más arriba). La subida a eMuwarez sí se completó.",
                        stream="system",
                    )
                elif "Torrent client add failed:" in line:
                    motivo = redact_secrets(line.split("Torrent client add failed:", 1)[1].strip(), secrets)
                    append_upload_log(
                        job_id, "error",
                        f"qBittorrent: falló al añadir o etiquetar el torrent ({motivo}). Revisa qBittorrent. "
                        "La subida a eMuwarez sí se completó.",
                        stream="system",
                    )
                else:
                    append_upload_log(
                        job_id, "error",
                        "qBittorrent: no se pudo añadir el torrent (credenciales incorrectas). Revisa la configuración de qBittorrent en Ajustes.",
                        stream="system",
                    )

        def _read_stream(stream, level, stream_name, buf):
            for line in stream:
                line = line.rstrip("\n")
                safe_line = redact_secrets(line, secrets)
                buf.append(safe_line)
                # Si guardar la línea falla (base bloqueada, disco lleno) se
                # sigue leyendo: sin nadie vaciando la tubería, Uploadrr se
                # queda bloqueado escribiendo hasta el timeout.
                try:
                    append_upload_log(job_id, level, safe_line, stream=stream_name)
                except Exception:
                    logger.exception("Subida %s: no se pudo registrar una línea de %s", job_id, stream_name)
                try:
                    # La línea sin redactar: un secreto que coincida con una palabra de las marcas las rompería.
                    # Lo que se registra de ella se redacta allí.
                    _track_uploadrr_progress(line)
                except Exception:
                    logger.exception("Subida %s: no se pudo actualizar el progreso", job_id)

        t_out = threading.Thread(
            target=_read_stream,
            args=(proc.stdout, "info", "stdout", stdout_lines),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_read_stream,
            args=(proc.stderr, "warning", "stderr", stderr_lines),
            daemon=True,
        )
        t_out.start()
        t_err.start()
        # El resultado lo decide el código de salida, no el fin de las tuberías:
        # un hijo de Uploadrr (mkbrr, ffmpeg…) que las herede las mantiene
        # abiertas aunque Uploadrr ya haya salido, y esperarlas daba por fallida
        # una subida buena tras el timeout.
        timed_out = False
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = _terminar_y_esperar(proc)
        limite = time.monotonic() + _GRACIA_LECTORES
        for t in (t_out, t_err):
            t.join(timeout=max(0, limite - time.monotonic()))
        if t_out.is_alive() or t_err.is_alive():
            _senalar_grupo(proc, signal.SIGKILL)  # lo que quede vivo en el grupo
            t_out.join(timeout=5)
            t_err.join(timeout=5)

        if timed_out:
            finished_dt = datetime.now(timezone.utc)
            finished_at = finished_dt.isoformat()
            duration_seconds = int((finished_dt - started_dt).total_seconds())
            msg = f"Proceso cancelado por timeout ({timeout}s)."
            subido = _ficha_del_torrent("\n".join(stdout_lines))
            _finalize_job_status(
                job_id, "failed",
                stage="timeout",
                exit_code=returncode,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                error_message=msg,
                **subido,
                last_log_at=_now(),
                last_error_at=finished_at,
            )
            append_upload_log(job_id, "error", msg, stream="system")
            _notify_upload_failed(job_id, msg, result_url=subido.get("result_url"))
            return

        # Transient progress marker only, applied atomically and only while
        # still "running" — must never clobber a "cancelled" status that
        # cancel_upload_job() may have set concurrently while this process
        # was still exiting after SIGTERM.
        conn = _get_db_conn()
        try:
            conn.execute(
                "UPDATE upload_jobs SET stage = 'finalizing', updated_at = ? WHERE id = ? AND status = 'running'",
                (_now(), job_id),
            )
            conn.commit()
        finally:
            conn.close()

        finished_dt = datetime.now(timezone.utc)
        finished_at = finished_dt.isoformat()
        duration_seconds = int((finished_dt - started_dt).total_seconds())

        stdout_text = "\n".join(stdout_lines)
        stderr_text = "\n".join(stderr_lines)

        result = classify_upload_result(stdout_text, stderr_text, returncode)

        if returncode == 0:
            # La ficha del torrent: la línea `Torrent URL:` de Uploadrr-EMU, no la primera URL que imprima.
            if result["result_url"]:
                create_upload_artifact(job_id, "uploaded_url", name="URL subida", url=result["result_url"])
            if result["torrent_id"]:
                create_upload_artifact(job_id, "torrent_id", name="torrent_id", value=result["torrent_id"])

            _finalize_job_status(
                job_id, "completed",
                stage="finished",
                exit_code=0,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                result_url=result["result_url"],
                result_torrent_id=result["torrent_id"],
                last_log_at=_now(),
                last_success_at=finished_at,
            )
            mark_phase_done(job_id, "uploading_emu")
            # Safety net: if qBittorrent isn't configured in Uploadrr, it
            # never prints anything for this step (not even to stderr) and
            # "qbittorrent_add" would otherwise stay stuck "pending" forever
            # on an otherwise-successful job — mark it done here regardless
            # of whether the real add_to_client() output was actually seen.
            # But NOT if we actually saw it fail (bad qBittorrent login) —
            # that's a real, detected failure, not silence, and force-marking
            # it "done" would hide it behind a fully green Fases table.
            # Y si falló se guarda como fallida: si no, se quedaba «En curso» con la duración contando.
            if progress_state.get("qbittorrent_add_failed"):
                mark_phase_failed(job_id, "qbittorrent_add")
            else:
                mark_phase_done(job_id, "qbittorrent_add")
            append_upload_log(
                job_id, "info",
                f"Proceso finalizado correctamente (exit code 0). Duración: {duration_seconds}s",
                stream="system",
            )
            logger.info("Subida completada (job %s) en %ss%s", job_id, duration_seconds,
                        f" → {result['result_url']}" if result["result_url"] else "")
            _check_trailer_and_log(job_id)
            if result["season_pack_warning"]:
                # Un aviso que no se puede registrar no cambia una subida ya hecha.
                try:
                    append_upload_log(job_id, "warning", result["season_pack_warning"], stream="system")
                except Exception:
                    logger.exception("Subida %s: no se pudo registrar el aviso de pack incompleto", job_id)
            _notify_upload_completed(job_id, result["result_url"], aviso=result["season_pack_warning"])
        else:
            safe_err = redact_secrets(result["error_summary"] or f"exit code {returncode}", secrets)
            # Si el torrent llegó a subirse antes de fallar, su ficha sigue siendo útil y su enlace no se borra.
            subido = _ficha_del_torrent(stdout_text)

            _finalize_job_status(
                job_id, "failed",
                stage="failed",
                exit_code=returncode,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                error_message=safe_err[:2000],
                **subido,
                last_log_at=_now(),
                last_error_at=finished_at,
            )
            append_upload_log(
                job_id, "error",
                f"Proceso fallido (exit code {returncode}). Duración: {duration_seconds}s",
                stream="system",
            )
            logger.warning("Subida fallida (job %s, exit %s): %s", job_id, returncode, safe_err[:300])
            _notify_upload_failed(job_id, safe_err, result_url=subido.get("result_url"))

    except FileNotFoundError as exc:
        finished_at = _now()
        msg = f"Ejecutable no encontrado: {exc}"
        _finalize_job_status(
            job_id, "failed",
            stage="failed",
            finished_at=finished_at,
            error_message=msg[:2000],
            last_error_at=finished_at,
        )
        append_upload_log(job_id, "error", msg, stream="system")
        logger.error("Subida fallida (job %s): %s", job_id, msg)
        _notify_upload_failed(job_id, msg)
    except Exception as exc:
        finished_at = _now()
        msg = redact_secrets(str(exc), secrets)
        _finalize_job_status(
            job_id, "failed",
            stage="failed",
            finished_at=finished_at,
            error_message=msg[:2000],
            last_error_at=finished_at,
        )
        append_upload_log(job_id, "error", msg if isinstance(exc, ConfigNoPreparada) else f"Excepción inesperada: {msg}",
                          stream="system")
        logger.error("Subida fallida (job %s): excepción inesperada: %s", job_id, msg)
        _notify_upload_failed(job_id, msg)
    finally:
        with _PROCESOS_LOCK:
            _PROCESOS.pop(job_id, None)
        if proc is not None and proc.poll() is None:
            # Se salió por una excepción con Uploadrr aún vivo: no se deja suelto.
            _senalar_grupo(proc, signal.SIGKILL)
        _release_staged_config(job_id, staged_config_path)


def start_upload_job(
    job_id: int,
    *,
    dry_run: bool = True,
    start: bool = False,
    confirmation: str | None = None,
    conn=None,
    pre_gated: bool = False,
    wait: bool = False,
) -> dict:
    """Start or preview a job.

    pre_gated=True: the caller already holds this job's concurrency slot
    (see _run_uploadrr_subprocess) — passed through unchanged to the spawned
    thread, not acted on here.

    wait=True: no volver hasta que la subida termine. Lo necesita el CLI, que
    sale al volver de aquí y se llevaría por delante el hilo (es daemon).

    - dry_run=True (default): validate and return command preview, do not execute.
    - dry_run=False, start=True, confirmation=INICIAR_UPLOADRR: execute real Uploadrr.
    - Any other combination: blocked.
    """
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        validation = validate_upload_job_start(job_id, conn=conn)
        job = validation.get("job")

        if dry_run:
            cmd = build_uploadrr_execution_command(job, conn=conn) if job else {}
            return {
                "job_id": job_id,
                "action": "dry_run",
                "status": job.get("status", "unknown") if job else "not_found",
                "stage": job.get("stage") if job else None,
                "dry_run": True,
                "valid": validation["valid"],
                "errors": validation["errors"],
                "warnings": validation["warnings"],
                "command_preview": cmd.get("command_preview"),
                "using_prepared_path": cmd.get("using_prepared_path"),
                "message": "Dry-run: no se ha ejecutado Uploadrr.",
                "error": None,
            }

        if not start:
            return {
                "job_id": job_id,
                "action": "blocked",
                "status": "blocked",
                "stage": None,
                "dry_run": False,
                "errors": ["Se requiere start=true para iniciar la ejecución."],
                "warnings": [],
                "command_preview": None,
                "message": None,
                "error": "blocked",
            }

        if confirmation != CONFIRMATION_TOKEN:
            return {
                "job_id": job_id,
                "action": "blocked",
                "status": "blocked",
                "stage": None,
                "dry_run": False,
                "errors": [f'Se requiere confirmación exacta: "{CONFIRMATION_TOKEN}".'],
                "warnings": [],
                "command_preview": None,
                "message": None,
                "error": "confirmation_required",
            }

        if not validation["valid"]:
            return {
                "job_id": job_id,
                "action": "blocked",
                "status": "blocked",
                "stage": None,
                "dry_run": False,
                "errors": validation["errors"],
                "warnings": validation["warnings"],
                "command_preview": None,
                "message": None,
                "error": "validation_failed",
            }

        runtime = get_runtime_settings(conn)
        if runtime["runtime_type"] != RUNTIME_EMU:
            return {
                "job_id": job_id,
                "action": "blocked",
                "status": "blocked",
                "stage": None,
                "dry_run": False,
                "errors": [
                    f"Ejecución controlada solo soportada para runtime_type={RUNTIME_EMU} "
                    f"(actual: {runtime['runtime_type']})."
                ],
                "warnings": [],
                "command_preview": None,
                "message": None,
                "error": "unsupported_runtime",
            }

        cmd = build_uploadrr_execution_command(job, conn=conn)
        secrets = _collect_secrets(conn)

        if not pre_gated:
            # Va a esperar plaza siguiendo en 'ready': la fase lo dice en la base
            # antes de lanzar el hilo, para que Cancelar (también desde otro
            # proceso) la encuentre desde el primer momento.
            from ..upload_states import escribir_estado
            escribir_estado(job_id, desde={"ready"}, stage=ETAPA_ESPERANDO_TURNO, conn=conn)
        t = threading.Thread(
            target=_run_uploadrr_subprocess,
            args=(job_id, cmd, secrets),
            kwargs={"pre_gated": pre_gated},
            daemon=True,
        )
        t.start()
        logger.info("Subida iniciada (job %s): «%s»", job_id,
                    (job or {}).get("title") or (job or {}).get("torrent_name") or "?")

        final = {"status": "running", "stage": "running"}
        if wait:
            try:
                t.join()
            except KeyboardInterrupt:
                # Uploadrr tiene su propia sesión y ya no recibe el Ctrl-C del terminal.
                with _PROCESOS_LOCK:
                    proc = _PROCESOS.get(job_id)
                if proc is not None:
                    _detener_proceso(proc)
                raise
            final = get_upload_job(job_id, conn=conn) or final

        return {
            "job_id": job_id,
            "action": "started",
            "status": final.get("status"),
            "stage": final.get("stage"),
            "dry_run": False,
            "errors": [],
            "warnings": validation.get("warnings", []),
            "command_preview": redact_secrets(cmd.get("command_preview", ""), secrets),
            "using_prepared_path": cmd.get("using_prepared_path"),
            "message": "Uploadrr ha terminado." if wait else "Uploadrr iniciado en background. Consulta los logs para el progreso.",
            "error": None,
        }
    finally:
        if own:
            conn.close()
