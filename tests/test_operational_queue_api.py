"""Tests for Phase 8C — /api/operational-queue endpoints."""
from __future__ import annotations

import pytest


# The global `client`, `admin_token`, and `auth_headers` fixtures come from conftest.py.
# `isolated_db` (autouse) gives each test a fresh DB.


# ---------------------------------------------------------------------------
# Auth guard — all endpoints must return 401 without token
# ---------------------------------------------------------------------------

def test_refresh_requires_auth(client):
    r = client.post("/api/operational-queue/refresh")
    assert r.status_code == 401


def test_list_requires_auth(client):
    r = client.get("/api/operational-queue")
    assert r.status_code == 401


def test_summary_requires_auth(client):
    r = client.get("/api/operational-queue/summary")
    assert r.status_code == 401


def test_show_requires_auth(client):
    r = client.get("/api/operational-queue/999")
    assert r.status_code == 401


def test_resolve_requires_auth(client):
    r = client.post("/api/operational-queue/999/resolve")
    assert r.status_code == 401


def test_ignore_requires_auth(client):
    r = client.post("/api/operational-queue/999/ignore")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Empty-state responses
# ---------------------------------------------------------------------------

def test_list_empty(client, auth_headers):
    r = client.get("/api/operational-queue", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert data["items"] == []


def test_summary_empty(client, auth_headers):
    r = client.get("/api/operational-queue/summary", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# 404 for unknown item
# ---------------------------------------------------------------------------

def test_show_404_unknown(client, auth_headers):
    r = client.get("/api/operational-queue/99999", headers=auth_headers)
    assert r.status_code == 404


def test_resolve_404_unknown(client, auth_headers):
    r = client.post("/api/operational-queue/99999/resolve", headers=auth_headers, json={})
    assert r.status_code == 404


def test_ignore_404_unknown(client, auth_headers):
    r = client.post("/api/operational-queue/99999/ignore", headers=auth_headers, json={})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# refresh OK
# ---------------------------------------------------------------------------

def test_refresh_ok(client, auth_headers):
    r = client.post("/api/operational-queue/refresh", headers=auth_headers, json={})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True


# ---------------------------------------------------------------------------
# list OK after refresh
# ---------------------------------------------------------------------------

def test_list_ok_after_refresh(client, auth_headers):
    client.post("/api/operational-queue/refresh", headers=auth_headers, json={})
    r = client.get("/api/operational-queue", headers=auth_headers)
    assert r.status_code == 200
    assert "items" in r.json()


# ---------------------------------------------------------------------------
# summary OK after refresh
# ---------------------------------------------------------------------------

def test_summary_ok_after_refresh(client, auth_headers):
    client.post("/api/operational-queue/refresh", headers=auth_headers, json={})
    r = client.get("/api/operational-queue/summary", headers=auth_headers)
    assert r.status_code == 200
    assert "total" in r.json()


# ---------------------------------------------------------------------------
# resolve ok
# ---------------------------------------------------------------------------

def test_resolve_ok(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path())
    init_db(conn)
    conn.execute(
        "INSERT INTO operational_queue_items (queue_key, item_type, entity_type, status, action) VALUES (?,?,?,?,?)",
        ("api-test:resolve", "x", "y", "open", "none"),
    )
    conn.commit()
    item_id = conn.execute(
        "SELECT id FROM operational_queue_items WHERE queue_key = 'api-test:resolve'"
    ).fetchone()["id"]
    conn.close()

    r = client.post(f"/api/operational-queue/{item_id}/resolve", headers=auth_headers, json={"reason": "test"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["status"] == "resolved"


# ---------------------------------------------------------------------------
# ignore ok
# ---------------------------------------------------------------------------

def test_ignore_ok(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path())
    init_db(conn)
    conn.execute(
        "INSERT INTO operational_queue_items (queue_key, item_type, entity_type, status, action) VALUES (?,?,?,?,?)",
        ("api-test:ignore", "x", "y", "open", "none"),
    )
    conn.commit()
    item_id = conn.execute(
        "SELECT id FROM operational_queue_items WHERE queue_key = 'api-test:ignore'"
    ).fetchone()["id"]
    conn.close()

    r = client.post(f"/api/operational-queue/{item_id}/ignore", headers=auth_headers, json={"reason": "test"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["status"] == "ignored"


# ---------------------------------------------------------------------------
# Dashboard includes Phase 8C counts
# ---------------------------------------------------------------------------

def test_dashboard_includes_phase8c_counts(client, auth_headers):
    r = client.get("/api/dashboard/summary", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "operational_queue_open" in data
    assert "operational_queue_ready" in data
    assert "operational_queue_blocked" in data
    assert "operational_queue_waiting" in data
