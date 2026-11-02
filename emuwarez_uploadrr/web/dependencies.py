"""FastAPI dependency injection for authentication."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import ExitStack
from typing import Annotated, Iterator, Optional

from fastapi import Depends, Header, HTTPException, status

from emuwarez_uploadrr.database import BaseMasNuevaError, db
from .runtime import _db_path

logger = logging.getLogger(__name__)

# Lo que significa «la base no responde». Un fallo de código (KeyError, ImportError...) no
# lo es: tiene que llegar como 500, no disfrazarse de una caída pasajera.
ERRORES_DE_BASE = (sqlite3.Error, OSError, BaseMasNuevaError)


def base_no_disponible(donde: str) -> HTTPException:
    """503 para un fallo de la base, que no se confunde con una sesión inválida.
    Se llama dentro del `except`: deja la traza en el registro."""
    logger.exception("%s: la base de datos falló", donde)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="La base de datos no responde. Inténtalo de nuevo en unos segundos.",
        headers={"Retry-After": "5"},
    )


def get_db() -> Iterator[sqlite3.Connection]:
    """Una conexión por petición: se confirma al terminar bien, se deshace si
    falla y se cierra siempre. Si no se puede abrir, responde 503."""
    with ExitStack() as pila:
        try:
            conn = pila.enter_context(db(_db_path(), entre_hilos=True))
        except ERRORES_DE_BASE:
            raise base_no_disponible("get_db")
        yield conn


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
        from .services.auth_service import get_user_by_token
        with db(_db_path()) as conn:
            return get_user_by_token(conn, token)
    except Exception:
        return None


def require_auth(
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict:
    """401 si no hay un token válido; 503 si la base no deja comprobarlo."""
    token = _resolve_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Incluye el token en Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    from .services.auth_service import get_user_by_token
    try:
        with db(_db_path()) as conn:
            user = get_user_by_token(conn, token)
    except ERRORES_DE_BASE:
        # Un fallo de la base no es un token inválido: con 401 el cliente
        # borraba la sesión por un bloqueo pasajero.
        raise base_no_disponible("require_auth")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_widget_key(
    x_api_key: Annotated[Optional[str], Header()] = None,
    authorization: Annotated[Optional[str], Header()] = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    """La clave del widget de Homepage, en `X-Api-Key` o en `Authorization: Bearer`. Solo abre /api/widget: no es
    un token de sesión y `require_auth` no la acepta. 404 si el widget no está activado; 401 si falta o no vale;
    503 si la base no responde."""
    from ..services.widget import clave_configurada, clave_valida
    try:
        if not clave_configurada(conn):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El widget no está activado. Genera su clave en Configuración.",
            )
        valida = clave_valida(conn, (x_api_key or "").strip() or _resolve_token(authorization))
    except ERRORES_DE_BASE:
        raise base_no_disponible("widget")
    if not valida:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clave del widget ausente o no válida. Envíala en X-Api-Key o en Authorization: Bearer.",
            headers={"WWW-Authenticate": "Bearer"},
        )
