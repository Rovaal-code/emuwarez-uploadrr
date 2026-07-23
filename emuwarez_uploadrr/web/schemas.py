"""Pydantic request/response schemas for the web API."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Health / Runtime
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    database: str
    initialized: bool


class RuntimeInfoResponse(BaseModel):
    app_name: str
    version: str
    config_dir: str
    database_path: str
    database_status: str
    cli_available: bool
    uploadrr_runtime_present: bool


class DiagnosticCheck(BaseModel):
    name: str
    status: str
    message: str
    details: dict = {}


class RuntimeDiagnosticsResponse(BaseModel):
    ok: bool
    checks: list[DiagnosticCheck]
    warnings: list[str]
    errors: list[str]


# ---------------------------------------------------------------------------
# Setup status
# ---------------------------------------------------------------------------

class SetupStatusResponse(BaseModel):
    initialized: bool
    admin_configured: bool
    tmdb_configured: bool
    emu_configured: bool
    radarr_instances: int
    sonarr_instances: int
    jellyfin_configured: bool
    next_step: Optional[str] = None


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class ContractSummaryResponse(BaseModel):
    message: str
    md_path: str
    json_path: str
    sections: list[str]
    docs_url: str


# ---------------------------------------------------------------------------
# Auth requests / responses
# ---------------------------------------------------------------------------

class CreateAdminRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre de usuario no puede estar vacío")
        if len(v) < 3:
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        from .security import validate_password_strength
        err = validate_password_strength(v)
        if err:
            raise ValueError(err)
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    message: str = "Sesión iniciada correctamente"


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: str
    last_login_at: Optional[str] = None


class LogoutResponse(BaseModel):
    message: str = "Sesión cerrada correctamente"


class ChangeCredentialsRequest(BaseModel):
    current_password: str
    new_username: Optional[str] = None
    new_password: Optional[str] = None

    @field_validator("new_username")
    @classmethod
    def username_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if len(v) < 3:
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres")
        return v

    @field_validator("new_password")
    @classmethod
    def password_valid(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        from .security import validate_password_strength
        err = validate_password_strength(v)
        if err:
            raise ValueError(err)
        return v


class ChangeCredentialsResponse(BaseModel):
    username: str
    message: str = "Credenciales actualizadas correctamente"


# ---------------------------------------------------------------------------
# System stats (sidebar gauges)
# ---------------------------------------------------------------------------

class GpuStatsResponse(BaseModel):
    name: str
    percent: float
    vram_used_gb: float
    vram_total_gb: float
    vram_percent: float


class SystemStatsResponse(BaseModel):
    cpu_percent: float
    cpu_name: str
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disk_path: str
    disk_used_gb: float
    disk_total_gb: float
    disk_percent: float
    net_down_bps: float
    net_up_bps: float
    gpu: Optional[GpuStatsResponse] = None


# ---------------------------------------------------------------------------
# Setup POST requests
# ---------------------------------------------------------------------------

class SetupTmdbRequest(BaseModel):
    api_key: str
    language: Optional[str] = "es-ES"
    region: Optional[str] = "ES"
    # Replace Sonarr/TVDB series titles (often English) with TMDb localized ones.
    localize_series_titles: Optional[bool] = True

    @field_validator("api_key")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La API key de TMDb no puede estar vacía")
        return v.strip()


class SetupQbitRequest(BaseModel):
    url: str
    port: Optional[str] = "8080"
    username: Optional[str] = ""
    password: Optional[str] = ""

    @field_validator("url")
    @classmethod
    def valid_url(cls, v: str) -> str:
        v = (v or "").strip()
        # Empty = skip qBittorrent setup; otherwise it must be a real http(s) URL.
        if v and not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("La URL de qBittorrent debe empezar por http:// o https:// e incluir un host válido")
        return v


class SetupImghostsRequest(BaseModel):
    enabled: list[str] = []
    keys: dict = {}  # {host_id: api_key}


class SetupEmuRequest(BaseModel):
    api_key: str
    endpoint_url: Optional[str] = None

    @field_validator("api_key")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La API key de eMuwarez no puede estar vacía")
        return v.strip()


class SetupInstanceRequest(BaseModel):
    type: str
    name: str
    url: str
    api_key: str
    is_4k: bool = False
    is_anime: bool = False

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in ("radarr", "sonarr"):
            raise ValueError("El tipo debe ser 'radarr' o 'sonarr'")
        return v

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La URL no puede estar vacía")
        if not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("La URL debe empezar por http:// o https:// e incluir un host válido")
        return v

    @field_validator("api_key")
    @classmethod
    def api_key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La API key no puede estar vacía")
        return v.strip()


# ---------------------------------------------------------------------------
# Settings / secrets
# ---------------------------------------------------------------------------

class SecretStatusField(BaseModel):
    configured: bool
    masked_value: Optional[str] = None


class SettingsStatusResponse(BaseModel):
    tmdb: SecretStatusField
    emu_api_key: SecretStatusField
    emu_endpoint: SecretStatusField
    uploadrr_path: SecretStatusField


# ---------------------------------------------------------------------------
# Instance response
# ---------------------------------------------------------------------------

class InstanceResponse(BaseModel):
    id: int
    type: str
    name: str
    url: str
    enabled: bool
    is_4k: bool = False
    is_anime: bool = False
    last_test_status: Optional[str] = None
    last_test_at: Optional[str] = None
    created_at: str


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------

class InstanceSafeResponse(BaseModel):
    id: int
    type: str
    name: str
    url: str
    api_key_masked: str
    enabled: bool
    is_4k: bool = False
    is_anime: bool = False
    last_test_status: Optional[str] = None
    last_test_at: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class InstanceTestResponse(BaseModel):
    ok: bool
    instance_id: Optional[int] = None
    instance_name: Optional[str] = None
    version: Optional[str] = None
    username: Optional[str] = None
    error: Optional[str] = None


_VALID_INSTANCE_TYPES = ("radarr", "sonarr")


class AddInstanceRequest(BaseModel):
    type: str
    name: str
    url: str
    api_key: str
    is_4k: bool = False
    is_anime: bool = False

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in _VALID_INSTANCE_TYPES:
            raise ValueError(f"El tipo debe ser uno de: {', '.join(_VALID_INSTANCE_TYPES)}")
        return v

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        if len(v) > 15:
            raise ValueError("El nombre no puede superar los 15 caracteres")
        return v

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La URL no puede estar vacía")
        if not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("La URL debe empezar por http:// o https:// e incluir un host válido")
        return v

    @field_validator("api_key")
    @classmethod
    def api_key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La API key no puede estar vacía")
        return v.strip()


class UpdateInstanceRequest(BaseModel):
    """Phase 11B — partial update; only provided fields are changed.
    Mirrors services/instances.py::update_instance's signature."""
    name: Optional[str] = None
    url: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    is_4k: Optional[bool] = None
    is_anime: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v

    @field_validator("url")
    @classmethod
    def url_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("La URL no puede estar vacía")
        if not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("La URL debe empezar por http:// o https:// e incluir un host válido")
        return v

    @field_validator("api_key")
    @classmethod
    def api_key_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("La API key no puede estar vacía")
        return v


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

