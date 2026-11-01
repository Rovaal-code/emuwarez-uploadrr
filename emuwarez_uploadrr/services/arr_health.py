"""ARR health monitoring — reads queue and history from Radarr/Sonarr.

SAFETY CONTRACT: Read-only. Never modifies Radarr/Sonarr data, never
initiates searches, never triggers imports or metadata refreshes.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..integrations.radarr import (
    radarr_get_queue,
    radarr_get_history,
    radarr_get_system_status,
    radarr_test_connection,
)
from ..integrations.sonarr import (
    sonarr_get_queue,
    sonarr_get_history,
    sonarr_get_system_status,
    sonarr_test_connection,
)
from .instances import list_instances


_QUEUE_STATUS_MAP = {
    "queued": "queued",
    "delay": "queued",
    "paused": "queued",
    "downloading": "downloading",
    "importpending": "pending_import",
    "completed": "pending_import",
    "failed": "import_error",
    "downloadclientunavailable": "import_error",
    "warning": "import_error",
    "fallback": "queued",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _queue_status(status_raw: str, status_messages: list | None = None) -> str:
    base = _QUEUE_STATUS_MAP.get((status_raw or "").lower(), "queued")
    if status_messages:
        for msg in status_messages:
            texts = [msg] if isinstance(msg, str) else (msg.get("messages") or [])
            for t in texts:
                if "error" in str(t).lower() or "import" in str(t).lower():
                    base = "import_error"
                    break
    return base


def _instance_dict(inst) -> dict:
    return {"url": inst.url, "api_key": inst.api_key, "name": inst.name}


def _limpiar_cola(conn: sqlite3.Connection, instance_id: int) -> None:
    """La cola de la instancia es lo que Radarr/Sonarr dicen ahora: lo que ya no está en ella deja de figurar."""
    conn.execute(
        "UPDATE library_items SET arr_queue_status = NULL, arr_queue_title = NULL, arr_queue_progress = NULL, "
        "arr_queue_timeleft = NULL, arr_queue_error = NULL "
        "WHERE instance_id = ? AND arr_queue_status IS NOT NULL",
        (instance_id,),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_arr_health(conn: sqlite3.Connection) -> dict[str, Any]:
    """Collect health summary from all enabled instances."""
    instances = list_instances(conn, enabled_only=True)
    instance_results = []
    summary = {"radarr": 0, "sonarr": 0, "ok": 0, "warning": 0, "error": 0}

    for inst in instances:
        result = collect_instance_health(inst.id, conn)
        instance_results.append(result)
        summary[inst.type] = summary.get(inst.type, 0) + 1
        summary[result.get("health_status", "error")] = summary.get(result.get("health_status", "error"), 0) + 1

    return {"instances": instance_results, "summary": summary, "checked_at": _now_utc()}


def collect_instance_health(instance_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    """Collect health for a single instance (connection test + system status)."""
    row = conn.execute(
        "SELECT id, type, name, url, api_key, enabled FROM instances WHERE id = ?",
        (instance_id,),
    ).fetchone()
    if not row:
        return {"instance_id": instance_id, "ok": False, "error": "instancia no encontrada", "health_status": "error"}

    inst_dict = {"url": row["url"], "api_key": row["api_key"], "name": row["name"]}
    inst_type = row["type"]

    result: dict[str, Any] = {
        "instance_id": instance_id,
        "instance_type": inst_type,
        "instance_name": row["name"],
        "url": row["url"],
        "enabled": bool(row["enabled"]),
        "checked_at": _now_utc(),
    }

    try:
        if inst_type == "radarr":
            test = radarr_test_connection(inst_dict)
            if test.get("ok"):
                status_data = radarr_get_system_status(inst_dict)
                result["version"] = status_data.get("version")
                result["app_name"] = status_data.get("appName", "Radarr")
                result["health_status"] = "ok"
                result["ok"] = True
            else:
                result["ok"] = False
                result["error"] = test.get("error", "conexión fallida")
                result["health_status"] = "error"
        elif inst_type == "sonarr":
            test = sonarr_test_connection(inst_dict)
            if test.get("ok"):
                status_data = sonarr_get_system_status(inst_dict)
                result["version"] = status_data.get("version")
                result["app_name"] = status_data.get("appName", "Sonarr")
                result["health_status"] = "ok"
                result["ok"] = True
            else:
                result["ok"] = False
                result["error"] = test.get("error", "conexión fallida")
                result["health_status"] = "error"
        else:
            result["ok"] = False
            result["error"] = f"tipo desconocido: {inst_type}"
            result["health_status"] = "error"
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        result["health_status"] = "error"

    return result


def refresh_arr_queue_diagnostics(
    conn: sqlite3.Connection,
    instance_id: Optional[int] = None,
) -> dict[str, Any]:
    """Read queue from ARR instances and update library_items with queue status."""
    instances = list_instances(conn, enabled_only=True)
    if instance_id is not None:
        instances = [i for i in instances if i.id == instance_id]

    updated = 0
    errors = []
    queue_items_total = 0

    for inst in instances:
        inst_dict = _instance_dict(inst)
        try:
            if inst.type == "radarr":
                queue = radarr_get_queue(inst_dict)
                _limpiar_cola(conn, inst.id)
                mapped = _map_radarr_queue(queue, inst.id, conn)
                updated += mapped
                queue_items_total += len(queue)
            elif inst.type == "sonarr":
                queue = sonarr_get_queue(inst_dict)
                _limpiar_cola(conn, inst.id)
                mapped = _map_sonarr_queue(queue, inst.id, conn)
                updated += mapped
                queue_items_total += len(queue)
        except Exception as exc:
            errors.append({"instance": inst.name, "error": str(exc)})

    conn.commit()
    return {
        "ok": not errors,
        "instances_checked": len(instances),
        "queue_items_found": queue_items_total,
        "library_items_updated": updated,
        "errors": errors,
    }


def refresh_arr_history_diagnostics(
    conn: sqlite3.Connection,
    instance_id: Optional[int] = None,
    page_size: int = 100,
) -> dict[str, Any]:
    """Read history from ARR instances and update library_items with history status."""
    instances = list_instances(conn, enabled_only=True)
    if instance_id is not None:
        instances = [i for i in instances if i.id == instance_id]

    updated = 0
    errors = []
    history_total = 0

    for inst in instances:
        inst_dict = _instance_dict(inst)
        try:
            if inst.type == "radarr":
                history = radarr_get_history(inst_dict, page_size=page_size)
                mapped = _map_radarr_history(history, inst.id, conn)
                updated += mapped
                history_total += len(history)
            elif inst.type == "sonarr":
                history = sonarr_get_history(inst_dict, page_size=page_size)
                mapped = _map_sonarr_history(history, inst.id, conn)
                updated += mapped
                history_total += len(history)
        except Exception as exc:
            errors.append({"instance": inst.name, "error": str(exc)})

    conn.commit()
    return {
        "ok": not errors,
        "instances_checked": len(instances),
        "history_items_found": history_total,
        "library_items_updated": updated,
        "errors": errors,
    }


def map_queue_to_library_items(queue_items: list[dict], instance_id: int, conn: sqlite3.Connection) -> dict:
    """Map queue items to library item IDs. Returns mapping result."""
    radarr_mapped = _map_radarr_queue(queue_items, instance_id, conn)
    return {"mapped": radarr_mapped}


def map_history_to_library_items(history_items: list[dict], instance_id: int, conn: sqlite3.Connection) -> dict:
    """Map history items to library item IDs. Returns mapping result."""
    radarr_mapped = _map_radarr_history(history_items, instance_id, conn)
    return {"mapped": radarr_mapped}


# ---------------------------------------------------------------------------
# Internal mapping helpers
# ---------------------------------------------------------------------------

def _map_radarr_queue(queue: list[dict], instance_id: int, conn: sqlite3.Connection) -> int:
    updated = 0
    for rec in queue:
        movie_id = rec.get("movieId")
        if not movie_id:
            continue
        # Find library item by external_id (movie id from Radarr)
        row = conn.execute(
            "SELECT id FROM library_items WHERE instance_id = ? AND item_type = 'movie' AND external_id = ?",
            (instance_id, str(movie_id)),
        ).fetchone()
        if not row:
            continue

        q_status_raw = rec.get("status") or ""
        status_msgs = rec.get("statusMessages") or []
        q_status = _queue_status(q_status_raw, status_msgs)
        progress = rec.get("sizeleft") and rec.get("size") and (
            round((1 - rec["sizeleft"] / rec["size"]) * 100, 1) if rec["size"] > 0 else 0.0
        )
        timeleft = rec.get("timeleft")
        error_msg = "; ".join(
            m for msg in status_msgs
            for m in ([msg] if isinstance(msg, str) else msg.get("messages", []))
        ) or None

        conn.execute(
            """
            UPDATE library_items SET
                arr_queue_status = ?,
                arr_queue_title = ?,
                arr_queue_progress = ?,
                arr_queue_timeleft = ?,
                arr_queue_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                q_status,
                rec.get("title"),
                progress,
                timeleft,
                error_msg,
                row["id"],
            ),
        )
        updated += 1
    return updated


