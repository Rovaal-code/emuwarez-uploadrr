"""Filesystem verification for library items.

SAFETY CONTRACT: Read-only. Never modifies, moves, renames, or deletes files.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..services.filesystem_safety import safe_stat, VIDEO_EXTENSIONS


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_library_item_file(item_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    """Verify filesystem state for a single library item. Returns result dict."""
    row = conn.execute(
        "SELECT id, title, path, local_status FROM library_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "error": f"Item {item_id} no encontrado", "item_id": item_id}

    path = row["path"]
    result: dict[str, Any] = {
        "item_id": item_id,
        "title": row["title"],
        "path": path,
        "file_exists": False,
        "file_is_video": False,
        "file_size_on_disk": None,
        "file_verification_error": None,
        "verified_at": _now_utc(),
    }

    if not path:
        result["file_verification_error"] = "path nulo en BD"
        update_library_item_file_status(item_id, result, conn)
        return result

    try:
        stat = safe_stat(path)
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

    update_library_item_file_status(item_id, result, conn)
    return result


def update_library_item_file_status(
    item_id: int, result: dict[str, Any], conn: sqlite3.Connection
) -> None:
    """Persist filesystem verification result to library_items."""
    conn.execute(
        """
        UPDATE library_items SET
            file_exists = ?,
            file_is_video = ?,
            file_size_on_disk = ?,
            file_verified_at = ?,
            file_verification_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            1 if result.get("file_exists") else 0,
            1 if result.get("file_is_video") else 0,
            result.get("file_size_on_disk"),
            result.get("verified_at"),
            result.get("file_verification_error"),
            item_id,
        ),
    )
    conn.commit()


def verify_library_files(
    conn: sqlite3.Connection,
    filters: Optional[dict] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Verify filesystem for multiple library items. Returns summary."""
    filters = filters or {}
    where_clauses = []
    params: list[Any] = []

    status_filter = filters.get("status")
    if status_filter:
        where_clauses.append("local_status = ?")
        params.append(status_filter)

    sql = "SELECT id FROM library_items"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY updated_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"

    rows = conn.execute(sql, params).fetchall()
    item_ids = [r["id"] for r in rows]

    checked = 0
    updated = 0
    errors = 0
    warnings = 0
    results = []

    for item_id in item_ids:
        r = verify_library_item_file(item_id, conn)
        checked += 1
        if r.get("file_exists"):
            updated += 1
        elif r.get("file_verification_error"):
            if "no encontrado" in (r.get("file_verification_error") or ""):
                errors += 1
            else:
                warnings += 1
        results.append(r)

    return {
        "ok": True,
        "items_checked": checked,
        "files_found": updated,
        "errors": errors,
        "warnings": warnings,
        "results": results,
    }
