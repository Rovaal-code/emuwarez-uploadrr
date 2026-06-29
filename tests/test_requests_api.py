"""Tests for /api/requests endpoints (Phase 5B).

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Sync status
# ---------------------------------------------------------------------------

def test_requests_sync_status_requires_auth(client):
    resp = client.get("/api/requests/sync-status")
    assert resp.status_code == 401


def test_requests_sync_status_with_auth(client, auth_headers):
    resp = client.get("/api/requests/sync-status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "can_sync" in data
    assert "wait_seconds" in data
    assert isinstance(data["can_sync"], bool)
    assert isinstance(data["wait_seconds"], int)
    assert data["min_interval_seconds"] == 3600


def test_requests_sync_status_initially_can_sync(client, auth_headers):
    resp = client.get("/api/requests/sync-status", headers=auth_headers)
    assert resp.json()["can_sync"] is True


# ---------------------------------------------------------------------------
# GET /api/requests
# ---------------------------------------------------------------------------

def test_requests_list_requires_auth(client):
    resp = client.get("/api/requests")
    assert resp.status_code == 401


def test_requests_list_empty(client, auth_headers):
    resp = client.get("/api/requests", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_requests_list_with_data(client, auth_headers, isolated_db):
    """Seed a request item and check it appears in the list."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    item = RequestItem(
        id=None,
        emu_id="emu-test-1",
        title="Test Movie 5B",
        category="Movies",
        requested_resolution="1080p",
        requested_source="BluRay",
        emu_status="pending",
    )
    upsert_request(conn, item)
    conn.close()

    resp = client.get("/api/requests", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    titles = [i["title"] for i in data["items"]]
    assert "Test Movie 5B" in titles


def test_requests_list_search(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    for title in ["Alpha Movie", "Beta Series", "Gamma Film"]:
        upsert_request(conn, RequestItem(id=None, emu_id=f"id-{title.lower().replace(' ','-')}", title=title))
    conn.close()

    resp = client.get("/api/requests?search=Beta", headers=auth_headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Beta Series"


def test_requests_list_pagination(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    for i in range(10):
        upsert_request(conn, RequestItem(id=None, emu_id=f"pag-{i}", title=f"Movie {i:02d}"))
    conn.close()

    resp1 = client.get("/api/requests?limit=5&offset=0", headers=auth_headers)
    resp2 = client.get("/api/requests?limit=5&offset=5", headers=auth_headers)
    assert resp1.json()["total"] == 10
    assert len(resp1.json()["items"]) == 5
    assert len(resp2.json()["items"]) == 5
    ids1 = {i["id"] for i in resp1.json()["items"]}
    ids2 = {i["id"] for i in resp2.json()["items"]}
    assert not (ids1 & ids2)  # no overlap


# ---------------------------------------------------------------------------
# POST /api/requests/sync
# ---------------------------------------------------------------------------

def test_requests_sync_requires_auth(client):
    resp = client.post("/api/requests/sync", json={})
    assert resp.status_code == 401


def test_requests_sync_no_api_key_returns_502(client, auth_headers):
    """Without EMU api key configured, sync should fail gracefully (502)."""
    resp = client.post("/api/requests/sync", json={})
    # Without auth
    assert resp.status_code == 401

    resp = client.post("/api/requests/sync", json={}, headers=auth_headers)
    # No EMU api key → 502 IntegrationError
    assert resp.status_code == 502


def test_requests_sync_throttled(client, auth_headers, isolated_db, monkeypatch):
    """After a successful sync, a second sync without force should be throttled."""
    import os, datetime as dt
    from emuwarez_uploadrr.database import connect, init_db, set_state, get_state
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    # Simulate a recent sync
    recent = dt.datetime.now(dt.timezone.utc).isoformat()
    set_state(conn, "last_emu_requests_sync_utc", recent)
    conn.commit()
    conn.close()

    # Now try to sync — should be throttled
    from emuwarez_uploadrr.services.requests import can_sync_requests
    conn2 = connect()
    init_db(conn2)
    can, wait = can_sync_requests(conn2, force=False)
    conn2.close()
    assert can is False
    assert wait > 0


def test_requests_sync_force_body(client, auth_headers):
    """force=True is accepted as body param."""
    resp = client.post("/api/requests/sync", json={"force": True}, headers=auth_headers)
    # No api key → 502, but body was parsed correctly
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /api/requests/{id}
# ---------------------------------------------------------------------------

def test_requests_detail_requires_auth(client):
    resp = client.get("/api/requests/1")
    assert resp.status_code == 401


def test_requests_detail_not_found(client, auth_headers):
    resp = client.get("/api/requests/99999", headers=auth_headers)
    assert resp.status_code == 404


def test_requests_detail_found(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    req_id = upsert_request(conn, RequestItem(
        id=None, emu_id="detail-test-1", title="Detail Movie",
        requested_resolution="1080p", requested_source="WEB-DL",
    ))
    conn.close()

    resp = client.get(f"/api/requests/{req_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == req_id
    assert data["title"] == "Detail Movie"
    assert data["requested_resolution"] == "1080p"
    assert "match" in data


# ---------------------------------------------------------------------------
# POST /api/requests/{id}/match
# ---------------------------------------------------------------------------

def test_requests_match_requires_auth(client):
    resp = client.post("/api/requests/1/match")
    assert resp.status_code == 401


def test_requests_match_not_found(client, auth_headers):
    resp = client.post("/api/requests/99999/match", headers=auth_headers)
    assert resp.status_code == 404


def test_requests_match_runs_matching(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.services.library import upsert_library_item
    from emuwarez_uploadrr.models import RequestItem, LibraryItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    # Seed matching pair
    lib_item = LibraryItem(
        id=None, item_type="movie", title="Matrix",
        tmdb_id="603", local_status="Disponible",
        instance_id=1, external_id="ext-603",
    )
    upsert_library_item(conn, lib_item)
    req_id = upsert_request(conn, RequestItem(id=None, emu_id="match-1", title="Matrix", tmdb_id="603"))
    conn.close()

    resp = client.post(f"/api/requests/{req_id}/match", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == req_id
    assert data["match"] is not None
    assert data["match"]["status"] in ("Compatible", "Parcial", "No compatible", "Llena")


# ---------------------------------------------------------------------------
# POST /api/requests/{id}/mark-reviewed
# ---------------------------------------------------------------------------

def test_requests_mark_reviewed_requires_auth(client):
    resp = client.post("/api/requests/1/mark-reviewed")
    assert resp.status_code == 401


def test_requests_mark_reviewed_not_found(client, auth_headers):
    resp = client.post("/api/requests/99999/mark-reviewed", headers=auth_headers)
    assert resp.status_code == 404


def test_requests_mark_reviewed_found(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    req_id = upsert_request(conn, RequestItem(id=None, emu_id="review-1", title="Review Me"))
    conn.close()

    resp = client.post(f"/api/requests/{req_id}/mark-reviewed", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# POST /api/missing/{id}/create-emu-request stays BLOCKED
# ---------------------------------------------------------------------------

def test_create_emu_request_still_blocked(client, auth_headers):
    resp = client.post("/api/missing/1/create-emu-request", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["implemented"] is False
    assert data["stub"] is True


# ---------------------------------------------------------------------------
# Dashboard summary includes EMU fields
# ---------------------------------------------------------------------------

def test_dashboard_summary_has_requests_fields(client, auth_headers):
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "requests_total" in data
    assert "requests_compatible" in data
    assert "requests_filled" in data
    assert isinstance(data["requests_total"], int)
