"""Los trabajos que deja el preflight se ven en /api/uploads, y el preflight no toca el disco (Phase 6A).

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations


def _insert_item(isolated_db, local_status="Disponible", path="/fake/movie.mkv", title="Test Movie"):
    # isolated_db is tmp_path; app uses CONFIG_DIR/emuwarez_uploadrr.db
    from emuwarez_uploadrr.database import connect
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    cursor = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path)
           VALUES ('movie', ?, ?, 'Sin petición', ?)""",
        (title, local_status, path),
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id


def _preflight(isolated_db, item_id) -> dict:
    """El trabajo que deja el preflight (lo que hace `upload` de la CLI)."""
    from emuwarez_uploadrr.database import connect
    from emuwarez_uploadrr.services.upload_preflight import build_upload_preflight
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    try:
        return build_upload_preflight(item_id, conn=conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/uploads
# ---------------------------------------------------------------------------

def test_get_uploads_no_auth(client):
    r = client.get("/api/uploads")
    assert r.status_code == 401


def test_get_uploads_empty(client, auth_headers):
    r = client.get("/api/uploads", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_uploads_after_preflight(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    _preflight(isolated_db, item_id)
    r = client.get("/api/uploads", headers=auth_headers)
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) >= 1


# ---------------------------------------------------------------------------
# GET /api/uploads/{job_id}
# ---------------------------------------------------------------------------

def test_get_upload_job_not_found(client, auth_headers):
    r = client.get("/api/uploads/99999", headers=auth_headers)
    assert r.status_code == 404


def test_get_upload_job_exists(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    job_id = _preflight(isolated_db, item_id)["job"]["id"]
    r = client.get(f"/api/uploads/{job_id}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == job_id


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------

def test_no_filesystem_modification(isolated_db, monkeypatch):
    """La propuesta de nomenclatura y el preflight nunca llaman a os.rename ni a os.remove."""
    import os
    calls: list = []

    def fake_rename(*args, **kwargs):
        calls.append(("rename", args))
        raise AssertionError(f"os.rename called: {args}")

    def fake_remove(*args, **kwargs):
        calls.append(("remove", args))
        raise AssertionError(f"os.remove called: {args}")

    monkeypatch.setattr(os, "rename", fake_rename)
    monkeypatch.setattr(os, "remove", fake_remove)

    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    cursor = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path)
           VALUES ('movie', 'Safe Test', 'Disponible', 'Sin petición', '/fake/safe.mkv')""",
    )
    conn.commit()
    item_id = cursor.lastrowid

    from emuwarez_uploadrr.services.nomenclature import build_nomenclature_proposal
    from emuwarez_uploadrr.services.upload_preflight import build_upload_preflight
    build_nomenclature_proposal(item_id, conn=conn)
    build_upload_preflight(item_id, conn=conn)
    conn.close()

    assert len(calls) == 0, f"Filesystem was modified: {calls}"
