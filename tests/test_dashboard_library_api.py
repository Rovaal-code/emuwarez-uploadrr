"""Tests for dashboard, library, missing, instances, and sync API endpoints (Phase 4).

Uses TestClient with isolated temp DB (conftest.py provides auth_headers fixture).
HTTP calls to Radarr/Sonarr are mocked so no real *Arr server is needed.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Instances API
# ---------------------------------------------------------------------------

def test_instances_list_empty(client, auth_headers):
    resp = client.get("/api/instances", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_instances_create(client, auth_headers):
    resp = client.post(
        "/api/instances",
        json={"type": "radarr", "name": "Radarr Test", "url": "http://radarr:7878", "api_key": "key123"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True


def test_instances_list_after_create(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R1", "url": "http://r:7878", "api_key": "key1"},
        headers=auth_headers,
    )
    resp = client.get("/api/instances", headers=auth_headers)
    items = resp.json()
    assert len(items) == 1
    # API key must NOT appear in full
    item = items[0]
    assert "api_key" not in item  # renamed to api_key_masked
    assert "api_key_masked" in item
    assert item["api_key_masked"] != "key1"


def test_instances_create_invalid_type(client, auth_headers):
    resp = client.post(
        "/api/instances",
        json={"type": "jellyfin", "name": "J", "url": "http://j:8096", "api_key": "k"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_instances_test_connection(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "TestRadarr", "url": "http://radarr:7878", "api_key": "key123"},
        headers=auth_headers,
    )
    # Get the instance id
    instances = client.get("/api/instances", headers=auth_headers).json()
    iid = instances[0]["id"]

    with patch("emuwarez_uploadrr.integrations.radarr.arr_request", return_value={"version": "5.0.0"}):
        resp = client.post(f"/api/instances/{iid}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["version"] == "5.0.0"
    assert data["instance_id"] == iid


def test_instances_test_not_found(client, auth_headers):
    resp = client.post("/api/instances/9999/test", headers=auth_headers)
    assert resp.status_code == 404


def test_instances_require_auth(client):
    resp = client.get("/api/instances")
    assert resp.status_code == 401

    resp = client.post("/api/instances", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Sync API
# ---------------------------------------------------------------------------

def test_sync_requires_auth(client):
    resp = client.post("/api/sync")
    assert resp.status_code == 401


def test_sync_no_instances(client, auth_headers):
    resp = client.post("/api/sync", json={"include_episodes": True}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["imported"] == 0


def test_sync_with_radarr_instance(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [
        {"id": 1, "title": "Film A", "year": 2021, "tmdbId": 100,
         "movieFile": {"id": 10, "path": "/m/A.mkv", "size": 1000,
                       "quality": {"quality": {"name": "WEB-DL-1080p"}}}},
        {"id": 2, "title": "Film B", "year": 2022, "tmdbId": 101},
    ]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        resp = client.post("/api/sync", json={"include_episodes": False}, headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["missing"] == 1


def test_instance_sync_endpoint(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R2", "url": "http://r2:7878", "api_key": "k2"},
        headers=auth_headers,
    )
    iid = client.get("/api/instances", headers=auth_headers).json()[0]["id"]
    movies = [{"id": 5, "title": "Solo Sync", "year": 2023, "tmdbId": 500}]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        resp = client.post(f"/api/instances/{iid}/sync", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 1


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------

def test_dashboard_summary_requires_auth(client):
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 401


def test_dashboard_summary_empty(client, auth_headers):
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["library_total"] == 0
    assert data["available"] == 0
    assert data["missing"] == 0
    assert data["last_sync_at"] is None


def test_dashboard_summary_after_sync(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [
        {"id": 1, "title": "Available", "year": 2020, "tmdbId": 1,
         "movieFile": {"id": 10, "path": "/m/a.mkv", "size": 100,
                       "quality": {"quality": {"name": "WEB-DL-1080p"}}}},
        {"id": 2, "title": "Missing", "year": 2020, "tmdbId": 2},
    ]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={"include_episodes": False}, headers=auth_headers)

    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    data = resp.json()
    assert data["available"] == 1
    assert data["missing"] == 1
    assert data["library_total"] == 2
    assert data["radarr_items"] == 2


def test_dashboard_summary_requests_mine_counts_only_visible_matching_author(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path())
    init_db(conn)
    conn.execute(
        "INSERT INTO request_items (emu_id, title, author, author_visible, updated_at) "
        "VALUES ('e1', 'Mine visible', 'myuser', 1, CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO request_items (emu_id, title, author, author_visible, updated_at) "
        "VALUES ('e2', 'Mine but hidden', 'myuser', 0, CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO request_items (emu_id, title, author, author_visible, updated_at) "
        "VALUES ('e3', 'Someone else', 'otheruser', 1, CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()

    # Before configuring emu.username, requests_mine must be 0 (no false positives).
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.json()["requests_mine"] == 0

    client.put("/api/settings", json={"emu_username": "myuser"}, headers=auth_headers)
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.json()["requests_mine"] == 1


def test_dashboard_activity_empty(client, auth_headers):
    resp = client.get("/api/dashboard/activity", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_dashboard_activity_shows_sync(client, auth_headers):
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={}, headers=auth_headers)

    resp = client.get("/api/dashboard/activity", headers=auth_headers)
    items = resp.json()["items"]
    assert len(items) >= 1
    assert items[0]["name"] == "sync-library"


# ---------------------------------------------------------------------------
# Library API
# ---------------------------------------------------------------------------

def test_library_requires_auth(client):
    resp = client.get("/api/library")
    assert resp.status_code == 401


def test_library_empty(client, auth_headers):
    resp = client.get("/api/library", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_library_after_sync(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [
        {"id": 1, "title": "Annihilation", "year": 2018, "tmdbId": 300804,
         "movieFile": {"id": 10, "path": "/m/a.mkv", "size": 8000000000,
                       "quality": {"quality": {"name": "Bluray-1080p"}}}},
    ]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={"include_episodes": False}, headers=auth_headers)

    resp = client.get("/api/library", headers=auth_headers)
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["title"] == "Annihilation"
    assert item["resolution"] == "1080p"
    assert item["source"] == "BluRay"


def test_library_after_sync_includes_poster_url(client, auth_headers):
    """Phase 11E — poster_url extracted from Radarr's images[] at sync time."""
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [
        {"id": 1, "title": "Annihilation", "year": 2018, "tmdbId": 300804,
         "movieFile": {"id": 10, "path": "/m/a.mkv", "size": 8000000000,
                       "quality": {"quality": {"name": "Bluray-1080p"}}},
         "images": [{"coverType": "poster", "remoteUrl": "https://example.com/annihilation.jpg"}]},
    ]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={"include_episodes": False}, headers=auth_headers)

    resp = client.get("/api/library", headers=auth_headers)
    item = resp.json()["items"][0]
    assert item["poster_url"] == "https://example.com/annihilation.jpg"