def _map_sonarr_queue(queue: list[dict], instance_id: int, conn: sqlite3.Connection) -> int:
    updated = 0
    for rec in queue:
        series_id = rec.get("seriesId")
        if not series_id:
            continue
        rows = conn.execute(
            "SELECT id FROM library_items WHERE instance_id = ? AND instance_type = 'sonarr' AND external_id = ?",
            (instance_id, str(series_id)),
        ).fetchall()
        if not rows:
            continue

        q_status = _queue_status(rec.get("status") or "")
        for row in rows:
            conn.execute(
                """
                UPDATE library_items SET
                    arr_queue_status = ?,
                    arr_queue_title = ?,
                    arr_queue_progress = ?,
                    arr_queue_timeleft = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    q_status,
                    rec.get("title"),
                    None,
                    rec.get("timeleft"),
                    row["id"],
                ),
            )
            updated += 1
    return updated


def _map_radarr_history(history: list[dict], instance_id: int, conn: sqlite3.Connection) -> int:
    updated = 0
    for rec in history:
        movie_id = rec.get("movieId")
        if not movie_id:
            continue
        row = conn.execute(
            "SELECT id FROM library_items WHERE instance_id = ? AND item_type = 'movie' AND external_id = ?",
            (instance_id, str(movie_id)),
        ).fetchone()
        if not row:
            continue

        event_type = rec.get("eventType") or ""
        error_msg = None
        if "Fail" in event_type or "Error" in event_type or rec.get("data", {}).get("importFailed"):
            error_msg = rec.get("data", {}).get("message") or event_type

        conn.execute(
            """
            UPDATE library_items SET
                arr_history_status = ?,
                arr_history_event_type = ?,
                arr_history_error = ?,
                arr_history_source_title = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                "error" if error_msg else "ok",
                event_type,
                error_msg,
                rec.get("sourceTitle"),
                row["id"],
            ),
        )
        updated += 1
    return updated


def _map_sonarr_history(history: list[dict], instance_id: int, conn: sqlite3.Connection) -> int:
    updated = 0
    for rec in history:
        series_id = rec.get("seriesId")
        if not series_id:
            continue
        rows = conn.execute(
            "SELECT id FROM library_items WHERE instance_id = ? AND instance_type = 'sonarr' AND external_id = ?",
            (instance_id, str(series_id)),
        ).fetchall()

        event_type = rec.get("eventType") or ""
        error_msg = None
        if "Fail" in event_type or "Error" in event_type:
            error_msg = rec.get("data", {}).get("message") or event_type

        for row in rows:
            conn.execute(
                """
                UPDATE library_items SET
                    arr_history_status = ?,
                    arr_history_event_type = ?,
                    arr_history_error = ?,
                    arr_history_source_title = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    "error" if error_msg else "ok",
                    event_type,
                    error_msg,
                    rec.get("sourceTitle"),
                    row["id"],
                ),
            )
            updated += 1
    return updated
