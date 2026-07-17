"""GET /api/library/{id}/suggest-provider — TMDB provider detection.

The TMDb watch-providers call is mocked; no real network traffic.
"""
from __future__ import annotations

from unittest.mock import patch


def _insert_movie(tmdb_id="1234", path=None, source=None):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.web.runtime import _db_path
    conn = connect(_db_path())
    init_db(conn)
    try:
        cur = conn.execute(
            """INSERT INTO library_items
               (item_type,title,instance_id,instance_type,instance_name,external_id,
                tmdb_id,local_status,nomenclature_status,path,source)
               VALUES ('movie','Peli WEB',1,'radarr','R','x1',?, 'Disponible','No adaptada',?,?)""",
            (tmdb_id, path, source),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def test_suggest_provider_requires_auth(client):
    assert client.get("/api/library/1/suggest-provider").status_code == 401


def test_suggest_provider_404_for_missing_item(client, auth_headers):
    assert client.get("/api/library/99999/suggest-provider", headers=auth_headers).status_code == 404


def test_suggest_provider_uses_priority(client, auth_headers):
    item_id = _insert_movie()
    # TMDb says the title is on Netflix and Disney+; the default priority
    # (AMZN, NF, DSNP, …) prefers NF over DSNP, so NF must win.
    with patch(
        "emuwarez_uploadrr.services.source_assistant.get_tmdb_available_providers",
        return_value=["DSNP", "NF"],
    ):
        resp = client.get(f"/api/library/{item_id}/suggest-provider", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested"] == "NF"
    assert set(data["tmdb_providers"]) == {"NF", "DSNP"}


def test_suggest_provider_none_when_no_tmdb_providers(client, auth_headers):
    item_id = _insert_movie()
    with patch(
        "emuwarez_uploadrr.services.source_assistant.get_tmdb_available_providers",
        return_value=[],
    ):
        resp = client.get(f"/api/library/{item_id}/suggest-provider", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["suggested"] is None


def test_suggest_provider_none_without_tmdb_id(client, auth_headers):
    item_id = _insert_movie(tmdb_id=None)
    resp = client.get(f"/api/library/{item_id}/suggest-provider", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["suggested"] is None


def test_suggest_provider_prefers_filename_over_tmdb_no_network_call(client, auth_headers):
    """Regression: switching Source away and back to WEB-DL in the upload
    wizard used to always re-query TMDb even when the filename already had a
    provider (e.g. "...WEB-DL AMZN..."). The filename must win, with zero
    TMDb calls — not just a matching final answer."""
    item_id = _insert_movie(
        path="/data/movies/Peli (2024)/Peli.2024.1080p.WEB-DL.AMZN.x265-EMUWAREZ.mkv",
        source="WEB-DL",
    )
    with patch(
        "emuwarez_uploadrr.services.source_assistant.get_tmdb_available_providers",
    ) as mock_tmdb:
        resp = client.get(f"/api/library/{item_id}/suggest-provider", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested"] == "AMZN"
    assert data["reason"] == "Detectado en el nombre del archivo"
    mock_tmdb.assert_not_called()


def test_suggest_provider_falls_back_to_tmdb_when_filename_has_no_provider(client, auth_headers):
    item_id = _insert_movie(
        path="/data/movies/Peli (2024)/Peli.2024.1080p.WEB-DL.x265-EMUWAREZ.mkv",
        source="WEB-DL",
    )
    with patch(
        "emuwarez_uploadrr.services.source_assistant.get_tmdb_available_providers",
        return_value=["NF"],
    ) as mock_tmdb:
        resp = client.get(f"/api/library/{item_id}/suggest-provider", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["suggested"] == "NF"
    mock_tmdb.assert_called_once()
