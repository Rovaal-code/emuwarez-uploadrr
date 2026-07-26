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


def test_stops_at_unrenameable_when_path_missing(db_conn):
    # Accessibility/integrity are no longer checked here — they're checked for
    # real once the upload is queued (upload_queue.py's "integrity" stage).
    # A nonexistent path still fails fast, but now at "renameable": its parent
    # directory doesn't exist either, so it's not writable.
    iid = _movie_with_path(db_conn, "/nope/does/not/exist.mkv")
    r = uc.run_upload_checks(db_conn, iid)
    assert r["ready"] is False
    assert len(r["checks"]) == 1
    assert r["checks"][0]["id"] == "renameable" and r["checks"][0]["status"] == "fail"


def test_output_check_falls_back_to_bundled_uploadrr_path(db_conn, tmp_path, monkeypatch):
    """Regression: the bundled runtime (RUNTIME_EMU, the default) needs no
    configuration at all — DEFAULT_UPLOADRR_PATH (/opt/Uploadrr, or
    UPLOADRR_PATH) must be used when `uploadrr.path` was never set by hand,
    the same way uploadrr_contract.py::get_runtime_settings() already does
    for the actual upload command. Previously this check read the setting
    directly with no fallback, so it failed with "no configurado" even
    though the runtime it validates for doesn't require configuring it."""
    from emuwarez_uploadrr.services import uploadrr_contract as ctr
    monkeypatch.setattr(ctr, "DEFAULT_UPLOADRR_PATH", str(tmp_path))
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root

    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    output_check = next(c for c in r["checks"] if c["id"] == "output")
    assert output_check["status"] == "ok"


def test_all_green_when_everything_passes(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root
    set_setting(db_conn, "qbit.url", "http://localhost:8080")     # so qBittorrent runs
    set_setting(db_conn, "uploadrr.path", str(tmp_path))           # writable output dir

    # Network checks all OK.
    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_qbit_connection", lambda **k: {"ok": True, "message": "ok"})
    monkeypatch.setattr(it, "test_emuwarez_connection", lambda **k: {"ok": True, "message": "ok"})
    import emuwarez_uploadrr.services.image_hosts as ih
    monkeypatch.setattr(ih, "test_image_host", lambda hid, key=None, **k: {"ok": True})

    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    ids = [c["id"] for c in r["checks"]]
    assert ids == ["renameable", "output", "qbittorrent", "imghosts", "emuwarez"]
    assert all(c["status"] == "ok" for c in r["checks"])
    assert r["ready"] is True


def test_skips_unconfigured_qbit(db_conn, tmp_path, monkeypatch):
    """qBittorrent not configured → yellow 'skip', non-blocking: the upload
    is still ready."""
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    f = tmp_path / "movie.mkv"; f.write_bytes(b"x" * 2048)
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root
    set_setting(db_conn, "uploadrr.path", str(tmp_path))
    # qbit.url intentionally not set → qbittorrent skip
    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_emuwarez_connection", lambda **k: {"ok": True, "message": "ok"})
    import emuwarez_uploadrr.services.image_hosts as ih
    monkeypatch.setattr(ih, "test_image_host", lambda hid, key=None, **k: {"ok": True})

    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    by_id = {c["id"]: c for c in r["checks"]}
    assert by_id["qbittorrent"]["status"] == "skip"
    assert r["ready"] is True  # skips don't block


def test_stops_at_qbit_before_emuwarez(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    f = tmp_path / "m.mkv"; f.write_bytes(b"x" * 2048)
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root
    set_setting(db_conn, "qbit.url", "http://localhost:8080")   # configured → qbit runs
    set_setting(db_conn, "uploadrr.path", str(tmp_path))
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
