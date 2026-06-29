"""Tests for upload preflight service (Phase 6A)."""
from __future__ import annotations

import pytest
from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.upload_preflight import (
    build_upload_preflight,
    validate_upload_preconditions,
    build_uploadrr_command_preview,
    list_upload_jobs,
    get_upload_job,
)


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    db_file = tmp_path / "test.db"
    conn = connect(db_file)
    init_db(conn)
    yield conn
    conn.close()


def _insert_item(conn, *, title="Test Movie", local_status="Disponible", path="/fake/movie.mkv"):
    cursor = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path, tmdb_id)
           VALUES ('movie', ?, ?, 'Sin petición', ?, '12345')""",
        (title, local_status, path),
    )
    conn.commit()
    return cursor.lastrowid


def test_validate_preconditions_empty_item():
    result = validate_upload_preconditions({})
    assert not result["ok"]
    assert result["errors"]


def test_validate_preconditions_faltante():
    item = {"title": "T", "local_status": "Faltante", "path": "/p"}
    result = validate_upload_preconditions(item)
    assert not result["ok"]
    assert any("disponible" in e.lower() or "localmente" in e.lower() for e in result["errors"])


def test_validate_preconditions_missing_uploadrr_config(db_conn):
    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv"}
    result = validate_upload_preconditions(item, conn=db_conn)
    assert not result["ok"]
    assert any("uploadrr" in e.lower() for e in result["errors"])


def test_validate_preconditions_missing_emu_key(db_conn):
    db_conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('uploadrr_path', '/fake/Uploadrr', 0)")
    db_conn.commit()
    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv"}
    result = validate_upload_preconditions(item, conn=db_conn)
    assert any("emu" in e.lower() or "emuwarez" in e.lower() for e in result["errors"])


def test_validate_preconditions_ready(db_conn, tmp_path):
    fake_uploadrr = tmp_path / "Uploadrr"
    fake_uploadrr.mkdir()
    db_conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('uploadrr_path', ?, 0)", (str(fake_uploadrr),))
    db_conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('emu_api_key', 'testkey12345', 1)")
    db_conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('tmdb_api_key', 'tmdbkey12345', 1)")
    db_conn.commit()
    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "tmdb_id": "12345"}
    result = validate_upload_preconditions(item, conn=db_conn)
    assert not any("uploadrr" in e.lower() for e in result["errors"])
    assert not any("emu" in e.lower() for e in result["errors"])
    assert not any("tmdb" in e.lower() for e in result["errors"])


def test_build_command_preview(db_conn):
    item = {"title": "Test Movie", "local_status": "Disponible", "path": "/media/movie.mkv", "item_type": "movie", "tmdb_id": "12345"}
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert "command_preview" in result
    assert result["tracker"] == "EMU"
    assert result["category"] == "movie"
    cmd = result.get("command_preview", "")
    # API keys must not appear in command preview
    assert "api_key" not in cmd.lower()


def test_build_command_preview_tv(db_conn):
    item = {"title": "Test Series", "local_status": "Disponible", "path": "/media/show.mkv", "item_type": "series", "tmdb_id": "999"}
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert result["category"] == "tv"


def test_build_preflight_item_not_found(db_conn):
    result = build_upload_preflight(99999, conn=db_conn)
    assert result["status"] == "blocked"
    assert result["errors"]


def test_build_preflight_creates_job(db_conn):
    item_id = _insert_item(db_conn)
    result = build_upload_preflight(item_id, conn=db_conn)
    assert result["status"] in ("ready", "blocked")
    assert result.get("job") is not None
    assert result["job"].get("id") is not None


def test_list_upload_jobs_empty(db_conn):
    result = list_upload_jobs(conn=db_conn)
    assert isinstance(result, list)
    assert len(result) == 0


def test_list_upload_jobs_after_preflight(db_conn):
    item_id = _insert_item(db_conn)
    build_upload_preflight(item_id, conn=db_conn)
    jobs = list_upload_jobs(conn=db_conn)
    assert len(jobs) >= 1


def test_get_upload_job(db_conn):
    item_id = _insert_item(db_conn)
    result = build_upload_preflight(item_id, conn=db_conn)
    job_id = result["job"]["id"]
    job = get_upload_job(job_id, conn=db_conn)
    assert job is not None
    assert job["id"] == job_id


def test_no_subprocess_execution(monkeypatch):
    """Ensure preflight never calls subprocess.run."""
    import subprocess
    calls: list = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"subprocess.run called unexpectedly: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv"}
    validate_upload_preconditions(item)
    assert len(calls) == 0
