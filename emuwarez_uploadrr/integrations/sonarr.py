"""Sonarr v3 API connector."""
from __future__ import annotations

import json
from typing import Any, Optional

from .arr_base import (
    ArrClientError, ArrConnectionError, ArrAuthError,
    arr_request, join_api_path, registros_de, todas_las_paginas,
)
from .base import (
    IntegrationError, build_url, es_lista_de_fichas, extract_backdrop_url, extract_media_info, extract_poster_url,
    extract_release_group, request_json,
)
from ..models import LibraryItem, LocalStatus, MediaKind, NomenclatureStatus


# ---------------------------------------------------------------------------
# Legacy-style helpers (used by existing services/library.py)
# ---------------------------------------------------------------------------

def test_connection(url: str, api_key: str) -> dict[str, Any]:
    return request_json("GET", build_url(url, "/api/v3/system/status"), api_key=api_key)


def get_root_folders(url: str, api_key: str) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/rootfolder"), api_key=api_key)
    return data if isinstance(data, list) else []


def get_series(url: str, api_key: str) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/series"), api_key=api_key)
    if not es_lista_de_fichas(data):
        raise IntegrationError("Sonarr no ha devuelto la lista de series")
    return data


def refresh_series(url: str, api_key: str, series_id: int) -> dict[str, Any]:
    """Ask Sonarr to refresh this series' metadata AND rescan its folder in
    one command (same as its own "Refresh & Scan" button) — used right after
    we rename/hardlink an episode file, so Sonarr actually adopts the new
    filename as that episode's file instead of just noticing the old one is
    gone. A disk-scan-only RescanSeries is not enough: Sonarr's own
    reconciliation between "file went missing" and "here's a new file" runs
    as part of the fuller refresh, not the bare rescan."""
    return request_json(
        "POST", build_url(url, "/api/v3/command"), api_key=api_key,
        data={"name": "RefreshSeries", "seriesId": series_id},
    )


def get_series_by_id(url: str, api_key: str, series_id: int) -> dict[str, Any]:
    data = request_json("GET", build_url(url, f"/api/v3/series/{series_id}"), api_key=api_key)
    if not es_lista_de_fichas([data]):
        raise IntegrationError(f"Sonarr no ha devuelto la serie {series_id}")
    return data


def get_command_status(url: str, api_key: str, command_id: int) -> dict[str, Any]:
    """Poll a previously-issued command (e.g. RefreshSeries) — Sonarr
    commands run async; `status` becomes "completed"/"failed" once done."""
    return request_json("GET", build_url(url, f"/api/v3/command/{command_id}"), api_key=api_key)


def get_episodes(url: str, api_key: str, series_id: int) -> list[dict[str, Any]]:
    data = request_json("GET", build_url(url, "/api/v3/episode", {"seriesId": series_id}), api_key=api_key)
    if not es_lista_de_fichas(data):
        raise IntegrationError(f"Sonarr no ha devuelto los capítulos de la serie {series_id}")
    return data


def get_episode_files(url: str, api_key: str, series_id: int) -> list[dict[str, Any]]:
    """Vacía es válida (una serie sin ningún archivo); lo que no es una lista de ficheros con id, no."""
    data = request_json("GET", build_url(url, "/api/v3/episodefile", {"seriesId": series_id}), api_key=api_key)
    if not es_lista_de_fichas(data):
        raise IntegrationError(f"Sonarr no ha devuelto los archivos de la serie {series_id}")
    return data


def get_queue(url: str, api_key: str) -> list[dict[str, Any]]:
    """La cola de descargas de Sonarr entera. Si falla o llega cortada lanza: una cola vacía por fallo dejaría
    como Faltante, y avisaría, todo lo que se está descargando."""
    return todas_las_paginas(
        lambda pagina, tamano: request_json(
            "GET",
            build_url(url, "/api/v3/queue", {"page": pagina, "pageSize": tamano, "includeSeries": "false"}),
            api_key=api_key,
        ),
        "La cola de Sonarr",
    )


