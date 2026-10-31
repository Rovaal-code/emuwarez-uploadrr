"""Tests for the FastAPI web backend — Phase 2 base + Phase 3 auth integration.

Run with:
    .venv/bin/pytest -q
    # or a specific file:
    .venv/bin/pytest tests/test_web_app.py -v
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from emuwarez_uploadrr.web.app import create_app


# conftest.py supplies `client` and `auth_headers` via shared fixtures.
# The `isolated_db` autouse fixture ensures each test uses a fresh temp DB.


# ---------------------------------------------------------------------------
# Health — public, no auth
# ---------------------------------------------------------------------------

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "eMuwarez Uploadrr"
    assert "version" in data
    assert "database" in data
    assert "initialized" in data


def test_api_runtime_ya_no_existe(client, auth_headers):
    """Era público y enseñaba la ruta de la base y el texto crudo del error."""
    assert client.get("/api/runtime").status_code == 404
    assert client.get("/api/runtime", headers=auth_headers).status_code == 404


# ---------------------------------------------------------------------------
# Setup status — public, no auth
# ---------------------------------------------------------------------------

def test_setup_status_endpoint(client):
    response = client.get("/api/setup/status")
    assert response.status_code == 200
    data = response.json()
    assert "initialized" in data
    assert isinstance(data["initialized"], bool)
    assert "radarr_instances" in data
    assert "sonarr_instances" in data


# ---------------------------------------------------------------------------
# Protected placeholders — return 401 without token (Phase 3 behavior)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/dashboard/summary",
    "/api/dashboard/activity",
    "/api/instances",
    "/api/library",
    "/api/missing",
    "/api/requests",
    "/api/uploads",
    "/api/tasks",
    "/api/logs",
    "/api/auth/me",
    "/api/config",
])
def test_protected_endpoints_require_auth(client, path):
    response = client.get(path)
    assert response.status_code == 401


# Phase 4+5B+6A: these are now real endpoints (no longer placeholders)
@pytest.mark.parametrize("path", [
    "/api/dashboard/summary",
    "/api/dashboard/activity",
    "/api/instances",
    "/api/library",
    "/api/missing",
    "/api/requests",
    "/api/uploads",
])
def test_real_endpoints_return_200_with_auth(client, auth_headers, path):
    response = client.get(path, headers=auth_headers)
    assert response.status_code == 200


# Phase 3+ placeholders that still return implemented=False
@pytest.mark.parametrize("path", [
    "/api/tasks",
    "/api/config",
])
def test_placeholder_returns_stub_with_auth(client, auth_headers, path):
    response = client.get(path, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["implemented"] is False


def test_logs_endpoint_returns_captured_records(client, auth_headers):
    # /api/logs is now a real endpoint backed by the in-memory capture buffer.
    response = client.get("/api/logs?limit=50", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data and isinstance(data["items"], list)


def test_create_emu_request_requires_auth(client):
    response = client.post("/api/missing/1/create-emu-request")
    assert response.status_code == 401


def test_create_emu_request_stub_with_auth(client, auth_headers):
    response = client.post("/api/missing/1/create-emu-request", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["implemented"] is False
    assert data["stub"] is True
    assert "DevTools" in data["message"] or "endpoint" in data["message"].lower() or "pendiente" in data["message"].lower()


# ---------------------------------------------------------------------------
# OpenAPI schema — public, no auth
# ---------------------------------------------------------------------------

def test_openapi_schema(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "eMuwarez Uploadrr"


# ---------------------------------------------------------------------------
# Phase 5A — static serving (backend works without frontend/dist)
# ---------------------------------------------------------------------------

def test_health_works_without_frontend_dist(isolated_db):
    """create_app() must not fail if frontend/dist does not exist."""
    import os
    import tempfile
    from emuwarez_uploadrr.web.app import create_app as _create_app
    # Create app without touching FRONTEND_DIST — it may or may not exist
    app = _create_app()
    from fastapi.testclient import TestClient
    os.environ["CONFIG_DIR"] = str(isolated_db)
    c = TestClient(app)
    resp = c.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
