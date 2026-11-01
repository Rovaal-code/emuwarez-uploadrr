"""Tests for nomenclature and upload preflight API endpoints (Phase 6A).

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations

import pytest


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


# ---------------------------------------------------------------------------
# GET /api/library/{id}/nomenclature
# ---------------------------------------------------------------------------

def test_get_nomenclature_no_auth(client):
    r = client.get("/api/library/1/nomenclature")
    assert r.status_code == 401


def test_get_nomenclature_not_found(client, auth_headers):
    r = client.get("/api/library/99999/nomenclature", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is False
    assert "message" in data


# ---------------------------------------------------------------------------
# POST /api/library/{id}/nomenclature/preview
# ---------------------------------------------------------------------------

def test_preview_nomenclature_no_auth(client):
    r = client.post("/api/library/1/nomenclature/preview", json={"force_refresh": False})
    assert r.status_code == 401


def test_preview_nomenclature_item_not_found(client, auth_headers):
    r = client.post("/api/library/99999/nomenclature/preview", json={"force_refresh": False}, headers=auth_headers)
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json()
        assert data.get("status") == "blocked"


def test_preview_nomenclature_available_item(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(f"/api/library/{item_id}/nomenclature/preview", json={"force_refresh": False}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "library_item_id" in data
    assert data["library_item_id"] == item_id
    assert "warnings" in data
    assert "errors" in data
    assert isinstance(data["warnings"], list)


def test_preview_nomenclature_faltante_item(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db, local_status="Faltante")
    r = client.post(f"/api/library/{item_id}/nomenclature/preview", json={"force_refresh": False}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "blocked"
    assert len(data["errors"]) > 0


def test_preview_nomenclature_force_refresh(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r1 = client.post(f"/api/library/{item_id}/nomenclature/preview", json={"force_refresh": False}, headers=auth_headers)
    r2 = client.post(f"/api/library/{item_id}/nomenclature/preview", json={"force_refresh": True}, headers=auth_headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Both return valid proposals
    assert r2.json().get("library_item_id") == item_id


def test_get_nomenclature_after_preview(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    client.post(f"/api/library/{item_id}/nomenclature/preview", json={"force_refresh": False}, headers=auth_headers)
    r = client.get(f"/api/library/{item_id}/nomenclature", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["proposal"] is not None


# ---------------------------------------------------------------------------
# POST /api/library/{id}/adapt-nomenclature
# ---------------------------------------------------------------------------

def test_adapt_nomenclature_no_auth(client):
    r = client.post("/api/library/1/adapt-nomenclature", json={"dry_run": True, "apply": False})
    assert r.status_code == 401


def test_adapt_nomenclature_dry_run(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(f"/api/library/{item_id}/adapt-nomenclature", json={"dry_run": True, "apply": False}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data.get("applied") is False or data.get("dry_run") is True


def test_adapt_nomenclature_apply_blocked(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(f"/api/library/{item_id}/adapt-nomenclature", json={"dry_run": False, "apply": True}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    # Phase 6B: returns real NomenclatureApplyResult; blocked without confirmation
    assert data.get("status") == "blocked"


# ---------------------------------------------------------------------------
# POST /api/library/{id}/upload/preflight
# ---------------------------------------------------------------------------

def test_upload_preflight_no_auth(client):
    r = client.post("/api/library/1/upload/preflight", json={"request_id": None})
    assert r.status_code == 401


def test_upload_preflight_item_not_found(client, auth_headers):
    r = client.post("/api/library/99999/upload/preflight", json={"request_id": None}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "blocked"


def test_upload_preflight_creates_job(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(f"/api/library/{item_id}/upload/preflight", json={"request_id": None}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ready", "blocked")
    assert data["job"] is not None
    assert "warnings" in data
    assert "errors" in data
    assert isinstance(data["warnings"], list)


def test_upload_preflight_blocked_without_config(client, auth_headers, isolated_db):
    item_id = _insert_item(isolated_db)
    r = client.post(f"/api/library/{item_id}/upload/preflight", json={"request_id": None}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    # Without uploadrr config it must be blocked
    assert data["status"] == "blocked"
    assert any("uploadrr" in e.lower() for e in data["errors"])


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
    client.post(f"/api/library/{item_id}/upload/preflight", json={"request_id": None}, headers=auth_headers)
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
    preflight_resp = client.post(f"/api/library/{item_id}/upload/preflight", json={"request_id": None}, headers=auth_headers)
    job_id = preflight_resp.json()["job"]["id"]
    r = client.get(f"/api/uploads/{job_id}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == job_id


# ---------------------------------------------------------------------------
# Safety checks
# ---------------------------------------------------------------------------

def test_no_filesystem_modification(isolated_db, monkeypatch):
    """Ensure nomenclature endpoints never call os.rename or os.remove."""
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
