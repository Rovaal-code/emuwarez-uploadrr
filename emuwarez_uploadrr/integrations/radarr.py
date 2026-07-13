"""Radarr v3 API connector."""
from __future__ import annotations

import json
from typing import Any, Optional

from .arr_base import (
    ArrClientError, ArrConnectionError, ArrAuthError,
    arr_request, join_api_path, safe_api_key,
)
from .base import build_url, extract_media_info, extract_poster_url, request_json
from ..models import LibraryItem, LocalStatus, MediaKind, NomenclatureStatus
from ..legacy import DEFAULT_TAG


# ---------------------------------------------------------------------------
# Legacy-style helpers (used by existing services/library.py)
# ---------------------------------------------------------------------------

def test_connection(url: str, api_key: str) -> dict[str, Any]:
    return request_json("GET", build_url(url, "/api/v3/system/status"), api_key=api_key)


def get_root_folders(url: str, api_key: str) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/rootfolder"), api_key=api_key)
    return data if isinstance(data, list) else []


def get_movies(url: str, api_key: str) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/movie"), api_key=api_key)
    return data if isinstance(data, list) else []


def get_queue(url: str, api_key: str) -> list[dict[str, Any]]:
    """Return current download queue entries from Radarr."""
    try:
        data = request_json(
            "GET",
            build_url(url, "/api/v3/queue", {"pageSize": 500, "includeMovie": "false"}),
            api_key=api_key,
        )
        if isinstance(data, dict):
            return data.get("records", [])
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# New instance-dict style API (for web layer and Phase 4+)
# ---------------------------------------------------------------------------

def _get(instance: dict, path: str, params: Optional[dict] = None) -> Any:
    return arr_request("GET", join_api_path(instance["url"], path, params), instance["api_key"])


def radarr_test_connection(instance: dict) -> dict:
    """Return {ok, version, instance_name} or {ok=False, error}."""
    try:
        data = _get(instance, "system/status")
        return {
            "ok": True,
            "version": data.get("version"),
            "instance_name": instance.get("name"),
        }
    except ArrAuthError:
        return {"ok": False, "error": "API key incorrecta o permisos insuficientes"}
    except ArrConnectionError as exc:
        return {"ok": False, "error": f"No se pudo conectar: {exc}"}
    except ArrClientError as exc:
        return {"ok": False, "error": str(exc)}


def radarr_get_system_status(instance: dict) -> dict:
    return _get(instance, "system/status")


def radarr_get_movies(instance: dict) -> list[dict]:
    data = _get(instance, "movie")
    return data if isinstance(data, list) else []


def radarr_get_queue(instance: dict) -> list[dict]:
    try:
        data = _get(instance, "queue", {"pageSize": 500, "includeMovie": "false"})
        if isinstance(data, dict):
            return data.get("records", [])
        return data if isinstance(data, list) else []
    except ArrClientError:
        return []


def radarr_get_history(instance: dict, page_size: int = 50) -> list[dict]:
    try:
        data = _get(instance, "history", {"pageSize": page_size})
        if isinstance(data, dict):
            return data.get("records", [])
        return data if isinstance(data, list) else []
    except ArrClientError:
        return []


def radarr_get_root_folders(instance: dict) -> list[dict]:
    data = _get(instance, "rootfolder")
    return data if isinstance(data, list) else []


def radarr_get_quality_profiles(instance: dict) -> list[dict]:
    data = _get(instance, "qualityprofile")
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Queue-status mapping
# ---------------------------------------------------------------------------

_QUEUE_STATUS_MAP: dict[str, str] = {
    "queued": LocalStatus.QUEUED.value,
    "delay": LocalStatus.QUEUED.value,
    "paused": LocalStatus.QUEUED.value,
    "downloading": LocalStatus.DOWNLOADING.value,
    "importPending": LocalStatus.PENDING_IMPORT.value,
    "completed": LocalStatus.PENDING_IMPORT.value,
    "failed": LocalStatus.IMPORT_ERROR.value,
    "downloadClientUnavailable": LocalStatus.ERROR.value,
    "warning": LocalStatus.IMPORT_ERROR.value,
    "fallback": LocalStatus.QUEUED.value,
}


