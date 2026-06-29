"""Tests for upload Phase 6D API endpoints: artifacts, retry, filters, dashboard counts.

All subprocess calls are mocked. No real Uploadrr execution.
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.upload_execution import (
    CONFIRMATION_TOKEN,
    create_upload_artifact,
)


def _make_mock_proc(returncode=0):
    proc = MagicMock()
    proc.pid = 9999
    proc.returncode = returncode
    proc.stdout = iter([])
    proc.stderr = iter([])
    proc.wait.return_value = returncode
    return proc


def _insert_job_db(conn, *, status="ready", source_path="/fake/movie.mkv"):
    cursor = conn.execute(
        """INSERT INTO upload_jobs
           (library_item_id, title, path, status, stage, source_path, created_at, updated_at)
           VALUES (NULL, 'API Test Movie', ?, ?, 'preflight', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (source_path, status, source_path),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_settings_db(conn, *, uploadrr_path="/fake/Uploadrr"):
    for key, val in [
        ("uploadrr_path", uploadrr_path),
        ("emu_api_key", "emu_key_test"),
        ("tmdb_api_key", "tmdb_key_test"),
    ]:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val))
    conn.commit()


# ---------------------------------------------------------------------------
# Artifacts endpoint
# ---------------------------------------------------------------------------

def test_artifacts_endpoint_requires_auth(client):
    resp = client.get("/api/uploads/1/artifacts")
    assert resp.status_code == 401


def test_artifacts_endpoint_returns_list(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    jid = _insert_job_db(conn, status="completed")
    create_upload_artifact(jid, "uploaded_url", url="https://emu.me/t/1", conn=conn)
    conn.close()

    resp = client.get(f"/api/uploads/{jid}/artifacts", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == jid
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["artifact_type"] == "uploaded_url"
    assert data["artifacts"][0]["url"] == "https://emu.me/t/1"


def test_artifacts_endpoint_no_secrets_in_response(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    jid = _insert_job_db(conn, status="completed")
    create_upload_artifact(jid, "command_preview", value="python upload.py movie.mkv", conn=conn)
    conn.close()

    resp = client.get(f"/api/uploads/{jid}/artifacts", headers=auth_headers)
    assert resp.status_code == 200
    # No raw API keys in response
    assert "emu_key" not in resp.text
    assert "tmdb_key" not in resp.text


def test_artifacts_endpoint_404_for_missing_job(client, auth_headers):
    resp = client.get("/api/uploads/9999/artifacts", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Retry endpoint
# ---------------------------------------------------------------------------

def test_retry_endpoint_requires_auth(client):
    resp = client.post("/api/uploads/1/retry", json={"dry_run": True, "start": False, "confirmation": None})
    assert resp.status_code == 401


def test_retry_endpoint_dry_run_no_execution(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    jid = _insert_job_db(conn, status="failed")
    conn.close()

    with patch("emuwarez_uploadrr.services.upload_execution.subprocess.Popen") as mock_popen:
        resp = client.post(f"/api/uploads/{jid}/retry", headers=auth_headers,
                           json={"dry_run": True, "start": False, "confirmation": None})

    mock_popen.assert_not_called()
    assert resp.status_code == 200


def test_retry_endpoint_blocked_without_confirmation(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    jid = _insert_job_db(conn, status="failed")
    conn.close()

    resp = client.post(f"/api/uploads/{jid}/retry", headers=auth_headers,
                       json={"dry_run": False, "start": True, "confirmation": "WRONG"})
    assert resp.status_code == 400


def test_retry_endpoint_with_confirmation_mocked(client, auth_headers, isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    _insert_settings_db(conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job_db(conn, status="failed", source_path=str(src))
    conn.close()

    mock_proc = _make_mock_proc(returncode=0)
    patcher = patch("emuwarez_uploadrr.services.upload_execution.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        resp = client.post(f"/api/uploads/{jid}/retry", headers=auth_headers,
                           json={"dry_run": False, "start": True, "confirmation": CONFIRMATION_TOKEN})
        time.sleep(0.4)  # Let background thread finish while mock is still active
    finally:
        patcher.stop()

    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] in ("started", "dry_run")


def test_retry_endpoint_blocks_completed_job(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    jid = _insert_job_db(conn, status="completed")
    conn.close()

    resp = client.post(f"/api/uploads/{jid}/retry", headers=auth_headers,
                       json={"dry_run": False, "start": True, "confirmation": CONFIRMATION_TOKEN})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Upload list with filters
# ---------------------------------------------------------------------------

def test_upload_list_requires_auth(client):
    resp = client.get("/api/uploads")
    assert resp.status_code == 401


def test_upload_list_filter_by_status(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    _insert_job_db(conn, status="ready")
    _insert_job_db(conn, status="failed")
    _insert_job_db(conn, status="failed")
    conn.close()

    resp = client.get("/api/uploads?status=failed", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(j["status"] == "failed" for j in data)


def test_upload_list_filter_by_limit(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    for _ in range(5):
        _insert_job_db(conn)
    conn.close()

    resp = client.get("/api/uploads?limit=2", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


def test_upload_list_all_statuses(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    _insert_job_db(conn, status="ready")
    _insert_job_db(conn, status="completed")
    conn.close()

    resp = client.get("/api/uploads", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# Dashboard upload counts
# ---------------------------------------------------------------------------

def test_dashboard_summary_has_upload_counts(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    _insert_job_db(conn, status="ready")
    _insert_job_db(conn, status="running")
    _insert_job_db(conn, status="completed")
    _insert_job_db(conn, status="failed")
    conn.close()

    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["uploads_ready"] == 1
    assert data["uploads_running"] == 1
    assert data["uploads_completed"] == 1
    assert data["uploads_failed"] == 1


def test_dashboard_summary_zero_when_no_jobs(client, auth_headers):
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["uploads_ready"] == 0
    assert data["uploads_completed"] == 0
