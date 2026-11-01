"""Tests for Phase 8B request readiness API endpoints."""
from __future__ import annotations



def _create_request(client, auth_headers, emu_id="test-api-1", title="Test API Movie"):
    from emuwarez_uploadrr.database import connect, init_db
    import os
    from pathlib import Path
    db_path = Path(os.environ["CONFIG_DIR"]) / "emuwarez_uploadrr.db"
    conn = connect(db_path)
    init_db(conn)
    conn.execute(
        """INSERT OR IGNORE INTO request_items
           (emu_id, title, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)""",
        (emu_id, title),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM request_items WHERE emu_id = ?", (emu_id,)).fetchone()
    conn.close()
    return row["id"]


# ---------------------------------------------------------------------------
# POST /api/requests/readiness/refresh
# ---------------------------------------------------------------------------

def test_readiness_refresh_requires_auth(client):
    resp = client.post("/api/requests/readiness/refresh")
    assert resp.status_code == 401


def test_readiness_refresh_ok_empty(client, auth_headers):
    resp = client.post("/api/requests/readiness/refresh", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# GET /api/requests/readiness
# ---------------------------------------------------------------------------

def test_list_readiness_requires_auth(client):
    resp = client.get("/api/requests/readiness")
    assert resp.status_code == 401


def test_list_readiness_ok_empty(client, auth_headers):
    resp = client.get("/api/requests/readiness", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["items"] == []


def test_list_readiness_after_refresh(client, auth_headers):
    _create_request(client, auth_headers, "emu-lr1", "List Readiness Movie")
    client.post("/api/requests/readiness/refresh", headers=auth_headers)
    resp = client.get("/api/requests/readiness", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1


# ---------------------------------------------------------------------------
# GET /api/requests/{id}/readiness
# ---------------------------------------------------------------------------

def test_get_readiness_requires_auth(client):
    resp = client.get("/api/requests/1/readiness")
    assert resp.status_code == 401


def test_get_readiness_404_if_not_evaluated(client, auth_headers):
    req_id = _create_request(client, auth_headers, "emu-rr1", "No Readiness Yet")
    resp = client.get(f"/api/requests/{req_id}/readiness", headers=auth_headers)
    assert resp.status_code == 404


def test_get_readiness_ok_after_evaluate(client, auth_headers):
    req_id = _create_request(client, auth_headers, "emu-rr2", "Readiness Test")
    client.post(f"/api/requests/{req_id}/readiness/evaluate", headers=auth_headers)
    resp = client.get(f"/api/requests/{req_id}/readiness", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_item_id"] == req_id
    assert "status" in data


# ---------------------------------------------------------------------------
# POST /api/requests/{id}/readiness/evaluate
# ---------------------------------------------------------------------------

def test_evaluate_requires_auth(client):
    resp = client.post("/api/requests/1/readiness/evaluate")
    assert resp.status_code == 401


def test_evaluate_404_unknown(client, auth_headers):
    resp = client.post("/api/requests/99999/readiness/evaluate", headers=auth_headers)
    assert resp.status_code == 404


def test_evaluate_ok(client, auth_headers):
    req_id = _create_request(client, auth_headers, "emu-ev1", "Evaluate Test")
    resp = client.post(f"/api/requests/{req_id}/readiness/evaluate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["request_item_id"] == req_id
    assert data["status"] == "no_local_match"


# ---------------------------------------------------------------------------
# GET /api/requests/{id}/candidates
# ---------------------------------------------------------------------------

def test_candidates_requires_auth(client):
    resp = client.get("/api/requests/1/candidates")
    assert resp.status_code == 401


def test_candidates_404_unknown(client, auth_headers):
    resp = client.get("/api/requests/99999/candidates", headers=auth_headers)
    assert resp.status_code == 404


def test_candidates_ok_empty(client, auth_headers):
    req_id = _create_request(client, auth_headers, "emu-cand1", "Candidates Test")
    resp = client.get(f"/api/requests/{req_id}/candidates", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Dashboard includes Phase 8B counts
# ---------------------------------------------------------------------------

def test_dashboard_includes_readiness_counts(client, auth_headers):
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    for key in ("requests_ready_to_upload", "requests_need_nomenclature",
                "requests_waiting_download", "requests_blocked"):
        assert key in data, f"Missing dashboard key: {key}"
        assert isinstance(data[key], int)


# ---------------------------------------------------------------------------
# Requests list includes readiness fields
# ---------------------------------------------------------------------------

def test_requests_list_includes_readiness_fields(client, auth_headers):
    _create_request(client, auth_headers, "emu-rl1", "List Fields Test")
    resp = client.get("/api/requests", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    item = items[0]
    # Phase 8B fields must be present (may be null)
    assert "readiness_status" in item
    assert "readiness_action" in item
    assert "readiness_best_library_item_id" in item
