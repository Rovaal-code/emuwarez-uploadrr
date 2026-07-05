"""Tests for library sync and quality extraction (Phase 4).

All HTTP calls are mocked — no real Radarr/Sonarr required.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.models import LocalStatus
from emuwarez_uploadrr.services import quality as quality_svc


# ---------------------------------------------------------------------------
# Quality helpers
# ---------------------------------------------------------------------------

def test_extract_quality_name():
    raw = {"quality": {"quality": {"name": "Bluray-1080p"}}}
    assert quality_svc.extract_quality_name(raw) == "Bluray-1080p"


def test_extract_quality_name_missing():
    assert quality_svc.extract_quality_name({}) is None


def test_extract_resolution_from_quality():
    raw = {"quality": {"quality": {"name": "WEBRip-2160p"}}}
    assert quality_svc.extract_resolution(raw) == "2160p"


def test_extract_resolution_from_path():
    raw = {"quality": {}, "path": "/movies/Film [1080p]/film.mkv"}
    assert quality_svc.extract_resolution(raw) == "1080p"


def test_extract_source_webdl():
    raw = {"quality": {"quality": {"name": "WEB-DL-1080p"}}}
    assert quality_svc.extract_source_from_quality(raw) == "WEB-DL"


def test_extract_source_remux():
    raw = {"quality": {"quality": {"name": "Remux-2160p"}}}
    assert quality_svc.extract_source_from_quality(raw) == "BDRemux"


def test_extract_source_from_title():
    result = quality_svc.extract_source_from_title_or_path("Film.BluRay.1080p.mkv", None)
    assert result == "BluRay"


def test_extract_source_from_path():
    result = quality_svc.extract_source_from_title_or_path(None, "/movies/Film.WEBRip.mkv")
    assert result == "WEBRip"


def test_extract_source_none_when_unknown():
    result = quality_svc.extract_source_from_title_or_path("Film 2023", "/movies/film.mkv")
    assert result is None


# ---------------------------------------------------------------------------
# Library sync — mocked HTTP
# ---------------------------------------------------------------------------

def _fake_movie(movie_id: int, title: str, has_file: bool = True) -> dict:
    result = {"id": movie_id, "title": title, "year": 2020, "tmdbId": movie_id + 10000}
    if has_file:
        result["movieFile"] = {
            "id": movie_id * 10, "path": f"/movies/{title}.mkv", "size": 1000000,
            "quality": {"quality": {"name": "WEB-DL-1080p"}},
        }
    return result


def _fake_series(series_id: int, title: str, has_episodes: bool = True) -> dict:
    return {
        "id": series_id, "title": title, "year": 2021, "tvdbId": series_id + 20000,
        "titleSlug": title.lower().replace(" ", "-"),
        "statistics": {
            "episodeCount": 10,
            "episodeFileCount": 10 if has_episodes else 0,
        },
        "path": f"/tv/{title}",
    }


def _fake_episode(ep_id: int, series_id: int, has_file: bool = True) -> dict:
    return {
        "id": ep_id, "seriesId": series_id,
        "seasonNumber": 1, "episodeNumber": ep_id,
        "title": f"Episode {ep_id}",
        "hasFile": has_file,
        "episodeFileId": ep_id * 10 if has_file else 0,
    }


def _fake_ep_file(ep_id: int) -> dict:
    return {
        "id": ep_id * 10,
        "path": f"/tv/Series/S01E{ep_id:02d}.mkv",
        "size": 500000,
        "quality": {"quality": {"name": "WEBRip-720p"}},
    }


@pytest.fixture
def mem_conn():
    """In-memory SQLite with schema initialized."""
    conn = connect(":memory:")
    init_db(conn)
    # Add a test instance
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES (?, ?, ?, ?, 1)",
        ("radarr", "Test Radarr", "http://radarr:7878", "key123"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sonarr_conn():
    conn = connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES (?, ?, ?, ?, 1)",
        ("sonarr", "Test Sonarr", "http://sonarr:8989", "key456"),
    )
    conn.commit()
    yield conn
    conn.close()


def test_sync_radarr_available_movie(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [_fake_movie(1, "Inception", has_file=True)]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(mem_conn, instance)

    assert imported == 1
    assert missing == 0
    rows = mem_conn.execute("SELECT * FROM library_items").fetchall()
    assert len(rows) == 1
    assert rows[0]["local_status"] == LocalStatus.AVAILABLE.value
    assert rows[0]["resolution"] == "1080p"
    assert rows[0]["source"] == "WEB-DL"


def test_sync_radarr_missing_movie(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [_fake_movie(2, "Missing Film", has_file=False)]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(mem_conn, instance)

    assert imported == 1
    assert missing == 1
    row = mem_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.MISSING.value


def test_sync_radarr_queued_movie(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [_fake_movie(3, "Downloading Film", has_file=False)]
    queue = [{"movieId": 3, "status": "downloading", "statusMessages": []}]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=queue),
    ):
        imported, missing = sync_instance(mem_conn, instance)

    row = mem_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.DOWNLOADING.value
    assert missing == 1  # still counts as not available


def test_sync_radarr_upsert_updates(mem_conn):
    """Running sync twice should update the item, not create a duplicate."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movie = [_fake_movie(4, "Cached Film", has_file=False)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movie),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    movie2 = [_fake_movie(4, "Cached Film", has_file=True)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movie2),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    rows = mem_conn.execute("SELECT * FROM library_items").fetchall()
    assert len(rows) == 1
    assert rows[0]["local_status"] == LocalStatus.AVAILABLE.value


def test_sync_sonarr_available_series(sonarr_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series = [_fake_series(10, "Peaky Blinders", has_episodes=True)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=series),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=False)

    assert imported == 1
    assert missing == 0
    row = sonarr_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.AVAILABLE.value
    assert row["item_type"] == "series"
    assert row["title_slug"] == "peaky-blinders"


def test_sync_sonarr_missing_series(sonarr_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series = [_fake_series(11, "Missing Show", has_episodes=False)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=series),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=False)

    assert missing == 1
    row = sonarr_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.MISSING.value


def test_sync_sonarr_with_episodes(sonarr_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series_data = [_fake_series(20, "Miniseries", has_episodes=False)]
    episodes = [_fake_episode(1, 20, has_file=True), _fake_episode(2, 20, has_file=False)]
    ep_files = [_fake_ep_file(1)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=series_data),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=True)

    # 1 series + 2 episodes
    assert imported == 3
    rows = sonarr_conn.execute("SELECT item_type, local_status FROM library_items ORDER BY id").fetchall()
    types = [r["item_type"] for r in rows]
    assert "series" in types
    assert "episode" in types


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

def test_dashboard_summary_empty(mem_conn):
    from emuwarez_uploadrr.services.library import get_dashboard_summary
    summary = get_dashboard_summary(mem_conn)
    assert summary["library_total"] == 0
    assert summary["available"] == 0
    assert summary["missing"] == 0
    assert summary["last_sync_at"] is None


def test_dashboard_summary_after_sync(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance, get_dashboard_summary
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [
        _fake_movie(10, "Available Film", has_file=True),
        _fake_movie(11, "Missing Film", has_file=False),
    ]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    summary = get_dashboard_summary(mem_conn)
    assert summary["library_total"] == 2
    assert summary["available"] == 1
    assert summary["missing"] == 1
    assert summary["radarr_items"] == 2
