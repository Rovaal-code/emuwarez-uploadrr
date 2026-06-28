"""Authentication endpoints.

POST /api/auth/login   — exchange credentials for a session token
GET  /api/auth/me      — return current user (requires Bearer token)
POST /api/auth/logout  — revoke current session token
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import CurrentUserResponse, LoginRequest, LoginResponse, LogoutResponse

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
