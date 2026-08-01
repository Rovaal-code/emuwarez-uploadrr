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
    DELETE_CONFIRMATION_TOKEN,
    append_upload_log,
    cancel_upload_job,
    create_upload_artifact,
    delete_upload_job,
    get_upload_job,
    get_upload_job_logs,
    list_upload_jobs,
    mark_phase_done,
    mark_phase_started,
    start_upload_job,
    update_phase_progress,
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


def test_run_subprocess_qbittorrent_success_logs_and_marks_done(db_conn, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0, stdout_lines=[
        "Torrent uploaded successfully",
        "Adding and rechecking torrent",
        "Added to: /downloads/",
    ])

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

    logs = get_upload_job_logs(jid, conn=db_conn)
    assert any("torrent añadido correctamente" in log["message"] for log in logs["logs"])

    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["qbittorrent_add"]["status"] == "done"


def test_run_subprocess_qbittorrent_bad_login_logs_and_skips_done(db_conn, tmp_path):
    """clients.py's _add_to_qbittorrent doesn't raise on a failed login — it
    just prints this line and the whole process still exits 0, which used to
    make the safety net silently mark "Subida a qBittorrent" as done even
    though nothing was actually added."""
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0, stdout_lines=[
        "Torrent uploaded successfully",
        "Adding and rechecking torrent",
        "INCORRECT QBIT LOGIN CREDENTIALS",
    ])

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
    assert job["status"] == "completed"  # the eMuwarez upload itself did succeed

    logs = get_upload_job_logs(jid, conn=db_conn)
    assert any("no se pudo añadir el torrent" in log["message"].lower() for log in logs["logs"])

    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["qbittorrent_add"]["status"] != "done"


def test_run_subprocess_torrent_redownload_403_logs_and_skips_done(db_conn, tmp_path):
    """Regression for a real production case (Chappie, 2026-07-28):
    UNIT3D.py's follow-up GET for the tracker-signed .torrent 403'd right
    after a successful upload, so [tracker]{name}.torrent never got written
    and add_to_client() silently returned without ever printing "Adding and
    rechecking torrent" at all — the whole process still exited 0."""
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))

    mock_proc = _make_mock_proc(returncode=0, stdout_lines=[
        "Torrent upload succeeded, but failed to download the torrent file: "
        "Client error '403 Forbidden' for url 'https://emuwarez.com/torrent/download/16209.abc'",
    ])

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
    assert job["status"] == "completed"  # the eMuwarez upload itself did succeed

    logs = get_upload_job_logs(jid, conn=db_conn)
    assert any(
        "no se pudo descargar el .torrent firmado" in log["message"].lower()
        for log in logs["logs"]
    )

    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["qbittorrent_add"]["status"] != "done"


# ---------------------------------------------------------------------------
# _run_uploadrr_subprocess — pre_gated hand-off ("Subidas en paralelo" full
# serialization: upload_queue.py's _run_queued_job acquires the concurrency
# slot before its own preprocessing and passes pre_gated=True through here,
# so this must not acquire a second time (double-counting the same job
# against the limit) — it only ever releases the slot once real work ends.
# ---------------------------------------------------------------------------

def test_run_subprocess_pre_gated_does_not_double_acquire(db_conn, tmp_path):
    from emuwarez_uploadrr.services.upload_execution import _run_uploadrr_subprocess, _upload_concurrency_gate
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    jid = _insert_job(db_conn, source_path=str(src))
    mock_proc = _make_mock_proc(returncode=0, stdout_lines=["Upload successful"])

    # Simulate the caller (the queued-job pipeline) already holding this
    # job's slot from before its own preprocessing.
    _upload_concurrency_gate._active = 1
    try:
        with patch("subprocess.Popen", return_value=mock_proc):
            _run_uploadrr_subprocess(
                jid,
                {
                    "executable": "/usr/bin/python3",
                    "args": ["/fake/upload.py", str(src)],
                    "cwd": str(tmp_path),
                    "command_preview": "python3 upload.py movie.mkv",
                },
                [],
                pre_gated=True,
            )
        # If this had acquired again first, _active would have hit 2 before
        # dropping to 1 (still holding the caller's own slot) — pre_gated
        # must skip straight to releasing the one slot that exists.
        assert _upload_concurrency_gate._active == 0
    finally:
        _upload_concurrency_gate._active = 0

    job = get_upload_job(jid, conn=db_conn)
    assert job["status"] == "completed"


