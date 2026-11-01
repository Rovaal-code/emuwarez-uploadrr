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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..database import connect, init_db, row_to_dict, rows_to_dicts, get_setting_canonical
from .upload_result_parser import classify_upload_result, extract_torrent_url, torrent_id_from_url
from .upload_states import PREPARATORY_STATUSES
from .uploadrr_progress import (
    RUNNING_DISPLAY_ORDER,
    RUNNING_SUB_PHASE_ORDER,
    build_phase_state,
    parse_uploadrr_progress,
    resolve_display_progress,
    with_phase_timestamps,
)
from .uploadrr_contract import (
    RUNTIME_EMU,
    build_uploadrr_emu_command,
    get_runtime_settings,
    render_command_preview,
)
from .uploadrr_config_staging import (
    SCREENS_API_KEY_HOSTS,
    default_uploadrr_config_path,
    backup_config,
    read_baseline_lines,
    restore_config_from_backup,
    restore_stale_config,
    stage_emu_config,
    stage_image_hosts,
    stage_add_logo,
    stage_blu_api_off,
    stage_per_episode_screens,
    stage_qbittorrent_config,
    stage_tmdb_key,
    staged_config_text,
    write_staged_config,
)
from .image_hosts import fallback_order, get_host_key
from .eventos import EVENTO_SUBIDA_ESTADO, EVENTO_SUBIDA_LOG, EVENTO_SUBIDA_PROGRESO, publicar, publicar_agrupado

logger = logging.getLogger("emuwarez.upload")

CONFIRMATION_TOKEN = "INICIAR_UPLOADRR"
DELETE_CONFIRMATION_TOKEN = "BORRAR_SUBIDA"
# Queda en los logs del job; al escribirla, append_upload_log marca `torrent_subido` para no borrar lo que siembra qBittorrent.
QBIT_AÑADIDO = "qBittorrent: torrent añadido correctamente."

# Phase 10F: approximate progress phases surfaced to the UI (string label
# only). Numeric per-phase percentages are tracked separately in
# upload_jobs.progress_json — see mark_phase_done/update_phase_progress below
# and uploadrr_progress.py's PHASES table.
PROGRESS_PHASES = (
    "staging", "queued", "verificacion_presubida", "nomenclature", "remux",
    "config_staging", "running", "finalizing", "succeeded", "failed",
    "cancelled", "timeout",
)


# Fase de un trabajo 'ready' lanzado directamente (CLI, reintento con
# confirmación) mientras espera plaza en "Subidas en paralelo".
ETAPA_ESPERANDO_TURNO = "queued"


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
    if status == "staging":
        return "staging"
    if status == "preparing":
        # Server-side prep queued jobs go through before the real Uploadrr
        # subprocess: verificación presubida (integrity + generic preconditions)
        # -> nomenclature rename -> track remux -> final preflight, all
        # against the SAME job row the user is watching.
        if stage in ("verificacion_presubida", "nomenclature", "remux"):
            return stage
        return "verificacion_presubida"
    if status == "running":
        if stage == "config_staging":
            return "config_staging"
        if stage == "finalizing":
            return "finalizing"
        return "running"
    if status == "ready":
        return "queued" if stage == ETAPA_ESPERANDO_TURNO else "verificacion_presubida"
    if status in ("draft", "preflight"):
        return "verificacion_presubida"
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
        from .settings import get_setting_canonical
        valor = get_setting_canonical(conn, key)
        if valor:
            return valor
    except Exception:
        pass
    try:
        from ..database import get_state
        return get_state(conn, key, default)
    except Exception:
        return default


def _collect_secrets(conn) -> list[str]:
    secrets = []
    # Los dos de qBittorrent también: un error de conexión de Uploadrr-EMU escribe la URL de qui, clave incluida.
    for key in ("emu.api_key", "tmdb.api_key", "qbit.password", "qbit.qui_proxy_url"):
        val = get_setting_canonical(conn, key)
        if val:
            secrets.append(val)
    # urllib3 escribe la ruta sin el host ("url: /proxy/<clave>/api/v2/..."): la clave de qui, sola.
    qui = (get_setting_canonical(conn, "qbit.qui_proxy_url") or "").strip().rstrip("/")
    if "/proxy/" in qui:
        secrets.append(qui.rsplit("/", 1)[-1])
    # Las de los hosts de imágenes también se stagean en el config.yaml del hijo.
    from .settings import all_settings
    secrets += [v for k, v in all_settings(conn).items() if k.startswith("imghost.key.") and v]
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


