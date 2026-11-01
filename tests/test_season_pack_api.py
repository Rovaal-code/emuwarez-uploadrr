"""Tests for the season-pack preview + per-episode read API endpoints.

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect


def _seed_season_with_episode(isolated_db, tmp_path):
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status, updated_at)
           VALUES ('series', 'One Piece', 1999, 'Parcial', 'Sin petición', 'N/A', CURRENT_TIMESTAMP)"""
    )
    series_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status, parent_id, season_number, updated_at)
           VALUES ('season', 'One Piece - Temporada 1', 1999, 'Parcial', 'Sin petición', 'N/A', ?, 1, CURRENT_TIMESTAMP)""",
        (series_id,),
    )
    season_id = cur.lastrowid
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"video")
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status,
            parent_id, season_number, episode_number, path, quality, subtitle_languages, updated_at)
           VALUES ('episode', 'One Piece S01E01', 1999, 'Disponible', 'Sin petición', 'No adaptada', ?, 1, 1, ?, 'WEBDL-1080p', 'spa', CURRENT_TIMESTAMP)""",
        (season_id, str(src)),
    )
    conn.commit()
    conn.close()
    return season_id


def test_pack_preview_requires_auth(client):
    resp = client.get("/api/library/season/1/pack-preview")
    assert resp.status_code == 401


def test_pack_preview_not_found(client, auth_headers):
    resp = client.get("/api/library/season/99999/pack-preview", headers=auth_headers)
    assert resp.status_code == 404


def test_pack_preview_valid(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.get(f"/api/library/season/{season_id}/pack-preview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "valid"
    assert data["pack_folder"] == str(tmp_path)
    assert len(data["episodes"]) == 1
    assert data["season_pack_title"].startswith("One Piece S01")


def test_pack_preview_exposes_field_breakdown(client, auth_headers, isolated_db, tmp_path):
    """Regression: build_season_pack_plan() already computed series_title/
    year/resolution/source/video_codec/audio_summary/subtitle_summary/
    release_tag internally, but SeasonPackPlanResponse (the Pydantic
    response_model) silently dropped every one of them before this — the
    wizard's season view had no way to show the same field-by-field
    confirmation grid a movie/episode gets, because the API response never
    carried the data at all."""
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.get(f"/api/library/season/{season_id}/pack-preview", headers=auth_headers)
    data = resp.json()
    assert data["series_title"] == "One Piece"
    assert data["year"] == 1999
    assert data["resolution"] == "1080p"
    assert data["release_tag"]


def test_pack_preview_exposes_season_number(client, auth_headers, isolated_db, tmp_path):
    """Regression: season_number was computed internally but never exposed
    in the response — the wizard's live title-preview call (fired whenever
    the user edits Source/Proveedor/Tag) has no other way to know it when
    the season was opened from its series' own ficha (the wizard's `item`
    prop is the series there, which has no season_number of its own),
    silently dropping the "Sxx" from the recomputed title in that case."""
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.get(f"/api/library/season/{season_id}/pack-preview", headers=auth_headers)
    assert resp.json()["season_number"] == 1


def test_pack_preview_progress_requires_auth(client):
    resp = client.get("/api/library/season/1/pack-preview/progress")
    assert resp.status_code == 401


def test_pack_preview_progress_reaches_total_after_preview(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    client.get(f"/api/library/season/{season_id}/pack-preview", headers=auth_headers)
    resp = client.get(f"/api/library/season/{season_id}/pack-preview/progress", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["done"] == data["total"] == 1


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_episode_names_endpoint(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.get(f"/api/library/season/{season_id}/episode-names", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["episodes"]) == 1
    assert data["episodes"][0]["torrent_name"]


def test_episode_mediainfo_endpoint(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.get(f"/api/library/season/{season_id}/episode-mediainfo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["episodes"]) == 1
    assert "report" in data["episodes"][0]


def test_episode_remux_preview_endpoint(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.get(f"/api/library/season/{season_id}/episode-remux-preview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["episodes"]) == 1
    assert "plan" in data["episodes"][0]


def test_pack_preview_fields_endpoint(client, auth_headers, isolated_db, tmp_path):
    """Cheap live preview while editing Source/Proveedor/Tag — no DB/disk
    work, season_id in the URL only for route consistency."""
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.post(
        f"/api/library/season/{season_id}/pack-preview-fields",
        json={
            "title": "One Piece", "year": 1999, "season_number": 1,
            "resolution": "1080p", "source": "BluRay", "video_codec": "x264",
            "audio_summary": "DUAL DD 5.1", "subtitle_summary": "SUBS", "tag": "CCX94",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["torrent_name"] == "One Piece S01 1999 1080p BluRay x264 DUAL DD 5.1 SUBS-CCX94"


def test_upload_queue_endpoint_persists_season_overrides(client, auth_headers, isolated_db, tmp_path):
    """Confirms UploadQueueBody's new source/provider/tag fields actually
    reach the DB for a season target, end to end through the real endpoint —
    the service layer already covers queue_upload_for_item() directly."""
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.post(
        f"/api/library/{season_id}/upload/queue",
        json={"source": "BluRay", "provider": None, "tag": "MYTAG"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    job_id = resp.json()["job"]["id"]
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    row = conn.execute("SELECT season_overrides_json FROM upload_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    import json as _json
    assert _json.loads(row["season_overrides_json"]) == {
        "source": "BluRay", "provider": None, "tag": "MYTAG", "title": None}


def test_adapt_pack_endpoint_removed(client, auth_headers, isolated_db, tmp_path):
    # Retired along with SeasonPackModal.tsx — applying a season now only
    # happens through the queued-upload pipeline (POST /library/{id}/upload/queue).
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.post(
        f"/api/library/season/{season_id}/adapt-pack",
        json={"dry_run": True},
        headers=auth_headers,
    )
    assert resp.status_code in (404, 405)