# ---------------------------------------------------------------------------
# New instance-dict style API (for web layer and Phase 4+)
# ---------------------------------------------------------------------------

def _get(instance: dict, path: str, params: Optional[dict] = None) -> Any:
    return arr_request("GET", join_api_path(instance["url"], path, params), instance["api_key"])


def sonarr_test_connection(instance: dict) -> dict:
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


def sonarr_get_system_status(instance: dict) -> dict:
    return _get(instance, "system/status")


def sonarr_get_series(instance: dict) -> list[dict]:
    data = _get(instance, "series")
    return data if isinstance(data, list) else []


def sonarr_get_episodes(instance: dict, series_id: Optional[int] = None) -> list[dict]:
    params = {"seriesId": series_id} if series_id is not None else None
    data = _get(instance, "episode", params)
    return data if isinstance(data, list) else []


def sonarr_get_queue(instance: dict) -> list[dict]:
    return todas_las_paginas(
        lambda pagina, tamano: _get(instance, "queue", {"page": pagina, "pageSize": tamano, "includeSeries": "false"}),
        "La cola de Sonarr",
    )


def sonarr_get_history(instance: dict, page_size: int = 50) -> list[dict]:
    return registros_de(_get(instance, "history", {"pageSize": page_size}), "El historial de Sonarr")


def sonarr_get_root_folders(instance: dict) -> list[dict]:
    data = _get(instance, "rootfolder")
    return data if isinstance(data, list) else []


def sonarr_get_quality_profiles(instance: dict) -> list[dict]:
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


def build_episode_queue_map(queue_records: list[dict]) -> dict[int, str]:
    """Build episodeId → local_status map from Sonarr queue records."""
    result: dict[int, str] = {}
    for rec in queue_records:
        for ep_id in rec.get("episodeIds") or []:
            q_status = (rec.get("status") or "").lower()
            local = _QUEUE_STATUS_MAP.get(q_status, LocalStatus.QUEUED.value)
            result[int(ep_id)] = local
    return result


def build_series_queue_map(queue_records: list[dict]) -> dict[int, str]:
    """Build seriesId → most-urgent local_status map."""
    result: dict[int, str] = {}
    for rec in queue_records:
        series_id = rec.get("seriesId")
        if not series_id:
            continue
        q_status = (rec.get("status") or "").lower()
        local = _QUEUE_STATUS_MAP.get(q_status, LocalStatus.QUEUED.value)
        # Keep the most urgent status if already set
        if int(series_id) not in result:
            result[int(series_id)] = local
    return result


# ---------------------------------------------------------------------------
# Quality helpers
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
        # "SD" y no "DVD": el vocabulario de sources de eMuwarez no tiene DVD
        # (ver source_assistant.EMU_SOURCES). Devolverlo dejaba en la
        # biblioteca un source que el tracker no acepta.
        return "SD"
    return None


def _nomenclature(path: str | None, available: bool) -> str:
    # Judged only by MediaInfo (per-track audio), not at sync time → starts
    # 'No comprobada' until the user runs the check. No file → N/A.
    return NomenclatureStatus.NA.value if not available else NomenclatureStatus.UNCHECKED.value


# ---------------------------------------------------------------------------
# *Arr data → LibraryItem
# ---------------------------------------------------------------------------

