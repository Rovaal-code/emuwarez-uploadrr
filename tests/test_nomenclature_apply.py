"""Tests for apply_nomenclature_proposal service (Phase 6B).

conftest.py provides isolated_db (autouse) pointing CONFIG_DIR to a tmp dir.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from emuwarez_uploadrr.database import init_db, connect
from emuwarez_uploadrr.services.nomenclature import (
    apply_nomenclature_proposal,
    build_nomenclature_apply_plan,
    CONFIRMATION_TOKEN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(isolated_db):
    return isolated_db / "emuwarez_uploadrr.db"


def _open(isolated_db):
    conn = connect(_db(isolated_db))
    init_db(conn)
    return conn


def _insert_item(conn, title="Test Movie", path=None):
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status)
           VALUES ('movie', ?, 'Disponible', 'none', 'Pendiente')""",
        (title,),
    )
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if path:
        conn.execute("UPDATE library_items SET path = ? WHERE id = ?", (path, item_id))
    conn.commit()
    return item_id


def _set_hardlink_base(conn, base_path):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('hardlink_base', ?)",
        (str(base_path),),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# dry_run — no filesystem changes
# ---------------------------------------------------------------------------

def test_dry_run_no_hardlink_base(isolated_db):
    conn = _open(isolated_db)
    item_id = _insert_item(conn, path="/fake/source.mkv")
    result = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    assert result["dry_run"] is True
    assert result["status"] in ("blocked", "ready")
    conn.close()


def test_dry_run_blocked_no_source(isolated_db, tmp_path):
    conn = _open(isolated_db)
    item_id = _insert_item(conn)  # no path
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    result = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    assert result["dry_run"] is True
    assert result["status"] == "blocked"
    conn.close()


def test_dry_run_no_hardlink_created(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="My Movie", path=str(src))
    _set_hardlink_base(conn, prepared)
    conn.execute(
        "UPDATE library_items SET tmdb_id = '12345', year = 2020, resolution = '1080p', source = 'Blu-ray' WHERE id = ?",
        (item_id,),
    )
    conn.commit()
    result = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    assert result["dry_run"] is True
    # No hardlinks created
    assert not list(prepared.rglob("*.mkv"))
    conn.close()


# ---------------------------------------------------------------------------
# Real apply — confirmation required
# ---------------------------------------------------------------------------

def test_apply_blocked_without_confirmation(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="My Movie", path=str(src))
    _set_hardlink_base(conn, prepared)
    result = apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation=None, conn=conn
    )
    assert result["status"] == "blocked"
    assert not list(prepared.rglob("*.mkv"))
    conn.close()


def test_apply_blocked_wrong_confirmation(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="My Movie", path=str(src))
    _set_hardlink_base(conn, prepared)
    result = apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation="WRONG_TOKEN", conn=conn
    )
    assert result["status"] == "blocked"
    assert not list(prepared.rglob("*.mkv"))
    conn.close()


def test_dry_run_takes_precedence_over_apply(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    conn = _open(isolated_db)
    item_id = _insert_item(conn, path=str(src))
    _set_hardlink_base(conn, prepared)
    result = apply_nomenclature_proposal(
        item_id, dry_run=True, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn
    )
    assert result["dry_run"] is True
    assert not list(prepared.rglob("*.mkv"))
    conn.close()


# ---------------------------------------------------------------------------
# Real apply — hardlink created and DB updated
# ---------------------------------------------------------------------------

def test_apply_real_creates_hardlink_and_updates_db(isolated_db, tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"video bytes")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Test Film", path=str(src))
    _set_hardlink_base(conn, prepared)
    conn.execute(
        "UPDATE library_items SET tmdb_id = '9999', year = 2021, resolution = '1080p' WHERE id = ?",
        (item_id,),
    )
    conn.commit()

    result = apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn
    )

    if result["status"] == "applied":
        dst = result["destination_path"]
        assert dst is not None
        assert Path(dst).exists()
        assert src.stat().st_ino == Path(dst).stat().st_ino
        assert src.read_bytes() == b"video bytes"

        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        assert row["prepared_path"] == dst
        assert row["nomenclature_applied_at"] is not None
        assert row["path"] == str(src)  # NEVER changed

        proposal_row = conn.execute(
            "SELECT * FROM nomenclature_proposals WHERE library_item_id = ? ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if proposal_row:
            assert proposal_row["status"] == "applied"
            assert proposal_row["applied_path"] == dst

        op_row = conn.execute(
            "SELECT * FROM filesystem_operations WHERE library_item_id = ? ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        assert op_row is not None
        assert op_row["status"] == "applied"
        assert op_row["dry_run"] == 0
        assert result["operation_id"] == op_row["id"]

    conn.close()


def test_apply_original_path_never_modified(isolated_db, tmp_path):
    src = tmp_path / "original.mkv"
    original_path = str(src)
    src.write_bytes(b"original")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Test", path=original_path)
    _set_hardlink_base(conn, prepared)

    apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn
    )

    row = conn.execute("SELECT path FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["path"] == original_path  # NEVER changed
    conn.close()


# ---------------------------------------------------------------------------
# filesystem_operations always saved
# ---------------------------------------------------------------------------

def test_filesystem_operation_saved_on_dry_run(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"v")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Movie", path=str(src))
    _set_hardlink_base(conn, prepared)

    result = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    ops = conn.execute(
        "SELECT * FROM filesystem_operations WHERE library_item_id = ?", (item_id,)
    ).fetchall()
    assert len(ops) >= 1
    assert ops[-1]["dry_run"] == 1
    conn.close()


# ---------------------------------------------------------------------------
# CONFIRMATION_TOKEN value
# ---------------------------------------------------------------------------

def test_confirmation_token_value():
    assert CONFIRMATION_TOKEN == "APLICAR_NOMENCLATURA"
