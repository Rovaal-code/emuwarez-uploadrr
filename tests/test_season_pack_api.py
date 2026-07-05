"""Tests for the season-pack preview/apply API endpoints (Phase 6 of the
Series/Season/Episode hierarchy batch).

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations

from emuwarez_uploadrr.database import connect
from emuwarez_uploadrr.services.season_pack import CONFIRMATION_TOKEN


def _seed_season_with_episode(isolated_db, tmp_path):
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('hardlink_base', ?)",
        (str(tmp_path / "prepared"),),
    )
    (tmp_path / "prepared").mkdir(exist_ok=True)
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
    assert len(data["episodes"]) == 1
    assert data["season_pack_title"].startswith("One Piece S01")


def test_adapt_pack_dry_run(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.post(
        f"/api/library/season/{season_id}/adapt-pack",
        json={"dry_run": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert not list((tmp_path / "prepared").rglob("*.mkv"))


def test_adapt_pack_apply_requires_confirmation(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.post(
        f"/api/library/season/{season_id}/adapt-pack",
        json={"dry_run": False, "apply": True},
        headers=auth_headers,
    )
    data = resp.json()
    assert data["status"] == "blocked"


def test_adapt_pack_apply_real(client, auth_headers, isolated_db, tmp_path):
    season_id = _seed_season_with_episode(isolated_db, tmp_path)
    resp = client.post(
        f"/api/library/season/{season_id}/adapt-pack",
        json={"dry_run": False, "apply": True, "confirmation": CONFIRMATION_TOKEN},
        headers=auth_headers,
    )
    data = resp.json()
    assert data["status"] == "applied"
    assert len(list((tmp_path / "prepared").rglob("*.mkv"))) == 1