def test_gate_admits_waiting_jobs_in_id_order(db_conn, tmp_path):
    """Admission order must be deterministic by job_id (== creation order),
    not whichever thread happens to wake first from notify_all() — otherwise
    upload_queue.get_queue_positions's "Esperando (2/4)" (also ordered by id)
    could lie about which job actually starts next. Uses real job rows
    because acquire() logs "esperando turno" against the job_id, which needs
    to exist for the FK on upload_job_logs."""
    import threading
    import time
    from emuwarez_uploadrr.services.upload_execution import _UploadConcurrencyGate

    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)
    j_holder = _insert_job(db_conn, source_path=str(src))
    j_a = _insert_job(db_conn, source_path=str(src))  # lowest id among the waiters
    j_b = _insert_job(db_conn, source_path=str(src))
    j_c = _insert_job(db_conn, source_path=str(src))  # highest id among the waiters

    gate = _UploadConcurrencyGate()
    admitted: list[int] = []
    admitted_lock = threading.Lock()

    with patch("emuwarez_uploadrr.services.upload_execution.get_upload_max_concurrent", return_value=1):
        gate.acquire(j_holder)  # holds the only slot so j_c/j_b/j_a all queue up behind it

        def worker(jid):
            gate.acquire(jid)
            with admitted_lock:
                admitted.append(jid)
            gate.release()

        # Start threads in reverse-id order to prove admission order is by
        # id, not by which thread happened to call acquire() first.
        threads = [threading.Thread(target=worker, args=(jid,)) for jid in (j_c, j_b, j_a)]
        for t in threads:
            t.start()
        time.sleep(0.3)  # let all three register themselves as waiting first

        gate.release()  # free j_holder's slot — lowest waiting id must go first
        for t in threads:
            t.join(timeout=5)

    assert admitted == [j_a, j_b, j_c]


# ---------------------------------------------------------------------------
# Post-upload trailer check + "Requiere Trailer" in the completion notification
# ---------------------------------------------------------------------------

def _notification_bodies(conn, job_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT body FROM notifications WHERE entity_type = 'upload_job' AND entity_id = ? ORDER BY id",
        (job_id,),
    ).fetchall()
    return [r["body"] for r in rows]


def test_notify_upload_completed_flags_requiere_trailer_when_not_found(db_conn):
    from emuwarez_uploadrr.services.upload_execution import _notify_upload_completed
    jid = _insert_job(db_conn, status="completed")

    _notify_upload_completed(jid, "https://emuwarez.com/torrents/1")

    bodies = _notification_bodies(db_conn, jid)
    assert len(bodies) == 1
    assert "Requiere Trailer" in bodies[0]


def test_notify_upload_completed_no_flag_when_trailer_artifact_present(db_conn):
    from emuwarez_uploadrr.services.upload_execution import _notify_upload_completed
    jid = _insert_job(db_conn, status="completed")
    create_upload_artifact(jid, "trailer_url", name="Trailer", url="https://youtube.com/watch?v=abc123", conn=db_conn)

    _notify_upload_completed(jid, "https://emuwarez.com/torrents/1")

    bodies = _notification_bodies(db_conn, jid)
    assert len(bodies) == 1
    assert "Requiere Trailer" not in bodies[0]


def test_check_trailer_and_log_records_artifact_and_logs(db_conn, tmp_path):
    from emuwarez_uploadrr.services.upload_execution import _check_trailer_and_log, get_upload_job_artifacts
    jid = _insert_job(db_conn)
    _insert_settings(db_conn, uploadrr_path=str(tmp_path))
    db_conn.execute(
        "UPDATE upload_jobs SET nomenclature_snapshot_json = ? WHERE id = ?",
        (json.dumps({"proposed_filename": "Movie.2024-EMUWAREZ", "proposed_title": "Movie 2024"}), jid),
    )
    db_conn.commit()
    folder = tmp_path / "tmp" / "Movie.2024-EMUWAREZ"
    folder.mkdir(parents=True)
    (folder / "[EMU]DESCRIPTION.txt").write_text("[youtube]xyz987[/youtube]", encoding="utf-8")

    _check_trailer_and_log(jid)

    artifacts = get_upload_job_artifacts(jid, conn=db_conn)
    trailer_artifacts = [a for a in artifacts if a["artifact_type"] == "trailer_url"]
    assert len(trailer_artifacts) == 1
    assert trailer_artifacts[0]["url"] == "https://www.youtube.com/watch?v=xyz987"

    logs = get_upload_job_logs(jid, conn=db_conn)
    assert any("Trailer incluido" in log["message"] for log in logs["logs"])


