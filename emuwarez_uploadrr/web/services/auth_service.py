"""User and session management for local authentication."""
from __future__ import annotations

import logging
import math
import sqlite3
import threading
import time
from typing import Optional

from ..security import hash_password, verify_password, create_token, hash_token

logger = logging.getLogger(__name__)

# Una sesión caduca a los 30 días sin usarse y, usándose, a los 90 de abrirse.
SESION_INACTIVA_DIAS = 30
SESION_MAXIMA_DIAS = 90
_SESION_VIVA = (
    "s.revoked_at IS NULL"
    f" AND s.created_at > datetime('now', '-{SESION_MAXIMA_DIAS} days')"
    f" AND COALESCE(s.last_used_at, s.created_at) > datetime('now', '-{SESION_INACTIVA_DIAS} days')"
)
# El uso se apunta como mucho cada 10 minutos: escribir en cada petición haría esperar a todas
# mientras una sincronización tiene la base ocupada.
_APUNTAR_CADA_SEGUNDOS = 600
_apuntadas: dict[str, float] = {}

# Tras 5 contraseñas falsas seguidas de la misma IP con el mismo usuario, 15 minutos sin poder probar.
# En memoria: el servidor es un solo proceso.
MAX_FALLOS = 5
BLOQUEO_SEGUNDOS = 15 * 60
_MAX_CLAVES = 1000
_fallos: dict[tuple[str, str], tuple[int, float]] = {}
_cerrojo = threading.Lock()


class AuthError(Exception):
    """Raised when an auth operation fails (wrong creds, inactive user, etc.)."""


def _clave(ip: Optional[str], usuario: str) -> tuple[str, str]:
    return (ip or "", usuario.strip().casefold())


def segundos_de_bloqueo(ip: Optional[str], usuario: str) -> int:
    """Lo que falta para que esa IP pueda volver a probar con ese usuario; 0 si puede."""
    with _cerrojo:
        entrada = _fallos.get(_clave(ip, usuario))
        if entrada is None:
            return 0
        fallos, ultimo = entrada
        resto = BLOQUEO_SEGUNDOS - (time.monotonic() - ultimo)
        return math.ceil(resto) if fallos >= MAX_FALLOS and resto > 0 else 0


def registrar_fallo(ip: Optional[str], usuario: str) -> None:
    with _cerrojo:
        ahora = time.monotonic()
        if len(_fallos) > _MAX_CLAVES:
            for clave, (_, ultimo) in list(_fallos.items()):
                if ahora - ultimo >= BLOQUEO_SEGUNDOS:
                    del _fallos[clave]
        clave = _clave(ip, usuario)
        fallos, ultimo = _fallos.get(clave, (0, ahora))
        if ahora - ultimo >= BLOQUEO_SEGUNDOS:
            fallos = 0  # son 5 seguidos, no 5 en la vida
        _fallos[clave] = (fallos + 1, ahora)


def registrar_acierto(ip: Optional[str], usuario: str) -> None:
    with _cerrojo:
        _fallos.pop(_clave(ip, usuario), None)


def admin_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()
    return (row["n"] > 0) if row else False


