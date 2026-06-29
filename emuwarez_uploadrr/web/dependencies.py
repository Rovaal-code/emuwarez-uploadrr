"""FastAPI dependency injection for authentication."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Header, HTTPException, status

from .runtime import _db_path


def _resolve_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
) -> Optional[dict]:
    """Return the authenticated user dict, or None if no valid token."""
    token = _resolve_token(authorization)
    if not token:
        return None
    try:
        from emuwarez_uploadrr.database import connect, init_db
        from .services.auth_service import get_user_by_token
        with connect(_db_path()) as conn:
            init_db(conn)
            return get_user_by_token(conn, token)
    except Exception:
        return None


def require_auth(
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict:
    """Raise 401 if no valid Bearer token is present."""
    token = _resolve_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Incluye el token en Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        from emuwarez_uploadrr.database import connect, init_db
        from .services.auth_service import get_user_by_token
        with connect(_db_path()) as conn:
            init_db(conn)
            user = get_user_by_token(conn, token)
    except Exception:
        user = None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
