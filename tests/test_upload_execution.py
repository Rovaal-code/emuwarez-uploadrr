"""Tests for upload_execution service — Phase 6C.

All subprocess calls are mocked: no real Uploadrr execution happens.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.upload_execution import (
    CONFIRMATION_TOKEN,
    append_upload_log,
    cancel_upload_job,
    get_upload_job,
    get_upload_job_logs,
    list_upload_jobs,
    start_upload_job,
    validate_upload_job_start,
)


@pytest.fixture
def db_conn(isolated_db):
    """Use the same DB file that the service's _get_db_conn() would use."""
    from emuwarez_uploadrr.database import db_path
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _insert_job(conn, *, status="ready", source_path="/fake/movie.mkv", prepared_path=None):
    cursor = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, title, path, status, stage, source_path, prepared_path, created_at, updated_at)
           VALUES (NULL, 'Test Movie', ?, ?, 'preflight', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (source_path or "", status, source_path, prepared_path),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_settings(conn, *, uploadrr_path="/fake/Uploadrr", emu_key="emu_key_xxx", tmdb_key="tmdb_key_yyy"):
    for key, val in [("uploadrr_path", uploadrr_path), ("emu_api_key", emu_key), ("tmdb_api_key", tmdb_key)]:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val))
    conn.commit()


# ---------------------------------------------------------------------------
# validate_upload_job_start
# ---------------------------------------------------------------------------

def test_validate_job_not_found(db_conn):
    result = validate_upload_job_start(999, conn=db_conn)
    assert not result["valid"]
    assert any("no encontrado" in e.lower() for e in result["errors"])


def test_validate_job_not_ready(db_conn):
    jid = _insert_job(db_conn, status="running")
    result = validate_upload_job_start(jid, conn=db_conn)
    assert not result["valid"]
    assert any("ejecución" in e.lower() or "running" in e.lower() for e in result["errors"])


def test_validate_job_missing_uploadrr_config(db_conn):
    jid = _insert_job(db_conn)
    result = validate_upload_job_start(jid, conn=db_conn)
    assert not result["valid"]
    assert any("uploadrr" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# start_upload_job — dry_run
# ---------------------------------------------------------------------------

def test_start_dry_run_does_not_call_subprocess(db_conn):
    jid = _insert_job(db_conn)
    with patch("subprocess.Popen") as mock_popen:
        result = start_upload_job(jid, dry_run=True, conn=db_conn)
    mock_popen.assert_not_called()
    assert result["dry_run"] is True
    assert result["action"] == "dry_run"


def test_start_no_start_flag_returns_blocked(db_conn):
    jid = _insert_job(db_conn)
    result = start_upload_job(jid, dry_run=False, start=False, conn=db_conn)
    assert result["action"] == "blocked"


def test_start_wrong_confirmation_returns_blocked(db_conn):
    jid = _insert_job(db_conn)
    result = start_upload_job(jid, dry_run=False, start=True, confirmation="WRONG_TOKEN", conn=db_conn)
    assert result["action"] == "blocked"
    assert result["error"] == "confirmation_required"


def test_start_no_confirmation_returns_blocked(db_conn):
    jid = _insert_job(db_conn)
    result = start_upload_job(jid, dry_run=False, start=True, confirmation=None, conn=db_conn)
    assert result["action"] == "blocked"
    assert result["error"] == "confirmation_required"


# ---------------------------------------------------------------------------
# start_upload_job — real execution (mocked)
# ---------------------------------------------------------------------------

def _make_mock_proc(returncode=0, stdout_lines=None, stderr_lines=None):
    mock = MagicMock()
    mock.pid = 12345
    mock.returncode = returncode
    mock.wait.return_value = returncode
    stdout_data = "\n".join(stdout_lines or ["Upload complete"]) + "\n"
    stderr_data = "\n".join(stderr_lines or []) + "\n"
    mock.stdout = iter(stdout_data.splitlines(keepends=True))
    mock.stderr = iter(stderr_data.splitlines(keepends=True))
    return mock


def test_start_real_validation_fails_when_no_config(db_conn):
    jid = _insert_job(db_conn)
    with patch("subprocess.Popen") as mock_popen:
        result = start_upload_job(
            jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn
        )
    # No settings configured → validation fails → blocked
    mock_popen.assert_not_called()
    assert result["action"] == "blocked"
    assert result["error"] == "validation_failed"


@patch("emuwarez_uploadrr.services.upload_execution._run_uploadrr_subprocess")
def test_start_real_with_valid_setup_starts_thread(mock_run, db_conn, tmp_path):
    uploadrr_path = tmp_path / "Uploadrr"
    uploadrr_path.mkdir()
    (uploadrr_path / "upload.py").write_text("# fake")
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    _insert_settings(db_conn, uploadrr_path=str(uploadrr_path))
    jid = _insert_job(db_conn, source_path=str(src))

    result = start_upload_job(
        jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn
    )
    assert result["action"] == "started"
    assert result["status"] == "running"
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# subprocess safety — shell=True never used
# ---------------------------------------------------------------------------

def test_subprocess_never_called_with_shell_true(db_conn, tmp_path):
    """Verify our wrapper never passes shell=True to Popen."""
    from emuwarez_uploadrr.services.upload_execution import _run_uploadrr_subprocess as _real_run
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0)
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        _real_run(jid, {
            "executable": "/usr/bin/python3",
            "args": [str(tmp_path / "upload.py"), str(src)],
            "cwd": str(tmp_path),
            "command_preview": "/usr/bin/python3 upload.py movie.mkv",
        }, [])

    assert mock_popen.call_args is not None
    call_kwargs = mock_popen.call_args.kwargs or {}
    assert call_kwargs.get("shell", False) is False


