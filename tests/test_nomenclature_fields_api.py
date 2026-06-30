"""API tests for Phase 10A nomenclature fields endpoints."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def _seed_item(client, auth_headers, title="Dune"):
    """Insert a library item via DB directly (no sync endpoint needed)."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.web.runtime import _db_path
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with connect(_db_path()) as conn:
        init_db(conn)
        conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, tmdb_id) VALUES (?,?,?,?)",
            (title, "movie", "downloaded", "438631"),
        )
        conn.commit()
        item_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        conn.execute(
            """INSERT INTO nomenclature_proposals
               (library_item_id, status, proposed_filename, proposed_title, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (item_id, "valid", f"{title}.2021.1080p.WEB-DL.AMZN-EMUWAREZ", title, now, now),
        )
        conn.commit()
    return item_id


def test_get_sources_requires_auth(client):
    resp = client.get("/api/nomenclature/sources")
    assert resp.status_code == 401


def test_get_sources_authenticated(client, auth_headers):
    resp = client.get("/api/nomenclature/sources", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    codes = [s["code"] for s in data["sources"]]
    assert "WEB-DL" in codes
    assert "BluRay" in codes


def test_get_providers_requires_auth(client):
    resp = client.get("/api/nomenclature/providers")
    assert resp.status_code == 401


def test_get_providers_authenticated(client, auth_headers):
    resp = client.get("/api/nomenclature/providers", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    codes = [p["code"] for p in data["providers"]]
    assert "AMZN" in codes
    assert "NF" in codes


def test_get_fields_requires_auth(client):
    resp = client.get("/api/library/1/nomenclature/fields")
    assert resp.status_code == 401


def test_get_fields_not_found(client, auth_headers):
    resp = client.get("/api/library/9999/nomenclature/fields", headers=auth_headers)
    assert resp.status_code == 404


def test_get_fields_found(client, auth_headers):
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=[]):
        item_id = _seed_item(client, auth_headers, title="Dune")
        resp = client.get(f"/api/library/{item_id}/nomenclature/fields", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "fields" in data
    assert "torrent_name" in data
    assert "internal_mkv_title" in data


def test_preview_fields_requires_auth(client):
    resp = client.post("/api/library/1/nomenclature/preview-fields", json={"fields": {}})
    assert resp.status_code == 401


def test_preview_fields_webdl(client, auth_headers):
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=["NF", "AMZN"]):
        item_id = _seed_item(client, auth_headers, title="Pelicula")
        fields = {
            "title": "Pelicula",
            "year": "2024",
            "resolution": "1080p",
            "source": "WEB-DL",
            "provider": "NF",
            "video_codec": "H.265",
            "audio_summary": "DDP5.1",
            "subs": "SPA",
            "tag": "EMUWAREZ",
        }
        resp = client.post(
            f"/api/library/{item_id}/nomenclature/preview-fields",
            json={"fields": fields},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "torrent_name" in data
    assert "internal_mkv_title" in data


def test_save_fields_requires_auth(client):
    resp = client.post("/api/library/1/nomenclature/save-fields", json={"fields": {}})
    assert resp.status_code == 401


def test_save_fields_creates_proposal(client, auth_headers):
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=[]):
        item_id = _seed_item(client, auth_headers, title="SaveTest")
        fields = {
            "title": "SaveTest",
            "year": "2024",
            "resolution": "1080p",
            "source": "BluRay",
            "provider": None,
            "video_codec": "H.265",
            "audio_summary": "DTS-HD",
            "subs": "SPA",
            "tag": "EMUWAREZ",
        }
        resp = client.post(
            f"/api/library/{item_id}/nomenclature/save-fields",
            json={"fields": fields},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "torrent_name" in data
    assert "AMZN" not in data.get("torrent_name", "")
