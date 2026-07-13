"""Controlled Uploadrr execution service.

SAFETY CONTRACT:
- Never executes Uploadrr without explicit confirmation INICIAR_UPLOADRR.
- Never uses shell=True.
- Never stores API keys in logs or database.
- Never modifies Uploadrr/.
- Never executes mkvpropedit.
- Never creates eMuwarez requests automatically.
- dry_run=True always by default; always takes precedence over start=True.
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..database import connect, init_db, row_to_dict, rows_to_dicts, get_setting_canonical
from .upload_result_parser import classify_upload_result, build_error_summary
from .uploadrr_contract import (
    RUNTIME_EMU,
    build_uploadrr_emu_command,
    get_runtime_settings,
    render_command_preview,
)
from .uploadrr_config_staging import (
    default_uploadrr_config_path,
    read_config_lines,
    restore_config_from_backup,
    stage_emu_config,
    stage_tmdb_key,
    write_staged_config,
)

CONFIRMATION_TOKEN = "INICIAR_UPLOADRR"

# Phase 10F: approximate progress phases surfaced to the UI. Uploadrr-EMU
# does not emit structured progress, so this is a coarse stage mapping, never
# a fabricated percentage.
PROGRESS_PHASES = (
    "queued", "preflight", "config_staging", "running",
    "finalizing", "succeeded", "failed", "cancelled", "timeout",
)


def compute_progress_phase(status: str, stage: str | None) -> str:
    """Map (status, stage) to one of PROGRESS_PHASES for display purposes only."""
    stage = stage or ""
    if status == "cancelled":
        return "cancelled"
    if status == "failed" and stage == "timeout":
        return "timeout"
    if status == "failed":
        return "failed"
    if status == "completed":
        return "succeeded"
    if status == "running":
        if stage == "config_staging":
            return "config_staging"
        if stage == "finalizing":
            return "finalizing"
        return "running"
    if status == "ready":
        return "preflight"
    if status in ("draft", "preflight"):
        return "preflight"
    return "queued"

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts",
    ".wmv", ".flv", ".webm", ".iso", ".m4v",
}

_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?token\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(token\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(key\s*=\s*)\S+", re.IGNORECASE),
]


def redact_secrets(value: str, secrets: list[str]) -> str:
    """Replace known secret values and common secret patterns with ***REDACTED***."""
    result = value
    for secret in secrets:
        if secret and len(secret) > 3:
            result = result.replace(secret, "***REDACTED***")
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(r"\1***REDACTED***", result)
    return result


def _get_db_conn():
    conn = connect()
    init_db(conn)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_setting(conn, key: str, default=None):
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row:
            return row["value"]
    except Exception:
        pass
    try:
        from ..database import get_state
        return get_state(conn, key, default)
    except Exception:
        return default


def _collect_secrets(conn) -> list[str]:
    secrets = []
    for key in ("emu.api_key", "tmdb.api_key"):
        val = get_setting_canonical(conn, key)
        if val:
            secrets.append(val)
    return secrets


def get_upload_job(job_id: int, conn=None) -> dict | None:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        row = conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
        return row_to_dict(row)
    finally:
        if own:
            conn.close()


def list_upload_jobs(filters: dict | None = None, conn=None) -> list[dict]:
    """List upload jobs with optional filters: status, limit, offset, search."""
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        filters = filters or {}
        conditions = []
        params: list[Any] = []

        status = filters.get("status")
        if status:
            conditions.append("status = ?")
            params.append(status)

        search = filters.get("search")
        if search:
            conditions.append("title LIKE ?")
            params.append(f"%{search}%")

        library_item_id = filters.get("library_item_id")
        if library_item_id is not None:
            conditions.append("library_item_id = ?")
            params.append(library_item_id)

        request_item_id = filters.get("request_item_id")
        if request_item_id is not None:
            conditions.append("request_item_id = ?")
            params.append(request_item_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        limit = int(filters.get("limit", 200))
        offset = int(filters.get("offset", 0))

        rows = conn.execute(
            f"SELECT * FROM upload_jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        if own:
            conn.close()


def validate_upload_job_start(job_id: int, conn=None) -> dict:
    """Validate all preconditions for starting a job. Returns {valid, errors, warnings, job}."""
    own = conn is None
    conn = conn or _get_db_conn()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        job = get_upload_job(job_id, conn=conn)
        if not job:
            return {"valid": False, "errors": [f"Job {job_id} no encontrado."], "warnings": [], "job": None}

        status = job.get("status", "")
        if status in ("running",):
            errors.append(f"El job ya está en ejecución (status={status}).")
        elif status in ("completed",):
            errors.append("El job ya está completado. Crea un nuevo preflight para reintentar.")
        elif status in ("blocked", "failed"):
            errors.append(f"El job está en estado {status}. Crea un nuevo preflight.")
        elif status in ("cancelled",):
            errors.append("El job fue cancelado. Crea un nuevo preflight para reintentar.")
        elif status != "ready":
            errors.append(f"El job no está listo (status={status}). Solo se puede iniciar desde 'ready'.")

        prepared = job.get("prepared_path")
        source = job.get("source_path") or job.get("path") or ""

        active_path = prepared or source
        if not active_path:
            errors.append("No hay ruta de archivo registrada en el job.")
        else:
            p = Path(active_path)
            if not p.exists():
                errors.append(f"El archivo no existe en disco: {active_path}")
            elif p.is_symlink():
                errors.append(f"El archivo es un symlink y no puede usarse: {active_path}")
            elif not p.is_file():
                errors.append(f"La ruta no es un archivo regular: {active_path}")
            elif p.suffix.lower() not in VIDEO_EXTENSIONS:
                warnings.append(f"El archivo no tiene extensión de vídeo reconocida: {p.suffix}")

        uploadrr_path = get_setting_canonical(conn, "uploadrr.path")
        if not uploadrr_path:
            errors.append("Ruta de Uploadrr no configurada (uploadrr.path).")
        else:
            script = Path(uploadrr_path) / "upload.py"
            if not script.exists():
                errors.append(f"Script de Uploadrr no encontrado: {script}")

        emu_key = get_setting_canonical(conn, "emu.api_key")
        if not emu_key:
            errors.append("API key de eMuwarez no configurada.")

        tmdb_key = get_setting_canonical(conn, "tmdb.api_key")
        if not tmdb_key:
            warnings.append("API key de TMDb no configurada.")

        if prepared:
            pass  # good
        elif source:
            warnings.append("Nomenclatura no aplicada: se usaría el archivo original.")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings, "job": job}
    finally:
        if own:
            conn.close()


def build_uploadrr_execution_command(job: dict, conn=None) -> dict:
    """Build the actual command list for subprocess. Resolves paths from settings at runtime.

    Returns {"executable": str, "args": list[str], "cwd": str, "command_preview": str,
    "timeout": int, "runtime_type": str}. Does NOT include secrets in the returned dict.

    For runtime_type=uploadrr_emu (the default), builds the real Uploadrr-EMU
    argv (-tk/-mt/-tmdb/-ua/-c/-res) via uploadrr_contract.py, using only
    prepared_path/applied_path — never the raw job "source_path" field name.
    """
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        runtime = get_runtime_settings(conn)
        uploadrr_path = runtime["uploadrr_path"]
        script = str(Path(uploadrr_path) / "upload.py") if uploadrr_path else ""

        prepared = job.get("prepared_path")
        source = job.get("source_path") or job.get("path") or ""
        active_path = prepared or source
        using_prepared = bool(prepared)

        preflight_raw = job.get("uploadrr_command_json")
        cmd_data: dict = {}
        if preflight_raw:
            try:
                cmd_data = json.loads(preflight_raw)
            except Exception:
                pass

        category = cmd_data.get("category") or "movie"
        tmdb_id = cmd_data.get("tmdb_id") or job.get("tmdb_id")
        resolution = cmd_data.get("resolution") or ""
        title = cmd_data.get("title") or job.get("title") or "Sin título"
        season = cmd_data.get("season")
        episode = cmd_data.get("episode")

        if runtime["runtime_type"] == RUNTIME_EMU:
            python_path = runtime["python_path"] or sys.executable
            full_argv = build_uploadrr_emu_command(
                python_path=python_path,
                uploadrr_script_path=script,
                prepared_path=active_path,
                torrent_name=title,
                tmdb_id=tmdb_id,
                category=category,
                resolution=resolution,
                season=season,
                episode=episode,
            )
            executable = full_argv[0]
            args = full_argv[1:]
        else:
            tracker = cmd_data.get("tracker") or "EMU"
            executable = sys.executable
            args = [script, active_path, "--tracker", tracker, "--category", category]
            if tmdb_id:
                args += ["--tmdb", str(tmdb_id)]
            if resolution:
                args += ["--resolution", resolution]

        preview = render_command_preview([executable] + args)

        return {
            "executable": executable,
            "args": args,
            "cwd": uploadrr_path,
            "command_preview": preview,
            "using_prepared_path": using_prepared,
            "source_path": active_path,
            "timeout": runtime["timeout"],
            "runtime_type": runtime["runtime_type"],
        }
    finally:
        if own:
            conn.close()


def append_upload_log(
    job_id: int,
    level: str,
    message: str,
    stream: str = "system",
    raw: dict | None = None,
    conn=None,
) -> None:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        # Get next sequence number
        row = conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM upload_job_logs WHERE upload_job_id = ?",
            (job_id,),
        ).fetchone()
        seq = row[0] if row else 1

        conn.execute(
            """INSERT INTO upload_job_logs
               (upload_job_id, level, message, stream, created_at, raw_json, sequence, is_secret_redacted)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                job_id,
                level,
                message[:8000],
                stream,
                _now(),
                json.dumps(raw, ensure_ascii=False) if raw else None,
                seq,
            ),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def get_upload_job_logs(job_id: int, limit: int = 500, offset: int = 0, conn=None) -> dict:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM upload_job_logs WHERE upload_job_id = ?", (job_id,)
        ).fetchone()
        total = total_row[0] if total_row else 0
        rows = conn.execute(
            "SELECT * FROM upload_job_logs WHERE upload_job_id = ? ORDER BY id ASC LIMIT ? OFFSET ?",
            (job_id, limit, offset),
        ).fetchall()
        return {
            "job_id": job_id,
            "logs": rows_to_dicts(rows),
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        if own:
            conn.close()


def create_upload_artifact(
    job_id: int,
    artifact_type: str,
    *,
    name: str | None = None,
    path: str | None = None,
    url: str | None = None,
    value: str | None = None,
    raw: dict | None = None,
    conn=None,
) -> dict:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        now = _now()
        cur = conn.execute(
            """INSERT INTO upload_artifacts
               (upload_job_id, artifact_type, name, path, url, value, created_at, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                artifact_type,
                name,
                path,
                url,
                value,
                now,
                json.dumps(raw, ensure_ascii=False) if raw else None,
            ),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "upload_job_id": job_id,
            "artifact_type": artifact_type,
            "name": name,
            "path": path,
            "url": url,
            "value": value,
            "created_at": now,
        }
    finally:
        if own:
            conn.close()


def get_upload_job_artifacts(job_id: int, conn=None) -> list[dict]:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM upload_artifacts WHERE upload_job_id = ? ORDER BY id ASC",
            (job_id,),
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        if own:
            conn.close()


def _update_job_status(job_id: int, status: str, **kwargs) -> None:
    conn = _get_db_conn()
    try:
        updates = {"status": status, "updated_at": _now()}
        updates.update(kwargs)
        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [job_id]
        conn.execute(f"UPDATE upload_jobs SET {set_clauses} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


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
    conn = _get_db_conn()
    try:
        updates = {"status": desired_status, "updated_at": _now()}
        updates.update(kwargs)
        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [job_id]
        cur = conn.execute(
            f"UPDATE upload_jobs SET {set_clauses} WHERE id = ? AND status != 'cancelled'",
            values,
        )
        conn.commit()
        if cur.rowcount == 0:
            # Already cancelled — keep status/stage, but still record the
            # bookkeeping fields (exit_code, finished_at, duration_seconds…)
            # for observability.
            extra = {k: v for k, v in kwargs.items() if k != "stage"}
            if extra:
                extra["updated_at"] = _now()
                set_clauses2 = ", ".join(f"{k} = ?" for k in extra)
                values2 = list(extra.values()) + [job_id]
                conn.execute(f"UPDATE upload_jobs SET {set_clauses2} WHERE id = ?", values2)
                conn.commit()
    finally:
        conn.close()


def _notify_upload_completed(job_id: int, result_url: str | None) -> None:
    """Emit a 'subida completada' notification. Best-effort: never lets a
    notification failure affect the upload result."""
    try:
        from .notification_center import emit
        conn = _get_db_conn()
        try:
            job = get_upload_job(job_id, conn=conn)
            title = (job or {}).get("title") or "Subida"
            emit(
                conn, "upload_completed",
                "Subida completada",
                f"«{title}» se ha subido a eMuwarez correctamente.",
                link=result_url,
                level="success",
                entity_type="upload_job",
                entity_id=job_id,
            )
        finally:
            conn.close()
    except Exception:
        logging.getLogger("emuwarez.notifications").exception(
            "No se pudo emitir la notificación de subida completada (job %s)", job_id
        )


def _stage_uploadrr_config(job_id: int, cwd: str) -> Path | None:
    """Best-effort staging of DEFAULT.tmdb / TRACKERS.EMU.api_key into config.yaml.

    Returns the config_path if staging happened (so the caller knows to
    restore it later), or None if there was nothing to stage (config.yaml
    missing, or no secrets configured) — in that case there is nothing to
    restore either. Never raises: staging failures are logged as warnings
    and execution proceeds without a staged config.
    """
    config_path = default_uploadrr_config_path(cwd)
    if not config_path.exists():
        append_upload_log(
            job_id, "warning",
            f"config.yaml no encontrado en {config_path}; no se stagean credenciales.",
            stream="system",
        )
        return None

    conn = _get_db_conn()
    try:
        tmdb_key = get_setting_canonical(conn, "tmdb.api_key")
        emu_key = get_setting_canonical(conn, "emu.api_key")
    finally:
        conn.close()

    try:
        lines = read_config_lines(config_path)
        changed = False
        if tmdb_key:
            lines, _msg = stage_tmdb_key(lines, tmdb_key)
            changed = True
        if emu_key:
            lines, _msg = stage_emu_config(lines, api_key=emu_key)
            changed = True
        if not changed:
            append_upload_log(
                job_id, "warning",
                "Sin tmdb.api_key/emu.api_key configuradas; config.yaml no se modifica.",
                stream="system",
            )
            return None
        write_staged_config(config_path, lines)
        append_upload_log(
            job_id, "info",
            "config.yaml stageado (DEFAULT.tmdb / TRACKERS.EMU.api_key). Backup creado.",
            stream="system",
        )
        return config_path
    except Exception as exc:
        append_upload_log(job_id, "warning", f"No se pudo stagear config.yaml: {exc}", stream="system")
        return None


def _restore_uploadrr_config(job_id: int, config_path: Path | None) -> None:
    if config_path is None:
        return
    try:
        restored = restore_config_from_backup(config_path)
        if restored:
            append_upload_log(job_id, "info", "config.yaml restaurado desde backup.", stream="system")
        else:
            append_upload_log(job_id, "warning", "No había backup de config.yaml que restaurar.", stream="system")
    except Exception as exc:
        append_upload_log(job_id, "error", f"Fallo al restaurar config.yaml: {exc}", stream="system")


# The staged config.yaml (TMDb/EMU keys) is a SHARED resource: every job stages
# the exact same secrets from settings. To let uploads run in PARALLEL without
# clobbering each other's config (or restoring it out from under a still-running
# job), we reference-count it: the first concurrent job stages it, the last one
# to finish restores it. All overlapping jobs read the same correct config.
_config_stage_lock = threading.Lock()
_config_stage_refcount: dict[str, int] = {}


def _acquire_staged_config(job_id: int, cwd: str) -> Path | None:
    """Stage the config for this job, sharing a single staged file across
    concurrent uploads. Returns the config_path to release later, or None if
    nothing was staged."""
    config_path = default_uploadrr_config_path(cwd)
    key = str(config_path)
    with _config_stage_lock:
        if _config_stage_refcount.get(key, 0) > 0:
            # Already staged by another in-flight upload — just join the count.
            _config_stage_refcount[key] += 1
            append_upload_log(job_id, "info", "config.yaml ya stageado por otra subida en curso; se reutiliza.", stream="system")
            return config_path
        staged = _stage_uploadrr_config(job_id, cwd)
        if staged is None:
            return None
        _config_stage_refcount[key] = 1
        return staged


def _release_staged_config(job_id: int, config_path: Path | None) -> None:
    """Drop this job's reference; restore the config only when the last
    concurrent upload finishes."""
    if config_path is None:
        return
    key = str(config_path)
    with _config_stage_lock:
        n = _config_stage_refcount.get(key, 0)
        if n <= 1:
            _config_stage_refcount.pop(key, None)
            _restore_uploadrr_config(job_id, config_path)
        else:
            _config_stage_refcount[key] = n - 1
            append_upload_log(job_id, "info", "config.yaml sigue en uso por otra subida; no se restaura todavía.", stream="system")


def _run_uploadrr_subprocess(job_id: int, cmd: dict, secrets: list[str]) -> None:
    """Execute Uploadrr in a background thread. Updates job status, logs, and result artifacts."""
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

    _update_job_status(
        job_id,
        "running",
        stage="running",
        started_at=started_at,
        safe_command_json=safe_cmd_json,
        last_log_at=_now(),
    )
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

    timeout = cmd.get("timeout") or None

    # Phase 10F: stage DEFAULT.tmdb / TRACKERS.EMU.api_key into Uploadrr-EMU's
    # own config.yaml before running, and always restore it afterwards
    # (success, failure, timeout, or cancellation) via the finally block.
    staged_config_path: Path | None = None
    if cmd.get("runtime_type") == RUNTIME_EMU and os.path.isdir(cwd):
        _update_job_status(job_id, "running", stage="config_staging")
        staged_config_path = _acquire_staged_config(job_id, cwd)
        _update_job_status(job_id, "running", stage="running")

    try:
        env = {k: v for k, v in os.environ.items()}

        proc = subprocess.Popen(
            [executable] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=cwd if os.path.isdir(cwd) else None,
            env=env,
        )

        _update_job_status(job_id, "running", process_id=proc.pid)
        append_upload_log(job_id, "info", f"PID: {proc.pid}", stream="system")

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def _read_stream(stream, level, stream_name, buf):
            for line in stream:
                line = line.rstrip("\n")
                safe_line = redact_secrets(line, secrets)
                buf.append(safe_line)
                append_upload_log(job_id, level, safe_line, stream=stream_name)

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
        t_out.join(timeout=timeout)
        t_err.join(timeout=timeout)

        timed_out = t_out.is_alive() or t_err.is_alive()
        if timed_out:
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
            t_out.join()
            t_err.join()
            try:
                returncode = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                returncode = -1

            finished_dt = datetime.now(timezone.utc)
            finished_at = finished_dt.isoformat()
            duration_seconds = int((finished_dt - started_dt).total_seconds())
            msg = f"Proceso cancelado por timeout ({timeout}s)."
            _finalize_job_status(
                job_id, "failed",
                stage="timeout",
                exit_code=returncode,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                error_message=msg,
                last_log_at=_now(),
                last_error_at=finished_at,
            )
            append_upload_log(job_id, "error", msg, stream="system")
            return

        returncode = proc.wait()

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
            # Save URL artifact if found
            if result["urls"]:
                first_url = result["urls"][0]
                create_upload_artifact(job_id, "uploaded_url", name="URL subida", url=first_url)

            # Save torrent ID artifact if found
            if result["torrent_ids"]:
                first_id = result["torrent_ids"][0]
                create_upload_artifact(job_id, "torrent_id", name="torrent_id", value=first_id)

            _finalize_job_status(
                job_id, "completed",
                stage="finished",
                exit_code=0,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                result_url=result["urls"][0] if result["urls"] else None,
                result_torrent_id=result["torrent_ids"][0] if result["torrent_ids"] else None,
                last_log_at=_now(),
                last_success_at=finished_at,
            )
            append_upload_log(
                job_id, "info",
                f"Proceso finalizado correctamente (exit code 0). Duración: {duration_seconds}s",
                stream="system",
            )
            _notify_upload_completed(job_id, result["urls"][0] if result["urls"] else None)
        else:
            err_summary = build_error_summary(stderr_text, stdout_text, returncode)
            safe_err = redact_secrets(err_summary or f"exit code {returncode}", secrets)

            _finalize_job_status(
                job_id, "failed",
                stage="failed",
                exit_code=returncode,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                error_message=safe_err[:2000],
                last_log_at=_now(),
                last_error_at=finished_at,
            )
            append_upload_log(
                job_id, "error",
                f"Proceso fallido (exit code {returncode}). Duración: {duration_seconds}s",
                stream="system",
            )

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
        append_upload_log(job_id, "error", f"Excepción inesperada: {msg}", stream="system")
    finally:
        _release_staged_config(job_id, staged_config_path)


def start_upload_job(
    job_id: int,
    *,
    dry_run: bool = True,
    start: bool = False,
    confirmation: str | None = None,
    conn=None,
) -> dict:
    """Start or preview a job.

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

        t = threading.Thread(
            target=_run_uploadrr_subprocess,
            args=(job_id, cmd, secrets),
            daemon=True,
        )
        t.start()

        return {
            "job_id": job_id,
            "action": "started",
            "status": "running",
            "stage": "running",
            "dry_run": False,
            "errors": [],
            "warnings": validation.get("warnings", []),
            "command_preview": redact_secrets(cmd.get("command_preview", ""), secrets),
            "using_prepared_path": cmd.get("using_prepared_path"),
            "message": "Uploadrr iniciado en background. Consulta los logs para el progreso.",
            "error": None,
        }
    finally:
        if own:
            conn.close()


def retry_upload_job(
    job_id: int,
    *,
    dry_run: bool = True,
    start: bool = False,
    confirmation: str | None = None,
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

        # Create new job
        now = _now()
        retry_count = (original.get("retry_count") or 0) + 1
        cur = conn.execute(
            """INSERT INTO upload_jobs
               (library_item_id, request_item_id, title, path,
                source_path, prepared_path, uploadrr_command_json,
                status, stage, retry_of_job_id, retry_count,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', 'preflight', ?, ?, ?, ?)""",
            (
                original.get("library_item_id"),
                original.get("request_item_id"),
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
        if status != "running":
            return {
                "ok": False,
                "message": f"El job no está en ejecución (status={status}). No hay proceso que cancelar.",
                "job_id": job_id,
            }

        pid = job.get("process_id")
        cancelled = False
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                cancelled = True
                append_upload_log(
                    job_id, "info",
                    f"SIGTERM enviado al proceso {pid}.",
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


__all__ = [
    "CONFIRMATION_TOKEN",
    "PROGRESS_PHASES",
    "compute_progress_phase",
    "redact_secrets",
    "get_upload_job",
    "list_upload_jobs",
    "validate_upload_job_start",
    "build_uploadrr_execution_command",
    "start_upload_job",
    "retry_upload_job",
    "append_upload_log",
    "get_upload_job_logs",
    "create_upload_artifact",
    "get_upload_job_artifacts",
    "cancel_upload_job",
]
