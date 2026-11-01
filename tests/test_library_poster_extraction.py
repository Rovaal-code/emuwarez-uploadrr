"""Tests for poster_url extraction from Radarr/Sonarr images[] (Phase 11E).

All HTTP calls are mocked — no real Radarr/Sonarr required.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.integrations.base import extract_backdrop_url, extract_poster_url
from emuwarez_uploadrr.integrations.radarr import movie_to_library_item
from emuwarez_uploadrr.integrations.sonarr import episode_to_library_item, series_to_library_item


# ---------------------------------------------------------------------------
# extract_poster_url() — pure unit tests
# ---------------------------------------------------------------------------

def test_extract_poster_url_prefers_remote_url():
    images = [
        {"coverType": "fanart", "remoteUrl": "https://example.com/fanart.jpg"},
        {"coverType": "poster", "url": "/MediaCover/1/poster.jpg", "remoteUrl": "https://example.com/poster.jpg"},
    ]
    assert extract_poster_url(images) == "https://example.com/poster.jpg"


def test_una_imagen_http_se_pide_por_https():
    """La CSP de la interfaz (img-src 'self' https: data:) bloquearía un http:// y el navegador ya no lo mezcla."""
    images = [
        {"coverType": "poster", "url": "/MediaCover/1/poster.jpg", "remoteUrl": "http://artworks.thetvdb.com/banners/posters/1.jpg"},
        {"coverType": "fanart", "remoteUrl": " HTTP://image.tmdb.org/t/p/original/f.jpg "},
    ]
    assert extract_poster_url(images) == "https://artworks.thetvdb.com/banners/posters/1.jpg"
    assert extract_backdrop_url(images) == "https://image.tmdb.org/t/p/original/f.jpg"


def test_una_imagen_https_se_deja_como_esta():
    images = [{"coverType": "poster", "remoteUrl": "https://image.tmdb.org/t/p/original/a.jpg?x=http://y"}]
    assert extract_poster_url(images) == "https://image.tmdb.org/t/p/original/a.jpg?x=http://y"


def test_extract_poster_url_no_poster_entry():
    images = [{"coverType": "fanart", "remoteUrl": "https://example.com/fanart.jpg"}]
    assert extract_poster_url(images) is None


def test_extract_poster_url_poster_without_remote_url():
    images = [{"coverType": "poster", "url": "/MediaCover/1/poster.jpg"}]
    assert extract_poster_url(images) is None


def test_extract_poster_url_empty_list():
    assert extract_poster_url([]) is None


def test_extract_poster_url_none():
    assert extract_poster_url(None) is None


def test_extract_poster_url_not_a_list():
    assert extract_poster_url({"coverType": "poster"}) is None


def test_extract_poster_url_ignores_malformed_entries():
    images = ["not-a-dict", {"coverType": "poster", "remoteUrl": "https://example.com/p.jpg"}]
    assert extract_poster_url(images) == "https://example.com/p.jpg"


def test_extract_poster_url_blank_remote_url_treated_as_missing():
    images = [{"coverType": "poster", "remoteUrl": "   "}]
    assert extract_poster_url(images) is None


# ---------------------------------------------------------------------------
# movie_to_library_item / series_to_library_item / episode_to_library_item
# ---------------------------------------------------------------------------

def test_movie_to_library_item_sets_poster_url():
    movie = {
        "id": 1, "title": "Inception", "year": 2010, "tmdbId": 100,
        "images": [{"coverType": "poster", "remoteUrl": "https://example.com/inception.jpg"}],
    }
    item = movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert item.poster_url == "https://example.com/inception.jpg"


def test_movie_to_library_item_without_images_key():
    movie = {"id": 2, "title": "No Images", "year": 2020}
    item = movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert item.poster_url is None


def test_series_to_library_item_sets_poster_url():
    series = {
        "id": 5, "title": "Breaking Bad", "year": 2008,
        "images": [{"coverType": "poster", "remoteUrl": "https://example.com/bb.jpg"}],
    }
    item = series_to_library_item(series, instance_id=1, instance_name="Sonarr")
    assert item.poster_url == "https://example.com/bb.jpg"


def test_episode_to_library_item_uses_series_poster():
    series = {
        "id": 5, "title": "Breaking Bad",
        "images": [{"coverType": "poster", "remoteUrl": "https://example.com/bb.jpg"}],
    }
    episode = {"id": 10, "seriesId": 5, "seasonNumber": 1, "episodeNumber": 1, "hasFile": False}
    item = episode_to_library_item(episode, None, series, instance_id=1, instance_name="Sonarr")
    assert item.poster_url == "https://example.com/bb.jpg"


# ---------------------------------------------------------------------------
# Full sync_instance() end to end — poster_url lands in library_items row
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_conn():
    conn = connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES (?, ?, ?, ?, 1)",
        ("radarr", "Test Radarr", "http://radarr:7878", "key123"),
    )
    conn.commit()
    yield conn
    conn.close()


def test_sync_radarr_persists_poster_url(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [{
        "id": 1, "title": "Inception", "year": 2010, "tmdbId": 100,
        "movieFile": {"id": 10, "path": "/movies/Inception.mkv", "size": 1000000,
                       "quality": {"quality": {"name": "WEB-DL-1080p"}}},
        "images": [{"coverType": "poster", "remoteUrl": "https://example.com/inception.jpg"}],
    }]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    row = mem_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["poster_url"] == "https://example.com/inception.jpg"


def test_sync_radarr_without_images_leaves_poster_null(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [{"id": 2, "title": "No Poster", "year": 2020}]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    row = mem_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["poster_url"] is None