def test_check_trailer_and_log_warns_when_not_found(db_conn, tmp_path):
    from emuwarez_uploadrr.services.upload_execution import _check_trailer_and_log, get_upload_job_artifacts
    jid = _insert_job(db_conn)
    _insert_settings(db_conn, uploadrr_path=str(tmp_path))
    db_conn.execute(
        "UPDATE upload_jobs SET nomenclature_snapshot_json = ? WHERE id = ?",
        (json.dumps({"proposed_filename": "Movie.2024-EMUWAREZ"}), jid),
    )
    db_conn.commit()
    folder = tmp_path / "tmp" / "Movie.2024-EMUWAREZ"
    folder.mkdir(parents=True)
    (folder / "[EMU]DESCRIPTION.txt").write_text("sin trailer", encoding="utf-8")

    _check_trailer_and_log(jid)

    artifacts = get_upload_job_artifacts(jid, conn=db_conn)
    assert not any(a["artifact_type"] == "trailer_url" for a in artifacts)
    logs = get_upload_job_logs(jid, conn=db_conn)
    assert any("No se encontró un trailer" in log["message"] for log in logs["logs"])


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


def test_cancel_staging_job(db_conn):
    """An Automático job still computing its previews (no subprocess, no
    grace-period timer yet) can be cancelled with a plain status flip —
    _run_staging_job() re-checks status before promoting/writing snapshots."""
    jid = _insert_job(db_conn, status="staging")
    result = cancel_upload_job(jid, conn=db_conn)
    assert result["ok"] is True
    job = db_conn.execute("SELECT status FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    assert job["status"] == "cancelled"


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


def test_get_upload_logs_tail_returns_last_lines_not_first(db_conn):
    """Regression: "Ver Logs" always fetched offset=0 with a fixed limit —
    fine while a job has few log lines, but a noisy one (several retries
    across multiple image hosts, each logging multiple lines) can easily
    produce more than that, and the modal was frozen on the SAME oldest
    window forever, never showing anything logged after it. tail=True must
    return the last `limit` lines instead."""
    jid = _insert_job(db_conn)
    for i in range(10):
        append_upload_log(jid, "info", f"line {i}", stream="system", conn=db_conn)

    head = get_upload_job_logs(jid, limit=3, offset=0, conn=db_conn)
    assert [l["message"] for l in head["logs"]] == ["line 0", "line 1", "line 2"]

    tail = get_upload_job_logs(jid, limit=3, tail=True, conn=db_conn)
    assert [l["message"] for l in tail["logs"]] == ["line 7", "line 8", "line 9"]
    assert tail["total"] == 10


# ---------------------------------------------------------------------------
# mark_phase_done / update_phase_progress (progress_json)
# ---------------------------------------------------------------------------

def test_mark_phase_done_accumulates_across_calls(db_conn):
    jid = _insert_job(db_conn)
    mark_phase_done(jid, "verificacion_presubida")
    mark_phase_done(jid, "nomenclature")

    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["verificacion_presubida"]["status"] == "done"
    assert by_key["nomenclature"]["status"] == "done"
    assert by_key["remux"]["status"] == "pending"
    assert state["global_pct"] == 27  # 22 (verificacion_presubida) + 5 (nomenclature)


def test_update_phase_progress_keeps_earlier_done_phases(db_conn):
    jid = _insert_job(db_conn)
    mark_phase_done(jid, "verificacion_presubida")
    mark_phase_done(jid, "nomenclature")
    update_phase_progress(jid, "remux", 40)

    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["verificacion_presubida"]["status"] == "done"
    assert by_key["remux"]["status"] == "running"
    assert by_key["remux"]["pct"] == 40
    # 22 + 5 + 15*0.4 = 33
    assert state["global_pct"] == 33


def test_mark_phase_started_then_done_records_duration(db_conn):
    jid = _insert_job(db_conn)
    mark_phase_started(jid, "verificacion_presubida")

    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["verificacion_presubida"]["status"] == "running"
    assert by_key["verificacion_presubida"]["started_at"] is not None
    assert by_key["verificacion_presubida"]["finished_at"] is None
    started_at = by_key["verificacion_presubida"]["started_at"]

    mark_phase_done(jid, "verificacion_presubida")
    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["verificacion_presubida"]["status"] == "done"
    # started_at must survive unchanged from the earlier mark_phase_started call.
    assert by_key["verificacion_presubida"]["started_at"] == started_at
    assert by_key["verificacion_presubida"]["finished_at"] is not None


# ---------------------------------------------------------------------------
# list_upload_jobs
# ---------------------------------------------------------------------------

def test_list_upload_jobs(db_conn):
    _insert_job(db_conn, status="ready")
    _insert_job(db_conn, status="completed")
    jobs = list_upload_jobs(conn=db_conn)
    assert len(jobs) == 2


# ---------------------------------------------------------------------------
# delete_upload_job
# ---------------------------------------------------------------------------

def test_delete_not_found(db_conn):
    result = delete_upload_job(999, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert not result["ok"]
    assert result["error"] == "not_found"


def test_delete_requires_confirmation_token(db_conn):
    jid = _insert_job(db_conn, status="failed")
    result = delete_upload_job(jid, confirmation=None, conn=db_conn)
    assert not result["ok"]
    assert result["error"] == "confirmation_required"
    # Nothing was deleted.
    assert db_conn.execute("SELECT id FROM upload_jobs WHERE id=?", (jid,)).fetchone() is not None


def test_delete_rejects_wrong_confirmation(db_conn):
    jid = _insert_job(db_conn, status="failed")
    result = delete_upload_job(jid, confirmation="nope", conn=db_conn)
    assert not result["ok"]
    assert result["error"] == "confirmation_required"


def test_delete_blocked_for_running_job(db_conn):
    jid = _insert_job(db_conn, status="running")
    result = delete_upload_job(jid, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert not result["ok"]
    assert result["error"] == "invalid_status"
    assert db_conn.execute("SELECT id FROM upload_jobs WHERE id=?", (jid,)).fetchone() is not None


def test_delete_blocked_for_queued_job(db_conn):
    jid = _insert_job(db_conn, status="queued")
    result = delete_upload_job(jid, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert not result["ok"]
    assert result["error"] == "invalid_status"


def test_a_completed_job_can_be_deleted(db_conn):
    """Borrar el registro de una subida que salió bien no deshace nada: el
    torrent ya está en eMuwarez y el archivo sigue en su sitio. Lo que se
    borra es el historial de esta aplicación."""
    jid = _insert_job(db_conn, status="completed")
    result = delete_upload_job(jid, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert result["ok"] is True


def test_delete_blocked_while_the_job_is_still_running(db_conn):
    """Lo que NO se puede borrar es algo en marcha: hay un subproceso o un
    temporizador vivo que esto no para. Primero se cancela."""
    for estado in ("queued", "staging", "preparing", "running"):
        jid = _insert_job(db_conn, status=estado)
        result = delete_upload_job(jid, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
        assert not result["ok"], estado
        assert result["error"] == "invalid_status"


def test_delete_cancelled_job_removes_row_logs_and_artifacts(db_conn):
    jid = _insert_job(db_conn, status="cancelled")
    append_upload_log(jid, "info", "algo", stream="system", conn=db_conn)
    create_upload_artifact(jid, "trailer_url", name="Trailer", url="http://x", conn=db_conn)

    result = delete_upload_job(jid, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert result["ok"] is True

    assert db_conn.execute("SELECT id FROM upload_jobs WHERE id=?", (jid,)).fetchone() is None
    assert db_conn.execute("SELECT id FROM upload_job_logs WHERE upload_job_id=?", (jid,)).fetchone() is None
    assert db_conn.execute("SELECT id FROM upload_artifacts WHERE upload_job_id=?", (jid,)).fetchone() is None


def test_delete_failed_job_ok(db_conn):
    jid = _insert_job(db_conn, status="failed")
    result = delete_upload_job(jid, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert result["ok"] is True


def _insert_retry(conn, parent_id: int, status: str = "failed") -> int:
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, title, path, status, stage, retry_of_job_id, created_at, updated_at)
           VALUES (NULL, 'Test Movie', '', ?, 'preflight', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (status, parent_id),
    )
    conn.commit()
    return cur.lastrowid


def test_delete_blocked_while_any_attempt_is_still_running(db_conn):
    """Un intento vivo en la cadena bloquea el borrado entero: hay un proceso
    en marcha que esto no sabe parar."""
    jid = _insert_job(db_conn, status="failed")
    retry = _insert_retry(db_conn, jid, status="queued")

    result = delete_upload_job(jid, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert not result["ok"]
    assert result["error"] == "invalid_status"
    # Y no borra nada a medias.
    for x in (jid, retry):
        assert db_conn.execute("SELECT id FROM upload_jobs WHERE id=?", (x,)).fetchone() is not None


def test_delete_removes_every_attempt_of_the_chain(db_conn):
    """Borrar es borrar la fila que se ve en la tabla, que son todos sus
    intentos: con 5 reintentos había que pulsar Borrar 6 veces."""
    original = _insert_job(db_conn, status="failed")
    cadena = [original]
    for _ in range(5):
        cadena.append(_insert_retry(db_conn, cadena[-1]))
    for jid in cadena:
        append_upload_log(jid, "info", "algo", stream="system", conn=db_conn)
        create_upload_artifact(jid, "trailer_url", name="Trailer", url="http://x", conn=db_conn)

    # Se entra por el último intento, que es la fila que enseña la tabla.
    result = delete_upload_job(cadena[-1], confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert result["ok"] is True
    assert sorted(result["deleted_job_ids"]) == sorted(cadena)

    for jid in cadena:
        assert db_conn.execute("SELECT id FROM upload_jobs WHERE id=?", (jid,)).fetchone() is None
        assert db_conn.execute("SELECT id FROM upload_job_logs WHERE upload_job_id=?", (jid,)).fetchone() is None
        assert db_conn.execute("SELECT id FROM upload_artifacts WHERE upload_job_id=?", (jid,)).fetchone() is None


def test_delete_from_an_older_attempt_also_removes_the_whole_chain(db_conn):
    """Los intentos antiguos también tienen su botón Borrar (desplegando
    Reintentos), y hace lo mismo: da igual por dónde se entre."""
    original = _insert_job(db_conn, status="failed")
    medio = _insert_retry(db_conn, original)
    ultimo = _insert_retry(db_conn, medio, status="completed")

    result = delete_upload_job(original, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)
    assert result["ok"] is True
    for jid in (original, medio, ultimo):
        assert db_conn.execute("SELECT id FROM upload_jobs WHERE id=?", (jid,)).fetchone() is None


def test_a_self_referencing_row_does_not_hang_the_chain_walk(db_conn):
    """Datos corruptos (una fila apuntándose a sí misma) no pueden colgar el
    bucle que resuelve la cadena."""
    from emuwarez_uploadrr.services.upload_execution import retry_chain_ids
    jid = _insert_job(db_conn, status="failed")
    db_conn.execute("UPDATE upload_jobs SET retry_of_job_id = id WHERE id = ?", (jid,))
    db_conn.commit()
    assert retry_chain_ids(jid, conn=db_conn) == [jid]


# --- La guardia de _fail (hallazgo 4.1 de la auditoría) --------------------

def test_a_failure_after_a_cancel_does_not_overwrite_the_cancel(db_conn):
    """Cancelar es una decisión del usuario y el sistema no puede pisarla.

    _finalize_job_status dedica catorce líneas de docstring a explicar por qué
    su guardia es imprescindible; _fail, llamada desde 24 sitios de la fase de
    preparación, no tenía ninguna. Cancelas mientras prepara, falla algo justo
    después (un fichero que ya no está, mkvmerge que devuelve error) y la fila
    acababa en Fallido: el usuario no veía lo que hizo, veía otra cosa."""
    from emuwarez_uploadrr.services.upload_queue import _fail

    jid = _insert_job(db_conn, status="cancelled")

    _fail(jid, "El archivo no es accesible")

    fila = db_conn.execute("SELECT status, error_message FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    assert fila["status"] == "cancelled", "un fallo posterior ha pisado la cancelación"


def test_a_failure_still_lands_on_a_job_that_was_running(db_conn):
    """Y lo normal sigue funcionando: un trabajo vivo que falla se marca."""
    from emuwarez_uploadrr.services.upload_queue import _fail

    jid = _insert_job(db_conn, status="running")
    _fail(jid, "mkvmerge devolvió error")

    fila = db_conn.execute("SELECT status, error_message FROM upload_jobs WHERE id=?", (jid,)).fetchone()
    assert fila["status"] == "failed"
    assert fila["error_message"] == "mkvmerge devolvió error"


def test_a_cancelled_job_does_not_notify_that_the_upload_failed(db_conn, monkeypatch):
    """Y tampoco se avisa por Discord/Telegram de una subida "fallida" que en
    realidad canceló el usuario: el aviso llegaba igual."""
    from emuwarez_uploadrr.services import upload_queue

    avisos = []
    import emuwarez_uploadrr.services.upload_execution as ue
    monkeypatch.setattr(ue, "_notify_upload_failed", lambda *a, **kw: avisos.append(a))

    jid = _insert_job(db_conn, status="cancelled")
    upload_queue._fail(jid, "El archivo no es accesible")
    assert not avisos, "ha avisado de una subida fallida que estaba cancelada"

    jid2 = _insert_job(db_conn, status="running")
    upload_queue._fail(jid2, "mkvmerge devolvió error")
    assert len(avisos) == 1
