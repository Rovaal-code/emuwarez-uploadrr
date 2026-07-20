"""Authentication endpoints.

POST /api/auth/login              — exchange credentials for a session token
GET  /api/auth/me                 — return current user (requires Bearer token)
POST /api/auth/logout             — revoke current session token
POST /api/auth/change-credentials — change username and/or password
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    ChangeCredentialsRequest, ChangeCredentialsResponse,
    CurrentUserResponse, LoginRequest, LoginResponse, LogoutResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    from ..services.auth_service import AuthError, authenticate, create_session
    with _get_conn() as conn:
        try:
            user = authenticate(conn, body.username, body.password)
        except AuthError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario o contraseña incorrectos",
            )
        ua = request.headers.get("user-agent")
        ip = request.client.host if request.client else None
        token = create_session(conn, user["id"], user_agent=ua, ip_address=ip)
        conn.commit()
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
    with _get_conn() as conn:
        try:
            if body.new_username and body.new_username != current_user["username"]:
                update_username(conn, current_user["id"], body.new_username)
            if body.new_password:
                update_password(conn, current_user["id"], body.new_password)
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Ese nombre de usuario ya está en uso.")
    return ChangeCredentialsResponse(username=body.new_username or current_user["username"])


@router.post("/logout", response_model=LogoutResponse)
def logout(
    current_user: dict = Depends(require_auth),
    authorization: Optional[str] = Header(None),
) -> LogoutResponse:
    if not authorization:
        return LogoutResponse()
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return LogoutResponse()
    token = parts[1].strip()
    from ..services.auth_service import revoke_session
    with _get_conn() as conn:
        revoke_session(conn, token)
        conn.commit()
    return LogoutResponse()