def series_to_library_item(
    series: dict[str, Any],
    *,
    instance_id: int,
    instance_name: str,
    series_queue_map: Optional[dict[int, str]] = None,
) -> LibraryItem:
    title = series.get("title") or series.get("sortTitle") or "Sin título"
    stats = series.get("statistics") or {}
    episode_count = int(stats.get("episodeCount") or 0)
    file_count = int(stats.get("episodeFileCount") or 0)
    has_all_files = episode_count > 0 and file_count >= episode_count
    series_id = series.get("id")

    if has_all_files:
        local_status = LocalStatus.AVAILABLE.value
    elif file_count > 0:
        # Some but not all episodes available — a real 3rd state, not
        # squeezed into a binary Disponible/Faltante rollup.
        local_status = LocalStatus.PARTIAL.value
    elif series_queue_map and series_id and int(series_id) in series_queue_map:
        local_status = series_queue_map[int(series_id)]
    else:
        local_status = LocalStatus.MISSING.value

    return LibraryItem(
        id=None,
        item_type=MediaKind.SERIES.value,
        title=title,
        year=series.get("year"),
        original_title=series.get("originalTitle"),
        # Lo deja puesto la sincronización antes de traducir el título (ver
        # services/library.py::_sync_one_series): Sonarr no manda ningún campo
        # de título original, pero el `title` que manda ya es el bueno para la
        # opción "Inglés" del desplegable de Título.
        english_title=series.get("englishTitle"),
        instance_id=instance_id,
        instance_type="sonarr",
        instance_name=instance_name,
        external_id=str(series_id),
        tmdb_id=str(series.get("tmdbId")) if series.get("tmdbId") else None,
        tvdb_id=str(series.get("tvdbId")) if series.get("tvdbId") else None,
        tvmaze_id=str(series.get("tvMazeId")) if series.get("tvMazeId") else None,
        title_slug=series.get("titleSlug"),
        imdb_id=series.get("imdbId"),
        path=series.get("path"),
        quality=None,
        resolution=None,
        source=None,
        local_status=local_status,
        nomenclature_status=NomenclatureStatus.NA.value,
        raw_json=json.dumps(series, ensure_ascii=False),
        poster_url=extract_poster_url(series.get("images")),
        backdrop_url=extract_backdrop_url(series.get("images")),
    )


def season_to_library_item(
    series: dict[str, Any],
    season_entry: dict[str, Any],
    *,
    instance_id: int,
    instance_name: str,
    parent_id: int,
    episode_count_override: Optional[int] = None,
    file_count_override: Optional[int] = None,
) -> LibraryItem:
    """Build a Season-level rollup row (item_type='season', the
    MediaKind.SEASON value that existed in the enum but was never
    instantiated until now). Mirrors series_to_library_item()'s own
    Disponible/Parcial/Faltante 3-state rollup, but reads the per-season
    statistics Sonarr already includes on each series' `seasons[]` entry
    instead of the series-wide statistics block.

    `episode_count_override`/`file_count_override` let sync_instance() feed
    a bottom-up count computed from the episodes it already fetched, for
    the defensive fallback when `season_entry["statistics"]` is missing or
    empty in practice."""
    season_number = season_entry.get("seasonNumber")
    stats = season_entry.get("statistics") or {}
    episode_count = int(
        episode_count_override if episode_count_override is not None
        else (stats.get("episodeCount") or stats.get("totalEpisodeCount") or 0)
    )
    file_count = int(
        file_count_override if file_count_override is not None
        else (stats.get("episodeFileCount") or 0)
    )
    has_all_files = episode_count > 0 and file_count >= episode_count

    if has_all_files:
        local_status = LocalStatus.AVAILABLE.value
    elif file_count > 0:
        local_status = LocalStatus.PARTIAL.value
    else:
        local_status = LocalStatus.MISSING.value

    series_title = series.get("title") or series.get("sortTitle") or "Serie"
    season_label = "Especiales" if season_number == 0 else f"Temporada {season_number}"
    series_id = series.get("id")

    return LibraryItem(
        id=None,
        item_type=MediaKind.SEASON.value,
        title=f"{series_title} - {season_label}",
        year=series.get("year"),
        original_title=series.get("originalTitle"),
        # Lo deja puesto la sincronización antes de traducir el título (ver
        # services/library.py::_sync_one_series): Sonarr no manda ningún campo
        # de título original, pero el `title` que manda ya es el bueno para la
        # opción "Inglés" del desplegable de Título.
        english_title=series.get("englishTitle"),
        instance_id=instance_id,
        instance_type="sonarr",
        instance_name=instance_name,
        external_id=f"season:{series_id}:{season_number}",
        tmdb_id=str(series.get("tmdbId")) if series.get("tmdbId") else None,
        tvdb_id=str(series.get("tvdbId")) if series.get("tvdbId") else None,
        tvmaze_id=str(series.get("tvMazeId")) if series.get("tvMazeId") else None,
        title_slug=series.get("titleSlug"),
        imdb_id=series.get("imdbId"),
        season_number=season_number,
        parent_id=parent_id,
        path=None,
        quality=None,
        resolution=None,
        source=None,
        local_status=local_status,
        nomenclature_status=NomenclatureStatus.NA.value,
        raw_json=json.dumps({"series_id": series_id, "season": season_entry}, ensure_ascii=False),
        poster_url=extract_poster_url(series.get("images")),
        backdrop_url=extract_backdrop_url(series.get("images")),
    )


