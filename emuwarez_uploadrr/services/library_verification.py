"""Filesystem verification for library items.

SAFETY CONTRACT: Read-only. Never modifies, moves, renames, or deletes files.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..services.filesystem_safety import safe_stat, VIDEO_EXTENSIONS
from .path_mapping import get_path_mappings

# Los ficheros que mira una petición como mucho: cada uno es un stat al disco, y con el NAS dormido son segundos.
MAX_VERIFICACION = 2000


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inspeccionar(
    item_id: int, title: Optional[str], path: Optional[str], mappings: Optional[list] = None,
) -> dict[str, Any]:
    """Mira el fichero en disco y devuelve el resultado, sin tocar la base."""
    result: dict[str, Any] = {
        "item_id": item_id,
        "title": title,
        "path": path,
        "file_exists": False,
        "file_is_video": False,
        "file_size_on_disk": None,
        "file_verification_error": None,
        "verified_at": _now_utc(),
    }

    if not path:
        result["file_verification_error"] = "path nulo en BD"
        return result

    try:
        stat = safe_stat(path, mappings)
        # file_exists=True only when path exists AND is a regular file
        result["file_exists"] = stat["exists"] and stat["is_file"]
        result["file_is_video"] = stat["is_video"]
        result["file_size_on_disk"] = stat["size_bytes"]

        if not stat["exists"]:
            result["file_verification_error"] = "archivo no encontrado en disco"
        elif stat["is_dir"]:
            result["file_verification_error"] = "la ruta apunta a un directorio, no a un archivo"
        elif not stat["is_file"]:
            result["file_verification_error"] = "la ruta existe pero no es un archivo regular"
        elif stat["extension"] and stat["extension"] not in VIDEO_EXTENSIONS:
            result["file_verification_error"] = f"extensión no reconocida como vídeo: {stat['extension']}"
    except Exception as exc:
        result["file_verification_error"] = f"error al inspeccionar: {exc}"

    return result


def verify_library_item_file(item_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    """Verify filesystem state for a single library item. Returns result dict."""
    row = conn.execute(
        "SELECT id, title, path, local_status FROM library_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "error": f"Item {item_id} no encontrado", "item_id": item_id}

    result = _inspeccionar(item_id, row["title"], row["path"])
    update_library_item_file_status(item_id, result, conn)
    return result


_SQL_ESTADO_DEL_FICHERO = """
    UPDATE library_items SET
        file_exists = ?,
        file_is_video = ?,
        file_size_on_disk = ?,
        file_verified_at = ?,
        file_verification_error = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
"""


def _valores_del_estado(item_id: int, result: dict[str, Any]) -> tuple:
    return (
        1 if result.get("file_exists") else 0,
        1 if result.get("file_is_video") else 0,
        result.get("file_size_on_disk"),
        result.get("verified_at"),
        result.get("file_verification_error"),
        item_id,
    )


def update_library_item_file_status(
    item_id: int, result: dict[str, Any], conn: sqlite3.Connection
) -> None:
    """Persist filesystem verification result to library_items."""
    conn.execute(_SQL_ESTADO_DEL_FICHERO, _valores_del_estado(item_id, result))
    conn.commit()


def verify_library_files(
    conn: sqlite3.Connection,
    filters: Optional[dict] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Verify filesystem for multiple library items. Returns summary counts.

    Primero se mira el disco sin tocar la base y al final se guarda todo de una
    vez: el bloqueo de escritura dura milisegundos y no lo que tarde el disco.
    Con `limit` se miran antes los que hace más que no se comprueban."""
    filters = filters or {}
    where_clauses = []
    params: list[Any] = []

    status_filter = filters.get("status")
    if status_filter:
        where_clauses.append("local_status = ?")
        params.append(status_filter)

    sql = "SELECT id, title, path FROM library_items"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY file_verified_at IS NOT NULL, file_verified_at, id"
    if limit:
        sql += f" LIMIT {int(limit)}"

    rows = conn.execute(sql, params).fetchall()
    mappings = get_path_mappings(conn)

    checked = 0
    updated = 0
    errors = 0
    warnings = 0
    por_guardar = []

    for row in rows:
        r = _inspeccionar(row["id"], row["title"], row["path"], mappings)
        por_guardar.append(_valores_del_estado(row["id"], r))
        checked += 1
        if r.get("file_exists"):
            updated += 1
        elif r.get("file_verification_error"):
            if "no encontrado" in (r.get("file_verification_error") or ""):
                errors += 1
            else:
                warnings += 1

    conn.executemany(_SQL_ESTADO_DEL_FICHERO, por_guardar)
    conn.commit()

    return {
        "ok": True,
        "items_checked": checked,
        "files_found": updated,
        "errors": errors,
        "warnings": warnings,
    }
