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
# Health / Runtime — public, no auth
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


def test_runtime_endpoint(client):
    response = client.get("/api/runtime")
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "eMuwarez Uploadrr"
    assert "config_dir" in data
    assert "database_path" in data
    assert isinstance(data["cli_available"], bool)
    assert isinstance(data["uploadrr_runtime_present"], bool)


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
# Contract — public, no auth
# ---------------------------------------------------------------------------

def test_contract_summary_endpoint(client):
    response = client.get("/api/contract")
    assert response.status_code == 200
    data = response.json()
    assert "sections" in data
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) > 0


def test_contract_json_endpoint(client):
    response = client.get("/api/contract/json")
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        data = response.json()
        assert "product" in data
        assert "api_endpoints" in data


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


# Phase 4: these are now real endpoints (no longer placeholders)
@pytest.mark.parametrize("path", [
    "/api/dashboard/summary",
    "/api/dashboard/activity",
    "/api/instances",
    "/api/library",
    "/api/missing",
])
def test_real_endpoints_return_200_with_auth(client, auth_headers, path):
    response = client.get(path, headers=auth_headers)
    assert response.status_code == 200


# Phase 3+ placeholders that still return implemented=False
@pytest.mark.parametrize("path", [
    "/api/requests",
    "/api/uploads",
    "/api/tasks",
    "/api/logs",
    "/api/config",
])
def test_placeholder_returns_stub_with_auth(client, auth_headers, path):
    response = client.get(path, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["implemented"] is False


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
