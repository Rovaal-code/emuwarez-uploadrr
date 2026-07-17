"""Tests for services/upload_queue.py — the queued-upload orchestration
("Subir a eMuwarez" -> queued job -> grace period -> server-side
integrity/nomenclature/remux/start)."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import upload_queue as uq


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _movie_with_path(conn, path: str, title: str = "X") -> int:
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path, size_bytes, updated_at)
           VALUES ('movie', ?, 'Disponible', 'Sin petición', 'N/A', ?, 100, CURRENT_TIMESTAMP)""",
        (title, path),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _queued_job_row(conn, item_id: int, path: str = "") -> int:
    """Insert a 'queued' job row directly, bypassing the real timer — lets
    tests drive _run_queued_job() deterministically instead of racing a
    real threading.Timer."""
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, title, path, source_path,
                                     queued_until, created_at, updated_at)
           VALUES (?, 'queued', 'queued', 'X', ?, ?, '2099-01-01T00:00:00+00:00',
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (item_id, path, path),
    )
    conn.commit()
    return cur.lastrowid


def test_queue_creates_queued_job_and_registers_timer(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))

    result = uq.queue_upload_for_item(iid, conn=db_conn)
    assert result["status"] == "queued"
    job = result["job"]
    assert job["status"] == "queued"
    assert job["queued_until"]

    job_id = job["id"]
    assert job_id in uq._QUEUE_TIMERS
    try:
        assert uq.cancel_queued_timer(job_id) is True
        assert job_id not in uq._QUEUE_TIMERS
    finally:
        uq.cancel_queued_timer(job_id)  # no-op safety net if the assert above failed


def test_queue_blocked_when_item_missing(db_conn):
    result = uq.queue_upload_for_item(999999, conn=db_conn)
    assert result["status"] == "blocked"
    assert result["job"] is None


def test_cancel_upload_job_stops_queued_timer(db_conn, tmp_path):
    from emuwarez_uploadrr.services.upload_execution import cancel_upload_job, get_upload_job

    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    result = uq.queue_upload_for_item(iid, conn=db_conn)
    job_id = result["job"]["id"]

    try:
        r = cancel_upload_job(job_id, conn=db_conn)
        assert r["ok"] is True
        job = get_upload_job(job_id, conn=db_conn)
        assert job["status"] == "cancelled"
        assert job_id not in uq._QUEUE_TIMERS
    finally:
        uq.cancel_queued_timer(job_id)


def test_run_queued_job_fails_fast_when_file_inaccessible(db_conn):
    iid = _movie_with_path(db_conn, "/nope/does/not/exist.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/nope/does/not/exist.mkv")

    uq._run_queued_job(job_id)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    job = get_upload_job(job_id, conn=db_conn)
    assert job["status"] == "failed"
    assert job["stage"] == "failed"
    assert "no es accesible" in (job["error_message"] or "")


def test_run_queued_job_skipped_when_job_not_queued_anymore(db_conn, tmp_path, monkeypatch):
    """Simulates the cancel-race: if the job's status isn't 'queued' anymore
    by the time the timer fires (e.g. cancelled a moment earlier), the
    orchestrator must not touch the filesystem at all."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = _queued_job_row(db_conn, iid, path=str(f))
    db_conn.execute("UPDATE upload_jobs SET status = 'cancelled' WHERE id = ?", (job_id,))
    db_conn.commit()

    called = []
    monkeypatch.setattr(uq, "_mark", lambda *a, **k: called.append((a, k)))

    uq._run_queued_job(job_id)

    assert called == []  # never even reached the integrity stage
    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    job = get_upload_job(job_id, conn=db_conn)
    assert job["status"] == "cancelled"  # left untouched
