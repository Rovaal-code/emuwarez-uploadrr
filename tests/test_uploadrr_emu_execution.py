"""Tests for controlled Uploadrr-EMU execution — Phase 10F.

Real subprocess execution against tests/fixtures/fake_uploadrr_emu.py only.
Never executes a real Uploadrr-EMU installation, never touches eMuwarez.
"""
from __future__ import annotations

import json
import time

import pytest

from emuwarez_uploadrr.database import connect, init_db, db_path
from emuwarez_uploadrr.services.upload_execution import (
    CONFIRMATION_TOKEN,
    build_uploadrr_execution_command,
    get_upload_job,
    get_upload_job_artifacts,
    start_upload_job,
)


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _insert_settings(conn, uploadrr_dir, python_path, *, timeout=None, runtime_type=None):
    settings = {
        "uploadrr.path": str(uploadrr_dir),
        "uploadrr.python_path": python_path,
        "tmdb.api_key": "tmdb_secret_abc123",
        "emu.api_key": "emu_secret_xyz789",
    }
    if timeout is not None:
        settings["uploadrr.timeout"] = str(timeout)
    if runtime_type is not None:
        settings["uploadrr.runtime_type"] = runtime_type
    for key, val in settings.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val))
    conn.commit()


def _insert_job(conn, *, prepared_path, category="movie", tmdb_id="12345", resolution="1080p", title="Test Movie 2024"):
    cmd_json = json.dumps({"category": category, "tmdb_id": tmdb_id, "resolution": resolution, "title": title})
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
    while time.monotonic() < deadline:
        job = get_upload_job(job_id, conn=conn)
        if job["status"] in ("completed", "failed", "cancelled"):
            # Grace period: the background thread's `finally` block (config
            # restore + its own log writes) runs right after the terminal
            # status is committed — give it time to finish before the
            # caller's isolated_db tmp_path is torn down, to avoid a stray
            # write leaking into the *next* test's fresh database.
            time.sleep(0.3)
            return job
        time.sleep(0.1)
    raise AssertionError(f"Job {job_id} never reached a terminal status (last: {job['status']})")


def test_command_uses_real_emu_flags_not_legacy(db_conn, tmp_path):
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# stub")
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, uploadrr_dir, "/usr/bin/python3")
    jid = _insert_job(db_conn, prepared_path=str(prepared))
    job = get_upload_job(jid, conn=db_conn)

    cmd = build_uploadrr_execution_command(job, conn=db_conn)

    assert "-tk" in cmd["args"]
    assert "-mt" in cmd["args"]
    assert "-tmdb" in cmd["args"]
    assert "-ua" in cmd["args"]
    assert "-c" in cmd["args"]
    assert "-res" in cmd["args"]
    joined = " ".join(cmd["args"])
    assert "--tracker" not in joined
    assert "--category" not in joined
    assert "--resolution" not in joined


def _real_args(db_conn, tmp_path, item, proposal):
    """Del preflight a la ejecución: lo guardado en uploadrr_command_json es lo único que lee la segunda."""
    from emuwarez_uploadrr.services.upload_preflight import build_uploadrr_command_preview

    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# stub")
    prepared = tmp_path / "release.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, uploadrr_dir, "/usr/bin/python3")
    item = {"title": "Serie", "path": str(prepared), "prepared_path": str(prepared), "tmdb_id": "1", **item}
    preview = build_uploadrr_command_preview(item, proposal, conn=db_conn)
    jid = _insert_job(db_conn, prepared_path=str(prepared))
    db_conn.execute("UPDATE upload_jobs SET uploadrr_command_json = ? WHERE id = ?", (json.dumps(preview), jid))
    db_conn.commit()
    return build_uploadrr_execution_command(get_upload_job(jid, conn=db_conn), conn=db_conn)["args"]


def test_episode_season_number_and_format_reach_the_real_command(db_conn, tmp_path):
    args = _real_args(
        db_conn,
        tmp_path,
        {"item_type": "episode", "season_number": 1, "episode_number": 3},
        {"proposed_filename": "Serie S01E03 1080p WEB-DL-GRP", "resolution": "1080p", "source": "WEB-DL"},
    )

    assert args[args.index("-season") + 1] == "S01"
    assert args[args.index("-episode") + 1] == "E03"
    assert args[args.index("-t") + 1] == "webdl"


def test_specials_season_zero_reaches_the_real_command(db_conn, tmp_path):
    args = _real_args(
        db_conn,
        tmp_path,
        {"item_type": "episode", "season_number": 0, "episode_number": 2},
        {"proposed_filename": "Serie S00E02 1080p WEB-DL-GRP", "resolution": "1080p", "source": "WEB-DL"},
    )

    assert args[args.index("-season") + 1] == "S00"
    assert args[args.index("-episode") + 1] == "E02"