def _upload_jobs_where(filters: dict) -> tuple[str, list[Any]]:
    conditions = []
    params: list[Any] = []

    # Un estado o varios separados por coma («running,preparing»).
    estados = [e.strip() for e in (filters.get("status") or "").split(",") if e.strip()]
    if estados:
        conditions.append(f"status IN ({','.join('?' * len(estados))})")
        params.extend(estados)

    if filters.get("hide_preparatory"):
        # No son subidas, y filtrados después ocuparían sitio en la página.
        ocultos = sorted(PREPARATORY_STATUSES)
        conditions.append(f"status NOT IN ({','.join('?' * len(ocultos))})")
        params.extend(ocultos)

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

    return (f"WHERE {' AND '.join(conditions)}" if conditions else ""), params


def list_upload_jobs(filters: dict | None = None, conn=None) -> list[dict]:
    """List upload jobs with optional filters: status, hide_preparatory, limit, offset, search."""
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        filters = filters or {}
        where, params = _upload_jobs_where(filters)
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


def count_upload_jobs(filters: dict | None = None, conn=None) -> int:
    """Cuántas subidas cumplen los mismos filtros que list_upload_jobs, sin límite: el «M» de «N de M»."""
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        where, params = _upload_jobs_where(filters or {})
        return conn.execute(f"SELECT COUNT(*) FROM upload_jobs {where}", params).fetchone()[0]
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
            from .carpeta_subida import en_carpeta_de_subidas
            p = Path(active_path)
            if not p.exists():
                errors.append(f"El archivo no existe en disco: {active_path}")
            elif p.is_symlink() and not en_carpeta_de_subidas(active_path):
                # Los de la carpeta de subidas sí valen: con /config y /data en
                # montajes distintos no cabe un enlace duro y se hace simbólico.
                errors.append(f"El archivo es un symlink y no puede usarse: {active_path}")
            elif p.is_dir():
                # A season pack's prepared_path is the shared hardlink folder,
                # not a single file — nothing more to check here (each
                # episode inside it was already validated during the
                # queue's own integrity/nomenclature/remux stages).
                pass
            elif not p.is_file():
                errors.append(f"La ruta no es un archivo regular: {active_path}")
            elif p.suffix.lower() not in VIDEO_EXTENSIONS:
                warnings.append(f"El archivo no tiene extensión de vídeo reconocida: {p.suffix}")

        # Falls back to the bundled runtime's own default the same way
        # get_runtime_settings() always does — it needs no configuration.
        uploadrr_path = get_runtime_settings(conn)["uploadrr_path"]
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
                release_format=cmd_data.get("release_format"),
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


def _avisar_de_log(job_id: int) -> None:
    """Avisa de que hay líneas nuevas, como mucho una vez por segundo.

    El aviso NO lleva las líneas. El proceso escupe cientos por segundo y
    mandarlas por el canal lo convertiría en una tubería de logs; además solo
    le importan a quien tenga abierta esa pantalla concreta. Así que solo se
    dice que las hay, y quien mire las pide.

    Agrupar aquí es seguro porque el aviso no lleva estado: el que sí sale trae
    consigo todo lo que se perdieron los que no salieron.
    """
    publicar_agrupado(f"log-{job_id}", EVENTO_SUBIDA_LOG, {"job_id": job_id}, cada=1.0)


def _ficha_del_torrent(stdout_text: str) -> dict:
    """Lo que guarda una subida que falla después de subir el torrent: su ficha, su id y la marca del enlace."""
    url = extract_torrent_url(stdout_text)
    if not url:
        return {}
    return {"result_url": url, "result_torrent_id": torrent_id_from_url(url), "torrent_subido": 1}


def _marca_torrent_subido(message: str) -> bool:
    """Si la línea dice que el torrent ya está en eMuwarez o en qBittorrent."""
    return message == QBIT_AÑADIDO or extract_torrent_url(message) is not None


