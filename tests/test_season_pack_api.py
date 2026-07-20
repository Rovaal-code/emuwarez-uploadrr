"""Tests for the season-pack preview + per-episode read API endpoints.

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations

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
            parent_id, season_number, episode_number, path, quality, updated_at)
           VALUES ('episode', 'One Piece S01E01', 1999, 'Disponible', 'Sin petición', 'No adaptada', ?, 1, 1, ?, 'WEBDL-1080p', CURRENT_TIMESTAMP)""",
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