# ---------------------------------------------------------------------------
# _run_uploadrr_subprocess — returncode handling
# ---------------------------------------------------------------------------

def test_run_subprocess_success_sets_completed(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0, stdout_lines=["Upload successful"])

    with patch("subprocess.Popen", return_value=mock_proc):
        from emuwarez_uploadrr.services.upload_execution import _run_uploadrr_subprocess
        _run_uploadrr_subprocess(
            jid,
            {
                "executable": "/usr/bin/python3",
                "args": ["/fake/upload.py", str(src)],
                "cwd": str(tmp_path),
                "command_preview": "python3 upload.py movie.mkv",
            },
            [],
        )

    job = get_upload_job(jid, conn=db_conn)
    assert job["status"] == "completed"
    assert job["exit_code"] == 0
    assert job["finished_at"] is not None


def test_run_subprocess_failure_sets_failed(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=1, stderr_lines=["Error: upload failed"])

    with patch("subprocess.Popen", return_value=mock_proc):
        from emuwarez_uploadrr.services.upload_execution import _run_uploadrr_subprocess
        _run_uploadrr_subprocess(
            jid,
            {
                "executable": "/usr/bin/python3",
                "args": ["/fake/upload.py", str(src)],
                "cwd": str(tmp_path),
                "command_preview": "python3 upload.py movie.mkv",
            },
            [],
        )

    job = get_upload_job(jid, conn=db_conn)
    assert job["status"] == "failed"
    assert job["exit_code"] == 1
    assert job["error_message"] is not None


# ---------------------------------------------------------------------------
# Logs stored correctly and secrets redacted
# ---------------------------------------------------------------------------

def test_stdout_saved_as_logs(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0, stdout_lines=["Processing file", "Done"])

    with patch("subprocess.Popen", return_value=mock_proc):
        from emuwarez_uploadrr.services.upload_execution import _run_uploadrr_subprocess
        _run_uploadrr_subprocess(
            jid,
            {"executable": "/usr/bin/python3", "args": [], "cwd": str(tmp_path), "command_preview": ""},
            [],
        )

    result = get_upload_job_logs(jid, conn=db_conn)
    messages = [log["message"] for log in result["logs"]]
    assert any("Processing file" in m for m in messages)
    assert any("Done" in m for m in messages)


def test_secrets_redacted_in_logs(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    secret = "mysupersecretapikey1234"
    mock_proc = _make_mock_proc(
        returncode=0,
        stdout_lines=[f"Uploading with token={secret}"],
    )

    with patch("subprocess.Popen", return_value=mock_proc):
        from emuwarez_uploadrr.services.upload_execution import _run_uploadrr_subprocess
        _run_uploadrr_subprocess(
            jid,
            {"executable": "/usr/bin/python3", "args": [], "cwd": str(tmp_path), "command_preview": ""},
            [secret],
        )

    result = get_upload_job_logs(jid, conn=db_conn)
    all_messages = " ".join(log["message"] for log in result["logs"])
    assert secret not in all_messages
    assert "***REDACTED***" in all_messages


# ---------------------------------------------------------------------------
# cancel_upload_job
# ---------------------------------------------------------------------------

def test_cancel_not_running_job(db_conn):
    jid = _insert_job(db_conn, status="ready")
    result = cancel_upload_job(jid, conn=db_conn)
    assert not result["ok"]
    assert "no está en ejecución" in result["message"].lower() or "running" in result["message"].lower()


def test_cancel_not_found(db_conn):
    result = cancel_upload_job(999, conn=db_conn)
    assert not result["ok"]


# ---------------------------------------------------------------------------
# append and retrieve logs
# ---------------------------------------------------------------------------

def test_append_and_get_logs(db_conn):
    jid = _insert_job(db_conn)
    append_upload_log(jid, "info", "Test log entry", stream="system", conn=db_conn)
    append_upload_log(jid, "error", "Error entry", stream="stderr", conn=db_conn)

    result = get_upload_job_logs(jid, conn=db_conn)
    assert result["total"] == 2
    messages = [l["message"] for l in result["logs"]]
    assert "Test log entry" in messages
    assert "Error entry" in messages


# ---------------------------------------------------------------------------
# list_upload_jobs
# ---------------------------------------------------------------------------

def test_list_upload_jobs(db_conn):
    _insert_job(db_conn, status="ready")
    _insert_job(db_conn, status="completed")
    jobs = list_upload_jobs(conn=db_conn)
    assert len(jobs) == 2