class SyncRequest(BaseModel):
    include_episodes: bool = True


class SyncResponse(BaseModel):
    ok: bool = True
    imported: int = 0
    missing: int = 0
    instances: int = 0
    errors: list[str] = []
    message: str = ""


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardSummaryResponse(BaseModel):
    library_total: int = 0
    available: int = 0
    missing: int = 0
    uploading: int = 0
    completed: int = 0
    unique_content: int = 0
    unique_movies: int = 0
    unique_seasons: int = 0
    unique_episodes: int = 0
    radarr_items: int = 0
    sonarr_items: int = 0
    last_sync_at: Optional[str] = None
    # Phase 5B — EMU request stats (optional, default 0 if not yet synced)
    requests_total: int = 0
    requests_compatible: int = 0
    requests_partial: int = 0
    requests_filled: int = 0
    requests_mine: int = 0
    # eMuwarez doesn't expose whether a claim belongs to you specifically —
    # this is every request currently Reclamado on the tracker, not just yours.
    requests_reclaimed: int = 0
    requests_last_sync_at: Optional[str] = None
    # Phase 6D — Upload job counts
    uploads_ready: int = 0
    uploads_running: int = 0
    uploads_completed: int = 0
    uploads_failed: int = 0
    last_upload_at: Optional[str] = None
    # Phase 8A — ARR health and filesystem diagnostics
    arr_health_ok: int = 0
    arr_health_warning: int = 0
    arr_health_error: int = 0
    files_verified: int = 0
    files_missing_on_disk: int = 0
    items_ready_for_nomenclature: int = 0
    items_ready_for_upload: int = 0
    items_waiting_download: int = 0
    items_need_arr_review: int = 0
    # Phase 8B — request readiness counts
    requests_ready_to_upload: int = 0
    requests_need_nomenclature: int = 0
    requests_waiting_download: int = 0
    requests_blocked: int = 0
    # Phase 8C — operational queue counts
    operational_queue_open: int = 0
    operational_queue_ready: int = 0
    operational_queue_waiting: int = 0
    operational_queue_blocked: int = 0


