"""Tests for Phase 9B — demo_seed service."""
from __future__ import annotations

import os
import pytest
from pathlib import Path


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# seed_demo_data — confirmation guard
# ---------------------------------------------------------------------------

def test_seed_requires_confirmation(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    with pytest.raises(ValueError, match="DEMO_SEED"):
        seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "wrong")


def test_seed_requires_confirmation_empty(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    with pytest.raises(ValueError):
        seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "")


# ---------------------------------------------------------------------------
# seed_demo_data — data creation
# ---------------------------------------------------------------------------

def test_seed_creates_library_item(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data, DEMO_TITLE, DEMO_YEAR
    result = seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    assert result["ok"] is True
    assert result["library_item_id"] is not None
    row = db_conn.execute(
        "SELECT * FROM library_items WHERE title = ? AND year = ?", (DEMO_TITLE, DEMO_YEAR)
    ).fetchone()
    assert row is not None
    assert row["item_type"] == "movie"
    assert row["local_status"] == "Disponible"
    assert row["resolution"] == "1080p"
    assert row["source"] == "webdl"


def test_seed_creates_request_item(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data, DEMO_EMU_ID
    result = seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    assert result["request_item_id"] is not None
    row = db_conn.execute(
        "SELECT * FROM request_items WHERE emu_id = ?", (DEMO_EMU_ID,)
    ).fetchone()
    assert row is not None
    assert row["title"] == "Demo Movie"
    assert row["emu_status"] == "approved"


def test_seed_creates_request_match(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    result = seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    lib_id = result["library_item_id"]
    req_id = result["request_item_id"]
    row = db_conn.execute(
        "SELECT * FROM request_matches WHERE library_item_id = ? AND request_item_id = ?",
        (lib_id, req_id),
    ).fetchone()
    assert row is not None
    assert row["status"] == "Compatible"


def test_seed_creates_fake_instance_disabled(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data, DEMO_INSTANCE_NAME
    seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    row = db_conn.execute(
        "SELECT * FROM instances WHERE name = ?", (DEMO_INSTANCE_NAME,)
    ).fetchone()
    assert row is not None
    assert row["type"] == "radarr"
    assert row["enabled"] == 0


def test_seed_creates_media_file(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    result = seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    media_file = Path(result["media_file"])
    assert media_file.exists()
    assert media_file.suffix == ".mkv"
    assert media_file.stat().st_size > 0


def test_seed_is_idempotent(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    r1 = seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    r2 = seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    assert r1["library_item_id"] == r2["library_item_id"]
    count = db_conn.execute("SELECT COUNT(*) FROM library_items WHERE title = 'Demo Movie'").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# seed_demo_data — isolation / safety
# ---------------------------------------------------------------------------

def test_seed_does_not_write_outside_tmpdir(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    media_root = tmp_path / "media"
    prepared_root = tmp_path / "uploads"
    result = seed_demo_data(db_conn, str(media_root), str(prepared_root), "DEMO_SEED")
    # Confirm media file is inside media_root
    media_file = Path(result["media_file"])
    assert str(media_file).startswith(str(media_root))


def test_seed_does_not_touch_uploadrr(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    uploadrr_marker = tmp_path / "Uploadrr" / "sentinel.txt"
    uploadrr_marker.parent.mkdir()
    uploadrr_marker.write_text("should not be touched")
    seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    assert uploadrr_marker.read_text() == "should not be touched"


def test_seed_no_real_api_calls(db_conn, tmp_path, monkeypatch):
    import urllib.request
    original_urlopen = urllib.request.urlopen

    def no_network(*args, **kwargs):
        raise AssertionError("seed_demo_data must not make network calls")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data
    result = seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# reset_demo_data — confirmation guard
# ---------------------------------------------------------------------------

def test_reset_requires_confirmation(db_conn):
    from emuwarez_uploadrr.services.demo_seed import reset_demo_data
    with pytest.raises(ValueError, match="DEMO_RESET"):
        reset_demo_data(db_conn, "wrong")


def test_reset_removes_demo_data(db_conn, tmp_path):
    from emuwarez_uploadrr.services.demo_seed import seed_demo_data, reset_demo_data, DEMO_EMU_ID, DEMO_TITLE, DEMO_YEAR
    seed_demo_data(db_conn, str(tmp_path / "media"), str(tmp_path / "uploads"), "DEMO_SEED")
    reset_demo_data(db_conn, "DEMO_RESET")
    assert db_conn.execute("SELECT COUNT(*) FROM request_items WHERE emu_id = ?", (DEMO_EMU_ID,)).fetchone()[0] == 0
    assert db_conn.execute(
        "SELECT COUNT(*) FROM library_items WHERE title = ? AND year = ?", (DEMO_TITLE, DEMO_YEAR)
    ).fetchone()[0] == 0
