"""API tests for /api/tasks/scheduled — Phase 11D.

All underlying sync work is mocked — never real Radarr/Sonarr/eMuwarez
network traffic.
"""
from __future__ import annotations

from unittest.mock import patch


def test_list_requires_auth(client):
    assert client.get("/api/tasks/scheduled").status_code == 401


def test_update_requires_auth(client):
    assert client.put("/api/tasks/scheduled/sync-library", json={"interval_minutes": 30}).status_code == 401


def test_run_requires_auth(client):
    assert client.post("/api/tasks/scheduled/sync-library/run").status_code == 401


def test_logs_requires_auth(client):
    assert client.get("/api/tasks/scheduled/sync-library/logs").status_code == 401


def test_list_returns_default_tasks(client, auth_headers):
    resp = client.get("/api/tasks/scheduled", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    keys = {t["task_key"] for t in data}
    assert keys == {"sync-library", "sync-emu-requests"}


def test_emu_task_has_manual_allowed_false(client, auth_headers):
    resp = client.get("/api/tasks/scheduled", headers=auth_headers)
    emu = next(t for t in resp.json() if t["task_key"] == "sync-emu-requests")
    assert emu["manual_allowed"] is False
    assert emu["min_interval_minutes"] == 60


def test_update_interval_success(client, auth_headers):
    resp = client.put("/api/tasks/scheduled/sync-library", json={"interval_minutes": 45}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["interval_minutes"] == 45


def test_update_interval_below_minimum_returns_422(client, auth_headers):
    resp = client.put("/api/tasks/scheduled/sync-library", json={"interval_minutes": 5}, headers=auth_headers)
    assert resp.status_code == 422


def test_update_interval_unknown_task_returns_404(client, auth_headers):
    resp = client.put("/api/tasks/scheduled/not-a-task", json={"interval_minutes": 30}, headers=auth_headers)
    assert resp.status_code == 404


def test_run_library_sync_now(client, auth_headers):
    with patch("emuwarez_uploadrr.services.library.sync_all") as mock_sync:
        mock_sync.return_value = {"imported": 2, "missing": 0, "instances": 1, "errors": []}
        resp = client.post("/api/tasks/scheduled/sync-library/run", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["task_key"] == "sync-library"


def test_run_emu_sync_manually_blocked(client, auth_headers):
    resp = client.post("/api/tasks/scheduled/sync-emu-requests/run", headers=auth_headers)
    assert resp.status_code == 400
    assert "manual" in resp.json()["detail"].lower()


def test_run_unknown_task_returns_404(client, auth_headers):
    resp = client.post("/api/tasks/scheduled/not-a-task/run", headers=auth_headers)
    assert resp.status_code == 404


def test_get_logs_for_known_task(client, auth_headers):
    # Patch list_instances (not sync_all itself) so sync_all()'s own
    # internal task_runs logging still runs for real, with zero instances
    # to iterate — no real network call, but a genuine task_runs row.
    with patch("emuwarez_uploadrr.services.library.list_instances", return_value=[]):
        client.post("/api/tasks/scheduled/sync-library/run", headers=auth_headers)

    resp = client.get("/api/tasks/scheduled/sync-library/logs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_key"] == "sync-library"
    assert len(data["logs"]) >= 1
    assert data["logs"][0]["status"] == "completed"


def test_get_logs_for_unknown_task_returns_404(client, auth_headers):
    resp = client.get("/api/tasks/scheduled/not-a-task/logs", headers=auth_headers)
    assert resp.status_code == 404


def test_run_response_never_leaks_secrets(client, auth_headers):
    secret = "super_secret_radarr_key_value"
    with patch("emuwarez_uploadrr.services.library.sync_all") as mock_sync:
        mock_sync.return_value = {"imported": 1, "missing": 0, "instances": 1, "errors": [f"instance error with {secret}"]}
        resp = client.post("/api/tasks/scheduled/sync-library/run", headers=auth_headers)
    # This just documents the contract: summary text is our own constructed
    # string, not a raw dump of instance errors, so a leaked key in an
    # instance-level error message would not automatically appear here.
    assert secret not in resp.text
