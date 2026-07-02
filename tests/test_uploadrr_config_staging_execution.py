"""Tests for config.yaml staging/restore around real execution — Phase 10F.

Uses the fake Uploadrr-EMU runner only (tests/fixtures/fake_uploadrr_emu.py).
Never touches a real Uploadrr-EMU install or its real config.yaml.
"""
from __future__ import annotations

import json
import time

import pytest

from emuwarez_uploadrr.database import connect, init_db, db_path
from emuwarez_uploadrr.services.upload_execution import (
    CONFIRMATION_TOKEN,
    get_upload_job,
    get_upload_job_logs,
    start_upload_job,
)

TMDB_SECRET = "tmdb_super_secret_key_000111"
EMU_SECRET = "emu_super_secret_key_222333"


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _insert_settings(conn, uploadrr_dir, python_path, *, timeout=None):
    settings = {
        "uploadrr.path": str(uploadrr_dir),
        "uploadrr.python_path": python_path,
        "tmdb.api_key": TMDB_SECRET,
        "emu.api_key": EMU_SECRET,
    }
    if timeout is not None:
        settings["uploadrr.timeout"] = str(timeout)
    for key, val in settings.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val))
    conn.commit()


def _insert_job(conn, *, prepared_path, title="Test Movie 2024"):
    cmd_json = json.dumps({"category": "movie", "tmdb_id": "12345", "resolution": "1080p", "title": title})
    cursor = conn.execute(
        """INSERT INTO upload_jobs
           (library_item_id, title, path, status, stage, source_path, prepared_path,
            uploadrr_command_json, created_at, updated_at)
           VALUES (NULL, ?, ?, 'ready', 'preflight', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (title, prepared_path, prepared_path, prepared_path, cmd_json),
    )
    conn.commit()
    return cursor.lastrowid


def _wait_for_terminal(job_id, conn, timeout=10):
    deadline = time.monotonic() + timeout
    job = None
    while time.monotonic() < deadline:
        job = get_upload_job(job_id, conn=conn)
        if job["status"] in ("completed", "failed", "cancelled"):
            # Grace period: let the background thread's `finally` block
            # (config restore + its own log writes) finish before the
            # caller's isolated_db tmp_path is torn down.
            time.sleep(0.3)
            return job
        time.sleep(0.1)
    raise AssertionError(f"Job {job_id} never reached a terminal status (last: {job['status'] if job else '?'})")


def test_config_staged_and_restored_on_success(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    config_path = fake_uploadrr_emu_dir / "data" / "config.yaml"
    original_content = config_path.read_text()

    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    assert result["action"] == "started"
    job = _wait_for_terminal(jid, db_conn)
    assert job["status"] == "completed"

    # config.yaml must be back to its original (pre-staging) content.
    assert config_path.read_text() == original_content
    # A backup file should exist as evidence that staging/restore happened.
    assert config_path.with_suffix(".yaml.bak").exists()


def test_config_restored_on_failure(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    monkeypatch.setenv("FAKE_UPLOADRR_FAIL", "1")
    config_path = fake_uploadrr_emu_dir / "data" / "config.yaml"
    original_content = config_path.read_text()

    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    job = _wait_for_terminal(jid, db_conn)
    assert job["status"] == "failed"

    assert config_path.read_text() == original_content


def test_config_restored_on_timeout(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    monkeypatch.setenv("FAKE_UPLOADRR_SLEEP", "5")
    config_path = fake_uploadrr_emu_dir / "data" / "config.yaml"
    original_content = config_path.read_text()

    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path, timeout=1)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    job = _wait_for_terminal(jid, db_conn, timeout=15)
    assert job["status"] == "failed"
    assert job["stage"] == "timeout"

    assert config_path.read_text() == original_content


def test_secrets_never_appear_in_logs_or_preview(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    assert TMDB_SECRET not in (result.get("command_preview") or "")
    assert EMU_SECRET not in (result.get("command_preview") or "")

    job = _wait_for_terminal(jid, db_conn)
    assert job["status"] == "completed"

    logs = get_upload_job_logs(jid, conn=db_conn)
    all_messages = " ".join(log["message"] for log in logs["logs"])
    assert TMDB_SECRET not in all_messages
    assert EMU_SECRET not in all_messages

    assert job.get("safe_command_json")
    assert TMDB_SECRET not in job["safe_command_json"]
    assert EMU_SECRET not in job["safe_command_json"]


def test_no_config_yaml_skips_staging_without_error(db_conn, tmp_path, fake_uploadrr_python_path):
    """If Uploadrr-EMU has no data/config.yaml yet, execution still runs
    (fake runner does not need it) and nothing is restored — no crash."""
    uploadrr_dir = tmp_path / "Uploadrr-no-config"
    uploadrr_dir.mkdir()
    import shutil
    from pathlib import Path
    shutil.copy(Path(__file__).parent / "fixtures" / "fake_uploadrr_emu.py", uploadrr_dir / "upload.py")

    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, uploadrr_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    job = _wait_for_terminal(jid, db_conn)
    assert job["status"] == "completed"

    logs = get_upload_job_logs(jid, conn=db_conn)
    all_messages = " ".join(log["message"] for log in logs["logs"])
    assert "config.yaml no encontrado" in all_messages