class DashboardActivityItem(BaseModel):
    id: int
    name: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: Optional[str] = None


class DashboardActivityResponse(BaseModel):
    items: list[DashboardActivityItem] = []


class DashboardRecommendationItem(BaseModel):
    id: int
    rec_group: int  # 1 = compatible request, 2 = unique/upload, 3 = missing/request
    item_type: str
    title: Optional[str] = None
    content_name: str
    year: Optional[int] = None
    poster_url: Optional[str] = None
    local_status: Optional[str] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    size_bytes: Optional[int] = None
    resolution: Optional[str] = None
    source: Optional[str] = None
    instance_type: Optional[str] = None
    missing_count: Optional[int] = None
    rec_request_id: Optional[int] = None


class DashboardRecommendationsResponse(BaseModel):
    items: list[DashboardRecommendationItem] = []


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

class LibraryItemResponse(BaseModel):
    id: int
    item_type: str
    title: str
    year: Optional[int] = None
    original_title: Optional[str] = None
    instance_type: Optional[str] = None
    instance_name: Optional[str] = None
    instance_id: Optional[int] = None
    external_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    # Resolved from the Fribb/anime-lists table (see services/anime_lists.py)
    # — Radarr/Sonarr never provide this themselves, unlike the 3 IDs above.
    mal_id: Optional[str] = None
    title_slug: Optional[str] = None
    # Series/Season/Episode hierarchy — parent_id points at the containing
    # row's id (episode -> season, season -> series); None for movies/series.
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    parent_id: Optional[int] = None
    path: Optional[str] = None
    # The real current local file once nomenclature has been applied — `path`
    # stays in Radarr/Sonarr's own raw convention and can go stale (e.g. a
    # later sync overwrites it) without ever pointing at a renamed file
    # again; prepared_path is the only field guaranteed current.
    prepared_path: Optional[str] = None
    quality: Optional[str] = None
    resolution: Optional[str] = None
    source: Optional[str] = None
    provider: Optional[str] = None
    provider_label: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_languages: Optional[str] = None
    subtitle_languages: Optional[str] = None
    size_bytes: Optional[int] = None
    local_status: str
    request_status: str
    nomenclature_status: str
    updated_at: Optional[str] = None
    # Phase 8A fields (optional — may not be populated yet)
    file_exists: Optional[bool] = None
    file_verified_at: Optional[str] = None
    diagnostic_status: Optional[str] = None
    diagnostic_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    arr_queue_status: Optional[str] = None
    arr_history_status: Optional[str] = None
    # Phase 11E — poster extracted from Radarr/Sonarr's raw images[] at sync time
    poster_url: Optional[str] = None
    # eMuwarez catalog comparison — 1 = already on eMuwarez, 0 = not, None = not synced.
    # emu_aportes: list of {dim, detail} describing what your copy would add.
    emu_in_catalog: Optional[int] = None
    emu_aportes: Optional[list] = None


class LibraryListResponse(BaseModel):
    items: list[LibraryItemResponse] = []
    total: int = 0
    limit: int = 50
    offset: int = 0


