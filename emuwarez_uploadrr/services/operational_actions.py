"""Phase 9A — Action planner for operational queue items.

SAFETY CONTRACT:
- get_queue_action_plan: read-only. Never modifies external entities.
- list_available_queue_actions: read-only.
- execute_safe_queue_action: only allows verify_file, refresh_queue_item, view_plan.
  Never executes Uploadrr. Never applies nomenclature. Never creates hardlinks.
  Never creates eMuwarez requests. Never modifies Radarr/Sonarr. Never modifies media.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Action → flow mapping
# ---------------------------------------------------------------------------

_ACTION_FLOW_MAP: dict[str, dict[str, Any]] = {
    "adapt_nomenclature": {
        "flow": "nomenclature",
        "route": "/library",
        "modal": "nomenclature",
        "label": "Adaptar nomenclatura",
        "requires_confirmation": True,
        "confirmation_token": "APLICAR_NOMENCLATURA",
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": "library_item_id",
    },
    "run_preflight": {
        "flow": "upload_preflight",
        "route": "/uploads",
        "modal": "preflight",
        "label": "Ejecutar preflight Uploadrr",
        "requires_confirmation": False,
        "confirmation_token": None,
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": "library_item_id",
    },
    "upload": {
        "flow": "upload_execution",
        "route": "/uploads",
        "modal": "upload_confirmation",
        "label": "Iniciar subida Uploadrr",
        "requires_confirmation": True,
        "confirmation_token": "INICIAR_UPLOADRR",
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": "upload_job_id",
    },
    "retry_upload": {
        "flow": "upload_retry",
        "route": "/uploads",
        "modal": "retry_upload",
        "label": "Reintentar subida Uploadrr",
        "requires_confirmation": True,
        "confirmation_token": "INICIAR_UPLOADRR",
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": "upload_job_id",
    },
    "view_upload": {
        "flow": "upload_logs",
        "route": "/uploads",
        "modal": "upload_detail",
        "label": "Ver logs de subida",
        "requires_confirmation": False,
        "confirmation_token": None,
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": "upload_job_id",
    },
    "verify_file": {
        "flow": "filesystem_verify",
        "route": "/library",
        "modal": None,
        "label": "Verificar archivo en disco",
        "requires_confirmation": False,
        "confirmation_token": None,
        "safe_to_execute_inline": True,
        "guided_flow": False,
        "needs_target": "library_item_id",
    },
    "wait_download": {
        "flow": "arr_status",
        "route": "/missing",
        "modal": None,
        "label": "Ver estado de descarga ARR",
        "requires_confirmation": False,
        "confirmation_token": None,
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": None,
    },
    "review_arr": {
        "flow": "arr_diagnostics",
        "route": "/instances",
        "modal": None,
        "label": "Revisar diagnóstico ARR",
        "requires_confirmation": False,
        "confirmation_token": None,
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": None,
    },
    "manual_review": {
        "flow": "context_review",
        "route": "/queue",
        "modal": None,
        "label": "Revisión manual",
        "requires_confirmation": False,
        "confirmation_token": None,
        "safe_to_execute_inline": False,
        "guided_flow": True,
        "needs_target": None,
    },
    "none": {
        "flow": "context_review",
        "route": "/queue",
        "modal": None,
        "label": "Sin acción definida",
        "requires_confirmation": False,
        "confirmation_token": None,
        "safe_to_execute_inline": False,
        "guided_flow": False,
        "needs_target": None,
    },
}

# Actions that CANNOT be executed inline (safety blocklist)
_BLOCKED_INLINE_ACTIONS = frozenset({
    "adapt_nomenclature",
    "run_preflight",
    "upload",
    "retry_upload",
    "review_arr",
    "check_emu",
    "manual_review",
    "view_upload",
    "wait_download",
})

# Actions that CAN be executed inline (read-only / local-safe)
_SAFE_INLINE_ACTIONS = frozenset({"verify_file", "refresh_queue_item", "view_plan"})


def _get_queue_item(item_id: int, conn: sqlite3.Connection) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM operational_queue_items WHERE id = ?", (item_id,)
    ).fetchone()
    return dict(row) if row else None


def _build_action_plan(item: dict) -> dict:
    """Build a full action plan dict from a queue item row."""
    action = item.get("action") or "none"
    flow_info = _ACTION_FLOW_MAP.get(action, _ACTION_FLOW_MAP["none"])

    target: dict[str, Any] = {}
    needs = flow_info.get("needs_target")
    if needs == "library_item_id" and item.get("library_item_id"):
        target["library_item_id"] = item["library_item_id"]
    if needs == "upload_job_id" and item.get("upload_job_id"):
        target["upload_job_id"] = item["upload_job_id"]
    if item.get("request_item_id"):
        target["request_item_id"] = item["request_item_id"]
    if item.get("library_item_id") and "library_item_id" not in target:
        target["library_item_id"] = item["library_item_id"]
    if item.get("upload_job_id") and "upload_job_id" not in target:
        target["upload_job_id"] = item["upload_job_id"]

    try:
        blockers = json.loads(item.get("blockers_json") or "[]")
    except Exception:
        blockers = []
    try:
        reasons = json.loads(item.get("reasons_json") or "[]")
    except Exception:
        reasons = []

    return {
        "queue_item_id": item["id"],
        "queue_key": item.get("queue_key"),
        "action": action,
        "flow": flow_info["flow"],
        "target": target,
        "ui": {
            "route": flow_info["route"],
            "modal": flow_info.get("modal"),
            "label": flow_info["label"],
        },
        "requires_confirmation": flow_info["requires_confirmation"],
        "confirmation_token": flow_info.get("confirmation_token"),
        "safe_to_execute_inline": flow_info["safe_to_execute_inline"],
        "guided_flow": flow_info.get("guided_flow", False),
        "blockers": blockers,
        "reasons": reasons,
        "title": item.get("title"),
        "status": item.get("status", "open"),
        "item_type": item.get("item_type"),
    }


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_queue_action_plan(item_id: int, conn: sqlite3.Connection) -> dict:
    """Return a full action plan for a queue item. Read-only."""
    item = _get_queue_item(item_id, conn)
    if not item:
        return {"ok": False, "error": f"Item {item_id} no encontrado"}
    plan = _build_action_plan(item)
    return {"ok": True, "plan": plan}


def list_available_queue_actions(item_id: int, conn: sqlite3.Connection) -> list[dict]:
    """Return list of available actions for a queue item. Read-only."""
    item = _get_queue_item(item_id, conn)
    if not item:
        return []
    action = item.get("action") or "none"
    actions_out = []
    # Primary action
    flow_info = _ACTION_FLOW_MAP.get(action, _ACTION_FLOW_MAP["none"])
    actions_out.append({
        "action": action,
        "label": flow_info["label"],
        "flow": flow_info["flow"],
        "safe_to_execute_inline": flow_info["safe_to_execute_inline"],
        "requires_confirmation": flow_info["requires_confirmation"],
        "confirmation_token": flow_info.get("confirmation_token"),
        "primary": True,
    })
    # Always offer view_plan (safe inline)
    if action != "none":
        actions_out.append({
            "action": "view_plan",
            "label": "Ver plan de acción",
            "flow": "context_review",
            "safe_to_execute_inline": True,
            "requires_confirmation": False,
            "confirmation_token": None,
            "primary": False,
        })
    # Offer verify_file if library_item_id present and not already primary
    if item.get("library_item_id") and action != "verify_file":
        actions_out.append({
            "action": "verify_file",
            "label": "Verificar archivo en disco",
            "flow": "filesystem_verify",
            "safe_to_execute_inline": True,
            "requires_confirmation": False,
            "confirmation_token": None,
            "primary": False,
        })
    return actions_out


def execute_safe_queue_action(
    item_id: int,
    conn: sqlite3.Connection,
    *,
    action: Optional[str] = None,
) -> dict:
    """Execute a safe (read-only / local) action on a queue item.

    SAFETY: Only verify_file, refresh_queue_item, view_plan are permitted.
    All other actions return a blocked response — they must be executed via
    their dedicated guided flows with explicit confirmation.
    """
    item = _get_queue_item(item_id, conn)
    if not item:
        return {"ok": False, "error": f"Item {item_id} no encontrado", "blocked": False}

    effective_action = action or item.get("action") or "none"

    if effective_action in _BLOCKED_INLINE_ACTIONS:
        flow_info = _ACTION_FLOW_MAP.get(effective_action, _ACTION_FLOW_MAP["none"])
        record_queue_action_event(
            item_id, "blocked", "blocked",
            f"Acción '{effective_action}' bloqueada — requiere flujo guiado",
            {"action": effective_action, "flow": flow_info["flow"]},
            conn,
        )
        return {
            "ok": False,
            "blocked": True,
            "action": effective_action,
            "message": (
                f"La acción '{effective_action}' requiere flujo guiado y confirmación explícita. "
                "No puede ejecutarse inline desde la cola."
            ),
            "guided_flow": flow_info["flow"],
            "ui_route": flow_info["route"],
            "confirmation_token": flow_info.get("confirmation_token"),
        }

    if effective_action not in _SAFE_INLINE_ACTIONS:
        record_queue_action_event(
            item_id, "blocked", "blocked",
            f"Acción '{effective_action}' no reconocida como acción segura inline",
            {"action": effective_action},
            conn,
        )
        return {
            "ok": False,
            "blocked": True,
            "action": effective_action,
            "message": f"Acción '{effective_action}' no disponible como acción segura inline.",
        }

    # --- view_plan ---
    if effective_action == "view_plan":
        plan = _build_action_plan(item)
        record_queue_action_event(
            item_id, "plan_viewed", "ok", "Plan visualizado", None, conn
        )
        _update_item_action_tracking(item_id, "ok", "Plan visualizado", conn)
        return {"ok": True, "action": "view_plan", "plan": plan}

    # --- refresh_queue_item ---
    if effective_action == "refresh_queue_item":
        try:
            from .operational_queue import refresh_operational_queue
            result = refresh_operational_queue(conn)
            msg = f"Cola refrescada: {result.get('items_built', 0)} items"
            record_queue_action_event(item_id, "safe_action_executed", "ok", msg, None, conn)
            _update_item_action_tracking(item_id, "ok", msg, conn)
            return {"ok": True, "action": "refresh_queue_item", "result": result}
        except Exception as exc:
            msg = f"Error al refrescar: {exc}"
            record_queue_action_event(item_id, "error", "error", msg, None, conn)
            return {"ok": False, "action": "refresh_queue_item", "error": msg}

    # --- verify_file ---
    if effective_action == "verify_file":
        lib_id = item.get("library_item_id")
        if not lib_id:
            msg = "Este item de cola no tiene library_item_id asociado para verificar"
            record_queue_action_event(item_id, "error", "warning", msg, None, conn)
            return {"ok": False, "action": "verify_file", "error": msg}
        try:
            from .library_verification import verify_library_item_file
            result = verify_library_item_file(lib_id, conn)
            status = "ok" if result.get("file_exists") else "warning"
            msg = (
                f"Archivo {'encontrado' if result.get('file_exists') else 'NO encontrado'}: "
                f"{result.get('path', '–')}"
            )
            record_queue_action_event(
                item_id, "safe_action_executed", status, msg,
                {k: v for k, v in result.items() if k not in ("path",)},
                conn,
            )
            _update_item_action_tracking(item_id, status, msg, conn)
            conn.commit()
            return {"ok": True, "action": "verify_file", "result": result}
        except Exception as exc:
            msg = f"Error verificando archivo: {exc}"
            record_queue_action_event(item_id, "error", "error", msg, None, conn)
            return {"ok": False, "action": "verify_file", "error": msg}

    return {"ok": False, "error": f"Acción no implementada: {effective_action}"}


def record_queue_action_event(
    item_id: int,
    event_type: str,
    status: str,
    message: Optional[str],
    details: Optional[dict],
    conn: sqlite3.Connection,
) -> dict:
    """Record an action event for a queue item. Never stores API keys or secrets."""
    details_json: Optional[str] = None
    if details:
        safe_details = {
            k: v for k, v in details.items()
            if k.lower() not in {"api_key", "apikey", "token", "password", "secret"}
        }
        details_json = json.dumps(safe_details, ensure_ascii=False)
    conn.execute(
        """INSERT INTO operational_action_events
           (queue_item_id, action, event_type, status, message, details_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (item_id, event_type, event_type, status, message, details_json, _now_utc()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM operational_action_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {"ok": True, "event_id": row["id"] if row else None, "event_type": event_type}


def get_queue_action_events(
    item_id: int,
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
) -> list[dict]:
    """Return action events for a queue item, newest first."""
    rows = conn.execute(
        """SELECT * FROM operational_action_events
           WHERE queue_item_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (item_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _update_item_action_tracking(
    item_id: int, status: str, message: str, conn: sqlite3.Connection
) -> None:
    conn.execute(
        """UPDATE operational_queue_items
           SET last_action_at = ?, last_action_status = ?, last_action_message = ?,
               updated_at = ?
           WHERE id = ?""",
        (_now_utc(), status, message, _now_utc(), item_id),
    )
