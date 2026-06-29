"""Pydantic request/response schemas for the web API."""
from __future__ import annotations

from typing import Any, Optional
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


# ---------------------------------------------------------------------------
# Setup status
# ---------------------------------------------------------------------------

class SetupStatusResponse(BaseModel):
    initialized: bool
    admin_configured: bool
    base_configured: bool = False
    tmdb_configured: bool
    emu_configured: bool
    uploadrr_configured: bool
    radarr_instances: int
    sonarr_instances: int
    jellyfin_configured: bool
    seerr_configured: bool
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


# ---------------------------------------------------------------------------
# Setup POST requests
# ---------------------------------------------------------------------------

class SetupBaseRequest(BaseModel):
    app_name: str = "eMuwarez Uploadrr"
    timezone: str = "Europe/Madrid"


class SetupUploadrrRequest(BaseModel):
    uploadrr_path: str

    @field_validator("uploadrr_path")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La ruta de Uploadrr no puede estar vacía")
        return v


class SetupTmdbRequest(BaseModel):
    api_key: str

    @field_validator("api_key")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La API key de TMDb no puede estar vacía")
        return v.strip()


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
        if not v.strip():
            raise ValueError("La URL no puede estar vacía")
        return v.strip()

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
    app_name: SecretStatusField
    timezone: SecretStatusField


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
    error: Optional[str] = None


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
        if v not in ("radarr", "sonarr"):
            raise ValueError("El tipo debe ser 'radarr' o 'sonarr'")
        return v

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La URL no puede estar vacía")
        return v.strip()

    @field_validator("api_key")
    @classmethod
    def api_key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La API key no puede estar vacía")
        return v.strip()


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
    radarr_items: int = 0
    sonarr_items: int = 0
    last_sync_at: Optional[str] = None


class DashboardActivityItem(BaseModel):
    id: int
    name: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: Optional[str] = None


class DashboardActivityResponse(BaseModel):
    items: list[DashboardActivityItem] = []


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
    external_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    path: Optional[str] = None
    quality: Optional[str] = None
    resolution: Optional[str] = None
    source: Optional[str] = None
    size_bytes: Optional[int] = None
    local_status: str
    request_status: str
    nomenclature_status: str
    updated_at: Optional[str] = None


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


class MissingListResponse(BaseModel):
    items: list[MissingItemResponse] = []
    total: int = 0
    limit: int = 50
    offset: int = 0


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