class MissingItemResponse(BaseModel):
    id: int
    item_type: str
    title: str
    year: Optional[int] = None
    instance_type: Optional[str] = None
    instance_name: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    local_status: str
    request_status: str
    updated_at: Optional[str] = None
    # Phase 8A fields (optional)
    arr_queue_status: Optional[str] = None
    arr_queue_progress: Optional[float] = None
    arr_queue_timeleft: Optional[str] = None
    arr_queue_error: Optional[str] = None
    arr_history_error: Optional[str] = None
    file_exists: Optional[bool] = None
    diagnostic_status: Optional[str] = None
    recommended_action: Optional[str] = None
    recommendation_reasons: Optional[list] = None


class MissingListResponse(BaseModel):
    items: list[MissingItemResponse] = []
    total: int = 0
    limit: int = 50
    offset: int = 0


# ---------------------------------------------------------------------------
# Requests (Phase 5B)
# ---------------------------------------------------------------------------

class RequestMatchResponse(BaseModel):
    id: int
    library_item_id: Optional[int] = None
    library_title: Optional[str] = None
    local_status: Optional[str] = None
    local_resolution: Optional[str] = None
    local_source: Optional[str] = None
    local_video_codec: Optional[str] = None
    local_audio_languages: Optional[str] = None
    local_size: Optional[int] = None
    local_tmdb_id: Optional[str] = None
    local_imdb_id: Optional[str] = None
    local_tvdb_id: Optional[str] = None
    local_mal_id: Optional[str] = None
    local_path: Optional[str] = None
    content_name: Optional[str] = None
    nomenclature_status: Optional[str] = None
    status: str
    confidence: float
    resolution_match: Optional[bool] = None
    source_match: Optional[bool] = None
    id_match: bool = False
    reasons: list[str] = []


class RequestItemResponse(BaseModel):
    id: int
    emu_id: str
    title: str
    category: Optional[str] = None
    requested_source: Optional[str] = None
    requested_resolution: Optional[str] = None
    emu_status: Optional[str] = None
    points: Optional[int] = None
    comments: Optional[int] = None
    votes: Optional[int] = None
    author: Optional[str] = None
    is_mine: bool = False
    req_scope: Optional[str] = None
    req_season: Optional[int] = None
    req_episode: Optional[int] = None
    created_at: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    mal_id: Optional[str] = None
    url: Optional[str] = None
    # author omitted — author_visible=0 by default
    compatibility_status: Optional[str] = None
    compatibility_confidence: Optional[float] = None
    library_item_id: Optional[int] = None
    library_title: Optional[str] = None
    local_status: Optional[str] = None
    poster_url: Optional[str] = None
    reviewed_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Phase 8B — readiness fields (optional, not populated if readiness not yet evaluated)
    readiness_status: Optional[str] = None
    readiness_action: Optional[str] = None
    readiness_best_library_item_id: Optional[int] = None


class RequestDetailResponse(RequestItemResponse):
    match: Optional[RequestMatchResponse] = None


class RequestListResponse(BaseModel):
    items: list[RequestItemResponse] = []
    total: int = 0
    limit: int = 50
    offset: int = 0


# ---------------------------------------------------------------------------
# Phase 8B — Request Readiness
# ---------------------------------------------------------------------------

class RequestReadinessResponse(BaseModel):
    id: int
    request_item_id: int
    title: Optional[str] = None
    emu_id: Optional[str] = None
    best_library_item_id: Optional[int] = None
    status: str
    recommended_action: Optional[str] = None
    compatibility_score: Optional[float] = None
    upload_readiness_score: Optional[float] = None
    blockers: list[str] = []
    reasons: list[str] = []
    candidate_summary: list[dict] = []
    last_evaluated_at: Optional[str] = None
    updated_at: Optional[str] = None


class RequestReadinessListResponse(BaseModel):
    items: list[RequestReadinessResponse] = []
    total: int = 0
    limit: int = 100
    offset: int = 0


