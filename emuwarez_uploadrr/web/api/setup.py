"""Setup wizard endpoints.

GET  /api/setup/status         — current wizard state (public)
POST /api/setup/admin          — create first admin user (public — only before admin exists)
POST /api/setup/tmdb           — TMDb API key (requires auth)
POST /api/setup/emu            — eMuwarez API key + optional endpoint (requires auth)
POST /api/setup/instances      — add Radarr/Sonarr instance (requires auth)
POST /api/setup/complete       — finalize setup (requires auth)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import require_auth
from ..errors import AppError
from ..runtime import _db_path
from ..schemas import (
    CreateAdminRequest,
    InstanceResponse,
    OkResponse,
    SetupEmuRequest,
    SetupInstanceRequest,
    SetupImghostsRequest,
    SetupQbitRequest,
    SetupStatusResponse,
    SetupTmdbRequest,
)

router = APIRouter(tags=["setup"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# GET /api/setup/status — public
# ---------------------------------------------------------------------------

@router.get("/setup/status", response_model=SetupStatusResponse)
def setup_status() -> SetupStatusResponse:
    from ..services.setup_service import get_setup_state, next_step
    try:
        with _get_conn() as conn:
            state = get_setup_state(conn)
    except Exception:
        state = {
            "initialized": False, "admin_configured": False,
            "tmdb_configured": False, "emu_configured": False,
            "radarr_instances": 0, "sonarr_instances": 0,
            "jellyfin_configured": False,
        }
    return SetupStatusResponse(**state, next_step=next_step(state))


# ---------------------------------------------------------------------------
# POST /api/setup/admin — public (only allowed before admin exists)
# ---------------------------------------------------------------------------

@router.post("/setup/admin", response_model=OkResponse, status_code=201)
def setup_admin(body: CreateAdminRequest) -> OkResponse:
    from ..services.auth_service import admin_exists
    from ..services.setup_service import SetupError, setup_admin as _setup_admin
    with _get_conn() as conn:
        if admin_exists(conn):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un usuario administrador. Inicia sesión para continuar el setup.",
            )
        try:
            _setup_admin(conn, body.username, body.password)
            conn.commit()
        except SetupError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OkResponse(message=f"Usuario administrador '{body.username}' creado correctamente")



# ---------------------------------------------------------------------------
# POST /api/setup/tmdb — requires auth
# ---------------------------------------------------------------------------

@router.post("/setup/tmdb", response_model=OkResponse)
def setup_tmdb(
    body: SetupTmdbRequest,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from ..services.setup_service import SetupError, setup_tmdb as _setup_tmdb
    with _get_conn() as conn:
        try:
            _setup_tmdb(conn, body.api_key, body.region or "ES",
                        localize_series_titles=body.localize_series_titles)
            conn.commit()
        except SetupError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OkResponse(message="API key de TMDb guardada correctamente")


# ---------------------------------------------------------------------------
# POST /api/setup/qbit — requires auth (optional/skippable)
# ---------------------------------------------------------------------------

@router.post("/setup/qbit", response_model=OkResponse)
def setup_qbit(
    body: SetupQbitRequest,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from ..services.setup_service import setup_qbit as _setup_qbit
    with _get_conn() as conn:
        _setup_qbit(conn, body.url, body.username, body.password, body.tag)
        conn.commit()
    return OkResponse(message="Configuración de qBittorrent guardada correctamente")


@router.post("/setup/imghosts", response_model=OkResponse)
def setup_imghosts(
    body: SetupImghostsRequest,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from ..services.setup_service import setup_imghosts as _setup_imghosts
    with _get_conn() as conn:
        _setup_imghosts(conn, body.enabled, body.keys)
        conn.commit()
    return OkResponse(message="Proveedores de imágenes guardados correctamente")


# ---------------------------------------------------------------------------
# POST /api/setup/emu — requires auth
# ---------------------------------------------------------------------------

@router.post("/setup/emu", response_model=OkResponse)
def setup_emu(
    body: SetupEmuRequest,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from ..services.setup_service import SetupError, setup_emu as _setup_emu
    with _get_conn() as conn:
        try:
            _setup_emu(conn, body.api_key, body.endpoint_url)
            conn.commit()
        except SetupError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OkResponse(message="Configuración de eMuwarez guardada correctamente")


# ---------------------------------------------------------------------------
# POST /api/setup/instances — requires auth
# ---------------------------------------------------------------------------

@router.post("/setup/instances", response_model=OkResponse, status_code=201)
def setup_instances(
    body: SetupInstanceRequest,
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from ..services.setup_service import setup_add_instance
    with _get_conn() as conn:
        try:
            instance_id = setup_add_instance(
                conn,
                body.type,
                body.name,
                body.url,
                body.api_key,
                is_4k=body.is_4k,
                is_anime=body.is_anime,
            )
            conn.commit()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OkResponse(
        message=f"Instancia {body.type.capitalize()} '{body.name}' añadida con ID {instance_id}"
    )


# ---------------------------------------------------------------------------
# POST /api/setup/complete — requires auth
# ---------------------------------------------------------------------------

@router.post("/setup/complete", response_model=OkResponse)
def setup_complete(
    current_user: dict = Depends(require_auth),
) -> OkResponse:
    from ..services.setup_service import SetupError, setup_complete as _setup_complete
    with _get_conn() as conn:
        try:
            _setup_complete(conn)
            conn.commit()
        except SetupError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OkResponse(message="Setup completado. La aplicación está lista para usar.")
