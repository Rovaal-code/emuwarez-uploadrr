"""Recommendation engine for library items.

Builds recommended_action and diagnostic_status based on local_status,
file_exists, arr_queue_status, nomenclature_status and request_status.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..models import LocalStatus, NomenclatureStatus, RequestStatus


_QUEUE_STATUSES_IN_PROGRESS = {"downloading", "queued", "pending_import"}
_QUEUE_STATUSES_ERROR = {"import_error"}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_item(row) -> dict:
    return dict(row)


def build_recommendation_for_item(item_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute and persist recommendation for a single library item."""
    row = conn.execute(
        """
        SELECT id, title, item_type, local_status, file_exists, nomenclature_status,
               request_status, prepared_path, arr_queue_status, arr_history_status,
               arr_history_event_type, arr_history_error, arr_queue_error,
               arr_queue_progress, diagnostic_status
        FROM library_items WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "error": f"Item {item_id} no encontrado"}

    item = _row_to_item(row)
    if item.get("item_type") in ("series", "season"):
        # Rollup rows have no file of their own — file_exists/nomenclature/
        # preflight diagnostics only make sense for the movie/episode rows
        # underneath them. Still persisted (not just returned) so a stale
        # diagnostic from before this row became a rollup never lingers.
        action = "none"
        reasons = ["rollup row (series/season) — sin diagnóstico propio"]
        diag_status = "not_applicable"
        diag_summary = "N/A (agregado de serie/temporada)"
    else:
        action, reasons, diag_status, diag_summary = _compute_recommendation(item)

    conn.execute(
        """
        UPDATE library_items SET
            recommended_action = ?,
            recommendation_reasons_json = ?,
            diagnostic_status = ?,
            diagnostic_summary = ?,
            recommendation_updated_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            action,
            json.dumps(reasons, ensure_ascii=False),
            diag_status,
            diag_summary,
            _now_utc(),
            item_id,
        ),
    )
    conn.commit()

    return {
        "ok": True,
        "item_id": item_id,
        "title": item["title"],
        "recommended_action": action,
        "recommendation_reasons": reasons,
        "diagnostic_status": diag_status,
        "diagnostic_summary": diag_summary,
    }


