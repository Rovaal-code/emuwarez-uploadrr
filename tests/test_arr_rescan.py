"""Tests for services.library.trigger_arr_rescan — asks Radarr/Sonarr to
rescan the movie/series a library item belongs to right after we rename/
hardlink its file, so Radarr/Sonarr's own DB picks up the new filename
without waiting for its next scheduled scan.

All HTTP calls are mocked — no real Radarr/Sonarr required.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.library import trigger_arr_rescan


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


def test_rescan_movie_calls_radarr(conn):
    instance_id = _insert_instance(conn, type_="radarr", url="http://radarr:7878", api_key="rkey")
    item_id = _insert_item(
        conn, item_type="movie", title="Una Película",
        instance_id=instance_id, external_id="42",
        local_status="Disponible", request_status="Sin petición", nomenclature_status="Correcta",
    )

    with patch("emuwarez_uploadrr.integrations.radarr.rescan_movie") as mock_rescan:
        result = trigger_arr_rescan(conn, item_id)

    assert result["ok"] is True
    mock_rescan.assert_called_once_with("http://radarr:7878", "rkey", 42)


def test_rescan_series_walks_up_from_episode(conn):
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

    with patch("emuwarez_uploadrr.integrations.sonarr.rescan_series") as mock_rescan:
        result = trigger_arr_rescan(conn, episode_id)

    assert result["ok"] is True
    # Walked episode -> season -> series, used the SERIES row's external_id
    # (the raw Sonarr seriesId), not the episode's own external_id.
    mock_rescan.assert_called_once_with("http://sonarr:8989", "skey", 99)


def test_rescan_missing_item_is_non_fatal(conn):
    result = trigger_arr_rescan(conn, 999999)
    assert result["ok"] is False


def test_rescan_item_without_instance_is_non_fatal(conn):
    item_id = _insert_item(conn, item_type="movie", title="Sin instancia")
    result = trigger_arr_rescan(conn, item_id)
    assert result["ok"] is False


def test_rescan_swallows_api_errors(conn):
    instance_id = _insert_instance(conn, type_="radarr")
    item_id = _insert_item(
        conn, item_type="movie", title="Falla al avisar",
        instance_id=instance_id, external_id="7",
    )
    with patch("emuwarez_uploadrr.integrations.radarr.rescan_movie", side_effect=RuntimeError("boom")):
        result = trigger_arr_rescan(conn, item_id)  # must not raise
    assert result["ok"] is False
    assert "boom" in result["message"]
