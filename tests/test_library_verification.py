"""Tests for library filesystem verification (Phase 8A)."""
from __future__ import annotations

import pytest


@pytest.fixture
def db_with_item(isolated_db):
    """DB with a single available library item."""
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO library_items
        (item_type, title, local_status, request_status, nomenclature_status, path, updated_at)
        VALUES ('movie', 'Test Movie', 'Disponible', 'Sin petición', 'N/A', ?, CURRENT_TIMESTAMP)
        """,
        (str(isolated_db / "movie.mkv"),),
    )
    conn.commit()
    item_id = conn.execute("SELECT id FROM library_items LIMIT 1").fetchone()["id"]
    return conn, item_id, isolated_db


def test_verify_existing_video_file(db_with_item):
    conn, item_id, tmp = db_with_item
    from emuwarez_uploadrr.services.library_verification import verify_library_item_file
    # Create the actual file
    path = tmp / "movie.mkv"
    path.write_bytes(b"fake mkv data")

    result = verify_library_item_file(item_id, conn)

    assert result["file_exists"] is True
    assert result["file_is_video"] is True
    assert result["file_size_on_disk"] > 0
    assert result["file_verification_error"] is None


def test_verify_nonexistent_file(db_with_item):
    conn, item_id, tmp = db_with_item
    from emuwarez_uploadrr.services.library_verification import verify_library_item_file
    # File not created — does not exist

    result = verify_library_item_file(item_id, conn)

    assert result["file_exists"] is False
    assert result["file_verification_error"] is not None
    assert "no encontrado" in result["file_verification_error"]


def test_verify_null_path(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.library_verification import verify_library_item_file
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO library_items
        (item_type, title, local_status, request_status, nomenclature_status, path, updated_at)
        VALUES ('movie', 'No Path Movie', 'Disponible', 'Sin petición', 'N/A', NULL, CURRENT_TIMESTAMP)
        """
    )
    conn.commit()
    item_id = conn.execute("SELECT id FROM library_items LIMIT 1").fetchone()["id"]

    result = verify_library_item_file(item_id, conn)

    assert result["file_exists"] is False
    assert "nulo" in result["file_verification_error"]


def test_verify_directory_instead_of_file(db_with_item):
    conn, item_id, tmp = db_with_item
    from emuwarez_uploadrr.services.library_verification import verify_library_item_file
    # Path points to directory
    dir_path = tmp / "movie.mkv"
    dir_path.mkdir()

    result = verify_library_item_file(item_id, conn)

    assert result["file_exists"] is False
    assert result["file_verification_error"] is not None


def test_verify_updates_db(db_with_item):
    conn, item_id, tmp = db_with_item
    from emuwarez_uploadrr.services.library_verification import verify_library_item_file
    path = tmp / "movie.mkv"
    path.write_bytes(b"data")

    verify_library_item_file(item_id, conn)

    row = conn.execute("SELECT file_exists, file_verified_at FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["file_exists"] == 1
    assert row["file_verified_at"] is not None


def test_verify_library_files_summary(db_with_item):
    conn, item_id, tmp = db_with_item
    from emuwarez_uploadrr.services.library_verification import verify_library_files
    path = tmp / "movie.mkv"
    path.write_bytes(b"data")

    result = verify_library_files(conn)

    assert result["ok"] is True
    assert result["items_checked"] >= 1


def test_verify_library_files_empty_db(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.library_verification import verify_library_files
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)

    result = verify_library_files(conn)

    assert result["ok"] is True
    assert result["items_checked"] == 0
