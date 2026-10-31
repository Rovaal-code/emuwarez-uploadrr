"""Tests for Radarr/Sonarr integration clients (Phase 4).

All HTTP calls are mocked — no real *Arr server needed.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from emuwarez_uploadrr.integrations.arr_base import (
    ArrAuthError, ArrClientError, ArrConnectionError, ArrApiError,
    normalize_base_url, join_api_path, safe_api_key,
)
from emuwarez_uploadrr.integrations import radarr, sonarr
from emuwarez_uploadrr.models import LocalStatus


# ---------------------------------------------------------------------------
# arr_base utilities
# ---------------------------------------------------------------------------

def test_normalize_base_url_strips_slash():
    assert normalize_base_url("http://radarr:7878/") == "http://radarr:7878"


def test_normalize_base_url_adds_http():
    assert normalize_base_url("radarr:7878").startswith("http://")


def test_normalize_base_url_empty_raises():
    with pytest.raises(ArrClientError):
        normalize_base_url("")


def test_join_api_path():
    url = join_api_path("http://radarr:7878", "movie")
    assert url == "http://radarr:7878/api/v3/movie"


def test_join_api_path_with_params():
    url = join_api_path("http://radarr:7878", "queue", {"pageSize": 100})
    assert "pageSize=100" in url


def test_safe_api_key_masks():
    masked = safe_api_key("abcd1234efgh5678")
    assert "abcd" in masked
    assert "5678" in masked
    assert "1234efgh" not in masked


def test_safe_api_key_short():
    assert safe_api_key("abc") == "****"


def test_error_hierarchy():
    assert issubclass(ArrConnectionError, ArrClientError)
    assert issubclass(ArrAuthError, ArrClientError)
    assert issubclass(ArrApiError, ArrClientError)


# ---------------------------------------------------------------------------
# Radarr — radarr_test_connection (instance dict style)
# ---------------------------------------------------------------------------

_RADARR_INSTANCE = {"url": "http://radarr:7878", "api_key": "testapikey1234", "name": "Radarr Test"}
_SONARR_INSTANCE = {"url": "http://sonarr:8989", "api_key": "testsonarr5678", "name": "Sonarr Test"}


def _mock_radarr(return_value):
    return patch("emuwarez_uploadrr.integrations.radarr.arr_request", return_value=return_value)


def _mock_sonarr(return_value):
    return patch("emuwarez_uploadrr.integrations.sonarr.arr_request", return_value=return_value)


def test_radarr_test_connection_ok():
    with _mock_radarr({"version": "5.0.0", "appName": "Radarr"}):
        result = radarr.radarr_test_connection(_RADARR_INSTANCE)
    assert result["ok"] is True
    assert result["version"] == "5.0.0"
    assert "api_key" not in str(result)


def test_radarr_test_connection_auth_error():
    with patch("emuwarez_uploadrr.integrations.radarr.arr_request", side_effect=ArrAuthError("bad key")):
        result = radarr.radarr_test_connection(_RADARR_INSTANCE)
    assert result["ok"] is False
    assert "key" in result["error"].lower() or "api" in result["error"].lower()


def test_radarr_test_connection_network_error():
    with patch("emuwarez_uploadrr.integrations.radarr.arr_request", side_effect=ArrConnectionError("timeout")):
        result = radarr.radarr_test_connection(_RADARR_INSTANCE)
    assert result["ok"] is False
    assert result["error"]


def test_radarr_get_movies():
    movies = [{"id": 1, "title": "Test Movie", "tmdbId": 12345, "year": 2023}]
    with _mock_radarr(movies):
        result = radarr.radarr_get_movies(_RADARR_INSTANCE)
    assert len(result) == 1
    assert result[0]["title"] == "Test Movie"


def test_radarr_get_queue_raises_on_error():
    """Una instancia caída no es una cola vacía: sus diagnósticos no se limpian ni dan «ok»."""
    with patch("emuwarez_uploadrr.integrations.radarr.arr_request", side_effect=ArrConnectionError("down")):
        with pytest.raises(ArrConnectionError):
            radarr.radarr_get_queue(_RADARR_INSTANCE)


def test_radarr_get_quality_profiles():
    profiles = [{"id": 1, "name": "HD-1080p"}, {"id": 2, "name": "4K"}]
    with _mock_radarr(profiles):
        result = radarr.radarr_get_quality_profiles(_RADARR_INSTANCE)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Sonarr — sonarr_test_connection
# ---------------------------------------------------------------------------

def test_sonarr_test_connection_ok():
    with _mock_sonarr({"version": "4.0.0", "appName": "Sonarr"}):
        result = sonarr.sonarr_test_connection(_SONARR_INSTANCE)
    assert result["ok"] is True
    assert result["version"] == "4.0.0"
    assert "api_key" not in str(result)


def test_sonarr_test_connection_auth_error():
    with patch("emuwarez_uploadrr.integrations.sonarr.arr_request", side_effect=ArrAuthError("bad key")):
        result = sonarr.sonarr_test_connection(_SONARR_INSTANCE)
    assert result["ok"] is False


def test_sonarr_get_series():
    series = [{"id": 1, "title": "Breaking Bad", "tvdbId": 81189, "year": 2008}]
    with _mock_sonarr(series):
        result = sonarr.sonarr_get_series(_SONARR_INSTANCE)
    assert len(result) == 1
    assert result[0]["title"] == "Breaking Bad"


def test_sonarr_get_quality_profiles():
    profiles = [{"id": 1, "name": "Any"}]
    with _mock_sonarr(profiles):
        result = sonarr.sonarr_get_quality_profiles(_SONARR_INSTANCE)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Queue map building
# ---------------------------------------------------------------------------

def test_radarr_build_queue_map_downloading():
    records = [{"movieId": 42, "status": "downloading", "statusMessages": []}]
    q = radarr.build_queue_map(records)
    assert q[42] == LocalStatus.DOWNLOADING.value


def test_radarr_build_queue_map_failed():
    records = [{"movieId": 7, "status": "failed", "statusMessages": []}]
    q = radarr.build_queue_map(records)
    assert q[7] == LocalStatus.IMPORT_ERROR.value


def test_radarr_build_queue_map_queued():
    records = [{"movieId": 5, "status": "queued", "statusMessages": []}]
    q = radarr.build_queue_map(records)
    assert q[5] == LocalStatus.QUEUED.value


def test_sonarr_build_episode_queue_map():
    records = [{"episodeIds": [101, 102], "status": "downloading"}]
    q = sonarr.build_episode_queue_map(records)
    assert q[101] == LocalStatus.DOWNLOADING.value
    assert q[102] == LocalStatus.DOWNLOADING.value


# ---------------------------------------------------------------------------
# movie_to_library_item
# ---------------------------------------------------------------------------

def test_movie_available():
    movie = {
        "id": 1, "title": "Dune", "year": 2021, "tmdbId": 438631,
        "movieFile": {"id": 10, "path": "/movies/Dune/Dune.mkv", "size": 10000,
                      "quality": {"quality": {"name": "Bluray-1080p"}}},
    }
    item = radarr.movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert item.local_status == LocalStatus.AVAILABLE.value
    assert item.resolution == "1080p"
    assert item.source == "BluRay"
    assert item.tmdb_id == "438631"


def test_movie_missing():
    movie = {"id": 2, "title": "Unknown", "year": 2022, "tmdbId": None}
    item = radarr.movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert item.local_status == LocalStatus.MISSING.value


def test_movie_parses_media_info():
    movie = {
        "id": 4, "title": "Ad Astra", "year": 2019, "tmdbId": 419704,
        "movieFile": {
            "id": 40, "path": "/movies/Ad Astra/Ad Astra.mkv", "size": 20000,
            "quality": {"quality": {"name": "WEBDL-1080p"}},
            "mediaInfo": {
                "videoCodec": "x265", "audioCodec": "EAC3",
                "audioLanguages": "eng / spa", "subtitles": "eng / spa",
            },
        },
    }
    item = radarr.movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert item.video_codec == "x265"
    assert item.audio_codec == "EAC3"
    assert item.audio_languages == "eng / spa"
    assert item.subtitle_languages == "eng / spa"


def test_movie_without_media_info_leaves_fields_none():
    movie = {
        "id": 5, "title": "No MediaInfo", "year": 2020, "tmdbId": 1,
        "movieFile": {"id": 50, "path": "/movies/x.mkv", "size": 100,
                      "quality": {"quality": {"name": "Bluray-1080p"}}},
    }
    item = radarr.movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert item.video_codec is None
    assert item.audio_codec is None


def test_movie_queued_via_queue_map():
    movie = {"id": 3, "title": "Queued Film", "year": 2023}
    q_map = {3: LocalStatus.DOWNLOADING.value}
    item = radarr.movie_to_library_item(movie, instance_id=1, instance_name="Radarr", queue_map=q_map)
    assert item.local_status == LocalStatus.DOWNLOADING.value


def test_movie_api_key_not_in_raw_json():
    movie = {"id": 4, "title": "Safe Movie", "tmdbId": 999}
    item = radarr.movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert "testapikey" not in (item.raw_json or "")


# ---------------------------------------------------------------------------
# episode_to_library_item
# ---------------------------------------------------------------------------

def test_episode_available():
    series = {"id": 1, "title": "The Wire", "year": 2002, "tvdbId": 79126}
    episode = {"id": 100, "seasonNumber": 1, "episodeNumber": 1, "title": "The Target",
                "hasFile": True, "episodeFileId": 50}
    ep_file = {"id": 50, "path": "/shows/The Wire/S01E01.mkv", "size": 5000,
               "quality": {"quality": {"name": "WEBRip-1080p"}}}
    item = sonarr.episode_to_library_item(episode, ep_file, series, instance_id=2, instance_name="Sonarr")
    assert item.local_status == LocalStatus.AVAILABLE.value
    assert item.resolution == "1080p"
    assert item.source == "WEBRip"


def test_episode_missing():
    series = {"id": 1, "title": "Dark", "year": 2017, "tvdbId": 318493}
    episode = {"id": 200, "seasonNumber": 2, "episodeNumber": 3, "title": "Ghosts"}
    item = sonarr.episode_to_library_item(episode, None, series, instance_id=2, instance_name="Sonarr")
    assert item.local_status == LocalStatus.MISSING.value


def test_episode_parses_media_info():
    series = {"id": 1, "title": "The Wire", "year": 2002, "tvdbId": 79126}
    episode = {"id": 101, "seasonNumber": 1, "episodeNumber": 2, "title": "The Detail",
                "hasFile": True, "episodeFileId": 51}
    ep_file = {
        "id": 51, "path": "/shows/The Wire/S01E02.mkv", "size": 5000,
        "quality": {"quality": {"name": "WEBRip-1080p"}},
        "mediaInfo": {"videoCodec": "h264", "audioCodec": "AAC", "audioLanguages": "eng"},
    }
    item = sonarr.episode_to_library_item(episode, ep_file, series, instance_id=2, instance_name="Sonarr")
    assert item.video_codec == "h264"
    assert item.audio_codec == "AAC"
    assert item.audio_languages == "eng"


# ---------------------------------------------------------------------------
# extract_media_info
# ---------------------------------------------------------------------------

def test_extract_media_info_full():
    from emuwarez_uploadrr.integrations.base import extract_media_info
    file_entry = {"mediaInfo": {
        "videoCodec": "HEVC", "audioCodec": "DTS",
        "audioLanguages": "eng / spa", "subtitles": "eng",
        "audioChannels": 5.1, "videoDynamicRangeType": "DV HDR10",
    }}
    result = extract_media_info(file_entry)
    assert result == {
        "video_codec": "HEVC", "audio_codec": "DTS",
        "audio_languages": "eng / spa", "subtitle_languages": "eng",
        "audio_channels": "5.1", "dynamic_range": "DV HDR10",
        # Este payload no trae `resolution`; cuando la trae se lee, y de ahí
        # depende que una serie SD tenga resolución (ver test_resolucion_sd).
        "resolution": None,
    }


def test_extract_media_info_missing_key():
    from emuwarez_uploadrr.integrations.base import extract_media_info
    result = extract_media_info({"path": "/x.mkv"})
    assert result == {
        "video_codec": None, "audio_codec": None,
        "audio_languages": None, "subtitle_languages": None,
        "audio_channels": None, "dynamic_range": None, "resolution": None,
    }


def test_extract_media_info_none_input():
    from emuwarez_uploadrr.integrations.base import extract_media_info
    assert extract_media_info(None)["video_codec"] is None


def test_sonarr_series_keeps_its_tvmaze_id():
    """Sonarr manda tvMazeId en su payload y no se estaba guardando: 50 de las
    52 series de una biblioteca real lo traen con valor.

    tvRageId también llega, pero no se guarda: solo lo trae la mitad y sus
    fichas devuelven 404, así que el enlace no llevaría a ninguna parte."""
    from emuwarez_uploadrr.integrations.sonarr import series_to_library_item
    item = series_to_library_item(
        {"id": 3, "title": "Serie", "tvdbId": 389597, "tvMazeId": 64632,
         "tmdbId": 127532, "imdbId": "tt21209876", "path": "/data/serie"},
        instance_id=1, instance_name="Mi Sonarr",
    )
    assert item.tvmaze_id == "64632"
    assert item.tvdb_id == "389597"


def test_a_series_without_tvmaze_id_leaves_it_empty():
    """Sonarr manda 0 cuando no lo tiene, y un 0 enlazaría a una ficha que no
    existe."""
    from emuwarez_uploadrr.integrations.sonarr import series_to_library_item
    item = series_to_library_item(
        {"id": 3, "title": "Serie", "tvdbId": 1, "tvMazeId": 0, "path": "/data/serie"},
        instance_id=1, instance_name="Mi Sonarr",
    )
    assert item.tvmaze_id is None
