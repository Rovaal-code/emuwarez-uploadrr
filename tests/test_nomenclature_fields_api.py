"""API tests for Phase 10A nomenclature fields endpoints."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


# Building the fields now requires an accessible file + MediaInfo.
_MI_OK = {
    "available": True,
    "audio_summary": "ESP AC3 5.1",
    "rows": [
        {"field": "Códec de vídeo", "mediainfo": "AVC", "emu": "H.264"},
        {"field": "Source", "mediainfo": "del nombre del archivo", "emu": "WEB-DL"},
    ],
}


def _seed_item(client, auth_headers, title="Dune", path=None):
    """Insert a library item via DB directly (no sync endpoint needed)."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.web.runtime import _db_path
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with connect(_db_path()) as conn:
        init_db(conn)
        conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, tmdb_id, path) VALUES (?,?,?,?,?)",
            (title, "movie", "downloaded", "438631", path),
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


def test_get_fields_found(client, auth_headers, tmp_path):
    f = tmp_path / "dune.mkv"; f.write_bytes(b"x" * 2048)
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=[]), \
         patch("emuwarez_uploadrr.services.media_info_service.build_mediainfo_report", return_value=_MI_OK):
        item_id = _seed_item(client, auth_headers, title="Dune", path=str(f))
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


def _preview_webdl(client, auth_headers, item_id, query=""):
    fields = {"title": "Pelicula", "year": "2024", "resolution": "1080p", "source": "WEB-DL",
              "provider": "NF", "video_codec": "H.265", "audio_summary": "DDP5.1", "subs": "SPA",
              "tag": "EMUWAREZ"}
    return client.post(
        f"/api/library/{item_id}/nomenclature/preview-fields{query}",
        json={"fields": fields}, headers=auth_headers,
    )


def test_preview_fields_pide_proveedores_a_tmdb_por_defecto(client, auth_headers):
    item_id = _seed_item(client, auth_headers, title="Pelicula")
    with patch("emuwarez_uploadrr.web.api.nomenclature.get_tmdb_available_providers",
               return_value=["NF"]) as tmdb:
        resp = _preview_webdl(client, auth_headers, item_id)
    assert resp.status_code == 200
    assert tmdb.call_count == 1
    assert resp.json()["provider_options"]


def test_preview_fields_sin_proveedores_no_llama_a_tmdb(client, auth_headers):
    """El asistente de subida llama en cada edición y no usa los proveedores."""
    item_id = _seed_item(client, auth_headers, title="Pelicula")
    with patch("emuwarez_uploadrr.web.api.nomenclature.get_tmdb_available_providers",
               return_value=["NF"]) as tmdb:
        resp = _preview_webdl(client, auth_headers, item_id, "?provider_options=false")
    assert resp.status_code == 200
    tmdb.assert_not_called()
    data = resp.json()
    assert data["provider_options"] == []
    assert data["torrent_name"] and data["internal_mkv_title"]


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

    # Regression: save-fields used to leave year/resolution/source/video_codec/
    # audio_summary/subtitle_summary/release_tag NULL on the new proposal row
    # (only proposed_title/proposed_filename/provider_final were set), so a
    # manual upload's "Nomenclatura" card showed every one of these as "–"
    # even though the user had just filled them in. It also wrote `source`
    # into a `source_final` column nobody reads instead of the real `source`
    # column build_nomenclature_proposal()/the job detail page both use.
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.web.runtime import _db_path
    with connect(_db_path()) as conn:
        init_db(conn)
        row = conn.execute(
            "SELECT * FROM nomenclature_proposals WHERE library_item_id = ? ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
    assert row["year"] == "2024"
    assert row["resolution"] == "1080p"
    assert row["source"] == "BluRay"
    assert row["video_codec"] == "H.265"
    assert row["audio_summary"] == "DTS-HD"
    assert row["subtitle_summary"] == "SPA"
    assert row["release_tag"] == "EMUWAREZ"
    # El título del aporte va con espacios; el archivo, que se renombra con
    # proposed_filename, con puntos.
    assert row["proposed_torrent_name"] == data["torrent_name"]
    assert row["proposed_torrent_name"].startswith("SaveTest 2024 ")
    assert row["proposed_filename"].startswith("SaveTest.2024.")
