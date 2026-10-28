"""Tests for CLI 'upload' command group — controlled execution, Phase 10F.

Uses the fake Uploadrr-EMU runner only. Never executes a real installation.
"""
from __future__ import annotations

import json
import time

import pytest

from emuwarez_uploadrr.cli import modern_main
from emuwarez_uploadrr.database import connect, init_db, db_path
from emuwarez_uploadrr.services.upload_execution import CONFIRMATION_TOKEN, get_upload_job


@pytest.fixture
def db_conn(isolated_db):
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
    cmd_json = json.dumps({"category": "movie", "tmdb_id": "1", "resolution": "1080p", "title": title})
    cursor = conn.execute(
        """INSERT INTO upload_jobs
           (library_item_id, title, path, status, stage, source_path, prepared_path,
            uploadrr_command_json, created_at, updated_at)
           VALUES (NULL, ?, ?, 'ready', 'preflight', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (title, prepared_path, prepared_path, prepared_path, cmd_json),
    )
    conn.commit()
    return cursor.lastrowid


def _run(args: list[str]) -> int:
    return modern_main(args)


def test_upload_status_is_alias_for_job(db_conn, tmp_path, capsys):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    rc_job = _run(["upload", "job", str(jid)])
    out_job = capsys.readouterr().out
    rc_status = _run(["upload", "status", str(jid)])
    out_status = capsys.readouterr().out

    assert rc_job == 0
    assert rc_status == 0
    assert out_job == out_status


def test_upload_start_dry_run_does_not_execute(db_conn, tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# stub")
    _insert_settings(db_conn, uploadrr_dir, "/usr/bin/python3")
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)

    rc = _run(["upload", "start", str(jid)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run" in out.lower() or "no se ha ejecutado" in out.lower()
    mock_popen.assert_not_called()


def test_upload_start_apply_without_confirm_is_blocked(db_conn, tmp_path, capsys):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# stub")
    _insert_settings(db_conn, uploadrr_dir, "/usr/bin/python3")
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    rc = _run(["upload", "start", str(jid), "--apply"])
    assert rc == 1
    job = get_upload_job(jid, conn=db_conn)
    assert job["status"] == "ready"


def test_upload_start_apply_with_confirm_uses_fake_runner(
    db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, capsys,
):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    rc = _run(["upload", "start", str(jid), "--apply", "--confirm", CONFIRMATION_TOKEN])
    assert rc == 0

    deadline = time.monotonic() + 10
    job = None
    while time.monotonic() < deadline:
        job = get_upload_job(jid, conn=db_conn)
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    time.sleep(0.3)  # let the background thread's finally block finish
    assert job["status"] == "completed"


def test_upload_logs_cli_shows_fake_runner_output(
    db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, capsys,
):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    _run(["upload", "start", str(jid), "--apply", "--confirm", CONFIRMATION_TOKEN])
    capsys.readouterr()

    deadline = time.monotonic() + 10
    job = None
    while time.monotonic() < deadline:
        job = get_upload_job(jid, conn=db_conn)
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    time.sleep(0.3)  # let the background thread's finally block finish
    assert job["status"] == "completed"

    rc = _run(["upload", "logs", str(jid)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Torrent creado correctamente" in out


def test_upload_cancel_cli_marks_job_cancelled(
    db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch, capsys,
):
    monkeypatch.setenv("FAKE_UPLOADRR_SLEEP", "0.5")
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    # `upload start --apply` espera a que termine la subida, así que el cancel
    # llega desde otra invocación mientras tanto, como lo haría el usuario.
    import threading
    arranque = threading.Thread(
        target=_run, args=(["upload", "start", str(jid), "--apply", "--confirm", CONFIRMATION_TOKEN],),
    )
    arranque.start()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = get_upload_job(jid, conn=db_conn)
        if job.get("process_id"):
            break
        time.sleep(0.05)

    rc = _run(["upload", "cancel", str(jid)])
    assert rc == 0

    deadline = time.monotonic() + 10
    job = None
    while time.monotonic() < deadline:
        job = get_upload_job(jid, conn=db_conn)
        if job["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.1)
    arranque.join(timeout=10)
    assert job["status"] == "cancelled"

    # Let the background thread (killed subprocess + reader threads + config
    # restore) fully finish before this test's isolated_db tmp_path is torn
    # down, so it can't leak a stray write into the next test's fresh DB.
    time.sleep(1.0)


def test_upload_start_apply_espera_a_que_la_subida_termine(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    """En un proceso aparte, como lo lanza el usuario: el hilo de la subida es
    daemon y moría con el CLI, que decía "iniciado" sin haber subido nada."""
    import subprocess
    import sys
    from pathlib import Path

    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    _insert_settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _insert_job(db_conn, prepared_path=str(prepared))

    raiz = Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, str(raiz / "emuwarez_uploader.py"), "--db", str(db_path()),
         "upload", "start", str(jid), "--apply", "--confirm", CONFIRMATION_TOKEN],
        cwd=raiz, capture_output=True, text=True, timeout=60,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert get_upload_job(jid, conn=db_conn)["status"] == "completed"


def test_upload_retry_no_crea_otra_subida_si_ya_hay_una_en_curso(db_conn, tmp_path, capsys):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00")
    db_conn.execute(
        "INSERT INTO library_items (item_type, title, local_status) VALUES ('movie', 'X', 'Disponible')"
    )
    item_id = db_conn.execute("SELECT max(id) FROM library_items").fetchone()[0]
    for status in ("failed", "queued"):
        db_conn.execute(
            "INSERT INTO upload_jobs (library_item_id, title, path, status, stage, created_at, updated_at)"
            " VALUES (?, 'X', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (item_id, str(prepared), status, status),
        )
    db_conn.commit()
    fallido = db_conn.execute("SELECT id FROM upload_jobs WHERE status = 'failed'").fetchone()[0]

    rc = _run(["upload", "retry", str(fallido), "--apply", "--confirm", CONFIRMATION_TOKEN])

    assert rc == 1
    assert "en curso" in capsys.readouterr().out
    assert db_conn.execute("SELECT COUNT(*) FROM upload_jobs").fetchone()[0] == 2
