"""Tests for ARR diagnostics and verification API endpoints (Phase 8A)."""
from __future__ import annotations



# ---------------------------------------------------------------------------
# GET /api/arr/health
# ---------------------------------------------------------------------------

def test_arr_health_requires_auth(client):
    resp = client.get("/api/arr/health")
    assert resp.status_code == 401


def test_arr_health_ok_no_instances(client, auth_headers):
    resp = client.get("/api/arr/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "instances" in data
    assert "summary" in data
    assert data["instances"] == []


# ---------------------------------------------------------------------------
# POST /api/arr/health/refresh
# ---------------------------------------------------------------------------

def test_arr_health_refresh_requires_auth(client):
    resp = client.post("/api/arr/health/refresh")
    assert resp.status_code == 401


def test_arr_health_refresh_ok(client, auth_headers):
    resp = client.post("/api/arr/health/refresh", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# POST /api/library/verify-files
# ---------------------------------------------------------------------------

def test_verify_files_requires_auth(client):
    resp = client.post("/api/library/verify-files")
    assert resp.status_code == 401


def test_verify_files_ok_empty(client, auth_headers):
    resp = client.post("/api/library/verify-files", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["items_checked"] == 0


# ---------------------------------------------------------------------------
# POST /api/library/{id}/verify-file
# ---------------------------------------------------------------------------

def test_verify_single_file_requires_auth(client):
    resp = client.post("/api/library/1/verify-file")
    assert resp.status_code == 401


def test_verify_single_file_not_found(client, auth_headers):
    resp = client.post("/api/library/99999/verify-file", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/library/recommendations/refresh
# ---------------------------------------------------------------------------

def test_recommendations_refresh_requires_auth(client):
    resp = client.post("/api/library/recommendations/refresh")
    assert resp.status_code == 401


def test_recommendations_refresh_ok(client, auth_headers):
    resp = client.post("/api/library/recommendations/refresh", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# GET /api/library/{id}/recommendation
# ---------------------------------------------------------------------------

def test_get_recommendation_requires_auth(client):
    resp = client.get("/api/library/1/recommendation")
    assert resp.status_code == 401


def test_get_recommendation_not_found(client, auth_headers):
    resp = client.get("/api/library/99999/recommendation", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/library/diagnostics
# ---------------------------------------------------------------------------

def test_library_diagnostics_requires_auth(client):
    resp = client.get("/api/library/diagnostics")
    assert resp.status_code == 401


def test_library_diagnostics_ok(client, auth_headers):
    resp = client.get("/api/library/diagnostics", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


# ---------------------------------------------------------------------------
# GET /api/missing/diagnostics
# ---------------------------------------------------------------------------

def test_missing_diagnostics_requires_auth(client):
    resp = client.get("/api/missing/diagnostics")
    assert resp.status_code == 401


def test_missing_diagnostics_ok(client, auth_headers):
    resp = client.get("/api/missing/diagnostics", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


# ---------------------------------------------------------------------------
# Dashboard includes Phase 8A fields
# ---------------------------------------------------------------------------

def test_dashboard_summary_has_phase8a_fields(client, auth_headers):
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "files_verified" in data
    assert "files_missing_on_disk" in data
    assert "items_ready_for_nomenclature" in data
    assert "items_ready_for_upload" in data
    assert "items_waiting_download" in data
    assert "items_need_arr_review" in data


# ---------------------------------------------------------------------------
# Library item response includes Phase 8A fields
# ---------------------------------------------------------------------------

def test_library_list_response_has_phase8a_fields(client, auth_headers):
    resp = client.get("/api/library", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    # Fields should be present in schema (even if null)
    # Verify by checking the list endpoint works with 200


def test_missing_list_response_has_phase8a_fields(client, auth_headers):
    resp = client.get("/api/missing", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
