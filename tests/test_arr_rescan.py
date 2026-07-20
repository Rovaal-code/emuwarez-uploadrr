"""Tests for services.library.refresh_arr_and_resync / resync_single_item —
asks Radarr/Sonarr to refresh+rescan the movie/series a library item belongs
to right after we rename/hardlink its file, waits for that command to
finish, then resyncs just this item so our own library_items row reflects
whatever Radarr/Sonarr now reports.

All HTTP calls are mocked — no real Radarr/Sonarr required.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.library import refresh_arr_and_resync, resync_single_item


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    yield c
    c.close()


def _insert_instance(conn, *, type_, url="http://arr:7878", api_key="key123") -> int:
    cur = conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES (?, ?, ?, ?, 1)",
        (type_, f"Test {type_}", url, api_key),
    )
    conn.commit()
    return cur.lastrowid


def _insert_item(conn, **kwargs) -> int:
    kwargs.setdefault("local_status", "Disponible")
    kwargs.setdefault("request_status", "Sin petición")
    kwargs.setdefault("nomenclature_status", "N/A")
    item_type = kwargs.pop("item_type")
    title = kwargs.pop("title")
    cols = ", ".join(kwargs.keys())
    placeholders = ", ".join("?" for _ in kwargs)
    cur = conn.execute(
        f"INSERT INTO library_items (item_type, title, updated_at, {cols}) "
        f"VALUES (?, ?, CURRENT_TIMESTAMP, {placeholders})",
        (item_type, title, *kwargs.values()),
    )
    conn.commit()
    return cur.lastrowid


def _movie_payload(movie_id=42, title="Una Película"):
    return {
        "id": movie_id, "title": title, "year": 2024, "tmdbId": 555, "imdbId": "tt555",
        "movieFile": {"id": 1, "path": f"/data/{title}.mkv", "quality": {"quality": {"name": "WEBDL-1080p"}}},
    }


@patch("emuwarez_uploadrr.integrations.radarr.get_command_status")
@patch("emuwarez_uploadrr.integrations.radarr.refresh_movie")
@patch("emuwarez_uploadrr.integrations.radarr.get_movie")
def test_refresh_movie_waits_then_resyncs(mock_get_movie, mock_refresh, mock_status, conn):
    instance_id = _insert_instance(conn, type_="radarr", url="http://radarr:7878", api_key="rkey")
    item_id = _insert_item(
        conn, item_type="movie", title="Una Película",
        instance_id=instance_id, external_id="42",
        local_status="Disponible", request_status="Sin petición", nomenclature_status="Correcta",
    )

    mock_refresh.return_value = {"id": 123}
    mock_status.return_value = {"status": "completed"}
    mock_get_movie.return_value = _movie_payload()

    logs: list[tuple[str, str]] = []
    result = refresh_arr_and_resync(
        conn, item_id, on_log=lambda level, msg: logs.append((level, msg)), poll_interval=0,
    )

    assert result["ok"] is True
    mock_refresh.assert_called_once_with("http://radarr:7878", "rkey", 42)
    mock_status.assert_called_once_with("http://radarr:7878", "rkey", 123)
    mock_get_movie.assert_called_once_with("http://radarr:7878", "rkey", 42)
    assert any("terminado" in m for _, m in logs)
    assert not any(level == "warning" for level, _ in logs)


@patch("emuwarez_uploadrr.integrations.radarr.get_command_status")
@patch("emuwarez_uploadrr.integrations.radarr.refresh_movie")
@patch("emuwarez_uploadrr.integrations.radarr.get_movie")
def test_refresh_movie_logs_warning_when_radarr_never_confirms(mock_get_movie, mock_refresh, mock_status, conn):
    instance_id = _insert_instance(conn, type_="radarr")
    item_id = _insert_item(
        conn, item_type="movie", title="Otra", instance_id=instance_id, external_id="7",
    )
    mock_refresh.return_value = {"id": 9}
    mock_status.return_value = {"status": "queued"}  # never reaches completed/failed
    mock_get_movie.return_value = _movie_payload(movie_id=7, title="Otra")

    logs: list[tuple[str, str]] = []
    result = refresh_arr_and_resync(
        conn, item_id, on_log=lambda level, msg: logs.append((level, msg)),
        poll_timeout=0.01, poll_interval=0.005,
    )

    assert result["ok"] is True  # never blocks/fails the upload
    assert any(level == "warning" for level, _ in logs)
    # Still resyncs even though Radarr never confirmed completion.
    mock_get_movie.assert_called_once()


def test_refresh_missing_item_is_non_fatal(conn):
    result = refresh_arr_and_resync(conn, 999999)
    assert result["ok"] is False


def test_refresh_item_without_instance_is_non_fatal(conn):
    item_id = _insert_item(conn, item_type="movie", title="Sin instancia")
    result = refresh_arr_and_resync(conn, item_id)
    assert result["ok"] is False


@patch("emuwarez_uploadrr.integrations.radarr.refresh_movie", side_effect=RuntimeError("boom"))
def test_refresh_swallows_api_errors(mock_refresh, conn):
    instance_id = _insert_instance(conn, type_="radarr")
    item_id = _insert_item(
        conn, item_type="movie", title="Falla al avisar",
        instance_id=instance_id, external_id="7",
    )
    result = refresh_arr_and_resync(conn, item_id)  # must not raise
    assert result["ok"] is False
    assert "boom" in result["message"]


@patch("emuwarez_uploadrr.integrations.sonarr.get_series_by_id")
def test_resync_series_walks_up_from_episode(mock_get_series, conn):
    instance_id = _insert_instance(conn, type_="sonarr", url="http://sonarr:8989", api_key="skey")
    series_id = _insert_item(
        conn, item_type="series", title="Una Serie",
        instance_id=instance_id, external_id="99",
    )
    season_id = _insert_item(
        conn, item_type="season", title="Una Serie - Temporada 1",
        instance_id=instance_id, external_id="season:99:1", parent_id=series_id, season_number=1,
    )
    episode_id = _insert_item(
        conn, item_type="episode", title="Una Serie S01E01",
        instance_id=instance_id, external_id="episode:1", parent_id=season_id,
        season_number=1, episode_number=1,
    )

    mock_get_series.return_value = {
        "id": 99, "title": "Una Serie", "tmdbId": None, "seasons": [],
    }
    with patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=[]), \
         patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=[]):
        result = resync_single_item(conn, episode_id)

    assert result["ok"] is True
    # Walked episode -> season -> series, used the SERIES row's external_id
    # (the raw Sonarr seriesId), not the episode's own external_id.
    mock_get_series.assert_called_once_with("http://sonarr:8989", "skey", 99)


def test_resync_missing_item_is_non_fatal(conn):
    result = resync_single_item(conn, 999999)
    assert result["ok"] is False
