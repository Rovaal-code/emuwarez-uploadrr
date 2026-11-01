"""Authentication endpoints.

POST /api/auth/login              — exchange credentials for a session token
GET  /api/auth/me                 — return current user (requires Bearer token)
POST /api/auth/logout             — revoke current session token
POST /api/auth/change-credentials — change username and/or password
GET  /api/auth/sessions           — open sessions of the current user
POST /api/auth/sessions/close-others — revoke every session but the current one
"""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from emuwarez_uploadrr.database import db
from ..dependencies import ERRORES_DE_BASE, _resolve_token, base_no_disponible, require_auth
from ..runtime import _db_path
from ..schemas import (
    ChangeCredentialsRequest, ChangeCredentialsResponse, CloseOtherSessionsResponse,
    CurrentUserResponse, LoginRequest, LoginResponse, LogoutResponse, SessionsResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@contextmanager
def _base() -> Iterator[sqlite3.Connection]:
    """Una conexión que confirma antes de responder (el token que devuelve el login ya tiene que existir) y
    que ante un fallo de la base responde 503, no 500."""
    try:
        with db(_db_path()) as conn:
            yield conn
    except ERRORES_DE_BASE:
        raise base_no_disponible("auth")


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    from ..services.auth_service import (
        AuthError, authenticate, create_session, registrar_acierto, registrar_fallo, segundos_de_bloqueo,
    )
    ip = request.client.host if request.client else None
    espera = segundos_de_bloqueo(ip, body.username)
    if espera:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Prueba de nuevo en {math.ceil(espera / 60)} min.",
            headers={"Retry-After": str(espera)},
        )
    with _base() as conn:
        try:
            user = authenticate(conn, body.username, body.password)
        except AuthError:
            registrar_fallo(ip, body.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario o contraseña incorrectos",
            )
        registrar_acierto(ip, body.username)
        token = create_session(conn, user["id"], user_agent=request.headers.get("user-agent"), ip_address=ip)
    return LoginResponse(
        token=token,
        username=user["username"],
        role=user["role"],
    )


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: dict = Depends(require_auth)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        created_at=current_user["created_at"],
        last_login_at=current_user.get("last_login_at"),
    )


@router.post("/change-credentials", response_model=ChangeCredentialsResponse)
def change_credentials(
    body: ChangeCredentialsRequest,
    current_user: dict = Depends(require_auth),
    authorization: Optional[str] = Header(None),
) -> ChangeCredentialsResponse:
    from ..services.auth_service import update_password, update_username
    from ..security import verify_password
    if not body.new_username and not body.new_password:
        raise HTTPException(status_code=400, detail="No hay ningún cambio que aplicar.")
    if not verify_password(body.current_password, current_user["password_hash"]):
        # 400, not 401 — this is "wrong current password", not an invalid
        # session token. The frontend's global 401 handler clears the
        # active session on any 401, which would otherwise log the user
        # out just for mistyping their current password.
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
    with _base() as conn:
        try:
            if body.new_username and body.new_username != current_user["username"]:
                update_username(conn, current_user["id"], body.new_username)
            if body.new_password:
                update_password(
                    conn, current_user["id"], body.new_password, keep_token=_resolve_token(authorization)
                )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Ese nombre de usuario ya está en uso.")
    return ChangeCredentialsResponse(username=body.new_username or current_user["username"])


@router.post("/logout", response_model=LogoutResponse)
def logout(
    current_user: dict = Depends(require_auth),
    authorization: Optional[str] = Header(None),
) -> LogoutResponse:
    from ..services.auth_service import revoke_session
    with _base() as conn:
        revoke_session(conn, _resolve_token(authorization) or "")
    return LogoutResponse()


@router.get("/sessions", response_model=SessionsResponse)
def sessions(
    current_user: dict = Depends(require_auth),
    authorization: Optional[str] = Header(None),
) -> SessionsResponse:
    from ..services.auth_service import SESION_INACTIVA_DIAS, list_sessions
    with _base() as conn:
        return SessionsResponse(
            sessions=list_sessions(conn, current_user["id"], _resolve_token(authorization) or ""),
            inactive_days=SESION_INACTIVA_DIAS,
        )


@router.post("/sessions/close-others", response_model=CloseOtherSessionsResponse)
def close_other_sessions(
    current_user: dict = Depends(require_auth),
    authorization: Optional[str] = Header(None),
) -> CloseOtherSessionsResponse:
    from ..services.auth_service import revoke_other_sessions
    with _base() as conn:
        return CloseOtherSessionsResponse(
            closed=revoke_other_sessions(conn, current_user["id"], _resolve_token(authorization) or ""),
        )
