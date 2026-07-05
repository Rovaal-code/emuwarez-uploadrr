"""Tests for the global-unique-instance-name migration
(_migrate_instances_unique_name, Phase 4B of the 12-part batch).

instances.name used to only be unique per type (UNIQUE(type, name)) — two
different-typed instances (e.g. a Radarr and a Sonarr) could share a name.
Nothing before this migration prevented that, so real pre-existing
conflicts must be resolved during the migration itself, not just blocked
going forward. This is the first migration in the project that needs a
dedicated data-conflict test (the widen/narrow CHECK migrations were only
ever exercised against freshly-created schemas)."""
from __future__ import annotations

import sqlite3

import pytest


def _seed_old_schema_with_conflict(conn: sqlite3.Connection) -> None:
    """Recreate the pre-migration instances table (UNIQUE(type, name)) with
    two different-typed rows sharing a name, simulating a real database that
    predates this migration."""
    conn.execute("DROP TABLE instances")
    conn.execute("""
        CREATE TABLE instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('radarr','sonarr')),
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            is_4k INTEGER NOT NULL DEFAULT 0,
            is_anime INTEGER NOT NULL DEFAULT 0,
            last_test_status TEXT,
            last_test_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(type, name)
        )
    """)
    conn.execute("INSERT INTO instances (id, type, name, url, api_key) VALUES (1, 'radarr', 'Main', 'http://r', 'k1')")
    conn.execute("INSERT INTO instances (id, type, name, url, api_key) VALUES (2, 'sonarr', 'Main', 'http://s', 'k2')")
    conn.execute("INSERT INTO instances (id, type, name, url, api_key) VALUES (3, 'radarr', 'Unique', 'http://r2', 'k3')")
    conn.commit()


def test_migration_renames_conflicting_duplicate_across_types(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    db_path = isolated_db / "emuwarez_uploadrr.db"
    conn = connect(db_path)
    init_db(conn)
    _seed_old_schema_with_conflict(conn)
    conn.close()

    conn2 = connect(db_path)
    init_db(conn2)
    rows = {r["id"]: r["name"] for r in conn2.execute("SELECT id, name FROM instances ORDER BY id").fetchall()}
    conn2.close()

    # Earliest-created row keeps its name unchanged.
    assert rows[1] == "Main"
    # The later duplicate got disambiguated with its type.
    assert rows[2] == "Main (sonarr)"
    # Unrelated row untouched.
    assert rows[3] == "Unique"


def test_migration_applies_unique_name_constraint(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    db_path = isolated_db / "emuwarez_uploadrr.db"
    conn = connect(db_path)
    init_db(conn)
    _seed_old_schema_with_conflict(conn)
    conn.close()

    conn2 = connect(db_path)
    init_db(conn2)
    sql = conn2.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='instances'"
    ).fetchone()["sql"]
    assert "UNIQUE(name)" in sql
    assert "UNIQUE(type, name)" not in sql

    # The constraint is now real: inserting a second "Unique" (any type) must fail.
    with pytest.raises(sqlite3.IntegrityError):
        conn2.execute(
            "INSERT INTO instances (type, name, url, api_key) VALUES ('sonarr', 'Unique', 'http://x', 'k')"
        )
    conn2.close()


def test_migration_is_idempotent_and_converges(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    db_path = isolated_db / "emuwarez_uploadrr.db"
    conn = connect(db_path)
    init_db(conn)
    _seed_old_schema_with_conflict(conn)
    conn.close()

    conn2 = connect(db_path)
    init_db(conn2)
    first_pass = {r["id"]: r["name"] for r in conn2.execute("SELECT id, name FROM instances ORDER BY id").fetchall()}

    # Running init_db() again must not re-rename anything or error.
    init_db(conn2)
    second_pass = {r["id"]: r["name"] for r in conn2.execute("SELECT id, name FROM instances ORDER BY id").fetchall()}
    conn2.close()

    assert first_pass == second_pass


def test_fresh_database_has_no_renames(isolated_db):
    """A brand-new DB (no pre-existing conflicts) should just get the
    tighter constraint with zero renamed rows."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.instances import add_instance
    db_path = isolated_db / "emuwarez_uploadrr.db"
    conn = connect(db_path)
    init_db(conn)
    add_instance(conn, "radarr", "Radarr 1", "http://r1", "k1")
    add_instance(conn, "sonarr", "Sonarr 1", "http://s1", "k2")
    conn.commit()

    names = [r["name"] for r in conn.execute("SELECT name FROM instances ORDER BY id").fetchall()]
    assert names == ["Radarr 1", "Sonarr 1"]
    conn.close()
