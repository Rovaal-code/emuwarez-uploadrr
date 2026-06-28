"""Pydantic response schemas for the web API."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    database: str
    initialized: bool


class SetupStatusResponse(BaseModel):
    initialized: bool
    admin_configured: bool
    tmdb_configured: bool
    emu_configured: bool
    uploadrr_configured: bool
    radarr_instances: int
    sonarr_instances: int
    jellyfin_configured: bool
    seerr_configured: bool
    next_step: Optional[str] = None


class RuntimeInfoResponse(BaseModel):
    app_name: str
    version: str
    config_dir: str
    database_path: str
    database_status: str
    cli_available: bool
    uploadrr_runtime_present: bool


class ContractSummaryResponse(BaseModel):
    message: str
    md_path: str
    json_path: str
    sections: list[str]
    docs_url: str


class ApiPlaceholderResponse(BaseModel):
    implemented: bool = False
    phase: str = "future"
    message: str = "Endpoint reservado para fase posterior"
    endpoint: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int
