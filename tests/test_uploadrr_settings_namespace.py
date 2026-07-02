"""Tests for the Phase 10E settings namespace fix.

The setup wizard / UI write dotted keys (uploadrr.path, tmdb.api_key,
emu.api_key). Older code and some fixtures still use the legacy underscore
form (uploadrr_path, tmdb_api_key, emu_api_key). Both must resolve to the
same value, with the dotted key always winning when both are present.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, get_setting_canonical, init_db
from emuwarez_uploadrr.services.upload_execution import validate_upload_job_start
from emuwarez_uploadrr.services.upload_preflight import validate_upload_preconditions
from emuwarez_uploadrr.web.services.setup_service import setup_emu, setup_tmdb, setup_uploadrr
from emuwarez_uploadrr.web.services.settings_service import get_configured


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


def test_dotted_key_read_when_only_dotted_set(db_conn):
    db_conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('uploadrr.path', '/opt/Uploadrr', 0)"
    )
    db_conn.commit()
    assert get_setting_canonical(db_conn, "uploadrr.path") == "/opt/Uploadrr"


def test_legacy_underscore_key_still_works_as_fallback(db_conn):
    db_conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('uploadrr_path', '/legacy/Uploadrr', 0)"
    )
    db_conn.commit()
    assert get_setting_canonical(db_conn, "uploadrr.path") == "/legacy/Uploadrr"


def test_dotted_key_wins_over_legacy_underscore(db_conn):
    db_conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('uploadrr_path', '/legacy/Uploadrr', 0)"
    )
    db_conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES ('uploadrr.path', '/new/Uploadrr', 0)"
    )
    db_conn.commit()
    assert get_setting_canonical(db_conn, "uploadrr.path") == "/new/Uploadrr"


def test_missing_key_returns_default(db_conn):
    assert get_setting_canonical(db_conn, "uploadrr.path", default="fallback") == "fallback"


def test_setup_writes_uploadrr_path_and_pipeline_reads_it(db_conn, tmp_path):
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# fake")
    setup_uploadrr(db_conn, str(uploadrr_dir))
    db_conn.commit()

    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "tmdb_id": "1"}
    result = validate_upload_preconditions(item, conn=db_conn)
    assert not any("uploadrr" in e.lower() for e in result["errors"])


def test_setup_writes_tmdb_api_key_and_pipeline_reads_it(db_conn):
    setup_tmdb(db_conn, api_key="tmdbkey12345")
    db_conn.commit()
    assert get_setting_canonical(db_conn, "tmdb.api_key") == "tmdbkey12345"
    assert get_configured(db_conn, "tmdb.api_key")


def test_setup_writes_emu_api_key_and_pipeline_reads_it(db_conn):
    setup_emu(db_conn, api_key="emukey12345")
    db_conn.commit()
    assert get_setting_canonical(db_conn, "emu.api_key") == "emukey12345"
    assert get_configured(db_conn, "emu.api_key")


def test_job_start_validation_reads_dotted_settings(db_conn, tmp_path):
    """validate_upload_job_start must see settings written via the dotted
    (setup/UI) namespace, not just the legacy underscore form."""
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# fake")
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"\x00" * 10)

    setup_uploadrr(db_conn, str(uploadrr_dir))
    setup_emu(db_conn, api_key="emukey12345")
    setup_tmdb(db_conn, api_key="tmdbkey12345")
    db_conn.commit()

    cursor = db_conn.execute(
        """INSERT INTO upload_jobs (library_item_id, title, path, status, stage, source_path, prepared_path, created_at, updated_at)
           VALUES (NULL, 'Test Movie', ?, 'ready', 'preflight', ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (str(src), str(src)),
    )
    db_conn.commit()
    job_id = cursor.lastrowid

    result = validate_upload_job_start(job_id, conn=db_conn)
    assert result["valid"] is True, result["errors"]


def test_only_legacy_underscore_settings_still_works_end_to_end(db_conn, tmp_path):
    """Fixtures/deployments that only ever wrote the legacy underscore keys
    must keep working (backwards compatibility, not just new writes)."""
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# fake")

    for key, val in [
        ("uploadrr_path", str(uploadrr_dir)),
        ("emu_api_key", "emukey12345"),
        ("tmdb_api_key", "tmdbkey12345"),
    ]:
        db_conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, val)
        )
    db_conn.commit()

    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "tmdb_id": "1"}
    result = validate_upload_preconditions(item, conn=db_conn)
    assert result["ok"] is True, result["errors"]
