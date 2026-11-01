"""Tests for upload lifecycle: duration, results, artifacts, retry — Phase 6D.

All subprocess calls are mocked. No real Uploadrr execution.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.upload_execution import (
    CONFIRMATION_TOKEN,
    get_upload_job,
    get_upload_job_artifacts,
    create_upload_artifact,
    list_upload_jobs,
    retry_upload_job,
    start_upload_job,
)


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _insert_job(conn, *, status="ready", source_path="/fake/movie.mkv", prepared_path=None, exit_code=None):
    cursor = conn.execute(
        """INSERT INTO upload_jobs
           (library_item_id, title, path, status, stage, source_path, prepared_path,
            exit_code, created_at, updated_at)
           VALUES (NULL, 'Test Movie', ?, ?, 'preflight', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (source_path or "", status, source_path, prepared_path, exit_code),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_settings(conn, *, uploadrr_path="/fake/Uploadrr", emu_key="emu_key_xxx", tmdb_key="tmdb_key_yyy"):
    for key, val in [("uploadrr_path", uploadrr_path), ("emu_api_key", emu_key), ("tmdb_api_key", tmdb_key)]:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val))
    conn.commit()


def _make_mock_proc(returncode=0, stdout_lines=None, stderr_lines=None):
    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = returncode
    proc.stdout = iter(stdout_lines or [])
    proc.stderr = iter(stderr_lines or [])
    proc.wait.return_value = returncode
    return proc


# ---------------------------------------------------------------------------
# Lifecycle: duration, timestamps, status
# Use patcher.start()/stop() so mock outlasts background thread
# ---------------------------------------------------------------------------

def test_completed_job_has_duration(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0, stdout_lines=["Done\n"])
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
        assert result["action"] == "started"
        time.sleep(0.6)
    finally:
        patcher.stop()

    job = get_upload_job(jid)
    assert job["status"] == "completed"
    assert job["duration_seconds"] is not None
    assert job["duration_seconds"] >= 0


def test_completed_job_has_last_success_at(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0)
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
        time.sleep(0.6)
    finally:
        patcher.stop()

    job = get_upload_job(jid)
    assert job["last_success_at"] is not None


def test_failed_job_has_error_message(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=1, stderr_lines=["ERROR: upload failed\n"])
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
        time.sleep(0.6)
    finally:
        patcher.stop()

    job = get_upload_job(jid)
    assert job["status"] == "failed"
    assert job["error_message"] is not None


def test_failed_job_has_last_error_at(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=2, stderr_lines=["ERR\n"])
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
        time.sleep(0.6)
    finally:
        patcher.stop()

    job = get_upload_job(jid)
    assert job["last_error_at"] is not None


def test_safe_command_json_no_secrets(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    emu_key = "super_secret_emu_key_123"
    tmdb_key = "tmdb_key_456"
    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path), emu_key=emu_key, tmdb_key=tmdb_key)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0)
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
        time.sleep(0.6)
    finally:
        patcher.stop()

    job = get_upload_job(jid)
    safe_cmd = job.get("safe_command_json") or ""
    assert emu_key not in safe_cmd
    assert tmdb_key not in safe_cmd


def test_artifacts_created_on_url_detected(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(
        returncode=0,
        stdout_lines=["Torrent URL: https://emuwarez.me/torrents/99999\n"],
    )
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
        time.sleep(0.6)
    finally:
        patcher.stop()

    job = get_upload_job(jid)
    assert job["result_url"] == "https://emuwarez.me/torrents/99999"
    artifacts = get_upload_job_artifacts(jid)
    artifact_types = [a["artifact_type"] for a in artifacts]
    assert "uploaded_url" in artifact_types


# ---------------------------------------------------------------------------
# create_upload_artifact / get_upload_job_artifacts
# ---------------------------------------------------------------------------

def test_create_artifact_and_retrieve(db_conn):
    jid = _insert_job(db_conn, status="completed")
    create_upload_artifact(jid, "torrent_url", url="https://emu.me/t/1", name="torrent")
    artifacts = get_upload_job_artifacts(jid)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "torrent_url"
    assert artifacts[0]["url"] == "https://emu.me/t/1"


# ---------------------------------------------------------------------------
# retry_upload_job
# ---------------------------------------------------------------------------

def test_retry_fails_on_running_job(db_conn):
    jid = _insert_job(db_conn, status="running")
    result = retry_upload_job(jid)
    assert result.get("error") == "invalid_status"


def test_retry_fails_on_completed_job(db_conn):
    jid = _insert_job(db_conn, status="completed")
    result = retry_upload_job(jid)
    assert result.get("error") == "invalid_status"


def test_retry_dry_run_no_subprocess(db_conn):
    jid = _insert_job(db_conn, status="failed")
    with patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen") as mock_popen:
        result = retry_upload_job(jid, dry_run=True)
    mock_popen.assert_not_called()
    assert result.get("action") == "dry_run"
    assert result.get("dry_run") is True


def test_retry_creates_new_job_not_mutates(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, status="failed", source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0)
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        result = retry_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN)
        new_job_id = result.get("new_job_id")
        time.sleep(0.5)
    finally:
        patcher.stop()

    assert new_job_id is not None
    assert new_job_id != jid

    # Original job must NOT be mutated
    original_after = get_upload_job(jid)
    assert original_after["status"] == "failed"


def test_retry_requires_confirmation(db_conn):
    jid = _insert_job(db_conn, status="failed")
    result = retry_upload_job(jid, dry_run=False, start=True, confirmation="WRONG")
    assert result.get("error") == "confirmation_required"


def test_retry_with_confirmation_creates_job_with_metadata(db_conn, tmp_path):
    """Verify retry creates a new job with correct retry metadata."""
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"x")
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# stub")

    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, status="cancelled", source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0)
    patcher = patch("emuwarez_uploadrr.services.upload_execution.ejecucion.subprocess.Popen", return_value=mock_proc)
    patcher.start()
    try:
        result = retry_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN)
        new_job_id = result.get("new_job_id")
        time.sleep(0.5)
    finally:
        patcher.stop()

    assert new_job_id is not None
    new_job = get_upload_job(new_job_id)
    assert new_job["retry_of_job_id"] == jid
    assert new_job["retry_count"] == 1


def test_retry_not_found(db_conn):
    result = retry_upload_job(9999)
    assert result.get("error") == "not_found"


# ---------------------------------------------------------------------------
# list_upload_jobs with filters
# ---------------------------------------------------------------------------

def test_list_jobs_filter_by_status(db_conn):
    _insert_job(db_conn, status="ready")
    _insert_job(db_conn, status="failed")
    _insert_job(db_conn, status="failed")

    failed = list_upload_jobs(filters={"status": "failed"}, conn=db_conn)
    ready = list_upload_jobs(filters={"status": "ready"}, conn=db_conn)
    assert len(failed) == 2
    assert len(ready) == 1


def test_list_jobs_filter_by_limit(db_conn):
    for _ in range(5):
        _insert_job(db_conn)
    jobs = list_upload_jobs(filters={"limit": 2}, conn=db_conn)
    assert len(jobs) <= 2
