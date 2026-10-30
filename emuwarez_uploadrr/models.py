"""Shared data models for the CLI and the web UI.

Defines the stable domain contract. It used to also re-export AppConfig,
MediaInfoData, FilePlan and RunPlan from legacy.py "to keep the original
uploader engine compatible", but the engine defines those itself and nothing
ever imported them from here, so the alias only widened this module's reach
into legacy for no reader.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class InstanceType(str, Enum):
    RADARR = "radarr"
    SONARR = "sonarr"


class MediaKind(str, Enum):
    MOVIE = "movie"
    SERIES = "series"
    SEASON = "season"
    EPISODE = "episode"


class LocalStatus(str, Enum):
    AVAILABLE = "Disponible"
    MISSING = "Faltante"
    QUEUED = "En cola"
    DOWNLOADING = "Descargando"
    PENDING_IMPORT = "Pendiente de importar"
    IMPORT_ERROR = "Error de importación"
    SEARCH_ERROR = "Error de búsqueda"
    UPLOADING = "Subiendo"
    UPLOADED = "Subido"
    ERROR = "Error"
    UNKNOWN = "Desconocido"
    # Rollup-only status for series/season rows (never a movie/episode leaf
    # row) — some but not all children are locally available. Deliberately
    # NOT included in not_available(): partial content is available in
    # part, not "not yet available".
    PARTIAL = "Parcial"

    @classmethod
    def not_available(cls) -> tuple[str, ...]:
        """Statuses that mean the content is not yet locally available."""
        return (
            cls.MISSING.value, cls.QUEUED.value, cls.DOWNLOADING.value,
            cls.PENDING_IMPORT.value, cls.IMPORT_ERROR.value, cls.SEARCH_ERROR.value,
        )


class RequestStatus(str, Enum):
    NONE = "Sin petición"
    COMPATIBLE = "Compatible"
    PARTIAL = "Parcial"
    NOT_COMPATIBLE = "No compatible"
    FILLED = "Llena"
    UNKNOWN = "Desconocida"


class NomenclatureStatus(str, Enum):
    UNCHECKED = "No comprobada"  # default — MediaInfo not run yet
    CORRECT = "Correcta"
    NOT_ADAPTED = "No adaptada"
    PARTIAL = "Parcial"  # rollup only (season/series with some episodes adapted)
    NA = "N/A"


class DupeStatus(str, Enum):
    NOT_CHECKED = "No comprobado"
    NONE = "Sin duplicado detectado"
    POSSIBLE = "Posible duplicado"
    CONFIRMED = "Duplicado confirmado"
    ALLOWED_DIFFERENT_QUALITY = "Permitido por calidad diferente"
    ERROR = "Error comprobando dupe"


class TaskStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class InstanceConfig:
    id: Optional[int]
    type: str
    name: str
    url: str
    api_key: str
    enabled: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["enabled"] = 1 if self.enabled else 0
        return data


@dataclass(slots=True)
class LibraryItem:
    id: Optional[int]
    item_type: str
    title: str
    year: Optional[int] = None
    original_title: Optional[str] = None
    # El título en inglés, resuelto durante la SINCRONIZACIÓN para que el
    # asistente no tenga que salir a TMDb al generar la nomenclatura. No es lo
    # mismo que original_title: el de un anime japonés es japonés, y la opción
    # "Inglés" del desplegable de Título pide justo el inglés.
    english_title: Optional[str] = None
    instance_id: Optional[int] = None
    instance_type: Optional[str] = None
    instance_name: Optional[str] = None
    external_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    # Sonarr lo trae en su payload (tvMazeId) y no se guardaba.
    tvmaze_id: Optional[str] = None
    # Resolved from the Fribb/anime-lists table (see services/anime_lists.py)
    # against tvdb_id/tmdb_id at upsert time — Radarr/Sonarr never provide
    # this themselves, unlike the three IDs above.
    mal_id: Optional[str] = None
    title_slug: Optional[str] = None
    # Series/Season/Episode hierarchy — parent_id points at the containing
    # row's id (episode -> its season, season -> its series); NULL for
    # movies/series (top-level). season_number/episode_number are real
    # columns instead of only being baked into the display title string.
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    parent_id: Optional[int] = None
    path: Optional[str] = None
    quality: Optional[str] = None
    resolution: Optional[str] = None
    source: Optional[str] = None
    # El grupo de release que *Arr lee del nombre del archivo (`releaseGroup`).
    release_group: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_languages: Optional[str] = None
    audio_channels: Optional[str] = None
    dynamic_range: Optional[str] = None
    subtitle_languages: Optional[str] = None
    size_bytes: Optional[int] = None
    local_status: str = LocalStatus.UNKNOWN.value
    request_status: str = RequestStatus.NONE.value
    nomenclature_status: str = NomenclatureStatus.NA.value
    request_id: Optional[int] = None
    added_at: Optional[str] = None
    updated_at: Optional[str] = None
    raw_json: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RequestItem:
    id: Optional[int]
    emu_id: str
    title: str
    category: Optional[str] = None
    requested_source: Optional[str] = None
    requested_resolution: Optional[str] = None
    emu_status: Optional[str] = None
    points: Optional[int] = None
    comments: Optional[int] = None
    created_at: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    # Sonarr lo trae en su payload (tvMazeId) y no se guardaba.
    tvmaze_id: Optional[str] = None
    mal_id: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    author_visible: bool = False
    # Qué parte de la serie pide: toda (None), una temporada ('season') o un capítulo ('episode').
    req_scope: Optional[str] = None
    req_season: Optional[int] = None
    req_episode: Optional[int] = None
    raw_json: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["author_visible"] = 1 if self.author_visible else 0
        return data


@dataclass(slots=True)
class RequestMatch:
    id: Optional[int]
    library_item_id: int
    request_item_id: int
    status: str
    confidence: float = 0.0
    resolution_match: Optional[bool] = None
    source_match: Optional[bool] = None
    type_match: Optional[bool] = None
    reasons: list[str] = field(default_factory=list)
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = "\n".join(self.reasons)
        return data


@dataclass(slots=True)
class TaskRun:
    id: Optional[int]
    name: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: Optional[str] = None
    details: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UploadJob:
    id: Optional[int]
    library_item_id: Optional[int]
    title: str
    path: str
    status: str = "pending"
    dupe_status: str = DupeStatus.NOT_CHECKED.value
    dupe_message: Optional[str] = None
    uploadrr_description: Optional[str] = None
    trailer_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "InstanceType", "MediaKind", "LocalStatus", "RequestStatus",
    "NomenclatureStatus", "DupeStatus", "TaskStatus",
    "InstanceConfig", "LibraryItem", "RequestItem", "RequestMatch",
    "TaskRun", "UploadJob",
]
