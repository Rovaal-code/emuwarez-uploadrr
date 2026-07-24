"""Tests for the Series/Season/Episode hierarchy data model (Phase 1)."""
from __future__ import annotations

from emuwarez_uploadrr.database import connect, init_db, get_state, SCHEMA_VERSION
from emuwarez_uploadrr.models import LocalStatus


def test_library_items_has_hierarchy_columns():
    conn = connect(":memory:")
    init_db(conn)
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(library_items)").fetchall()}
    assert "parent_id" in cols
    assert "season_number" in cols
    assert "episode_number" in cols
    conn.close()


def test_schema_version_is_26():
    conn = connect(":memory:")
    init_db(conn)
    assert SCHEMA_VERSION == 26
    assert get_state(conn, "schema_version") == "26"
    conn.close()


def test_hierarchy_indexes_exist():
    conn = connect(":memory:")
    init_db(conn)
    indexes = {row["name"] for row in conn.execute("PRAGMA index_list(library_items)").fetchall()}
    assert "idx_library_parent" in indexes
    assert "idx_library_tvdb" in indexes
    conn.close()


def test_migration_is_idempotent():
    conn = connect(":memory:")
    init_db(conn)
    init_db(conn)  # must not raise on a second call
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(library_items)").fetchall()}
    assert "parent_id" in cols
    conn.close()


def test_local_status_partial_value():
    assert LocalStatus.PARTIAL.value == "Parcial"


def test_partial_not_in_not_available():
    assert LocalStatus.PARTIAL.value not in LocalStatus.not_available()


def test_cli_status_arg_accepts_partial_alias():
    from emuwarez_uploadrr.cli import _status_arg
    assert _status_arg("parcial") == LocalStatus.PARTIAL.value
    assert _status_arg("partial") == LocalStatus.PARTIAL.value
