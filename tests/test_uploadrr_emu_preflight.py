"""Tests for the uploadrr_emu preflight command preview (Phase 10E).

Covers the runtime_type=uploadrr_emu branch of
services/upload_preflight.py::build_uploadrr_command_preview — real
Uploadrr-EMU flags, allowed_roots enforcement, and safe-preflight
guarantees (can_execute is always False in this phase).
"""
from __future__ import annotations

import sys

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.upload_execution import CONFIRMATION_TOKEN
from emuwarez_uploadrr.services.upload_preflight import build_uploadrr_command_preview


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


def _set(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (key, value))
    conn.commit()


def test_default_runtime_type_is_uploadrr_emu(db_conn):
    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "item_type": "movie"}
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert result["runtime_type"] == "uploadrr_emu"


def test_command_args_use_real_flags(tmp_path, db_conn):
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# fake")
    _set(db_conn, "uploadrr.path", str(uploadrr_dir))
    _set(db_conn, "uploadrr.python_path", "/usr/bin/python3")

    root = tmp_path / "library"
    root.mkdir()
    prepared = root / "Movie.2024.1080p.mkv"
    prepared.write_bytes(b"\x00")
    _set(db_conn, "uploadrr.allowed_roots", f'["{root}"]')

    item = {
        "title": "Movie 2024",
        "local_status": "Disponible",
        "path": str(prepared),
        "prepared_path": str(prepared),
        "item_type": "movie",
        "tmdb_id": "12345",
        "resolution": "1080p",
    }
    result = build_uploadrr_command_preview(item, conn=db_conn)

    args = result["command_args"]
    assert "-tk" in args and args[args.index("-tk") + 1] == "EMU"
    assert "-mt" in args
    assert "-tmdb" in args and args[args.index("-tmdb") + 1] == "12345"
    assert "-ua" in args
    assert "-c" in args and args[args.index("-c") + 1] == "movie"
    assert "-res" in args and args[args.index("-res") + 1] == "1080p"
    joined = " ".join(args)
    assert "--tracker" not in joined
    assert "--category" not in joined
    assert "--resolution" not in joined


def test_mt_uses_full_proposed_filename_not_bare_title(tmp_path, db_conn):
    """Regression: -mt is Uploadrr-EMU's --manual-title, which OVERRIDES
    the generated name outright (its own --help says so, and UNIT3D.py
    confirms manual_name wins over anything auto-generated) — it's not just
    a display label. Using proposal["proposed_title"] (the bare title,
    e.g. "Chappie") made the torrent appear on eMuwarez literally named
    "Chappie" instead of the full release name. Must use proposed_filename,
    the complete already-computed nomenclature string."""
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# fake")
    _set(db_conn, "uploadrr.path", str(uploadrr_dir))
    _set(db_conn, "uploadrr.python_path", sys.executable)

    root = tmp_path / "library"
    root.mkdir()
    prepared = root / "Chappie.2015.1080p.MHD.x264.DUAL.DD.5.1.SUBS-EMUWAREZ.mkv"
    prepared.write_bytes(b"\x00")
    _set(db_conn, "uploadrr.allowed_roots", f'["{root}"]')

    item = {
        "title": "Chappie", "local_status": "Disponible", "path": str(prepared),
        "prepared_path": str(prepared), "item_type": "movie",
        "tmdb_id": "198184", "resolution": "1080p",
    }
    proposal = {
        "proposed_title": "Chappie",
        "proposed_filename": "Chappie.2015.1080p.MHD.x264.DUAL.DD.5.1.SUBS-EMUWAREZ",
        "resolution": "1080p",
    }
    result = build_uploadrr_command_preview(item, proposal, conn=db_conn)

    args = result["command_args"]
    mt_value = args[args.index("-mt") + 1]
    assert mt_value == "Chappie.2015.1080p.MHD.x264.DUAL.DD.5.1.SUBS-EMUWAREZ"
    assert mt_value != "Chappie"
    assert result["contract_valid"] is True


def test_can_execute_always_false(db_conn):
    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "item_type": "movie"}
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert result["can_execute"] is False
    assert result["safe_to_execute"] is False
    assert result["requires_confirmation"] == CONFIRMATION_TOKEN


def test_blocks_when_path_outside_allowed_roots(tmp_path, db_conn):
    root = tmp_path / "allowed"
    root.mkdir()
    _set(db_conn, "uploadrr.allowed_roots", f'["{root}"]')

    outside = tmp_path / "outside" / "movie.mkv"
    item = {
        "title": "T",
        "local_status": "Disponible",
        "path": str(outside),
        "prepared_path": str(outside),
        "item_type": "movie",
    }
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert result["contract_valid"] is False
    assert any("allowed_roots" in e for e in result["contract_errors"])


def test_blocks_when_using_unprepared_source_path(tmp_path, db_conn):
    """If nomenclature hasn't been applied yet, the only path available is
    the original library path — using it must still be checked against
    allowed_roots just like a prepared_path would be."""
    root = tmp_path / "allowed"
    root.mkdir()
    _set(db_conn, "uploadrr.allowed_roots", f'["{root}"]')

    original_source = tmp_path / "downloads" / "movie.mkv"
    item = {
        "title": "T",
        "local_status": "Disponible",
        "path": str(original_source),
        "item_type": "movie",
    }
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert result["using_prepared_path"] is False
    assert result["contract_valid"] is False
    assert any("allowed_roots" in e for e in result["contract_errors"])


def test_reports_missing_python_path(tmp_path, db_conn):
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# fake")
    _set(db_conn, "uploadrr.path", str(uploadrr_dir))
    _set(db_conn, "uploadrr.python_path", str(tmp_path / "no-such-python"))

    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "item_type": "movie"}
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert result["contract_valid"] is False
    assert any("python_path" in e for e in result["contract_errors"])


def test_reports_missing_upload_script(tmp_path, db_conn):
    empty_dir = tmp_path / "Uploadrr"
    empty_dir.mkdir()
    _set(db_conn, "uploadrr.path", str(empty_dir))

    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "item_type": "movie"}
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert result["contract_valid"] is False
    assert any("Uploadrr" in e for e in result["contract_errors"])


def test_no_api_keys_in_command_preview(tmp_path, db_conn):
    _set(db_conn, "emu.api_key", "supersecretemukey")
    _set(db_conn, "tmdb.api_key", "supersecrettmdbkey")
    item = {"title": "T", "local_status": "Disponible", "path": "/fake/movie.mkv", "item_type": "movie"}
    result = build_uploadrr_command_preview(item, conn=db_conn)
    assert "supersecretemukey" not in result["command_preview"]
    assert "supersecrettmdbkey" not in result["command_preview"]