class RequestCandidateResponse(BaseModel):
    id: int
    request_item_id: int
    library_item_id: int
    candidate_rank: int
    match_status: str
    match_score: Optional[float] = None
    compatibility_status: Optional[str] = None
    compatibility_score: Optional[float] = None
    readiness_status: Optional[str] = None
    readiness_score: Optional[float] = None
    blockers: list[str] = []
    reasons: list[str] = []
    lib_title: Optional[str] = None
    local_status: Optional[str] = None
    resolution: Optional[str] = None
    source: Optional[str] = None


class RequestReadinessRefreshBody(BaseModel):
    limit: Optional[int] = None
    force: bool = False


class RequestReadinessEvaluateResponse(BaseModel):
    ok: bool
    request_item_id: int
    title: Optional[str] = None
    status: str
    recommended_action: Optional[str] = None
    compatibility_score: Optional[float] = None
    upload_readiness_score: Optional[float] = None
    best_library_item_id: Optional[int] = None
    blockers: list[str] = []
    reasons: list[str] = []
    candidates_count: int = 0


class RequestSyncStatusResponse(BaseModel):
    last_sync_at: Optional[str] = None
    next_sync_at: Optional[str] = None
    can_sync: bool = True
    wait_seconds: int = 0
    min_interval_seconds: int = 3600


class RequestSyncResponse(BaseModel):
    ok: bool = True
    status: str = "ok"
    imported: int = 0
    matched: int = 0
    wait_seconds: int = 0
    message: str = ""


class RequestSyncBody(BaseModel):
    force: bool = False


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class ApiPlaceholderResponse(BaseModel):
    implemented: bool = False
    phase: str = "future"
    message: str = "Endpoint reservado para fase posterior"
    endpoint: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int


class OkResponse(BaseModel):
    ok: bool = True
    message: str


# ---------------------------------------------------------------------------
# Nomenclature (Phase 6A)
# ---------------------------------------------------------------------------

