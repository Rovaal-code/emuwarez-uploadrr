"""Tests for upload execution API endpoints — Phase 6C."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.upload_execution import CONFIRMATION_TOKEN, DELETE_CONFIRMATION_TOKEN


@pytest.fixture
def db_conn(client):
    """Use the same DB file as the test client app."""
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _insert_job(conn, *, status="ready", source_path="/fake/movie.mkv"):
    cursor = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, title, path, status, stage, source_path, created_at, updated_at)
           VALUES (NULL, 'Test Movie', ?, ?, 'preflight', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (source_path or "", status, source_path),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_settings(conn, uploadrr_path="/fake/Uploadrr"):
    for key, val in [
        ("uploadrr_path", uploadrr_path),
        ("emu_api_key", "emu_secret_key"),
        ("tmdb_api_key", "tmdb_secret_key"),
    ]:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val))
    conn.commit()


# ---------------------------------------------------------------------------
# GET /api/uploads — requires auth
# ---------------------------------------------------------------------------

def test_get_uploads_without_token(client):
    resp = client.get("/api/uploads")
    assert resp.status_code == 401


def test_get_uploads_with_token(client, auth_headers, db_conn):
    resp = client.get("/api/uploads", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# GET /api/uploads/{id}
# ---------------------------------------------------------------------------

def test_get_upload_not_found(client, auth_headers):
    resp = client.get("/api/uploads/999", headers=auth_headers)
    assert resp.status_code == 404


def test_get_upload_found(client, auth_headers, db_conn):
    jid = _insert_job(db_conn)
    resp = client.get(f"/api/uploads/{jid}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == jid
    assert data["status"] == "ready"


# ---------------------------------------------------------------------------
# GET /api/uploads/{id}/logs
# ---------------------------------------------------------------------------

def test_get_upload_logs_not_found(client, auth_headers):
    resp = client.get("/api/uploads/999/logs", headers=auth_headers)
    assert resp.status_code == 404


def test_get_upload_logs_empty(client, auth_headers, db_conn):
    jid = _insert_job(db_conn)
    resp = client.get(f"/api/uploads/{jid}/logs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == jid
    assert data["logs"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# POST /api/uploads/{id}/start
# ---------------------------------------------------------------------------

def test_start_without_token(client, db_conn):
    jid = _insert_job(db_conn)
    resp = client.post(f"/api/uploads/{jid}/start", json={"dry_run": True, "start": False, "confirmation": None})
    assert resp.status_code == 401


def test_start_dry_run_does_not_call_subprocess(client, auth_headers, db_conn):
    jid = _insert_job(db_conn)
    with patch("subprocess.Popen") as mock_popen:
        resp = client.post(
            f"/api/uploads/{jid}/start",
            json={"dry_run": True, "start": False, "confirmation": None},
            headers=auth_headers,
        )
    mock_popen.assert_not_called()
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["action"] == "dry_run"


def test_start_without_confirmation_returns_400(client, auth_headers, db_conn):
    jid = _insert_job(db_conn)
    resp = client.post(
        f"/api/uploads/{jid}/start",
        json={"dry_run": False, "start": True, "confirmation": None},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_start_wrong_confirmation_returns_400(client, auth_headers, db_conn):
    jid = _insert_job(db_conn)
    resp = client.post(
        f"/api/uploads/{jid}/start",
        json={"dry_run": False, "start": True, "confirmation": "WRONG"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@patch("emuwarez_uploadrr.services.upload_execution._run_uploadrr_subprocess")
def test_start_real_with_correct_confirmation_calls_runner(mock_run, client, auth_headers, db_conn, tmp_path):
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# fake")
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, source_path=str(src))

    resp = client.post(
        f"/api/uploads/{jid}/start",
        json={"dry_run": False, "start": True, "confirmation": CONFIRMATION_TOKEN},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "started"
    assert data["status"] == "running"
    mock_run.assert_called_once()


def test_start_real_no_uploadrr_config_returns_400(client, auth_headers, db_conn):
    jid = _insert_job(db_conn)
    resp = client.post(
        f"/api/uploads/{jid}/start",
        json={"dry_run": False, "start": True, "confirmation": CONFIRMATION_TOKEN},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/uploads/{id}/cancel
# ---------------------------------------------------------------------------

def test_cancel_non_running_job(client, auth_headers, db_conn):
    jid = _insert_job(db_conn, status="ready")
    resp = client.post(f"/api/uploads/{jid}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False


def test_cancel_not_found(client, auth_headers):
    resp = client.post("/api/uploads/999/cancel", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False


def test_cancel_without_token(client, db_conn):
    jid = _insert_job(db_conn)
    resp = client.post(f"/api/uploads/{jid}/cancel", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/uploads/{id}/delete
# ---------------------------------------------------------------------------

def test_delete_without_auth(client, db_conn):
    jid = _insert_job(db_conn, status="failed")
    resp = client.post(f"/api/uploads/{jid}/delete", json={"confirmation": DELETE_CONFIRMATION_TOKEN})
    assert resp.status_code == 401


def test_delete_requires_confirmation_token(client, auth_headers, db_conn):
    jid = _insert_job(db_conn, status="failed")
    resp = client.post(f"/api/uploads/{jid}/delete", json={}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "confirmation_required"


def test_delete_blocked_for_running_job(client, auth_headers, db_conn):
    jid = _insert_job(db_conn, status="running")
    resp = client.post(
        f"/api/uploads/{jid}/delete", json={"confirmation": DELETE_CONFIRMATION_TOKEN}, headers=auth_headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_status"


def test_delete_not_found(client, auth_headers):
    resp = client.post(
        "/api/uploads/999/delete", json={"confirmation": DELETE_CONFIRMATION_TOKEN}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_delete_cancelled_job_ok(client, auth_headers, db_conn):
    jid = _insert_job(db_conn, status="cancelled")
    resp = client.post(
        f"/api/uploads/{jid}/delete", json={"confirmation": DELETE_CONFIRMATION_TOKEN}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    get_resp = client.get(f"/api/uploads/{jid}", headers=auth_headers)
    assert get_resp.status_code == 404
