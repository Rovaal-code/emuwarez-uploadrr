"""Tests for the pre-upload checks (services/upload_checks)."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import upload_checks as uc


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _movie_with_path(conn, path: str) -> int:
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path, size_bytes, updated_at)
           VALUES ('movie', 'X', 'Disponible', 'Sin petición', 'N/A', ?, 100, CURRENT_TIMESTAMP)""",
        (path,),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def test_stops_at_inaccessible(db_conn):
    iid = _movie_with_path(db_conn, "/nope/does/not/exist.mkv")
    r = uc.run_upload_checks(db_conn, iid)
    assert r["ready"] is False
    assert len(r["checks"]) == 1
    assert r["checks"][0]["id"] == "accessible" and r["checks"][0]["status"] == "fail"


def test_all_green_when_everything_passes(db_conn, tmp_path, monkeypatch):
    # A real file so accessible/renameable/integrity pass.
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    set_setting(db_conn, "nomenclature.use_hardlinks", "false")   # skip hardlink check
    set_setting(db_conn, "uploadrr.path", str(tmp_path))           # writable output dir

    # Integrity: pretend mediainfo reads it fine.
    monkeypatch.setattr(uc, "run_upload_checks", uc.run_upload_checks)  # noop, keep ref
    import emuwarez_uploadrr.services.media_info_service as mis
    monkeypatch.setattr(mis, "mediainfo_available", lambda: True)
    monkeypatch.setattr(mis, "read_media_info_summary", lambda p: {"video_codec": "AVC"})
    # Network checks all OK.
    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_qbit_connection", lambda **k: {"ok": True, "message": "ok"})
    monkeypatch.setattr(it, "test_emuwarez_connection", lambda **k: {"ok": True, "message": "ok"})
    import emuwarez_uploadrr.services.image_hosts as ih
    monkeypatch.setattr(ih, "test_image_host", lambda hid, key=None, **k: {"ok": True})

    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    ids = [c["id"] for c in r["checks"]]
    assert ids == ["accessible", "renameable", "integrity", "output", "qbittorrent", "imghosts", "emuwarez"]
    assert all(c["status"] == "ok" for c in r["checks"])
    assert r["ready"] is True


def test_stops_at_qbit_before_emuwarez(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    f = tmp_path / "m.mkv"; f.write_bytes(b"x" * 2048)
    set_setting(db_conn, "nomenclature.use_hardlinks", "false")
    set_setting(db_conn, "uploadrr.path", str(tmp_path))
    import emuwarez_uploadrr.services.media_info_service as mis
    monkeypatch.setattr(mis, "mediainfo_available", lambda: True)
    monkeypatch.setattr(mis, "read_media_info_summary", lambda p: {"ok": 1})
    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_qbit_connection", lambda **k: {"ok": False, "message": "caído"})
    # eMuwarez must NOT be reached — make it explode if called.
    monkeypatch.setattr(it, "test_emuwarez_connection", lambda **k: (_ for _ in ()).throw(AssertionError("no debe llamarse")))

    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    ids = [c["id"] for c in r["checks"]]
    assert ids[-1] == "qbittorrent" and r["checks"][-1]["status"] == "fail"
    assert "emuwarez" not in ids
    assert r["ready"] is False