def append_upload_log(
    job_id: int,
    level: str,
    message: str,
    stream: str = "system",
    raw: dict | None = None,
    conn=None,
) -> None:
    _avisar_de_log(job_id)
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        # La secuencia se calcula en el INSERT: dos hilos no cogen la misma, y el MAX lo resuelve el índice.
        conn.execute(
            """INSERT INTO upload_job_logs
               (upload_job_id, level, message, stream, created_at, raw_json, sequence, is_secret_redacted)
               VALUES (?, ?, ?, ?, ?, ?,
                       (SELECT COALESCE(MAX(sequence), 0) + 1 FROM upload_job_logs WHERE upload_job_id = ?), 1)""",
            (
                job_id,
                level,
                message[:8000],
                stream,
                _now(),
                json.dumps(raw, ensure_ascii=False) if raw else None,
                job_id,
            ),
        )
        if _marca_torrent_subido(message):
            # Al leer la línea, no al terminar: si el proceso muere después, el enlace sigue siendo de lo que se siembra.
            conn.execute("UPDATE upload_jobs SET torrent_subido = 1 WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        if own:
            conn.close()


def get_upload_job_logs(
    job_id: int,
    limit: int = 500,
    offset: int = 0,
    *,
    tail: bool = False,
    after_sequence: int | None = None,
    conn=None,
) -> dict:
    """tail=True overrides `offset` to fetch the LAST `limit` lines instead
    of the first — a noisy job (many retries across several image hosts,
    each logging multiple lines) can easily produce more lines than a fixed
    small `limit`, and a caller that always passes offset=0 would otherwise
    be frozen on the SAME oldest window forever, never seeing anything
    logged after it — exactly what made "Ver Logs" look stuck/stale during
    a real per-host upload failure storm.

    after_sequence: solo las líneas posteriores a esa, de la más antigua a la más nueva (seguir una subida en vivo)."""
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM upload_job_logs WHERE upload_job_id = ?", (job_id,)
        ).fetchone()
        total = total_row[0] if total_row else 0
        if after_sequence is not None:
            rows = conn.execute(
                "SELECT * FROM upload_job_logs WHERE upload_job_id = ? AND sequence > ? "
                "ORDER BY sequence ASC, id ASC LIMIT ?",
                (job_id, after_sequence, limit),
            ).fetchall()
        elif tail:
            # Del final hacia atrás por el índice y se da la vuelta: sin OFFSET, que recorre todo lo anterior.
            rows = conn.execute(
                "SELECT * FROM upload_job_logs WHERE upload_job_id = ? ORDER BY sequence DESC, id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()[::-1]
            offset = max(0, total - limit)
        else:
            rows = conn.execute(
                "SELECT * FROM upload_job_logs WHERE upload_job_id = ? ORDER BY sequence ASC, id ASC LIMIT ? OFFSET ?",
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
    """Escribe el estado sin condiciones. Solo para Cancelar, que es la
    decisión del usuario. Para arrancar usa _avanzar_job y para terminar un
    trabajo _finalize_job_status: los dos protegen la cancelación."""
    from .upload_states import escribir_estado
    escribir_estado(job_id, status=status, **kwargs)


def _avanzar_job(job_id: int, status: str, **kwargs) -> bool:
    """Escribe el estado salvo que el usuario ya haya cancelado el trabajo.
    False significa cancelado: quien llama no debe seguir."""
    from .upload_states import escribir_estado
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
    from .upload_states import escribir_estado

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
        from .trailer_check import check_trailer_for_job

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
        from .notification_center import emit
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
        from .notification_center import emit
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


class ConfigNoPreparada(RuntimeError):
    """El config.yaml de Uploadrr no se pudo preparar: lanzarlo así lo haría fallar con las claves sin poner."""


def _stage_uploadrr_config(job_id: int, cwd: str) -> Path | None:
    """Staging of DEFAULT.tmdb / TRACKERS.EMU.api_key into config.yaml.

    Returns the config_path if staging happened (so the caller knows to
    restore it later), or None if there was nothing to stage (config.yaml
    missing, or no secrets configured) — in that case there is nothing to
    restore either. Si preparar el config falla lanza ConfigNoPreparada: el
    job termina fallido sin lanzar Uploadrr.
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
        img_hosts = fallback_order(conn)
        img_api_keys = {
            host_id: key for host_id in SCREENS_API_KEY_HOSTS
            if (key := get_host_key(conn, host_id))
        }
        qbit_url = get_setting_canonical(conn, "qbit.url")
        qbit_tag = get_setting_canonical(conn, "qbit.tag")
        # El logo va en la descripción salvo que se haya apagado a mano.
        add_logo = get_setting_canonical(conn, "emu.add_logo") != "false"
        # Las capturas de un pack, solo del primer capítulo salvo que se pidan todas.
        per_episode_screens = get_setting_canonical(conn, "emu.per_episode_screens") == "true"
        qbit_username = get_setting_canonical(conn, "qbit.username")
        qbit_password = get_setting_canonical(conn, "qbit.password")
        qbit_qui = get_setting_canonical(conn, "qbit.qui_proxy_url")
    finally:
        conn.close()

    try:
        # Del config de verdad (.bak), no del config.yaml de ahora: puede ser el
        # que dejó stageado una subida que murió, o el de otra que sigue en curso.
        lines = read_baseline_lines(config_path)
        changed = False
        if tmdb_key:
            lines, _msg = stage_tmdb_key(lines, tmdb_key)
            changed = True
        if emu_key:
            lines, _msg = stage_emu_config(lines, api_key=emu_key)
            changed = True
        lines, _msg = stage_add_logo(lines, add_logo)
        lines, _msg = stage_per_episode_screens(lines, per_episode_screens)
        lines, _msg = stage_blu_api_off(lines)
        changed = True
        if img_hosts:
            # Always staged (imgbox is always in fallback_order()'s result,
            # even with nothing else enabled) — this is what makes the
            # configured preference (e.g. Pixhost) actually reach Uploadrr-EMU
            # instead of it silently defaulting to its own img_hosts order.
            lines, _msg = stage_image_hosts(lines, img_hosts=img_hosts, api_keys=img_api_keys)
            changed = True
        if (qbit_url and qbit_username and qbit_password) or qbit_qui:
            # Without this, Uploadrr-EMU falls back to whatever
            # DEFAULT.default_torrent_client its own config.yaml ships with
            # (confirmed: "watch", not "qbit") — the job finishes
            # "successfully" but silently never touches qBittorrent's API.
            lines, _msg = stage_qbittorrent_config(
                lines, url=qbit_url or "", username=qbit_username or "", password=qbit_password or "", tag=qbit_tag,
                base_dir=cwd, qui_proxy_url=qbit_qui,
            )
            changed = True
        if not changed:
            append_upload_log(
                job_id, "warning",
                "Sin tmdb.api_key/emu.api_key configuradas; config.yaml no se modifica.",
                stream="system",
            )
            return None
        backup_config(config_path)
        if config_path.read_text(encoding="utf-8", errors="ignore") == staged_config_text(lines):
            return config_path  # ya está así: no se reescribe bajo una subida en curso
        write_staged_config(config_path, lines)
        append_upload_log(
            job_id, "info",
            "config.yaml stageado (DEFAULT.tmdb / TRACKERS.EMU.api_key / SCREENS.img_hosts / TORRENT_CLIENTS.qbit). Backup creado.",
            stream="system",
        )
        return config_path
    except Exception as exc:
        raise ConfigNoPreparada(
            f"No se pudo preparar el config.yaml de Uploadrr ({exc}). No se lanza la subida: con el config sin preparar fallaría."
        ) from exc


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
            # Ya lo stageó otra subida en curso. Se vuelve a calcular por si Ajustes
            # cambió desde entonces: solo reescribe si el resultado es otro.
            _stage_uploadrr_config(job_id, cwd)
            append_upload_log(job_id, "info", "config.yaml ya stageado por otra subida en curso; se reutiliza.", stream="system")
            _config_stage_refcount[key] += 1
            return config_path
        # Sin subidas en curso config.yaml debería ser el .bak: si no, es el
        # stageado de una que murió a medias.
        try:
            if restore_stale_config(config_path):
                append_upload_log(
                    job_id, "warning",
                    "config.yaml seguía stageado por una subida interrumpida; restaurado desde el backup.",
                    stream="system",
                )
        except OSError as exc:
            logger.warning("No se pudo restaurar el config.yaml interrumpido (%s): %s", config_path, exc)
        staged = _stage_uploadrr_config(job_id, cwd)
        if staged is None:
            return None
        _config_stage_refcount[key] = 1
        return staged


def restaurar_config_interrumpida() -> bool:
    """Al arrancar no hay ninguna subida viva: si config.yaml sigue stageado es
    el de una que murió sin restaurarlo, con las claves reales dentro."""
    conn = _get_db_conn()
    try:
        uploadrr_path = get_runtime_settings(conn)["uploadrr_path"]
    finally:
        conn.close()
    return bool(uploadrr_path) and restore_stale_config(default_uploadrr_config_path(uploadrr_path))


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


# "Subidas en paralelo" (Configuración → Otros): caps how many jobs run their
# actual Uploadrr-EMU subprocess at once — hashing the torrent, generating
# and uploading screenshots, transferring to eMuwarez, the genuinely CPU/
# network-heavy tail — regardless of which entry point queued them (the
# normal "Subir a eMuwarez" flow, a retry, or the legacy direct-start
# endpoints). El trabajo encolado toma la plaza antes de preparar los ficheros
# (upload_queue._run_queued_job) y la pasa al subproceso. 0 = sin límite.
UPLOAD_MAX_CONCURRENT_SETTING_KEY = "uploads.max_concurrent"
UPLOAD_MAX_CONCURRENT_CHOICES = tuple(range(0, 11))  # 0, 1, 2, … 10
UPLOAD_MAX_CONCURRENT_DEFAULT = 1


def get_upload_max_concurrent(conn=None) -> int:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        raw = get_setting_canonical(conn, UPLOAD_MAX_CONCURRENT_SETTING_KEY)
    finally:
        if own:
            conn.close()
    try:
        val = int(raw) if raw else UPLOAD_MAX_CONCURRENT_DEFAULT
    except (TypeError, ValueError):
        return UPLOAD_MAX_CONCURRENT_DEFAULT
    return val if val in UPLOAD_MAX_CONCURRENT_CHOICES else UPLOAD_MAX_CONCURRENT_DEFAULT


def _limite_de_subidas() -> int:
    try:
        return get_upload_max_concurrent()
    except Exception:
        logger.warning("No se pudo leer %s; se usa %s", UPLOAD_MAX_CONCURRENT_SETTING_KEY,
                       UPLOAD_MAX_CONCURRENT_DEFAULT, exc_info=True)
        return UPLOAD_MAX_CONCURRENT_DEFAULT


class _UploadConcurrencyGate:
    """Re-reads the configured limit on every wait loop instead of capturing
    it once at acquire time — so lowering/raising the setting takes effect
    immediately for whichever job is next in line, with no need to touch
    jobs already past the gate and no need to block changing the setting
    while uploads are running: shrinking the limit just makes new jobs wait
    longer, it never kills or pauses one already running.

    Admission order is by job_id ascending (== creation order), never by
    whichever waiting thread happens to wake up first from notify_all() —
    threading.Condition doesn't guarantee FIFO wakeup order, and the UI's
    puesto en la cola (posiciones(), also ordered by id) would otherwise
    sometimes lie about which job starts next.

    Una subida en espera se puede retirar (Cancelar en «En cola»): deja la cola
    al momento y acquire() devuelve False, sin ocupar plaza."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._active = 0
        self._waiting: set[int] = set()
        self._retirados: set[int] = set()
        self._liberaciones = 0

    def acquire(self, job_id: int, *, cancelada: Callable[[], bool] | None = None) -> bool:
        """True con la plaza tomada; False si se retiró mientras esperaba.
        `cancelada` se consulta en cada vuelta de la espera: así una
        cancelación escrita desde otro proceso (el CLI) también la saca.
        No lanza: corre antes del try de quien llama, y un fallo aquí dejaba
        el job en cola para siempre. La base se consulta fuera del candado."""
        with self._cond:
            if job_id in self._retirados:
                self._retirados.discard(job_id)
                return False
            self._waiting.add(job_id)
        announced = False
        try:
            while True:
                if cancelada is not None and _sin_fallos(cancelada):
                    return False
                limit = _limite_de_subidas()
                with self._cond:
                    if job_id in self._retirados:
                        self._retirados.discard(job_id)
                        return False
                    is_next = job_id == min(self._waiting - self._retirados)
                    if limit == 0 or (self._active < limit and is_next):
                        self._waiting.discard(job_id)
                        self._active += 1
                        return True
                    activas, vistas = self._active, self._liberaciones
                if not announced:
                    announced = True
                    # Ahora sí espera de verdad: la interfaz pasa a enseñar su puesto.
                    publicar(EVENTO_SUBIDA_ESTADO, {"job_id": job_id, "status": "queued", "stage": "queued"})
                    try:
                        append_upload_log(
                            job_id, "info",
                            f"Esperando turno para empezar la subida real: {activas} en curso, límite {limit}.",
                            stream="system",
                        )
                    except Exception:
                        logger.warning("Subida %s: no se pudo registrar la espera de turno", job_id, exc_info=True)
                with self._cond:
                    if self._liberaciones == vistas:
                        self._cond.wait(timeout=3)
        finally:
            with self._cond:
                self._waiting.discard(job_id)
                # Una retirada que llegó mientras esperaba ya no hace falta,
                # salga como salga (con plaza, retirada o por `cancelada`).
                self._retirados.discard(job_id)
                # Los de detrás suben un puesto: que lo vean ya, sin esperar al siguiente ciclo.
                self._liberaciones += 1
                self._cond.notify_all()
            if announced:
                publicar(EVENTO_SUBIDA_ESTADO, {"job_id": job_id})

    def release(self) -> None:
        with self._cond:
            self._active = max(0, self._active - 1)
            self._liberaciones += 1
            self._cond.notify_all()

    def retirar_si_espera(self, job_id: int) -> None:
        """Como retirar(), pero solo si ya está esperando: quien aún no ha
        llegado a la puerta lo para su `cancelada` al llegar, y así no queda
        una retirada apuntada que nadie recoja."""
        with self._cond:
            if job_id in self._waiting:
                self._retirados.add(job_id)
                self._liberaciones += 1
                self._cond.notify_all()

    def retirar(self, job_id: int) -> None:
        """Saca de la cola una subida cancelada. Si su hilo aún no ha llegado
        a la puerta, al llegar se va sin esperar."""
        with self._cond:
            self._retirados.add(job_id)
            self._liberaciones += 1
            self._cond.notify_all()

    def olvidar(self, job_id: int) -> None:
        """Lo llama el hilo de la subida al terminar: una retirada que llegó
        cuando ya tenía plaza no se queda apuntada para siempre."""
        with self._cond:
            self._retirados.discard(job_id)

    def posiciones(self) -> dict[int, tuple[int, int]]:
        """Puesto (desde 1) y total de cada subida que espera plaza, por id."""
        with self._cond:
            en_cola = sorted(self._waiting - self._retirados)
        return {jid: (i + 1, len(en_cola)) for i, jid in enumerate(en_cola)}


_upload_concurrency_gate = _UploadConcurrencyGate()


def _sin_fallos(pregunta: Callable[[], bool]) -> bool:
    try:
        return bool(pregunta())
    except Exception:
        logger.warning("No se pudo comprobar si la subida se canceló", exc_info=True)
        return False


def _esta_cancelado(job_id: int) -> bool:
    conn = _get_db_conn()
    try:
        row = conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    return bool(row) and row["status"] == "cancelled"


def _read_progress_state(job_id: int) -> dict:
    conn = _get_db_conn()
    try:
        row = conn.execute(
            "SELECT progress_json FROM upload_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["progress_json"]:
        return {"phases": [], "global_pct": 0}
    try:
        return json.loads(row["progress_json"])
    except (TypeError, ValueError):
        return {"phases": [], "global_pct": 0}


def _write_progress_json(job_id: int, state: dict) -> None:
    conn = _get_db_conn()
    try:
        conn.execute(
            "UPDATE upload_jobs SET progress_json = ? WHERE id = ?",
            (json.dumps(state, ensure_ascii=False), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_phase_started(job_id: int, stage_key: str) -> None:
    """Record the wall-clock start of a phase — call this right when a
    phase's real work begins (mark_phase_done when it completes), so the
    Fases table's Creado/Finalizado/Duración columns reflect real timing,
    not just the current status snapshot. Safe to call even if the phase
    finishes almost immediately (started_at/finished_at can be equal)."""
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    completed.discard(stage_key)
    new_state = build_phase_state(list(completed), current=stage_key, current_pct=0)
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))


def mark_phase_done(job_id: int, stage_key: str) -> None:
    """Mark a pipeline phase (integrity/nomenclature/remux/preflight/running)
    as fully complete, keeping whichever other phases were already done, and
    persist the recomputed job-wide percentage."""
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    completed.add(stage_key)
    new_state = build_phase_state(list(completed))
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))
    # Sin agrupar: es el último cambio de la fase, y el aviso de estado del job puede haber salido antes.
    publicar(EVENTO_SUBIDA_PROGRESO, {"job_id": job_id, "phase": stage_key})


def mark_phase_failed(job_id: int, stage_key: str) -> None:
    """Deja una fase como fallida aunque el job acabe bien (qBittorrent tras una subida que sí se hizo)."""
    state = _read_progress_state(job_id)
    for p in state.get("phases", []):
        if p["key"] == stage_key:
            p["status"] = "failed"
            p["finished_at"] = p.get("finished_at") or _now()
    _write_progress_json(job_id, state)
    publicar(EVENTO_SUBIDA_PROGRESO, {"job_id": job_id, "phase": stage_key})


def update_phase_progress(job_id: int, stage_key: str, pct: int) -> None:
    """Update the live in-progress percentage of one phase (remux via
    mkvmerge --gui-mode), keeping whatever phases were already marked done
    intact."""
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    completed.discard(stage_key)
    new_state = build_phase_state(list(completed), current=stage_key, current_pct=pct)
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))


