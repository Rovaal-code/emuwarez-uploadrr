"""Settings API — read and update editable application settings.

GET  /api/settings  — return editable settings (no raw secrets)
PUT  /api/settings  — update one or more settings
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..dependencies import require_auth
from ..runtime import _db_path
from ..services.settings_service import get_setting, mask_secret, set_setting

router = APIRouter(tags=["settings"])

# Provider codes that are valid in provider_priority_order
_VALID_PROVIDER_CODES: frozenset[str] = frozenset({
    "AMZN", "ATVP", "DSNP", "F1TV", "GLB", "HS", "HULU", "M+", "IT",
    "MA", "MAX", "HMAX", "SKY", "PCOK", "PMTP", "iP", "PLAY", "MUBI",
    "NF", "RKTN", "SL", "SNXT", "VIU", "RTVE", "HBO",
})

_DEFAULT_PRIORITY: list[str] = ["AMZN", "NF", "DSNP", "MAX", "ATVP"]
_DEFAULT_REGION = "ES"
_DEFAULT_LANGUAGE = "es-ES"
_DEFAULT_TAG = "EMUWAREZ"


class SettingsResponse(BaseModel):
    default_release_tag: str
    provider_priority_order: list[str]
    tmdb_watch_region: str
    tmdb_language: str
    tmdb_api_key_configured: bool
    tmdb_api_key_masked: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    default_release_tag: Optional[str] = None
    provider_priority_order: Optional[list[str]] = None
    tmdb_watch_region: Optional[str] = None
    tmdb_language: Optional[str] = None
    tmdb_api_key: Optional[str] = None


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _build_response(conn) -> SettingsResponse:
    raw_priority = get_setting(conn, "provider_priority_order")
    try:
        priority = json.loads(raw_priority) if raw_priority else _DEFAULT_PRIORITY
    except Exception:
        priority = _DEFAULT_PRIORITY

    tmdb_key = get_setting(conn, "tmdb.api_key")
    configured = bool(tmdb_key and tmdb_key.strip())
    masked = mask_secret(tmdb_key) if configured else None

    return SettingsResponse(
        default_release_tag=get_setting(conn, "default_release_tag") or _DEFAULT_TAG,
        provider_priority_order=priority,
        tmdb_watch_region=get_setting(conn, "tmdb_watch_region") or _DEFAULT_REGION,
        tmdb_language=get_setting(conn, "tmdb_language") or _DEFAULT_LANGUAGE,
        tmdb_api_key_configured=configured,
        tmdb_api_key_masked=masked,
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings(current_user: dict = Depends(require_auth)) -> SettingsResponse:
    with _get_conn() as conn:
        return _build_response(conn)


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    body: SettingsUpdateRequest,
    current_user: dict = Depends(require_auth),
) -> SettingsResponse:
    errors: list[str] = []

    if body.default_release_tag is not None:
        tag = body.default_release_tag.strip()
        if not tag:
            errors.append("default_release_tag no puede estar vacío")

    if body.provider_priority_order is not None:
        codes = [c.strip() for c in body.provider_priority_order]
        invalid = [c for c in codes if c not in _VALID_PROVIDER_CODES]
        if invalid:
            errors.append(f"Códigos de provider inválidos: {', '.join(invalid)}")
        if len(codes) != len(set(codes)):
            errors.append("provider_priority_order contiene duplicados")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    with _get_conn() as conn:
        if body.default_release_tag is not None:
            set_setting(conn, "default_release_tag", body.default_release_tag.strip())

        if body.provider_priority_order is not None:
            codes = [c.strip() for c in body.provider_priority_order]
            set_setting(conn, "provider_priority_order", json.dumps(codes, ensure_ascii=False))

        if body.tmdb_watch_region is not None:
            set_setting(conn, "tmdb_watch_region", body.tmdb_watch_region.strip())

        if body.tmdb_language is not None:
            set_setting(conn, "tmdb_language", body.tmdb_language.strip())

        if body.tmdb_api_key is not None and body.tmdb_api_key.strip():
            set_setting(conn, "tmdb.api_key", body.tmdb_api_key.strip())

        conn.commit()
        return _build_response(conn)