def test_season_pack_reaches_the_real_command_without_episode(db_conn, tmp_path):
    args = _real_args(
        db_conn, tmp_path, {"item_type": "season", "season": 2, "episode": None, "release_format": "BDRemux"}, None
    )

    assert args[args.index("-season") + 1] == "S02"
    assert "-episode" not in args
    assert args[args.index("-t") + 1] == "remux"


def test_movie_gets_no_season_or_episode(db_conn, tmp_path):
    proposal = {"proposed_filename": "Peli 2020 1080p BluRay-GRP", "source": "BluRay"}
    args = _real_args(db_conn, tmp_path, {"item_type": "movie"}, proposal)

    assert "-season" not in args
    assert "-episode" not in args
    assert args[args.index("-t") + 1] == "encode"


def test_apply_with_fake_runner_succeeds(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00" * 16)
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    assert result["action"] == "started"

    job = _wait_for_terminal(jid, db_conn)
    assert job["status"] == "completed"
    assert job["exit_code"] == 0
    assert job["result_url"] is not None

    artifacts = get_upload_job_artifacts(jid, conn=db_conn)
    assert any(a["artifact_type"] == "uploaded_url" for a in artifacts)


def test_un_fallo_al_guardar_el_log_no_cuelga_la_subida(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    """Si guardar una línea fallaba (base bloqueada), el hilo lector moría,
    nadie vaciaba la tubería y Uploadrr se quedaba bloqueado hasta el timeout."""
    import sqlite3

    from emuwarez_uploadrr.services import upload_execution

    monkeypatch.setenv("FAKE_UPLOADRR_LINES", "1000")
    original = upload_execution.append_upload_log

    def falla_en_stdout(job_id, level, message, *args, stream="system", **kwargs):
        if stream == "stdout":
            raise sqlite3.OperationalError("database is locked")
        return original(job_id, level, message, *args, stream=stream, **kwargs)

    monkeypatch.setattr(upload_execution, "append_upload_log", falla_en_stdout)
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00" * 16)
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path, timeout=30)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)

    job = _wait_for_terminal(jid, db_conn, timeout=15)
    assert job["status"] == "completed"


def test_apply_with_fake_runner_fail_marks_failed(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    monkeypatch.setenv("FAKE_UPLOADRR_FAIL", "1")
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00" * 16)
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    assert result["action"] == "started"

    job = _wait_for_terminal(jid, db_conn)
    assert job["status"] == "failed"
    assert job["exit_code"] == 1


def test_apply_without_confirmation_never_starts(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    result = start_upload_job(jid, dry_run=False, start=True, confirmation="WRONG_TOKEN", conn=db_conn)
    assert result["action"] == "blocked"
    assert result["error"] == "confirmation_required"

    job = get_upload_job(jid, conn=db_conn)
    assert job["status"] == "ready"


def test_dry_run_never_executes_subprocess(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    from unittest.mock import MagicMock
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)

    result = start_upload_job(jid, dry_run=True, start=False, confirmation=None, conn=db_conn)
    assert result["action"] == "dry_run"
    mock_popen.assert_not_called()


def test_generic_runtime_blocks_real_start(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    from unittest.mock import MagicMock
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path, runtime_type="uploadrr_generic")
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)

    result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    assert result["action"] == "blocked"
    assert result["error"] == "unsupported_runtime"
    mock_popen.assert_not_called()


def test_cancel_running_job_marks_cancelled(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    from emuwarez_uploadrr.services.upload_execution import cancel_upload_job

    monkeypatch.setenv("FAKE_UPLOADRR_SLEEP", "0.5")
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    result = start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    assert result["action"] == "started"

    # Wait until the subprocess actually has a PID before cancelling.
    deadline = time.monotonic() + 5
    pid = None
    while time.monotonic() < deadline:
        job = get_upload_job(jid, conn=db_conn)
        pid = job.get("process_id")
        if pid:
            break
        time.sleep(0.05)
    assert pid, "El proceso fake nunca llegó a arrancar"

    cancel_result = cancel_upload_job(jid, conn=db_conn)
    assert cancel_result["ok"] is True

    job = _wait_for_terminal(jid, db_conn)
    assert job["status"] == "cancelled"

    # Give the background thread (killed subprocess + its reader threads +
    # config restore) time to fully wind down before the test's isolated_db
    # tmp_path is torn down — otherwise it can leak a stray write into the
    # *next* test's fresh database once CONFIG_DIR is repointed.
    time.sleep(1.0)
