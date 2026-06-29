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
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..database import connect, init_db, row_to_dict, rows_to_dicts

CONFIRMATION_TOKEN = "INICIAR_UPLOADRR"

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
    for key in ("emu_api_key", "EMU_API_KEY", "tmdb_api_key", "TMDB_API_KEY"):
        val = _get_setting(conn, key)
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
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM upload_jobs ORDER BY created_at DESC LIMIT 200"
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

        uploadrr_path = _get_setting(conn, "uploadrr_path") or _get_setting(conn, "UPLOADRR_PATH")
        if not uploadrr_path:
            errors.append("Ruta de Uploadrr no configurada (uploadrr_path).")
        else:
            script = Path(uploadrr_path) / "upload.py"
            if not script.exists():
                errors.append(f"Script de Uploadrr no encontrado: {script}")

        emu_key = _get_setting(conn, "emu_api_key") or _get_setting(conn, "EMU_API_KEY")
        if not emu_key:
            errors.append("API key de eMuwarez no configurada.")

        tmdb_key = _get_setting(conn, "tmdb_api_key") or _get_setting(conn, "TMDB_API_KEY")
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

    Returns {"executable": str, "args": list[str], "cwd": str, "command_preview": str}.
    Does NOT include secrets in the returned dict.
    """
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        uploadrr_path = _get_setting(conn, "uploadrr_path") or _get_setting(conn, "UPLOADRR_PATH") or ""
        script = str(Path(uploadrr_path) / "upload.py")

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

        tracker = cmd_data.get("tracker") or "EMU"
        category = cmd_data.get("category") or "movie"
        tmdb_id = cmd_data.get("tmdb_id") or job.get("tmdb_id")
        resolution = cmd_data.get("resolution") or ""

        executable = sys.executable
        args = [script, active_path, "--tracker", tracker, "--category", category]
        if tmdb_id:
            args += ["--tmdb", str(tmdb_id)]
        if resolution:
            args += ["--resolution", resolution]

        safe_args = list(args)
        preview = " ".join(
            f'"{a}"' if " " in a else a
            for a in [executable] + safe_args
        )

        return {
            "executable": executable,
            "args": args,
            "cwd": uploadrr_path,
            "command_preview": preview,
            "using_prepared_path": using_prepared,
            "source_path": active_path,
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
        conn.execute(
            """INSERT INTO upload_job_logs (upload_job_id, level, message, stream, created_at, raw_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                level,
                message[:8000],
                stream,
                _now(),
                json.dumps(raw, ensure_ascii=False) if raw else None,
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


def _run_uploadrr_subprocess(job_id: int, cmd: dict, secrets: list[str]) -> None:
    """Execute Uploadrr in a background thread. Updates job status and logs output."""
    executable = cmd["executable"]
    args = cmd["args"]
    cwd = cmd.get("cwd") or "."

    _update_job_status(
        job_id,
        "running",
        stage="running",
        started_at=_now(),
    )
    append_upload_log(job_id, "info", "Iniciando proceso Uploadrr…", stream="system")
    append_upload_log(
        job_id,
        "info",
        f"Comando: {redact_secrets(cmd.get('command_preview', ''), secrets)}",
        stream="system",
    )

    try:
        env = {k: v for k, v in os.environ.items()}

        proc = subprocess.Popen(
            [executable] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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

        t_out = threading.Thread(target=_read_stream, args=(proc.stdout, "info", "stdout", stdout_lines), daemon=True)
        t_err = threading.Thread(target=_read_stream, args=(proc.stderr, "warning", "stderr", stderr_lines), daemon=True)
        t_out.start()
        t_err.start()
        t_out.join()
        t_err.join()

        returncode = proc.wait()

        if returncode == 0:
            _update_job_status(
                job_id, "completed",
                stage="finished",
                exit_code=0,
                finished_at=_now(),
            )
            append_upload_log(job_id, "info", f"Proceso finalizado correctamente (exit code 0).", stream="system")
        else:
            err_summary = redact_secrets(
                "; ".join(stderr_lines[-5:]) if stderr_lines else f"exit code {returncode}",
                secrets,
            )
            _update_job_status(
                job_id, "failed",
                stage="failed",
                exit_code=returncode,
                finished_at=_now(),
                error_message=err_summary[:2000],
            )
            append_upload_log(job_id, "error", f"Proceso fallido (exit code {returncode}).", stream="system")

    except FileNotFoundError as exc:
        msg = f"Ejecutable no encontrado: {exc}"
        _update_job_status(job_id, "failed", stage="failed", finished_at=_now(), error_message=msg[:2000])
        append_upload_log(job_id, "error", msg, stream="system")
    except Exception as exc:
        msg = redact_secrets(str(exc), secrets)
        _update_job_status(job_id, "failed", stage="failed", finished_at=_now(), error_message=msg[:2000])
        append_upload_log(job_id, "error", f"Excepción inesperada: {msg}", stream="system")


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
                append_upload_log(job_id, "info", f"SIGTERM enviado al proceso {pid}.", stream="system", conn=conn)
            except (ProcessLookupError, PermissionError) as exc:
                append_upload_log(job_id, "warning", f"No se pudo enviar SIGTERM al PID {pid}: {exc}", stream="system", conn=conn)

        _update_job_status(job_id, "cancelled", stage="cancelled", finished_at=_now())
        append_upload_log(job_id, "info", "Job marcado como cancelado.", stream="system")

        return {
            "ok": True,
            "message": "Job cancelado." + (" Señal enviada al proceso." if cancelled else " El proceso puede no estar activo."),
            "job_id": job_id,
        }
    finally:
        if own:
            conn.close()


__all__ = [
    "CONFIRMATION_TOKEN",
    "redact_secrets",
    "get_upload_job",
    "list_upload_jobs",
    "validate_upload_job_start",
    "build_uploadrr_execution_command",
    "start_upload_job",
    "append_upload_log",
    "get_upload_job_logs",
    "cancel_upload_job",
]
