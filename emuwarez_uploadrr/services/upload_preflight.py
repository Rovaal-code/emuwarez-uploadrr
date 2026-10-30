"""Upload preflight service.

SAFETY CONTRACT: This module never executes Uploadrr, never creates torrents,
never uploads files, and never modifies any filesystem paths.
It only builds previews of what WOULD happen.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..database import connect, row_to_dict, rows_to_dicts, get_setting_canonical
from .filesystem_safety import safe_stat
from .uploadrr_contract import (
    DEFAULT_UPLOADRR_PATH,
    RUNTIME_EMU,
    RUNTIME_GENERIC,
    build_uploadrr_emu_command,
    get_runtime_settings,
    render_command_preview,
    validate_uploadrr_emu_contract,
)
from .uploadrr_config_staging import default_uploadrr_config_path
from .upload_execution import CONFIRMATION_TOKEN

JOB_STATUS_DRAFT = "draft"
JOB_STATUS_PREFLIGHT = "preflight"
JOB_STATUS_READY = "ready"
JOB_STATUS_BLOCKED = "blocked"


def validate_upload_preconditions(library_item: dict, proposal: dict | None = None, conn=None) -> dict:
    own = conn is None
    conn = conn or connect()
    errors = []
    warnings = []

    try:
        if not library_item:
            return {"ok": False, "errors": ["Item no encontrado."], "warnings": []}

        local_status = library_item.get("local_status", "")
        if local_status in ("Faltante", "Missing", "missing", "faltante"):
            errors.append("El ítem no está disponible localmente.")

        path = library_item.get("path")
        if not path:
            errors.append("El ítem no tiene ruta de archivo registrada.")
        elif not safe_stat(path)["exists"]:
            warnings.append(f"La ruta no existe actualmente en disco: {path}")

        if not library_item.get("tmdb_id"):
            warnings.append("No hay TMDb ID asociado. Se recomienda para la subida.")

        # Same fallback as the runtime layer: when the setting is unset, use the
        # bundled path (/opt/Uploadrr in the Docker image). Only fail when it's
        # genuinely absent, not merely "not explicitly configured".
        uploadrr_path = get_setting_canonical(conn, "uploadrr.path") or DEFAULT_UPLOADRR_PATH
        if not uploadrr_path:
            errors.append("Ruta de Uploadrr no configurada (uploadrr.path).")
        elif not os.path.exists(uploadrr_path):
            errors.append(f"Ruta de Uploadrr no existe: {uploadrr_path}")
        else:
            runtime_type = get_setting_canonical(conn, "uploadrr.runtime_type") or RUNTIME_EMU
            if runtime_type == RUNTIME_EMU:
                config_path = default_uploadrr_config_path(uploadrr_path)
                if not config_path.exists():
                    warnings.append(
                        f"config.yaml de Uploadrr-EMU no encontrado en {config_path}; "
                        "no se podrán stagear credenciales antes de ejecutar."
                    )

        emu_key = get_setting_canonical(conn, "emu.api_key")
        if not emu_key:
            errors.append("API key de eMuwarez no configurada.")

        tmdb_key = get_setting_canonical(conn, "tmdb.api_key")
        if not tmdb_key:
            errors.append("API key de TMDb no configurada.")

        if proposal and proposal.get("status") == "blocked":
            errors.append("Hay errores en la propuesta de nomenclatura que bloquean la subida.")

        if not library_item.get("prepared_path"):
            warnings.append(
                "Nomenclatura no aplicada: se usaría el archivo original. "
                "Considera aplicar la nomenclatura antes de subir."
            )

        return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}
    finally:
        if own:
            conn.close()


def build_uploadrr_command_preview(
    library_item: dict,
    proposal: dict | None = None,
    request_item: dict | None = None,
    conn=None,
) -> dict:
    """Build a preview of what the Uploadrr command would look like. NEVER executes it.

    For runtime_type=uploadrr_emu (the default), builds the real Uploadrr-EMU
    argv (-tk/-mt/-tmdb/-ua/-c/-res) via uploadrr_contract.py and validates it
    against the contract (allowed_roots, python_path, script path). The
    result always has can_execute=False / safe_to_execute=False in this
    phase — real execution is Phase 10F.
    """
    own = conn is None
    conn = conn or connect()
    try:
        runtime = get_runtime_settings(conn)
        runtime_type = runtime["runtime_type"]

        # Uploadrr-EMU's -mt/--manual-title is NOT just a display label — its
        # own argparse help says "Override generated name", and UNIT3D.py
        # confirms it wins outright over anything Uploadrr-EMU would
        # otherwise generate (src/trackers/UNIT3D.py: "manual_name > edit_name
        # > meta['name']"). proposed_title is only the bare title ("Chappie"),
        # never meant to stand alone as the whole release name — using it
        # here made the torrent appear on eMuwarez literally named "Chappie"
        # instead of the full nomenclature. proposed_torrent_name is the complete
        # release name as eMuwarez shows it (spaces, accents); proposed_filename,
        # its dotted file form, only stands in for proposals saved before it existed.
        title = (
            (proposal or {}).get("proposed_torrent_name")
            or (proposal or {}).get("proposed_filename")
            or (proposal or {}).get("proposed_title")
            or library_item.get("title")
            or "Sin título"
        )
        media_type = library_item.get("item_type") or "movie"
        tmdb_id = library_item.get("tmdb_id")
        resolution = (proposal or {}).get("resolution") or library_item.get("resolution") or ""
        # Cuál de las dos rutas se lee: path_mapping.py::ruta_de_lectura.
        from .path_mapping import ruta_de_lectura
        active_path = ruta_de_lectura(library_item) or ""
        # Cuál de las dos ha salido, y no "hay prepared_path guardado": lo que
        # se informa es de dónde se está leyendo de verdad, que ya no es lo
        # mismo desde que una ruta preparada muerta cede el paso a la de la
        # biblioteca.
        has_prepared = bool(active_path) and active_path == library_item.get("prepared_path")
        # Un episodio de la biblioteca lo trae en season_number/episode_number; un pack, en season. Vale el
        # primero que venga, aunque sea 0 (especiales).
        prop = proposal or {}
        season = next(
            (v for v in (prop.get("season"), library_item.get("season"), library_item.get("season_number")) if v is not None),
            None,
        )
        episode = next(
            (v for v in (prop.get("episode"), library_item.get("episode"), library_item.get("episode_number")) if v is not None),
            None,
        )
        # El mismo formato que lleva el nombre del release (`-t` en Uploadrr-EMU).
        release_format = prop.get("source") or library_item.get("release_format") or library_item.get("source")

        category = "tv" if media_type in ("tv", "series", "anime", "season", "episode") else "movie"

        if runtime_type == RUNTIME_EMU:
            uploadrr_path = runtime["uploadrr_path"] or "/path/to/Uploadrr"
            script_path = str(Path(uploadrr_path) / "upload.py")
            python_path = runtime["python_path"] or "python"

            contract = validate_uploadrr_emu_contract(
                prepared_path=active_path,
                torrent_name=title,
                tmdb_id=tmdb_id,
                category=category,
                resolution=resolution,
                allowed_roots=runtime["allowed_roots"],
                python_path=runtime["python_path"],
                uploadrr_script_path=str(Path(runtime["uploadrr_path"]) / "upload.py") if runtime["uploadrr_path"] else "",
            )

            command_args = build_uploadrr_emu_command(
                python_path=python_path,
                uploadrr_script_path=script_path,
                prepared_path=active_path,
                torrent_name=title,
                tmdb_id=tmdb_id,
                category=category,
                resolution=resolution,
                season=season,
                episode=episode,
                release_format=release_format,
            )
            command_preview = render_command_preview(command_args)

            # Lo que lee la ejecución (build_uploadrr_execution_command): lo que falte aquí no llega a Uploadrr.
            return {
                "runtime_type": RUNTIME_EMU,
                "uploadrr_path": uploadrr_path,
                "tracker": "EMU",
                "category": category,
                "title": title,
                "tmdb_id": tmdb_id,
                "resolution": resolution,
                "season": season,
                "episode": episode,
                "release_format": release_format,
                "source_path": active_path,
                "using_prepared_path": has_prepared,
                "command_preview": command_preview,
                "command_args": command_args,
                "contract_valid": contract["valid"],
                "contract_errors": contract["errors"],
                "contract_warnings": contract["warnings"],
                "can_execute": False,
                "requires_confirmation": CONFIRMATION_TOKEN,
                "safe_to_execute": False,
                "note": "Esta es una previsualización. El comando NO ha sido ejecutado.",
            }

        # runtime_type == uploadrr_generic: best-effort legacy preview for
        # forks whose exact flag mapping is unknown. Not validated against a
        # real contract — kept only for forward compatibility.
        uploadrr_path = runtime["uploadrr_path"] or "/path/to/Uploadrr"
        tracker = "EMU"
        args = [
            f"python3 {uploadrr_path}/upload.py",
            f"--tracker {tracker}",
            f"--category {category}",
        ]
        if tmdb_id:
            args.append(f"--tmdb {tmdb_id}")
        if resolution:
            args.append(f"--resolution {resolution}")
        if active_path:
            args.append(f'--source "{active_path}"')
        if title:
            args.append(f'--title "{title}"')

        command_str = " \\\n  ".join(args)

        return {
            "runtime_type": RUNTIME_GENERIC,
            "uploadrr_path": uploadrr_path,
            "tracker": tracker,
            "category": category,
            "title": title,
            "tmdb_id": tmdb_id,
            "resolution": resolution,
            "source_path": active_path,
            "using_prepared_path": has_prepared,
            "command_preview": command_str,
            "command_args": args,
            "can_execute": False,
            "requires_confirmation": CONFIRMATION_TOKEN,
            "safe_to_execute": False,
            "note": "Esta es una previsualización. El comando NO ha sido ejecutado.",
        }
    finally:
        if own:
            conn.close()


def build_upload_preflight(item_id: int, *, request_id: int | None = None, conn=None) -> dict:
    own = conn is None
    conn = conn or connect()
    try:
        item = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        library_item = row_to_dict(item)

        if not library_item:
            return {
                "status": JOB_STATUS_BLOCKED,
                "errors": ["Item no encontrado."],
                "warnings": [],
                "preflight": {},
                "command_preview": {},
                "job": None,
            }

        proposal_row = conn.execute(
            "SELECT * FROM nomenclature_proposals "
            "WHERE library_item_id = ? AND status != 'expired' "
            "ORDER BY created_at DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        proposal = row_to_dict(proposal_row)

        request_item = None
        if request_id:
            req_row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
            request_item = row_to_dict(req_row)

        preconditions = validate_upload_preconditions(library_item, proposal=proposal, conn=conn)
        command_preview = build_uploadrr_command_preview(library_item, proposal, request_item, conn=conn)

        status = JOB_STATUS_READY if preconditions["ok"] else JOB_STATUS_BLOCKED

        preflight_data = {
            "item_id": item_id,
            "title": library_item.get("title"),
            "local_status": library_item.get("local_status"),
            "path": library_item.get("path"),
            "tmdb_id": library_item.get("tmdb_id"),
            "has_nomenclature_proposal": proposal is not None,
            "nomenclature_status": proposal.get("status") if proposal else None,
        }

        job = save_upload_job_preflight(
            {
                "library_item_id": item_id,
                "request_item_id": request_id,
                "status": status,
                "stage": "preflight",
                "title": library_item.get("title") or "Sin título",
                "source_path": library_item.get("path"),
                "uploadrr_command_json": json.dumps(command_preview, ensure_ascii=False),
                "preflight_json": json.dumps(preflight_data, ensure_ascii=False),
                "error_message": "; ".join(preconditions["errors"]) if preconditions["errors"] else None,
            },
            conn=conn,
        )

        return {
            "status": status,
            "job": job,
            "preflight": preflight_data,
            "command_preview": command_preview,
            "warnings": preconditions["warnings"],
            "errors": preconditions["errors"],
        }
    finally:
        if own:
            conn.close()


def save_upload_job_preflight(data: dict, conn=None) -> dict:
    own = conn is None
    conn = conn or connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        # path is NOT NULL in original schema; use source_path or empty string
        path_value = data.get("source_path") or data.get("path") or ""
        cursor = conn.execute(
            """
            INSERT INTO upload_jobs (
                library_item_id, request_item_id, status, stage, title,
                path, source_path, uploadrr_command_json, preflight_json, error_message,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("library_item_id"),
                data.get("request_item_id"),
                data.get("status", JOB_STATUS_PREFLIGHT),
                data.get("stage", "preflight"),
                data.get("title") or "Sin título",
                path_value,
                data.get("source_path"),
                data.get("uploadrr_command_json"),
                data.get("preflight_json"),
                data.get("error_message"),
                now, now,
            ),
        )
        conn.commit()
        data["id"] = cursor.lastrowid
        data["created_at"] = now
        data["updated_at"] = now
        return data
    finally:
        if own:
            conn.close()


def get_upload_job(job_id: int, conn=None) -> dict | None:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
        return row_to_dict(row)
    finally:
        if own:
            conn.close()


def list_upload_jobs(filters: dict | None = None, conn=None) -> list[dict]:
    own = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute(
            "SELECT * FROM upload_jobs ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        if own:
            conn.close()