def advance_running_phase(job_id: int, phase_key: str, pct: int) -> None:
    """Update progress_json as Uploadrr-EMU's own output reports a new
    internal sub-phase (queue -> video processing -> MediaInfo -> ... ->
    uploading to eMuwarez). Uploadrr-EMU reports these strictly in order.

    Several raw sub-phases now share one displayed PHASES row (see
    uploadrr_progress.PHASE_KEY_ALIASES) — resolve_display_progress() maps
    `phase_key`'s raw progress to that merged key + an interpolated pct, and
    every DISPLAYED phase before it is marked done, same retroactive
    safety net as before (just over merged keys instead of raw ones)."""
    if phase_key not in RUNNING_SUB_PHASE_ORDER:
        return
    display_key, display_pct = resolve_display_progress(phase_key, pct)
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    idx = RUNNING_DISPLAY_ORDER.index(display_key)
    completed.update(RUNNING_DISPLAY_ORDER[:idx])
    completed.discard(display_key)
    # Never regress the merged phase's displayed pct — a later raw member
    # firing at a lower interpolated pct than an earlier one already showed
    # (shouldn't normally happen, but stay defensive) must not roll it back.
    current_row = next((p for p in state.get("phases", []) if p["key"] == display_key), None)
    if current_row and current_row.get("status") == "running":
        display_pct = max(display_pct, current_row.get("pct", 0))
    new_state = build_phase_state(list(completed), current=display_key, current_pct=display_pct)
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))

    # El progreso ya está escrito: ahora se puede avisar. Se agrupa por trabajo
    # porque el proceso reporta a mucha más resolución de la que un ojo
    # distingue, y recargar la tabla de subidas veinte veces por segundo sería
    # más caro que el sondeo de 2,5 s que esto viene a sustituir.
    publicar_agrupado(f"progreso-{job_id}", EVENTO_SUBIDA_PROGRESO,
                      {"job_id": job_id, "phase": display_key, "pct": display_pct},
                      cada=0.5)