def _compute_recommendation(item: dict) -> tuple[str, list[str], str, str]:
    """Core logic. Returns (action, reasons, diag_status, diag_summary)."""
    local_status = item.get("local_status") or ""
    file_exists = bool(item.get("file_exists"))
    nomenclature = item.get("nomenclature_status") or NomenclatureStatus.NA.value
    request_status = item.get("request_status") or RequestStatus.NONE.value
    prepared_path = item.get("prepared_path")
    queue_status = item.get("arr_queue_status") or ""
    history_status = item.get("arr_history_status") or ""
    history_event = item.get("arr_history_event_type") or ""
    history_error = item.get("arr_history_error")
    queue_error = item.get("arr_queue_error")

    reasons: list[str] = []

    is_available = local_status == LocalStatus.AVAILABLE.value
    is_missing = local_status == LocalStatus.MISSING.value
    in_queue = queue_status in _QUEUE_STATUSES_IN_PROGRESS
    has_queue_error = queue_status in _QUEUE_STATUSES_ERROR
    has_history_error = history_status == "error" or ("Fail" in history_event) or bool(history_error)
    request_compatible = request_status in (RequestStatus.COMPATIBLE.value, RequestStatus.PARTIAL.value)
    request_filled = request_status == RequestStatus.FILLED.value

    # --- Downloading / in progress ---
    if queue_status == "downloading":
        reasons.append("descargando en ARR")
        if item.get("arr_queue_progress"):
            reasons.append(f"progreso: {item['arr_queue_progress']}%")
        return "view_progress", reasons, "downloading", "Descarga en progreso"

    if queue_status == "queued":
        reasons.append("en cola de descarga ARR")
        return "wait_download", reasons, "queued", "En cola"

    if queue_status == "pending_import":
        reasons.append("pendiente de importación en ARR")
        return "review_arr", reasons, "pending_import", "Pendiente de importación"

    # --- Queue error ---
    if has_queue_error:
        reasons.append(f"error en cola ARR: {queue_error or queue_status}")
        return "review_arr", reasons, "import_error", "Error de importación en cola"

    # --- History error ---
    if has_history_error and not is_available:
        reasons.append(f"error en historial ARR: {history_error or history_event}")
        return "review_arr", reasons, "history_error", "Error en historial ARR"

    # --- Available ---
    if is_available:
        if not file_exists:
            reasons.append("Radarr/Sonarr dice disponible pero archivo no encontrado en disco")
            return "fix_path", reasons, "path_broken", "Path roto — archivo no en disco"

        if nomenclature == NomenclatureStatus.NOT_ADAPTED.value:
            reasons.append("archivo disponible, nomenclatura no adaptada")
            return "adapt_nomenclature", reasons, "ready_nomenclature", "Listo para adaptar nomenclatura"

        if nomenclature == NomenclatureStatus.CORRECT.value:
            if prepared_path:
                reasons.append("nomenclatura correcta y path preparado")
                return "upload", reasons, "ready_upload", "Listo para subir"
            reasons.append("nomenclatura correcta, sin preflight completado")
            return "run_preflight", reasons, "ready_preflight", "Listo para preflight"

        # nomenclature N/A (series level) — check request
        if request_compatible and file_exists:
            reasons.append("contenido disponible y petición compatible")
            return "check_emu", reasons, "ready_emu", "Disponible con petición compatible"

        reasons.append("archivo disponible")
        return "none", reasons, "available", "Disponible"

    # --- Missing ---
    if is_missing:
        if has_history_error:
            reasons.append("faltante y error en historial ARR")
            return "review_arr", reasons, "history_error", "Faltante con error historial"
        reasons.append("faltante sin cola activa")
        return "review_arr", reasons, "missing", "Faltante — revisar ARR"

    # --- Other statuses ---
    if local_status in (LocalStatus.UPLOADING.value, LocalStatus.UPLOADED.value):
        return "open_emu", [local_status], "uploading", local_status

    reasons.append(f"estado: {local_status}")
    return "none", reasons, "unknown", local_status or "desconocido"


def refresh_recommendations(
    conn: sqlite3.Connection,
    filters: Optional[dict] = None,
) -> dict[str, Any]:
    """Recalculate recommendations for multiple items."""
    filters = filters or {}
    # Series/season are organizational rollup rows with no file of their
    # own — always excluded, regardless of other filters.
    where_clauses = ["item_type IN ('movie', 'episode')"]
    params: list[Any] = []

    status_filter = filters.get("status")
    if status_filter:
        where_clauses.append("local_status = ?")
        params.append(status_filter)

    sql = "SELECT id FROM library_items"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY updated_at DESC"

    limit = filters.get("limit")
    if limit:
        sql += f" LIMIT {int(limit)}"

    rows = conn.execute(sql, params).fetchall()
    updated = 0
    errors = 0

    for row in rows:
        try:
            build_recommendation_for_item(row["id"], conn)
            updated += 1
        except Exception:
            errors += 1

    return {"ok": True, "items_updated": updated, "errors": errors}


def get_recommendation_for_item(
    item_id: int, conn: sqlite3.Connection
) -> Optional[dict[str, Any]]:
    """Return stored recommendation for an item."""
    row = conn.execute(
        """
        SELECT id, title, recommended_action, recommendation_reasons_json,
               diagnostic_status, diagnostic_summary, recommendation_updated_at
        FROM library_items WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    if not row:
        return None

    reasons = []
    try:
        reasons = json.loads(row["recommendation_reasons_json"] or "[]")
    except Exception:
        pass

    return {
        "item_id": row["id"],
        "title": row["title"],
        "recommended_action": row["recommended_action"],
        "recommendation_reasons": reasons,
        "diagnostic_status": row["diagnostic_status"],
        "diagnostic_summary": row["diagnostic_summary"],
        "recommendation_updated_at": row["recommendation_updated_at"],
    }
