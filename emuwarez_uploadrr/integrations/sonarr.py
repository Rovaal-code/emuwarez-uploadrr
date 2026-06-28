"""Sonarr v3 API connector."""
from __future__ import annotations

import json
from typing import Any

from .base import build_url, request_json
from ..models import LibraryItem, LocalStatus, MediaKind, NomenclatureStatus
from ..legacy import DEFAULT_TAG


def test_connection(url: str, api_key: str) -> dict[str, Any]:
    return request_json("GET", build_url(url, "/api/v3/system/status"), api_key=api_key)


def get_root_folders(url: str, api_key: str) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/rootfolder"), api_key=api_key)
    return data if isinstance(data, list) else []


def get_series(url: str, api_key: str) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/series"), api_key=api_key)
    return data if isinstance(data, list) else []


def get_episodes(url: str, api_key: str, series_id: int) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/episode", {"seriesId": series_id}), api_key=api_key)
    return data if isinstance(data, list) else []


def get_episode_files(url: str, api_key: str, series_id: int) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/episodefile", {"seriesId": series_id}), api_key=api_key)
    return data if isinstance(data, list) else []


def _resolution_from_quality(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()
    if "2160" in text or "4k" in text:
        return "2160p"
    if "1080" in text:
        return "1080p"
    if "720" in text:
        return "720p"
    if "576" in text:
        return "576p"
    if "480" in text:
        return "480p"
    return None


def _source_from_quality(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()
    if "remux" in text:
        return "BDRemux"
    if "webdl" in text or "web-dl" in text:
        return "WEB-DL"
    if "webrip" in text or "web-rip" in text:
        return "WEBRip"
    if "bluray" in text or "blu-ray" in text:
        return "BluRay"
    if "hdtv" in text:
        return "HDTV"
    return None


def _nomenclature(path: str | None, available: bool) -> str:
    if not available:
        return NomenclatureStatus.NA.value
    if path and DEFAULT_TAG.lower() in path.lower():
        return NomenclatureStatus.CORRECT.value
    return NomenclatureStatus.NOT_ADAPTED.value


def series_to_library_item(series: dict[str, Any], *, instance_id: int, instance_name: str) -> LibraryItem:
    title = series.get("title") or series.get("sortTitle") or "Sin título"
    stats = series.get("statistics") or {}
    episode_count = int(stats.get("episodeCount") or 0)
    file_count = int(stats.get("episodeFileCount") or 0)
    available = episode_count > 0 and file_count >= episode_count
    return LibraryItem(
        id=None,
        item_type=MediaKind.SERIES.value,
        title=title,
        year=series.get("year"),
        original_title=series.get("originalTitle"),
        instance_id=instance_id,
        instance_type="sonarr",
        instance_name=instance_name,
        external_id=str(series.get("id")),
        tvdb_id=str(series.get("tvdbId")) if series.get("tvdbId") else None,
        imdb_id=series.get("imdbId"),
        path=series.get("path"),
        quality=None,
        resolution=None,
        source=None,
        local_status=LocalStatus.AVAILABLE.value if available else LocalStatus.MISSING.value,
        nomenclature_status=NomenclatureStatus.NA.value,
        raw_json=json.dumps(series, ensure_ascii=False),
    )


def episode_to_library_item(
    episode: dict[str, Any],
    episode_file: dict[str, Any] | None,
    series: dict[str, Any],
    *,
    instance_id: int,
    instance_name: str,
) -> LibraryItem:
    quality_name = None
    path = None
    size = None
    if episode_file:
        quality_name = (((episode_file.get("quality") or {}).get("quality") or {}).get("name"))
        path = episode_file.get("path")
        size = episode_file.get("size")
    season = episode.get("seasonNumber")
    number = episode.get("episodeNumber")
    series_title = series.get("title") or "Serie"
    title = f"{series_title} S{int(season):02d}E{int(number):02d}" if season is not None and number is not None else series_title
    if episode.get("title"):
        title = f"{title} - {episode.get('title')}"
    available = bool(episode_file)
    return LibraryItem(
        id=None,
        item_type=MediaKind.EPISODE.value,
        title=title,
        year=series.get("year"),
        original_title=series.get("originalTitle"),
        instance_id=instance_id,
        instance_type="sonarr",
        instance_name=instance_name,
        external_id=f"episode:{episode.get('id')}",
        tvdb_id=str(series.get("tvdbId")) if series.get("tvdbId") else None,
        imdb_id=series.get("imdbId"),
        path=path,
        quality=quality_name,
        resolution=_resolution_from_quality(quality_name),
        source=_source_from_quality(quality_name),
        size_bytes=size,
        local_status=LocalStatus.AVAILABLE.value if available else LocalStatus.MISSING.value,
        nomenclature_status=_nomenclature(path, available),
        raw_json=json.dumps({"series": series, "episode": episode, "episodeFile": episode_file}, ensure_ascii=False),
    )
