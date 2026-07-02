"""Tests for progress-phase mapping and job detail/logs surfacing — Phase 10F."""
from __future__ import annotations

import json
import time

import pytest

from emuwarez_uploadrr.database import connect, init_db, db_path
from emuwarez_uploadrr.services.upload_execution import (
    CONFIRMATION_TOKEN,
    PROGRESS_PHASES,
    compute_progress_phase,
    get_upload_job,
    start_upload_job,
)


# ---------------------------------------------------------------------------
# compute_progress_phase — pure mapping, no I/O
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,stage,expected", [
    ("draft", None, "preflight"),
    ("preflight", "preflight", "preflight"),
    ("ready", None, "preflight"),
    ("running", "config_staging", "config_staging"),
    ("running", "running", "running"),
    ("running", "finalizing", "finalizing"),
    ("completed", "finished", "succeeded"),
    ("failed", "failed", "failed"),
    ("failed", "timeout", "timeout"),
    ("cancelled", "cancelled", "cancelled"),
    ("cancelled", "running", "cancelled"),
])
def test_compute_progress_phase_mapping(status, stage, expected):
    assert compute_progress_phase(status, stage) == expected
    assert expected in PROGRESS_PHASES


def test_unknown_status_falls_back_to_queued():
    assert compute_progress_phase("something_unexpected", None) == "queued"


# ---------------------------------------------------------------------------
# API — job detail exposes progress_phase / runtime_type / command_preview
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(client):
    """Use the same DB file as the test client app."""
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _insert_settings(conn, uploadrr_dir, python_path):
    for key, val in [
        ("uploadrr.path", str(uploadrr_dir)),
        ("uploadrr.python_path", python_path),
        ("tmdb.api_key", "tmdb_key"),
        ("emu.api_key", "emu_key"),
    ]:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val))
    conn.commit()


def _insert_job(conn, *, prepared_path, title="Test Movie"):
    cmd_json = json.dumps({
        "category": "movie", "tmdb_id": "1", "resolution": "1080p",
        "title": title, "runtime_type": "uploadrr_emu", "command_preview": "preview text",
    })
    cursor = conn.execute(
        """INSERT INTO upload_jobs
           (library_item_id, title, path, status, stage, source_path, prepared_path,
            uploadrr_command_json, created_at, updated_at)
           VALUES (NULL, ?, ?, 'ready', 'preflight', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (title, prepared_path, prepared_path, prepared_path, cmd_json),
    )
    conn.commit()
    return cursor.lastrowid


def test_upload_job_detail_api_exposes_progress_fields(client, auth_headers, db_conn, tmp_path):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, tmp_path / "Uploadrr", "/usr/bin/python3")
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    resp = client.get(f"/api/uploads/{jid}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["progress_phase"] == "preflight"
    assert data["runtime_type"] == "uploadrr_emu"
    assert data["command_preview"] == "preview text"


def test_upload_job_logs_visible_during_and_after_fake_run(
    client, auth_headers, db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path,
):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    assert result["action"] == "started"

    deadline = time.monotonic() + 10
    job = None
    while time.monotonic() < deadline:
        job = get_upload_job(jid, conn=db_conn)
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    time.sleep(0.3)  # let the background thread's finally block finish
    assert job["status"] == "completed"

    resp = client.get(f"/api/uploads/{jid}/logs", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    messages = [entry["message"] for entry in data["logs"]]
    assert any("Torrent creado correctamente" in m for m in messages)

    detail_resp = client.get(f"/api/uploads/{jid}", headers=auth_headers)
    assert detail_resp.json()["progress_phase"] == "succeeded"
