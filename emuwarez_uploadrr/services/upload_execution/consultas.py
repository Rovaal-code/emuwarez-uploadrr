"""Lectura de trabajos de subida (get/list/count), validación previa al arranque y construcción del comando de Uploadrr."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ...database import get_setting_canonical, row_to_dict, rows_to_dicts
from ..upload_states import PREPARATORY_STATUSES
from ..uploadrr_contract import (
    RUNTIME_EMU,
    build_uploadrr_emu_command,
    get_runtime_settings,
    render_command_preview,
)
from .comun import _get_db_conn


VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts",
    ".wmv", ".flv", ".webm", ".iso", ".m4v",
}


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
            from ..carpeta_subida import en_carpeta_de_subidas
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
