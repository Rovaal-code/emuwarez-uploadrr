"""Radarr v3 API connector."""
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


def get_movies(url: str, api_key: str) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/movie"), api_key=api_key)
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


def movie_to_library_item(movie: dict[str, Any], *, instance_id: int, instance_name: str) -> LibraryItem:
    movie_file = movie.get("movieFile") or {}
    available = bool(movie_file)
    quality_name = None
    if isinstance(movie_file, dict):
        quality_name = (((movie_file.get("quality") or {}).get("quality") or {}).get("name"))
    file_path = movie_file.get("path") if isinstance(movie_file, dict) else None
    path = file_path or movie.get("path")
    title = movie.get("title") or movie.get("originalTitle") or "Sin título"
    tmdb_id = str(movie.get("tmdbId")) if movie.get("tmdbId") else None
    imdb_id = movie.get("imdbId")
    year = movie.get("year")
    return LibraryItem(
        id=None,
        item_type=MediaKind.MOVIE.value,
        title=title,
        year=int(year) if str(year).isdigit() else None,
        original_title=movie.get("originalTitle"),
        instance_id=instance_id,
        instance_type="radarr",
        instance_name=instance_name,
        external_id=str(movie.get("id")),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        path=path,
        quality=quality_name,
        resolution=_resolution_from_quality(quality_name),
        source=_source_from_quality(quality_name),
        size_bytes=movie_file.get("size") if isinstance(movie_file, dict) else None,
        local_status=LocalStatus.AVAILABLE.value if available else LocalStatus.MISSING.value,
        nomenclature_status=_nomenclature(path, available),
        raw_json=json.dumps(movie, ensure_ascii=False),
    )