class NomenclatureProposalResponse(BaseModel):
    id: Optional[int] = None
    library_item_id: int
    status: str
    current_name: Optional[str] = None
    current_path: Optional[str] = None
    proposed_title: Optional[str] = None
    proposed_filename: Optional[str] = None
    proposed_folder: Optional[str] = None
    proposed_path: Optional[str] = None
    media_type: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    resolution: Optional[str] = None
    source: Optional[str] = None
    provider: Optional[str] = None
    video_codec: Optional[str] = None
    audio_summary: Optional[str] = None
    subtitle_summary: Optional[str] = None
    release_tag: Optional[str] = None
    warnings: list[str] = []
    errors: list[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class NomenclatureExistsResponse(BaseModel):
    exists: bool
    message: Optional[str] = None
    proposal: Optional[NomenclatureProposalResponse] = None


class NomenclaturePreviewBody(BaseModel):
    force_refresh: bool = False


class AdaptNomenclatureBody(BaseModel):
    dry_run: bool = True
    apply: bool = False
    confirmation: Optional[str] = None
    proposal_id: Optional[int] = None


class NomenclatureApplyResult(BaseModel):
    dry_run: bool
    apply: bool
    status: str
    source_path: Optional[str] = None
    destination_path: Optional[str] = None
    operation_id: Optional[int] = None
    proposal: Optional["NomenclatureProposalResponse"] = None
    # Pre-existing gap: apply_nomenclature_proposal() has always returned
    # these two keys, but this schema never declared them, so they were
    # silently stripped from the response.
    warnings: list[str] = []
    errors: list[str] = []


# Phase 6 (Series/Season/Episode hierarchy) — season pack: one release for
# a whole Temporada, not N independent per-episode jobs.

class SeasonPackEpisodePlan(BaseModel):
    episode_id: int
    title: Optional[str] = None
    episode_number: Optional[int] = None
    source_path: Optional[str] = None
    destination_path: Optional[str] = None
    proposed_filename: Optional[str] = None


class SeasonPackPlanResponse(BaseModel):
    status: str
    errors: list[str] = []
    warnings: list[str] = []
    season_pack_title: Optional[str] = None
    pack_folder: Optional[str] = None
    episodes: list[SeasonPackEpisodePlan] = []
    # Resolved provider (filename-detected across episodes, or the single
    # TMDb fallback when none revealed one and source is WEB-DL).
    provider: Optional[str] = None


# ---------------------------------------------------------------------------
# Upload preflight (Phase 6A)
# ---------------------------------------------------------------------------

class UploadPreflightBody(BaseModel):
    request_id: Optional[int] = None


class CommandPreviewResponse(BaseModel):
    uploadrr_path: Optional[str] = None
    tracker: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    tmdb_id: Optional[str] = None
    resolution: Optional[str] = None
    source_path: Optional[str] = None
    command_preview: Optional[str] = None
    note: Optional[str] = None
    using_prepared_path: Optional[bool] = None
    # Phase 10E: Uploadrr-EMU contract fields.
    runtime_type: Optional[str] = None
    contract_valid: Optional[bool] = None
    contract_errors: Optional[list[str]] = None
    contract_warnings: Optional[list[str]] = None
    can_execute: Optional[bool] = None
    requires_confirmation: Optional[str] = None
    safe_to_execute: Optional[bool] = None


class UploadJobResponse(BaseModel):
    id: Optional[int] = None
    library_item_id: Optional[int] = None
    request_item_id: Optional[int] = None
    status: str
    stage: Optional[str] = None
    title: Optional[str] = None
    source_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UploadPreflightResponse(BaseModel):
    status: str
    job: Optional[UploadJobResponse] = None
    preflight: dict = {}
    command_preview: Optional[CommandPreviewResponse] = None
    warnings: list[str] = []
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Upload execution (Phase 6C)
# ---------------------------------------------------------------------------

class UploadStartRequest(BaseModel):
    dry_run: bool = True
    start: bool = False
    confirmation: Optional[str] = None


class UploadJobDetail(BaseModel):
    id: Optional[int] = None
    library_item_id: Optional[int] = None
    request_item_id: Optional[int] = None
    status: str
    stage: Optional[str] = None
    title: Optional[str] = None
    source_path: Optional[str] = None
    prepared_path: Optional[str] = None
    using_prepared_path: Optional[bool] = None
    error_message: Optional[str] = None
    exit_code: Optional[int] = None
    process_id: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Phase 6D fields
    result_url: Optional[str] = None
    result_torrent_id: Optional[str] = None
    result_tracker: Optional[str] = None
    result_category: Optional[str] = None
    duration_seconds: Optional[int] = None
    retry_count: int = 0
    retry_of_job_id: Optional[int] = None
    safe_command_json: Optional[str] = None
    last_success_at: Optional[str] = None
    last_error_at: Optional[str] = None
    last_log_at: Optional[str] = None
    # Phase 10F: progress/runtime surfaced for the UI.
    runtime_type: Optional[str] = None
    command_preview: Optional[str] = None
    progress_phase: Optional[str] = None
    # Media type (movie/series/…) from the linked library item, for filtering.
    media_type: Optional[str] = None
    # Poster thumbnail from the linked library item, for the Subidas row.
    poster_url: Optional[str] = None
    # Year from the linked library item, shown next to the title (same
    # format Biblioteca's detail page already uses).
    year: Optional[int] = None
    # Origen (Radarr/Sonarr instance) and Petición status from the linked
    # library item — same fields Biblioteca already shows per content.
    instance_type: Optional[str] = None
    instance_name: Optional[str] = None
    # instance_id/tmdb_id/title_slug — also from the linked library item,
    # only needed to build the same Origen deep link Biblioteca's own column
    # uses (see buildDeepLink in frontend/src/utils/libraryItem.ts).
    instance_id: Optional[int] = None
    tmdb_id: Optional[str] = None
    title_slug: Optional[str] = None
    request_status: Optional[str] = None
    # Grace-period deadline while status='queued' — lets the UI show a
    # countdown + Cancel before the server starts renaming/remuxing/uploading.
    queued_until: Optional[str] = None
    # Read-only snapshots taken at apply time — the nomenclature field
    # breakdown and the applied remux track plan, neither of which survive
    # anywhere else once nomenclature.py/mkv_remux.py return. Backs the job
    # detail page's "Nomenclatura"/"Remux aplicado" sections.
    nomenclature_snapshot: Optional[dict] = None
    remux_snapshot: Optional[dict] = None
    # Pre-upload checks ({"checks": [...], "ready": bool}) as computed by the
    # wizard before the user confirmed — backs "Verificación pre-subida".
    checks_snapshot: Optional[dict] = None
    # Real per-phase progress ({"phases": [...], "global_pct": N}), built
    # from uploadrr_progress.py's fixed-weight phase table.
    progress: Optional[dict] = None


class UploadJobLog(BaseModel):
    id: Optional[int] = None
    upload_job_id: int
    level: str
    message: str
    stream: Optional[str] = None
    created_at: str


class UploadJobLogsResponse(BaseModel):
    job_id: int
    logs: list[UploadJobLog] = []
    total: int = 0
    limit: int = 500
    offset: int = 0


class UploadStartResult(BaseModel):
    job_id: int
    action: str
    status: str
    stage: Optional[str] = None
    dry_run: bool
    command_preview: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 6D — Artifacts and retry
# ---------------------------------------------------------------------------

class UploadArtifact(BaseModel):
    id: Optional[int] = None
    upload_job_id: int
    artifact_type: str
    name: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    value: Optional[str] = None
    created_at: str


class UploadArtifactsResponse(BaseModel):
    job_id: int
    artifacts: list[UploadArtifact] = []


class UploadRetryRequest(BaseModel):
    dry_run: bool = True
    start: bool = False
    confirmation: Optional[str] = None


class UploadDeleteRequest(BaseModel):
    confirmation: Optional[str] = None


class DashboardSummaryResponseV2(DashboardSummaryResponse):
    uploads_ready: int = 0
    uploads_running: int = 0
    uploads_completed: int = 0
    uploads_failed: int = 0
    last_upload_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 7C — Maintenance / Backup / Config Export
# ---------------------------------------------------------------------------

class BackupRequest(BaseModel):
    include_secrets: bool = False
    confirmation: Optional[str] = None


class RestoreRequest(BaseModel):
    backup_path: str
    dry_run: bool = True
    apply: bool = False
    confirmation: Optional[str] = None


class ImportSettingsRequest(BaseModel):
    payload: dict[str, Any]
    dry_run: bool = True
    apply: bool = False
    confirmation: Optional[str] = None


class VacuumRequest(BaseModel):
    dry_run: bool = True
    apply: bool = False
    confirmation: Optional[str] = None


class CleanupLogsRequest(BaseModel):
    days: int = 30
    dry_run: bool = True
    apply: bool = False
    confirmation: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 8C — Operational queue
# ---------------------------------------------------------------------------

class OperationalQueueItem(BaseModel):
    id: int
    queue_key: str
    item_type: str
    entity_type: str
    entity_id: Optional[int] = None
    request_item_id: Optional[int] = None
    library_item_id: Optional[int] = None
    upload_job_id: Optional[int] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    status: str
    action: str
    blockers: list[str] = []
    reasons: list[str] = []
    context: dict = {}
    target_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    resolved_at: Optional[str] = None


class OperationalQueueListResponse(BaseModel):
    items: list[OperationalQueueItem]
    total: int = 0


class OperationalQueueSummary(BaseModel):
    total: int = 0
    open: int = 0
    ready: int = 0
    waiting: int = 0
    blocked: int = 0
    running: int = 0


class OperationalQueueRefreshBody(BaseModel):
    limit: Optional[int] = None
    include_requests: bool = True
    include_library: bool = True
    include_uploads: bool = True
    include_arr: bool = True


class OperationalQueueResolveBody(BaseModel):
    reason: Optional[str] = None


class OperationalQueueRefreshResponse(BaseModel):
    ok: bool
    items_built: int = 0
    summary: OperationalQueueSummary = OperationalQueueSummary()


class OperationalQueueActionResponse(BaseModel):
    ok: bool
    item_id: int
    status: str
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 10A — Nomenclature fields, Source Assistant, MKV title
# ---------------------------------------------------------------------------

class NomenclatureFieldsPreviewBody(BaseModel):
    fields: dict[str, Any]


class NomenclatureFieldsSaveBody(BaseModel):
    fields: dict[str, Any]


class MkvTitleApplyBody(BaseModel):
    dry_run: bool = True
    apply: bool = False
    confirmation: Optional[str] = None


class TrackRemuxOverride(BaseModel):
    new_name: Optional[str] = None
    default_after: Optional[bool] = None


class TrackRemuxApplyBody(BaseModel):
    dry_run: bool = True
    apply: bool = False
    confirmation: Optional[str] = None
    # Keyed by track id (string in JSON — object keys are always strings).
    overrides: Optional[Dict[str, TrackRemuxOverride]] = None


class UploadCheckResultItem(BaseModel):
    id: str
    label: str
    status: str
    message: Optional[str] = None


class UploadChecksSnapshot(BaseModel):
    checks: list[UploadCheckResultItem] = []
    ready: bool = False


class UploadQueueBody(BaseModel):
    # Manual edits the user made in the wizard's "Ver Remux" card, carried
    # through to the server-side remux step that runs after the grace period.
    remux_overrides: Optional[Dict[str, TrackRemuxOverride]] = None
    # The pre-upload checks result the wizard already computed and showed
    # the user before they confirmed — persisted verbatim on the new job so
    # its detail page's "Verificación pre-subida" section can show exactly
    # what was checked, without re-running anything server-side.
    checks: Optional[UploadChecksSnapshot] = None


class UploadQueueResponse(BaseModel):
    status: str
    job: Optional[UploadJobDetail] = None
    errors: list[str] = []


class AutoUploadRequest(BaseModel):
    """Optional source/provider override for an "Automático" upload — set
    once the user resolved a source-disparity by hand (see
    services/source_assistant.py::check_auto_upload_source)."""
    source: Optional[str] = None
    provider: Optional[str] = None


class AutoUploadSourceCheckResponse(BaseModel):
    disparity: bool
    from_name: Optional[str] = None
    from_radarr: Optional[str] = None
    from_mediainfo: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 10C — External API connection tests
# ---------------------------------------------------------------------------

class TestTmdbRequest(BaseModel):
    api_key: Optional[str] = None
    language: Optional[str] = None
    region: Optional[str] = None


class TestEmuwarezRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class TestArrRequest(BaseModel):
    instance_id: Optional[int] = None
    kind: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class TestQbitRequest(BaseModel):
    # All optional — omitted fields fall back to the stored qBittorrent config.
    url: Optional[str] = None
    port: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class TestImghostRequest(BaseModel):
    host: str
    api_key: Optional[str] = None  # omitted → falls back to the stored key


class TestUploadrrRequest(BaseModel):
    """Phase 10F — filesystem-only check, never executes Uploadrr."""
    path: Optional[str] = None
    python_path: Optional[str] = None


class IntegrationTestResult(BaseModel):
    ok: bool
    service: str
    status: str
    message: str
    details: dict = {}


# ---------------------------------------------------------------------------
# Phase 11A — Notifications (Discord webhook / Telegram bot) test-send
# ---------------------------------------------------------------------------

class TestDiscordRequest(BaseModel):
    """If webhook_url is omitted, the stored notify.discord.webhook_url is used."""
    webhook_url: Optional[str] = None


class TestTelegramRequest(BaseModel):
    """If bot_token/chat_id are omitted, the stored values are used."""
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 11D — Automatic tasks scheduler
# ---------------------------------------------------------------------------

class ScheduledTaskResponse(BaseModel):
    task_key: str
    name: str
    description: str
    interval_minutes: int
    min_interval_minutes: int
    manual_allowed: bool
    enabled: bool
    last_run_at: Optional[str] = None
    last_status: Optional[str] = None
    last_summary: Optional[str] = None
    next_run_at: Optional[str] = None


class UpdateScheduledTaskRequest(BaseModel):
    interval_minutes: int


class RunScheduledTaskResponse(BaseModel):
    task_key: str
    status: str
    summary: str
    next_run_at: Optional[str] = None


class TaskRunLogEntry(BaseModel):
    id: int
    name: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: Optional[str] = None
    details: Optional[str] = None


class TaskRunLogsResponse(BaseModel):
    task_key: str
    logs: list[TaskRunLogEntry] = []
