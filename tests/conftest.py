"""Shared pytest fixtures.

Every test gets its own temp directory as CONFIG_DIR so the database is
isolated from the real ~/.config/emuwarez-renamer/ path.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point CONFIG_DIR to a per-test temp dir so each test starts with a fresh DB."""
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture
def client(isolated_db):
    """TestClient with a freshly created app (DB is already isolated)."""
    from emuwarez_uploadrr.web.app import create_app
    return TestClient(create_app())


@pytest.fixture
def admin_token(client):
    """Create admin user and return a valid session token."""
    resp = client.post("/api/setup/admin", json={
        "username": "testadmin",
        "password": "TestPass1!secret",
    })
    assert resp.status_code == 201, resp.text
    resp = client.post("/api/auth/login", json={
        "username": "testadmin",
        "password": "TestPass1!secret",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture
def auth_headers(admin_token):
    """Authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {admin_token}"}