# Los Uploadrr en marcha de ESTE proceso, por trabajo: Cancelar los señala.
_PROCESOS: dict[int, subprocess.Popen] = {}
_PROCESOS_LOCK = threading.Lock()
_apagando = False
# Segundos entre SIGTERM y SIGKILL, y de margen a las tuberías tras salir Uploadrr.
_GRACIA_SIGKILL = 10
_GRACIA_LECTORES = 15


def _senalar_grupo(proc: subprocess.Popen, sig: int) -> bool:
    """Manda la señal al grupo del proceso (start_new_session hace pgid == pid)."""
    try:
        os.killpg(proc.pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _detener_proceso(proc: subprocess.Popen) -> bool:
    """SIGTERM al grupo y, si Uploadrr sigue vivo pasado el plazo, SIGKILL.
    Sin bloquear: lo usa Cancelar, que responde a una petición web."""
    enviada = _senalar_grupo(proc, signal.SIGTERM)
    if enviada:
        def _rematar() -> None:
            if proc.poll() is None:
                _senalar_grupo(proc, signal.SIGKILL)
        timer = threading.Timer(_GRACIA_SIGKILL, _rematar)
        timer.daemon = True
        timer.start()
    return enviada


def detener_procesos_en_marcha() -> None:
    """Al apagar el servidor: Uploadrr va en su propia sesión y ya no cae con él.
    Desde aquí no se lanza ninguno más."""
    global _apagando
    with _PROCESOS_LOCK:
        _apagando = True
        procesos = list(_PROCESOS.values())
    for proc in procesos:
        _detener_proceso(proc)


def _pid_es_de_este_job(pid: int, job: dict) -> bool:
    """El PID guardado es de otro proceso si Uploadrr ya terminó (los PID se
    reutilizan): solo se señala si su línea de comandos es la de este job."""
    try:
        import psutil
        cmdline = psutil.Process(pid).cmdline()
        ruta = json.loads(job.get("safe_command_json") or "{}").get("source_path")
    except Exception:  # sin psutil (CLI sin extras), proceso ya muerto o JSON ilegible
        return False
    return bool(ruta) and ruta in cmdline and any(a.endswith("upload.py") for a in cmdline)


def _terminar_y_esperar(proc: subprocess.Popen) -> int:
    """Lo mismo pero esperando: devuelve el código de salida (-1 si no sale)."""
    _senalar_grupo(proc, signal.SIGTERM)
    try:
        return proc.wait(timeout=_GRACIA_SIGKILL)
    except subprocess.TimeoutExpired:
        _senalar_grupo(proc, signal.SIGKILL)
    try:
        return proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return -1


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
            if _apagando:
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
            from .upload_states import escribir_estado
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

        from .upload_queue import trabajo_activo
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
            from .upload_states import escribir_estado
            if not escribir_estado(job_id, desde={"queued"}, status="cancelled", stage="cancelled",
                                   finished_at=_now(), conn=conn):
                return cancel_upload_job(job_id, conn=conn)
            from .upload_queue import retirar_de_la_cola
            retirar_de_la_cola(job_id)
            append_upload_log(job_id, "info", "Subida cancelada mientras esperaba turno en la cola.", stream="system")
            return {"ok": True, "message": "Subida cancelada.", "job_id": job_id}

        if status == "ready" and job.get("stage") == ETAPA_ESPERANDO_TURNO:
            # Arranque directo esperando plaza: aún no hay proceso. La escritura
            # solo cae si sigue en 'ready'; si justo entró y ya está en marcha,
            # se cancela como lo que es ahora.
            from .upload_states import escribir_estado
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
        from .carpeta_subida import ENLACES, borrar_de_subidas
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


__all__ = [
    "CONFIRMATION_TOKEN",
    "DELETE_CONFIRMATION_TOKEN",
    "PROGRESS_PHASES",
    "compute_progress_phase",
    "redact_secrets",
    "get_upload_job",
    "list_upload_jobs",
    "count_upload_jobs",
    "validate_upload_job_start",
    "build_uploadrr_execution_command",
    "start_upload_job",
    "retry_upload_job",
    "append_upload_log",
    "get_upload_job_logs",
    "create_upload_artifact",
    "get_upload_job_artifacts",
    "cancel_upload_job",
    "delete_upload_job",
    "mark_phase_started",
    "mark_phase_done",
    "update_phase_progress",
    "advance_running_phase",
]
