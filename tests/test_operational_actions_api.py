"""Tests for Phase 9A — operational actions API endpoints."""
from __future__ import annotations

import pytest


def _seed_queue_item(client, auth_headers, action="upload", title="API Test Item"):
    """Refresh queue or insert a queue item via DB directly."""
    from emuwarez_uploadrr.database import connect, init_db
    import os, pathlib
    db_path = pathlib.Path(os.environ["CONFIG_DIR"]) / "emuwarez_uploadrr.db"
    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """INSERT INTO operational_queue_items
           (queue_key, item_type, entity_type, entity_id, title, status, action,
            priority_score, priority_bucket, blockers_json, reasons_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
        (f"key-api-{action}", "upload_ready", "library", 1, title, "ready", action,
         80, "high", "[]", "[]"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM operational_queue_items ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["id"]


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_list_actions_requires_auth(client):
    r = client.get("/api/operational-queue/1/actions")
    assert r.status_code == 401


def test_action_plan_requires_auth(client):
    r = client.get("/api/operational-queue/1/action-plan")
    assert r.status_code == 401


def test_execute_safe_requires_auth(client):
    r = client.post("/api/operational-queue/1/execute-safe-action", json={})
    assert r.status_code == 401


def test_events_requires_auth(client):
    r = client.get("/api/operational-queue/1/action-events")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 404 for missing items
# ---------------------------------------------------------------------------

def test_list_actions_404(client, auth_headers):
    r = client.get("/api/operational-queue/99999/actions", headers=auth_headers)
    assert r.status_code == 404


def test_action_plan_404(client, auth_headers):
    r = client.get("/api/operational-queue/99999/action-plan", headers=auth_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_list_actions_returns_list(client, auth_headers):
    iid = _seed_queue_item(client, auth_headers, action="upload")
    r = client.get(f"/api/operational-queue/{iid}/actions", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["item_id"] == iid
    assert isinstance(data["actions"], list)
    assert len(data["actions"]) >= 1
    primary = next(a for a in data["actions"] if a["primary"])
    assert primary["action"] == "upload"


def test_action_plan_returns_plan(client, auth_headers):
    iid = _seed_queue_item(client, auth_headers, action="adapt_nomenclature", title="Plan Test")
    r = client.get(f"/api/operational-queue/{iid}/action-plan", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    plan = data["plan"]
    assert plan["action"] == "adapt_nomenclature"
    assert plan["flow"] == "nomenclature"
    assert plan["ui"]["route"] == "/library"
    assert plan["confirmation_token"] == "APLICAR_NOMENCLATURA"


def test_execute_safe_blocked_returns_409(client, auth_headers):
    iid = _seed_queue_item(client, auth_headers, action="upload")
    r = client.post(
        f"/api/operational-queue/{iid}/execute-safe-action",
        json={"action": "upload"},
        headers=auth_headers,
    )
    assert r.status_code == 409
    data = r.json()
    assert "detail" in data
    assert "upload" in data["detail"].lower() or "flujo" in data["detail"].lower()


def test_execute_safe_view_plan_ok(client, auth_headers):
    iid = _seed_queue_item(client, auth_headers, action="upload")
    r = client.post(
        f"/api/operational-queue/{iid}/execute-safe-action",
        json={"action": "view_plan"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True


def test_execute_safe_no_action_uses_item_action(client, auth_headers):
    iid = _seed_queue_item(client, auth_headers, action="retry_upload")
    r = client.post(
        f"/api/operational-queue/{iid}/execute-safe-action",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 409
    data = r.json()
    assert "detail" in data
    assert "retry" in data["detail"].lower() or "flujo" in data["detail"].lower()


def test_events_returns_list(client, auth_headers):
    iid = _seed_queue_item(client, auth_headers, action="upload")
    r = client.get(f"/api/operational-queue/{iid}/action-events", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["item_id"] == iid
    assert isinstance(data["events"], list)
    assert "total" in data


def test_events_populated_after_execute(client, auth_headers):
    iid = _seed_queue_item(client, auth_headers, action="upload")
    client.post(
        f"/api/operational-queue/{iid}/execute-safe-action",
        json={"action": "view_plan"},
        headers=auth_headers,
    )
    r = client.get(f"/api/operational-queue/{iid}/action-events", headers=auth_headers)
    data = r.json()
    assert data["total"] >= 1
