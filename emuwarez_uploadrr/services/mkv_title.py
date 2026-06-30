"""MKV internal title service (Phase 10A).

SAFETY CONTRACT:
- dry_run=True by default.
- apply_internal_title_update() requires confirmation="APLICAR_TITULO_MKV".
- Only operates on prepared_path/applied_path, never on source_path.
- Uses subprocess without shell=True.
- mkvpropedit is never called in tests (caller must mock subprocess).
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..database import connect

MKV_CONFIRMATION_TOKEN = "APLICAR_TITULO_MKV"
_MKV_EXTENSION = ".mkv"


def build_internal_mkv_title(torrent_name: str) -> str:
    """Replace spaces with dots to derive the internal MKV title."""
    if not torrent_name:
        return ""
    return torrent_name.replace(" ", ".")


def check_mkvpropedit_available() -> dict:
    """Check whether mkvpropedit is installed and callable."""
    path = shutil.which("mkvpropedit")
    if path:
        return {"available": True, "path": path}
    return {"available": False, "path": None, "message": "mkvpropedit no encontrado en PATH"}


def _get_prepared_path(library_item_id: int, conn) -> str | None:
    """Return prepared_path or applied_path from the latest nomenclature proposal."""
    row = conn.execute(
        "SELECT prepared_path FROM library_items WHERE id = ?",
        (library_item_id,),
    ).fetchone()
    if row and row["prepared_path"]:
        return row["prepared_path"]
    row2 = conn.execute(
        """SELECT applied_path FROM nomenclature_proposals
           WHERE library_item_id = ? AND status != 'expired'
           ORDER BY created_at DESC LIMIT 1""",
        (library_item_id,),
    ).fetchone()
    if row2 and row2["applied_path"]:
        return row2["applied_path"]
    return None


def _get_torrent_name_for_item(library_item_id: int, conn) -> str | None:
    """Return the latest proposed_filename for the item."""
    row = conn.execute(
        """SELECT proposed_filename FROM nomenclature_proposals
           WHERE library_item_id = ? AND status != 'expired'
           ORDER BY created_at DESC LIMIT 1""",
        (library_item_id,),
    ).fetchone()
    if row and row["proposed_filename"]:
        return row["proposed_filename"]
    row2 = conn.execute(
        """SELECT fields_json FROM nomenclature_proposals
           WHERE library_item_id = ? AND status != 'expired'
           ORDER BY created_at DESC LIMIT 1""",
        (library_item_id,),
    ).fetchone()
    if row2 and row2["fields_json"]:
        try:
            import json
            fields = json.loads(row2["fields_json"])
            return fields.get("torrent_name")
        except Exception:
            pass
    return None


def preview_internal_title_update(library_item_id: int, conn=None) -> dict:
    """Return a dry-run preview of the MKV title update. Never modifies anything."""
    own = conn is None
    conn = conn or connect()
    try:
        mkv_check = check_mkvpropedit_available()

        prepared_path = _get_prepared_path(library_item_id, conn)
        if not prepared_path:
            return {
                "status": "blocked",
                "library_item_id": library_item_id,
                "prepared_path": None,
                "internal_mkv_title": None,
                "mkvpropedit_available": mkv_check.get("available", False),
                "errors": ["No hay prepared_path disponible. Aplica la nomenclatura primero."],
                "warnings": [],
            }

        p = Path(prepared_path)
        if p.suffix.lower() != _MKV_EXTENSION:
            return {
                "status": "blocked",
                "library_item_id": library_item_id,
                "prepared_path": prepared_path,
                "internal_mkv_title": None,
                "mkvpropedit_available": mkv_check.get("available", False),
                "errors": [f"El archivo no es .mkv: {p.suffix}"],
                "warnings": [],
            }

        torrent_name = _get_torrent_name_for_item(library_item_id, conn)
        internal_title = build_internal_mkv_title(torrent_name or p.stem)

        warnings: list[str] = []
        if not mkv_check.get("available"):
            warnings.append("mkvpropedit no está instalado. Instala mkvtoolnix para aplicar el título interno.")
        if not p.exists():
            warnings.append(f"El archivo preparado no existe todavía en disco: {prepared_path}")

        cmd_preview = [
            "mkvpropedit",
            prepared_path,
            "--edit", "info",
            "--set", f"title={internal_title}",
        ]

        return {
            "status": "ready" if not warnings else "warning",
            "library_item_id": library_item_id,
            "prepared_path": prepared_path,
            "torrent_name": torrent_name,
            "internal_mkv_title": internal_title,
            "mkvpropedit_available": mkv_check.get("available", False),
            "mkvpropedit_path": mkv_check.get("path"),
            "command_preview": " ".join(f'"{a}"' if " " in a else a for a in cmd_preview),
            "errors": [],
            "warnings": warnings,
        }
    finally:
        if own:
            conn.close()


def apply_internal_title_update(
    library_item_id: int,
    *,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
    conn=None,
) -> dict:
    """Apply or preview the MKV internal title update.

    Real execution requires:
      dry_run=False, apply=True, confirmation='APLICAR_TITULO_MKV'
    """
    own = conn is None
    conn = conn or connect()
    try:
        preview = preview_internal_title_update(library_item_id, conn=conn)

        if preview["status"] == "blocked":
            return {**preview, "dry_run": True, "apply": False}

        if dry_run or not apply:
            return {**preview, "dry_run": True, "apply": False}

        if confirmation != MKV_CONFIRMATION_TOKEN:
            return {
                **preview,
                "status": "blocked",
                "dry_run": dry_run,
                "apply": False,
                "errors": preview.get("errors", []) + [
                    f"Para aplicar el título MKV debes confirmar escribiendo: {MKV_CONFIRMATION_TOKEN}"
                ],
            }

        mkv_check = check_mkvpropedit_available()
        if not mkv_check.get("available"):
            return {
                **preview,
                "status": "blocked",
                "dry_run": False,
                "apply": False,
                "errors": ["mkvpropedit no disponible en el sistema."],
            }

        prepared_path = preview["prepared_path"]
        internal_title = preview["internal_mkv_title"]

        if not Path(prepared_path).exists():
            return {
                **preview,
                "status": "blocked",
                "dry_run": False,
                "apply": False,
                "errors": [f"El archivo no existe: {prepared_path}"],
            }

        cmd = [
            "mkvpropedit",
            prepared_path,
            "--edit", "info",
            "--set", f"title={internal_title}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                shell=False,
            )
        except FileNotFoundError:
            return {
                **preview,
                "status": "error",
                "dry_run": False,
                "apply": True,
                "errors": ["mkvpropedit no encontrado al ejecutar."],
            }
        except subprocess.TimeoutExpired:
            return {
                **preview,
                "status": "error",
                "dry_run": False,
                "apply": True,
                "errors": ["mkvpropedit agotó el timeout de 60s."],
            }

        now = datetime.now(timezone.utc).isoformat()
        status_val = "applied" if result.returncode == 0 else "error"
        error_msg = result.stderr.strip() if result.returncode != 0 else None

        try:
            conn.execute(
                """UPDATE nomenclature_proposals
                   SET internal_mkv_title = ?,
                       internal_title_status = ?,
                       internal_title_applied_at = ?,
                       internal_title_error = ?,
                       updated_at = ?
                   WHERE library_item_id = ? AND id = (
                       SELECT id FROM nomenclature_proposals
                       WHERE library_item_id = ? AND status != 'expired'
                       ORDER BY created_at DESC LIMIT 1
                   )""",
                (internal_title, status_val, now if status_val == "applied" else None,
                 error_msg, now, library_item_id, library_item_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            **preview,
            "status": status_val,
            "dry_run": False,
            "apply": True,
            "applied_at": now if status_val == "applied" else None,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip()[:500] if result.stdout else None,
            "error_message": error_msg,
            "errors": [error_msg] if error_msg else [],
        }
    finally:
        if own:
            conn.close()