def create_user(conn: sqlite3.Connection, username: str, password: str, role: str = "admin") -> int:
    """Insert a new user, return its id. Does NOT commit."""
    ph = hash_password(password)
    cur = conn.execute(
        """
        INSERT INTO users (username, password_hash, role, is_active)
        VALUES (?, ?, ?, 1)
        """,
        (username, ph, role),
    )
    return cur.lastrowid  # type: ignore[return-value]


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        (username,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM users WHERE id = ? AND is_active = 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict:
    """Return user dict or raise AuthError."""
    user = get_user_by_username(conn, username)
    if not user or not verify_password(password, user["password_hash"]):
        raise AuthError("Credenciales incorrectas")
    conn.execute(
        "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user["id"],),
    )
    return user


def create_session(
    conn: sqlite3.Connection,
    user_id: int,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> str:
    """Create an auth session, return the CLEAR token (not stored in DB)."""
    token = create_token()
    th = hash_token(token)
    conn.execute(
        """
        INSERT INTO auth_sessions (user_id, token_hash, user_agent, ip_address, last_used_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (user_id, th, user_agent[:300] if user_agent else None, ip_address),
    )
    return token


def get_user_by_token(conn: sqlite3.Connection, token: str) -> Optional[dict]:
    """Resolve a clear token to the active user, or return None."""
    th = hash_token(token)
    row = conn.execute(
        f"""
        SELECT u.*,
               (s.last_used_at IS NULL OR s.last_used_at < datetime('now', '-10 minutes')) AS por_apuntar
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
          AND {_SESION_VIVA}
          AND u.is_active = 1
        """,
        (th,),
    ).fetchone()
    if not row:
        return None
    user = dict(row)
    if user.pop("por_apuntar"):
        _apuntar_uso(conn, th)
    return user


def _apuntar_uso(conn: sqlite3.Connection, token_hash: str) -> None:
    """Apunta que la sesión se ha usado. Con la base ocupada se deja para la próxima: la petición no espera."""
    ahora = time.monotonic()
    if ahora - _apuntadas.get(token_hash, -_APUNTAR_CADA_SEGUNDOS) < _APUNTAR_CADA_SEGUNDOS:
        return
    _apuntadas[token_hash] = ahora
    try:
        conn.execute("UPDATE auth_sessions SET last_used_at = CURRENT_TIMESTAMP WHERE token_hash = ?", (token_hash,))
    except sqlite3.OperationalError:
        logger.debug("No se pudo apuntar el uso de la sesión (base ocupada)", exc_info=True)


def list_sessions(conn: sqlite3.Connection, user_id: int, token: str) -> list[dict]:
    """Las sesiones abiertas del usuario, la más reciente primero; `current` marca la de *token*."""
    th = hash_token(token)
    rows = conn.execute(
        f"""
        SELECT s.id, s.token_hash, s.created_at, COALESCE(s.last_used_at, s.created_at) AS last_used_at,
               s.user_agent, s.ip_address
        FROM auth_sessions s
        WHERE s.user_id = ? AND {_SESION_VIVA}
        ORDER BY last_used_at DESC, s.id DESC
        """,
        (user_id,),
    ).fetchall()
    return [
        {
            "id": r["id"], "current": r["token_hash"] == th, "created_at": r["created_at"],
            "last_used_at": r["last_used_at"], "user_agent": r["user_agent"], "ip_address": r["ip_address"],
        }
        for r in rows
    ]


def revoke_other_sessions(conn: sqlite3.Connection, user_id: int, token: str) -> int:
    """Cierra las demás sesiones abiertas del usuario, todas menos la de *token*. Devuelve cuántas."""
    cur = conn.execute(
        f"""
        UPDATE auth_sessions AS s
        SET revoked_at = CURRENT_TIMESTAMP
        WHERE s.user_id = ? AND s.token_hash != ? AND {_SESION_VIVA}
        """,
        (user_id, hash_token(token)),
    )
    return cur.rowcount


def update_username(conn: sqlite3.Connection, user_id: int, new_username: str) -> None:
    """Rename a user. Raises sqlite3.IntegrityError if the name is taken."""
    conn.execute(
        "UPDATE users SET username = ? WHERE id = ?",
        (new_username, user_id),
    )


def update_password(
    conn: sqlite3.Connection, user_id: int, new_password: str, keep_token: Optional[str] = None
) -> None:
    """Change the password and revoke every session of the user except *keep_token*."""
    ph = hash_password(new_password)
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (ph, user_id),
    )
    # Cambiar la contraseña tras una fuga tiene que echar al que tenga un token viejo.
    conn.execute(
        """
        UPDATE auth_sessions
        SET revoked_at = CURRENT_TIMESTAMP
        WHERE user_id = ? AND revoked_at IS NULL AND token_hash IS NOT ?
        """,
        (user_id, hash_token(keep_token) if keep_token else None),
    )


def revoke_session(conn: sqlite3.Connection, token: str) -> bool:
    """Mark the session for *token* as revoked. Return True if found."""
    th = hash_token(token)
    cur = conn.execute(
        """
        UPDATE auth_sessions
        SET revoked_at = CURRENT_TIMESTAMP
        WHERE token_hash = ? AND revoked_at IS NULL
        """,
        (th,),
    )
    return cur.rowcount > 0
