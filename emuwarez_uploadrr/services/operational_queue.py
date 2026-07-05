"""Phase 8C — Unified operational queue.

Aggregates items from:
  - request_readiness (Phase 8B)
  - library recommendations (Phase 8A)
  - upload jobs (Phase 6D)
  - ARR diagnostics (Phase 8A)

The queue is READ-ONLY with respect to:
  - eMuwarez
  - Radarr / Sonarr
  - filesystem
  - Uploadrr

Only writes to local tables: operational_queue_items, operational_queue_runs.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(s: Any) -> Any:
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Status/action mapping helpers
# ---------------------------------------------------------------------------

_READINESS_STATUS_TO_ACTION = {
    "ready_to_upload":   "upload",
    "needs_nomenclature": "adapt_nomenclature",
    "preflight_needed":  "run_preflight",
    "downloading":       "wait_download",
    "uploading":         "view_upload",
    "pending_import":    "review_arr",
    "import_error":      "review_arr",
    "file_missing":      "verify_file",
    "already_exists":    "check_emu",
    "upload_error":      "retry_upload",
    "uploaded":          "view_upload",
    "no_local_match":    "review_arr",
}

_READINESS_STATUS_TO_STATUS = {
    "ready_to_upload":   "ready",
    "needs_nomenclature": "ready",
    "preflight_needed":  "ready",
    "downloading":       "waiting",
    "uploading":         "running",
    "pending_import":    "blocked",
    "import_error":      "blocked",
    "file_missing":      "blocked",
    "already_exists":    "blocked",
    "upload_error":      "blocked",
    "uploaded":          "blocked",
    "no_local_match":    "open",
}

_REC_ACTION_TO_STATUS = {
    "upload":             "ready",
    "adapt_nomenclature": "ready",
    "run_preflight":      "ready",
    "wait_download":      "waiting",
    "review_arr":         "blocked",
    "verify_file":        "blocked",
    "fix_path":           "blocked",
    "check_emu":          "open",
    "none":               "open",
}

_UPLOAD_STATUS_TO_ACTION = {
    "ready":     "upload",
    "running":   "view_upload",
    "failed":    "retry_upload",
    "cancelled": "retry_upload",
    "completed": "view_upload",
    "pending":   "upload",
}

_UPLOAD_STATUS_TO_QUEUE_STATUS = {
    "ready":     "ready",
    "running":   "running",
    "failed":    "blocked",
    "cancelled": "ready",
    "completed": "resolved",
    "pending":   "open",
}


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert_queue_item(item: dict, conn: sqlite3.Connection) -> dict:
    """Insert or update a queue item by queue_key."""
    now = _now_utc()
    existing = conn.execute(
        "SELECT id, resolved_at FROM operational_queue_items WHERE queue_key = ?",
        (item["queue_key"],),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE operational_queue_items SET
                item_type = ?, entity_type = ?, entity_id = ?,
                request_item_id = ?, library_item_id = ?, upload_job_id = ?,
                title = ?, subtitle = ?, status = ?, action = ?,
                blockers_json = ?, reasons_json = ?, context_json = ?,
                target_url = ?, updated_at = ?, last_seen_at = ?,
                resolved_at = NULL
            WHERE queue_key = ?
            """,
            (
                item.get("item_type", ""),
                item.get("entity_type", ""),
                item.get("entity_id"),
                item.get("request_item_id"),
                item.get("library_item_id"),
                item.get("upload_job_id"),
                item.get("title"),
                item.get("subtitle"),
                item.get("status", "open"),
                item.get("action", "none"),
                json.dumps(item.get("blockers") or [], ensure_ascii=False),
                json.dumps(item.get("reasons") or [], ensure_ascii=False),
                json.dumps(item.get("context") or {}, ensure_ascii=False),
                item.get("target_url"),
                now,
                now,
                item["queue_key"],
            ),
        )
        row = conn.execute(
            "SELECT * FROM operational_queue_items WHERE queue_key = ?",
            (item["queue_key"],),
        ).fetchone()
    else:
        conn.execute(
            """
            INSERT INTO operational_queue_items
            (queue_key, item_type, entity_type, entity_id,
             request_item_id, library_item_id, upload_job_id,
             title, subtitle, status, action,
             blockers_json, reasons_json, context_json,
             target_url, created_at, updated_at, last_seen_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                item["queue_key"],
                item.get("item_type", ""),
                item.get("entity_type", ""),
                item.get("entity_id"),
                item.get("request_item_id"),
                item.get("library_item_id"),
                item.get("upload_job_id"),
                item.get("title"),
                item.get("subtitle"),
                item.get("status", "open"),
                item.get("action", "none"),
                json.dumps(item.get("blockers") or [], ensure_ascii=False),
                json.dumps(item.get("reasons") or [], ensure_ascii=False),
                json.dumps(item.get("context") or {}, ensure_ascii=False),
                item.get("target_url"),
                now, now, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM operational_queue_items WHERE queue_key = ?",
            (item["queue_key"],),
        ).fetchone()

    return _row_to_item(dict(row))


def _row_to_item(row: dict) -> dict:
    row["blockers"] = _loads(row.get("blockers_json"))
    row["reasons"] = _loads(row.get("reasons_json"))
    row["context"] = _loads(row.get("context_json")) if isinstance(_loads(row.get("context_json")), dict) else {}
    return row


# ---------------------------------------------------------------------------
# Source builders
# ---------------------------------------------------------------------------

def build_items_from_request_readiness(
    limit: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """Build queue items from request_readiness table (Phase 8B data)."""
    if conn is None:
        return []
    q = """
        SELECT rr.id AS rr_id, rr.request_item_id, rr.status AS rr_status,
               rr.recommended_action,
               rr.blockers_json, rr.reasons_json,
               ri.title, ri.emu_id
        FROM request_readiness rr
        JOIN request_items ri ON ri.id = rr.request_item_id
        WHERE rr.status NOT IN ('uploaded', 'already_exists')
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()
    items = []
    for r in rows:
        rd = dict(r)
        rr_status = rd.get("rr_status", "no_local_match")
        action = _READINESS_STATUS_TO_ACTION.get(rr_status, "manual_review")
        status = _READINESS_STATUS_TO_STATUS.get(rr_status, "open")

        items.append({
            "queue_key": f"request:{rd['request_item_id']}:readiness",
            "item_type": "request_readiness",
            "entity_type": "request",
            "entity_id": rd["request_item_id"],
            "request_item_id": rd["request_item_id"],
            "library_item_id": None,
            "upload_job_id": None,
            "title": rd.get("title", ""),
            "subtitle": f"EMU: {rd.get('emu_id', '')}",
            "status": status,
            "action": action,
            "blockers": _loads(rd.get("blockers_json")),
            "reasons": _loads(rd.get("reasons_json")),
            "context": {"rr_status": rr_status, "emu_id": rd.get("emu_id")},
        })
    return items


def build_items_from_library_recommendations(
    limit: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """Build queue items from library_items recommended_action (Phase 8A data)."""
    if conn is None:
        return []
    q = """
        SELECT id, title, local_status, recommended_action,
               recommendation_reasons_json, diagnostic_status, diagnostic_summary,
               request_status
        FROM library_items
        WHERE recommended_action IS NOT NULL
          AND recommended_action != 'none'
          AND local_status NOT IN ('Subido', 'Subiendo')
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()
    items = []
    for r in rows:
        rd = dict(r)
        lib_id = rd["id"]
        # Skip if already covered by request_readiness for same lib item
        rr_exists = conn.execute(
            "SELECT 1 FROM request_readiness WHERE best_library_item_id = ?", (lib_id,)
        ).fetchone()
        if rr_exists:
            continue

        action = rd.get("recommended_action", "none")
        status = _REC_ACTION_TO_STATUS.get(action, "open")

        reasons = _loads(rd.get("recommendation_reasons_json"))
        items.append({
            "queue_key": f"library:{lib_id}:recommendation",
            "item_type": "library_recommendation",
            "entity_type": "library_item",
            "entity_id": lib_id,
            "request_item_id": None,
            "library_item_id": lib_id,
            "upload_job_id": None,
            "title": rd.get("title", ""),
            "subtitle": rd.get("diagnostic_summary") or rd.get("local_status", ""),
            "status": status,
            "action": action,
            "blockers": [],
            "reasons": reasons,
            "context": {
                "local_status": rd.get("local_status"),
                "diagnostic_status": rd.get("diagnostic_status"),
                "request_status": rd.get("request_status"),
            },
        })
    return items


def build_items_from_upload_jobs(
    limit: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """Build queue items from upload_jobs (Phase 6D data)."""
    if conn is None:
        return []
    q = """
        SELECT id, title, status, path, library_item_id
        FROM upload_jobs
        WHERE status NOT IN ('completed', 'cancelled')
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()
    items = []
    for r in rows:
        rd = dict(r)
        job_id = rd["id"]
        job_status = rd.get("status", "pending")
        action = _UPLOAD_STATUS_TO_ACTION.get(job_status, "view_upload")
        q_status = _UPLOAD_STATUS_TO_QUEUE_STATUS.get(job_status, "open")
        items.append({
            "queue_key": f"upload:{job_id}:status",
            "item_type": "upload_job",
            "entity_type": "upload_job",
            "entity_id": job_id,
            "request_item_id": None,
            "library_item_id": rd.get("library_item_id"),
            "upload_job_id": job_id,
            "title": rd.get("title", ""),
            "subtitle": f"Job #{job_id} · {job_status}",
            "status": q_status,
            "action": action,
            "blockers": ["Upload falló — revisar logs"] if job_status == "failed" else [],
            "reasons": [f"Upload job en estado {job_status}"],
            "context": {"job_status": job_status, "path": rd.get("path")},
        })
    return items


def build_items_from_arr_diagnostics(
    limit: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """Build queue items from library_items with ARR queue/history issues."""
    if conn is None:
        return []
    q = """
        SELECT id, title, arr_queue_status, arr_queue_error,
               arr_history_status, arr_history_error
        FROM library_items
        WHERE arr_queue_status IN ('import_error', 'pending_import')
           OR arr_history_status IN ('failed', 'error')
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()
    items = []
    for r in rows:
        rd = dict(r)
        lib_id = rd["id"]
        arr_qs = rd.get("arr_queue_status")
        arr_hs = rd.get("arr_history_status")

        if arr_qs in ("import_error", "pending_import"):
            code = arr_qs
        else:
            code = f"history_{arr_hs}"

        items.append({
            "queue_key": f"arr:{lib_id}:issue:{code}",
            "item_type": "arr_issue",
            "entity_type": "library_item",
            "entity_id": lib_id,
            "request_item_id": None,
            "library_item_id": lib_id,
            "upload_job_id": None,
            "title": rd.get("title", ""),
            "subtitle": f"ARR: {arr_qs or arr_hs}",
            "status": "blocked",
            "action": "review_arr",
            "blockers": [
                rd.get("arr_queue_error") or rd.get("arr_history_error") or "Error ARR"
            ],
            "reasons": [f"ARR queue: {arr_qs}", f"ARR history: {arr_hs}"],
            "context": {
                "arr_queue_status": arr_qs,
                "arr_history_status": arr_hs,
            },
        })
    return items


# ---------------------------------------------------------------------------
# Core refresh
# ---------------------------------------------------------------------------

def refresh_operational_queue(
    conn: sqlite3.Connection,
    filters: Optional[dict] = None,
    limit: Optional[int] = None,
    include_requests: bool = True,
    include_library: bool = True,
    include_uploads: bool = True,
    include_arr: bool = True,
) -> dict:
    """Rebuild the operational queue from all sources. Returns summary dict."""
    started_at = _now_utc()
    all_items: list[dict] = []

    if include_requests:
        all_items.extend(build_items_from_request_readiness(limit=limit, conn=conn))
    if include_library:
        all_items.extend(build_items_from_library_recommendations(limit=limit, conn=conn))
    if include_uploads:
        all_items.extend(build_items_from_upload_jobs(limit=limit, conn=conn))
    if include_arr:
        all_items.extend(build_items_from_arr_diagnostics(limit=limit, conn=conn))

    seen_keys: set[str] = set()
    built = 0
    for item in all_items:
        key = item["queue_key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        upsert_queue_item(item, conn)
        built += 1

    # Mark items not seen in this refresh as resolved (if previously open)
    if seen_keys:
        placeholders = ",".join("?" for _ in seen_keys)
        conn.execute(
            f"""
            UPDATE operational_queue_items
            SET status = 'resolved', resolved_at = ?, updated_at = ?
            WHERE queue_key NOT IN ({placeholders})
              AND status IN ('open', 'ready', 'waiting', 'blocked')
            """,
            [_now_utc(), _now_utc()] + list(seen_keys),
        )
    else:
        conn.execute(
            """
            UPDATE operational_queue_items
            SET status = 'resolved', resolved_at = ?, updated_at = ?
            WHERE status IN ('open', 'ready', 'waiting', 'blocked')
            """,
            [_now_utc(), _now_utc()],
        )

    summary = get_operational_queue_summary(conn)
    conn.commit()

    conn.execute(
        """
        INSERT INTO operational_queue_runs
        (run_type, status, items_built, items_open, items_ready, items_blocked,
         started_at, finished_at, summary_json, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "refresh",
            "completed",
            built,
            summary.get("open", 0),
            summary.get("ready", 0),
            summary.get("blocked", 0),
            started_at,
            _now_utc(),
            json.dumps(summary, ensure_ascii=False),
            _now_utc(),
            _now_utc(),
        ),
    )
    conn.commit()

    return {
        "ok": True,
        "items_built": built,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def list_operational_queue(
    conn: sqlite3.Connection,
    filters: Optional[dict] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """List queue items, most recently updated first."""
    f = filters or {}
    conditions = ["status NOT IN ('resolved', 'ignored', 'completed')"]
    params: list[Any] = []

    if f.get("status"):
        conditions.append("status = ?")
        params.append(f["status"])
    if f.get("action"):
        conditions.append("action = ?")
        params.append(f["action"])
    if f.get("item_type"):
        conditions.append("item_type = ?")
        params.append(f["item_type"])
    if f.get("entity_type"):
        conditions.append("entity_type = ?")
        params.append(f["entity_type"])
    if f.get("search"):
        conditions.append("title LIKE ?")
        params.append(f"%{f['search']}%")

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT * FROM operational_queue_items
        WHERE {where}
        ORDER BY updated_at DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()
    return [_row_to_item(dict(r)) for r in rows]


def get_operational_queue_summary(conn: sqlite3.Connection) -> dict:
    """Return aggregate counts for the operational queue. 'blocked' is (and
    always was) status-based, not priority-based."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open,
            SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) AS ready,
            SUM(CASE WHEN status = 'waiting' THEN 1 ELSE 0 END) AS waiting,
            SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) AS blocked,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running
        FROM operational_queue_items
        WHERE status NOT IN ('resolved', 'ignored', 'completed')
        """
    ).fetchone()
    if row:
        d = dict(row)
        return {
            "total": d.get("total") or 0,
            "open": d.get("open") or 0,
            "ready": d.get("ready") or 0,
            "waiting": d.get("waiting") or 0,
            "blocked": d.get("blocked") or 0,
            "running": d.get("running") or 0,
        }
    return {"total": 0, "open": 0, "ready": 0, "waiting": 0, "blocked": 0, "running": 0}


def get_operational_queue_item(item_id: int, conn: sqlite3.Connection) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM operational_queue_items WHERE id = ?", (item_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_item(dict(row))


def mark_queue_item_resolved(
    item_id: int,
    conn: sqlite3.Connection,
    *,
    reason: Optional[str] = None,
) -> dict:
    now = _now_utc()
    existing = conn.execute(
        "SELECT id FROM operational_queue_items WHERE id = ?", (item_id,)
    ).fetchone()
    if not existing:
        return {"ok": False, "error": f"Item {item_id} no encontrado"}
    conn.execute(
        "UPDATE operational_queue_items SET status = 'resolved', resolved_at = ?, updated_at = ? WHERE id = ?",
        (now, now, item_id),
    )
    conn.commit()
    return {"ok": True, "item_id": item_id, "status": "resolved", "reason": reason}


def ignore_queue_item(
    item_id: int,
    conn: sqlite3.Connection,
    *,
    reason: Optional[str] = None,
) -> dict:
    now = _now_utc()
    existing = conn.execute(
        "SELECT id FROM operational_queue_items WHERE id = ?", (item_id,)
    ).fetchone()
    if not existing:
        return {"ok": False, "error": f"Item {item_id} no encontrado"}
    conn.execute(
        "UPDATE operational_queue_items SET status = 'ignored', resolved_at = ?, updated_at = ? WHERE id = ?",
        (now, now, item_id),
    )
    conn.commit()
    return {"ok": True, "item_id": item_id, "status": "ignored", "reason": reason}


def get_dashboard_queue_counts(conn: sqlite3.Connection) -> dict:
    """Return operational queue counts for dashboard."""
    try:
        summary = get_operational_queue_summary(conn)
        return {
            "operational_queue_open": summary.get("open", 0),
            "operational_queue_ready": summary.get("ready", 0),
            "operational_queue_waiting": summary.get("waiting", 0),
            "operational_queue_blocked": summary.get("blocked", 0),
        }
    except Exception:
        return {
            "operational_queue_open": 0,
            "operational_queue_ready": 0,
            "operational_queue_waiting": 0,
            "operational_queue_blocked": 0,
        }
