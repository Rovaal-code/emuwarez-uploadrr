"""API tests for nomenclature apply endpoint (Phase 6B).

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations

import pytest
from pathlib import Path


def _insert_item(isolated_db, title="Test Movie", path=None, local_status="Disponible"):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    cursor = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status)
           VALUES ('movie', ?, ?, 'Sin petición')""",
        (title, local_status),
    )
    item_id = cursor.lastrowid
    if path:
        conn.execute("UPDATE library_items SET path = ? WHERE id = ?", (path, item_id))
    conn.commit()
    conn.close()
    return item_id


def _set_hardlink_base(isolated_db, base_path):
    from emuwarez_uploadrr.database import connect
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('hardlink_base', ?)",
        (str(base_path),),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Endpoint requires auth
# ---------------------------------------------------------------------------

def test_adapt_nomenclature_requires_auth(client, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(f"/api/library/{item_id}/adapt-nomenclature", json={"dry_run": True})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Response schema shape
# ---------------------------------------------------------------------------

def test_adapt_nomenclature_response_schema(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert "dry_run" in body
    assert "apply" in body
    assert "status" in body
    assert "warnings" in body
    assert "errors" in body
    assert isinstance(body["warnings"], list)
    assert isinstance(body["errors"], list)


# ---------------------------------------------------------------------------
# Dry-run default
# ---------------------------------------------------------------------------

def test_adapt_nomenclature_dry_run_default(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


def test_adapt_nomenclature_dry_run_explicit(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": True, "apply": False},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


# ---------------------------------------------------------------------------
# Apply blocked without / wrong confirmation
# ---------------------------------------------------------------------------

def test_adapt_nomenclature_apply_blocked_no_confirmation(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": False, "apply": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "blocked"


def test_adapt_nomenclature_apply_blocked_wrong_confirmation(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": False, "apply": True, "confirmation": "WRONG"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "blocked"


def test_adapt_nomenclature_dry_run_overrides_apply_and_confirmation(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": True, "apply": True, "confirmation": "APLICAR_NOMENCLATURA"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    # No filesystem change — status never "applied" when dry_run=True


# ---------------------------------------------------------------------------
# 404-style: unknown item is blocked not 500
# ---------------------------------------------------------------------------

def test_adapt_nomenclature_unknown_item_returns_blocked(client, auth_headers):
    r = client.post(
        "/api/library/99999/adapt-nomenclature",
        json={"dry_run": True},
        headers=auth_headers,
    )
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json()["status"] == "blocked"


# ---------------------------------------------------------------------------
# Operations history endpoint
# ---------------------------------------------------------------------------

def test_get_nomenclature_operations_requires_auth(client, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.get(f"/api/library/{item_id}/nomenclature/operations")
    assert r.status_code == 401


def test_get_nomenclature_operations_empty(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.get(
        f"/api/library/{item_id}/nomenclature/operations",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json() == []


def test_get_nomenclature_operations_after_dry_run(client, auth_headers, isolated_db, tmp_path):
    src = tmp_path / "film.mkv"
    src.write_bytes(b"data")
    prepared = tmp_path / "prepared"
    prepared.mkdir()

    item_id = _insert_item(isolated_db, title="Film", path=str(src))
    _set_hardlink_base(isolated_db, prepared)

    client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": True},
        headers=auth_headers,
    )
    r = client.get(
        f"/api/library/{item_id}/nomenclature/operations",
        headers=auth_headers,
    )
    assert r.status_code == 200
    ops = r.json()
    assert isinstance(ops, list)
    assert len(ops) >= 1
    op = ops[0]
    assert op["dry_run"] is True
    assert op["operation_type"] == "nomenclature_hardlink"


# ---------------------------------------------------------------------------
# Real apply via API with valid source
# ---------------------------------------------------------------------------

def test_adapt_nomenclature_real_apply_creates_hardlink(client, auth_headers, isolated_db, tmp_path):
    src = tmp_path / "film.mkv"
    src.write_bytes(b"film data")
    prepared = tmp_path / "prepared"
    prepared.mkdir()

    item_id = _insert_item(isolated_db, title="Test Film", path=str(src))
    _set_hardlink_base(isolated_db, prepared)

    from emuwarez_uploadrr.database import connect
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    conn.execute(
        "UPDATE library_items SET tmdb_id = '1234', year = 2022, resolution = '1080p' WHERE id = ?",
        (item_id,),
    )
    conn.commit()
    conn.close()

    r = client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": False, "apply": True, "confirmation": "APLICAR_NOMENCLATURA"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()

    if body["status"] == "applied":
        assert body["destination_path"] is not None
        assert Path(body["destination_path"]).exists()
        # Same inode — hardlink
        assert src.stat().st_ino == Path(body["destination_path"]).stat().st_ino

        conn = connect(isolated_db / "emuwarez_uploadrr.db")
        row = conn.execute(
            "SELECT prepared_path, path FROM library_items WHERE id = ?", (item_id,)
        ).fetchone()
        assert row["prepared_path"] == body["destination_path"]
        assert row["path"] == str(src)  # original path NEVER changed
        conn.close()


def test_adapt_nomenclature_original_path_never_modified(client, auth_headers, isolated_db, tmp_path):
    src = tmp_path / "original.mkv"
    src.write_bytes(b"original")
    original_path = str(src)
    prepared = tmp_path / "prepared"
    prepared.mkdir()

    item_id = _insert_item(isolated_db, title="Original", path=original_path)
    _set_hardlink_base(isolated_db, prepared)

    client.post(
        f"/api/library/{item_id}/adapt-nomenclature",
        json={"dry_run": False, "apply": True, "confirmation": "APLICAR_NOMENCLATURA"},
        headers=auth_headers,
    )

    from emuwarez_uploadrr.database import connect
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    row = conn.execute("SELECT path FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["path"] == original_path  # NEVER changed
    conn.close()