def episode_to_library_item(
    episode: dict[str, Any],
    episode_file: dict[str, Any] | None,
    series: dict[str, Any],
    *,
    instance_id: int,
    instance_name: str,
    ep_queue_map: Optional[dict[int, str]] = None,
    parent_id: Optional[int] = None,
) -> LibraryItem:
    quality_name = None
    path = None
    size = None
    if episode_file:
        quality_name = (((episode_file.get("quality") or {}).get("quality") or {}).get("name"))
        path = episode_file.get("path")
        size = episode_file.get("size")
    media_info = extract_media_info(episode_file)
    season = episode.get("seasonNumber")
    number = episode.get("episodeNumber")
    series_title = series.get("title") or "Serie"
    title = (
        f"{series_title} S{int(season):02d}E{int(number):02d}"
        if season is not None and number is not None
        else series_title
    )
    if episode.get("title"):
        title = f"{title} - {episode.get('title')}"
    episode_id = episode.get("id")
    has_file = bool(episode_file)

    if has_file:
        local_status = LocalStatus.AVAILABLE.value
    elif ep_queue_map and episode_id and int(episode_id) in ep_queue_map:
        local_status = ep_queue_map[int(episode_id)]
    else:
        local_status = LocalStatus.MISSING.value

    return LibraryItem(
        id=None,
        item_type=MediaKind.EPISODE.value,
        title=title,
        year=series.get("year"),
        original_title=series.get("originalTitle"),
        # Lo deja puesto la sincronización antes de traducir el título (ver
        # services/library.py::_sync_one_series): Sonarr no manda ningún campo
        # de título original, pero el `title` que manda ya es el bueno para la
        # opción "Inglés" del desplegable de Título.
        english_title=series.get("englishTitle"),
        instance_id=instance_id,
        instance_type="sonarr",
        instance_name=instance_name,
        external_id=f"episode:{episode_id}",
        tmdb_id=str(series.get("tmdbId")) if series.get("tmdbId") else None,
        tvdb_id=str(series.get("tvdbId")) if series.get("tvdbId") else None,
        tvmaze_id=str(series.get("tvMazeId")) if series.get("tvMazeId") else None,
        title_slug=series.get("titleSlug"),
        imdb_id=series.get("imdbId"),
        season_number=season,
        episode_number=number,
        parent_id=parent_id,
        path=path,
        quality=quality_name,
        # El nombre de calidad primero; si no lleva número ("SDTV", "DVD",
        # "Raw-HD"), la resolución real que ya manda *Arr en su mediaInfo.
        resolution=_resolution_from_quality(quality_name) or media_info.get("resolution"),
        source=_source_from_quality(quality_name),
        release_group=extract_release_group(episode_file),
        video_codec=media_info.get("video_codec"),
        audio_codec=media_info.get("audio_codec"),
        audio_languages=media_info.get("audio_languages"),
        audio_channels=media_info.get("audio_channels"),
        dynamic_range=media_info.get("dynamic_range"),
        subtitle_languages=media_info.get("subtitle_languages"),
        size_bytes=size,
        local_status=local_status,
        nomenclature_status=_nomenclature(path, has_file),
        raw_json=json.dumps(
            {"series": series, "episode": episode, "episodeFile": episode_file},
            ensure_ascii=False,
        ),
        poster_url=extract_poster_url(series.get("images")),
        backdrop_url=extract_backdrop_url(series.get("images")),
    )