def test_library_filter_by_type(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [{"id": 10, "title": "Film", "year": 2020, "tmdbId": 10}]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={}, headers=auth_headers)

    resp = client.get("/api/library?type=movie", headers=auth_headers)
    assert resp.json()["total"] == 1

    resp = client.get("/api/library?type=series", headers=auth_headers)
    assert resp.json()["total"] == 0


def test_library_detail(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [{"id": 20, "title": "Detailed Film", "year": 2019, "tmdbId": 20000}]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={}, headers=auth_headers)

    items = client.get("/api/library", headers=auth_headers).json()["items"]
    item_id = items[0]["id"]

    resp = client.get(f"/api/library/{item_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Detailed Film"


def test_library_detail_not_found(client, auth_headers):
    resp = client.get("/api/library/99999", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Missing API
# ---------------------------------------------------------------------------

def test_missing_requires_auth(client):
    resp = client.get("/api/missing")
    assert resp.status_code == 401


def test_missing_empty(client, auth_headers):
    resp = client.get("/api/missing", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []


def test_missing_after_sync(client, auth_headers):
    client.post(
        "/api/instances",
        json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [
        {"id": 30, "title": "Have It", "year": 2020, "tmdbId": 30,
         "movieFile": {"id": 300, "path": "/m/have.mkv", "size": 1000,
                       "quality": {"quality": {"name": "WEB-DL-1080p"}}}},
        {"id": 31, "title": "Want It", "year": 2020, "tmdbId": 31},
        {"id": 32, "title": "Downloading It", "year": 2020, "tmdbId": 32},
    ]
    queue = [{"movieId": 32, "status": "downloading", "statusMessages": []}]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=queue),
    ):
        client.post("/api/sync", json={}, headers=auth_headers)

    resp = client.get("/api/missing", headers=auth_headers)
    data = resp.json()
    # Should include "Want It" (missing) and "Downloading It" (downloading), but not "Have It"
    assert data["total"] == 2
    titles = {i["title"] for i in data["items"]}
    assert "Have It" not in titles
    assert "Want It" in titles
    assert "Downloading It" in titles


# ---------------------------------------------------------------------------
# GET /api/dashboard/library-activity (Phase 11F)
# ---------------------------------------------------------------------------

def test_dashboard_library_activity_requires_auth(client):
    resp = client.get("/api/dashboard/library-activity")
    assert resp.status_code == 401


def test_dashboard_library_activity_empty(client, auth_headers):
    resp = client.get("/api/dashboard/library-activity", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_dashboard_library_activity_prioritizes_filled_requests(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services.library import update_request_status

    movies = [
        {"id": 1, "title": "No Request", "year": 2020, "tmdbId": 1,
         "movieFile": {"id": 10, "path": "/m/a.mkv", "size": 1000}},
        {"id": 2, "title": "Compatible Match", "year": 2020, "tmdbId": 2,
         "movieFile": {"id": 20, "path": "/m/b.mkv", "size": 1000}},
        {"id": 3, "title": "Filled Request", "year": 2020, "tmdbId": 3,
         "movieFile": {"id": 30, "path": "/m/c.mkv", "size": 1000}},
    ]
    client.post(
        "/api/instances", json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={"include_episodes": False}, headers=auth_headers)

    conn = connect(db_path())
    init_db(conn)
    rows = {r["title"]: r["id"] for r in conn.execute("SELECT id, title FROM library_items").fetchall()}
    update_request_status(conn, rows["Compatible Match"], "Compatible")
    update_request_status(conn, rows["Filled Request"], "Llena")
    conn.close()

    resp = client.get("/api/dashboard/library-activity", headers=auth_headers)
    titles = [i["title"] for i in resp.json()["items"]]
    assert titles[0] == "Filled Request"
    assert titles[1] == "Compatible Match"
    assert titles[2] == "No Request"


def test_dashboard_library_activity_respects_limit(client, auth_headers):
    client.post(
        "/api/instances", json={"type": "radarr", "name": "R", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    movies = [{"id": i, "title": f"Movie {i}", "year": 2020, "tmdbId": i} for i in range(1, 6)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        client.post("/api/sync", json={"include_episodes": False}, headers=auth_headers)

    resp = client.get("/api/dashboard/library-activity?limit=2", headers=auth_headers)
    assert len(resp.json()["items"]) == 2