def build_queue_map(queue_records: list[dict]) -> dict[int, str]:
    """Build a movieId → local_status map from Radarr queue records."""
    result: dict[int, str] = {}
    for rec in queue_records:
        movie_id = rec.get("movieId")
        if not movie_id:
            continue
        q_status = (rec.get("status") or "").lower()
        local = _QUEUE_STATUS_MAP.get(q_status, LocalStatus.QUEUED.value)
        # If there are status messages hinting at errors, downgrade
        for msg in rec.get("statusMessages") or []:
            if any("error" in str(m).lower() or "import" in str(m).lower()
                   for m in ([msg] if isinstance(msg, str) else msg.get("messages", []))):
                local = LocalStatus.IMPORT_ERROR.value
                break
        result[int(movie_id)] = local
    return result


# ---------------------------------------------------------------------------
# Movie → LibraryItem mapping
# ---------------------------------------------------------------------------

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
    if "dvd" in text:
        return "DVD"
    return None


def _nomenclature(path: str | None, available: bool) -> str:
    # Nomenclature can only be judged by reading MediaInfo (per-track audio),
    # which the sync doesn't do — so a file starts 'No comprobada' until the
    # user runs the check. No file → N/A.
    return NomenclatureStatus.NA.value if not available else NomenclatureStatus.UNCHECKED.value


def movie_to_library_item(
    movie: dict[str, Any],
    *,
    instance_id: int,
    instance_name: str,
    queue_map: Optional[dict[int, str]] = None,
) -> LibraryItem:
    movie_file = movie.get("movieFile") or {}
    has_file = bool(movie_file and isinstance(movie_file, dict) and movie_file.get("id"))
    quality_name = None
    if isinstance(movie_file, dict):
        quality_name = (((movie_file.get("quality") or {}).get("quality") or {}).get("name"))
    file_path = movie_file.get("path") if isinstance(movie_file, dict) else None
    path = file_path or movie.get("path")
    media_info = extract_media_info(movie_file)
    title = movie.get("title") or movie.get("originalTitle") or "Sin título"
    tmdb_id = str(movie.get("tmdbId")) if movie.get("tmdbId") else None
    imdb_id = movie.get("imdbId")
    year = movie.get("year")
    movie_id = movie.get("id")

    # Determine local status
    if has_file:
        local_status = LocalStatus.AVAILABLE.value
    elif queue_map and movie_id and int(movie_id) in queue_map:
        local_status = queue_map[int(movie_id)]
    else:
        local_status = LocalStatus.MISSING.value

    return LibraryItem(
        id=None,
        item_type=MediaKind.MOVIE.value,
        title=title,
        year=int(year) if str(year).isdigit() else None,
        original_title=movie.get("originalTitle"),
        instance_id=instance_id,
        instance_type="radarr",
        instance_name=instance_name,
        external_id=str(movie_id),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        path=path,
        quality=quality_name,
        resolution=_resolution_from_quality(quality_name),
        source=_source_from_quality(quality_name),
        video_codec=media_info.get("video_codec"),
        audio_codec=media_info.get("audio_codec"),
        audio_languages=media_info.get("audio_languages"),
        audio_channels=media_info.get("audio_channels"),
        dynamic_range=media_info.get("dynamic_range"),
        subtitle_languages=media_info.get("subtitle_languages"),
        size_bytes=movie_file.get("size") if isinstance(movie_file, dict) else None,
        local_status=local_status,
        nomenclature_status=_nomenclature(path, has_file),
        raw_json=json.dumps(movie, ensure_ascii=False),
        poster_url=extract_poster_url(movie.get("images")),
    )
