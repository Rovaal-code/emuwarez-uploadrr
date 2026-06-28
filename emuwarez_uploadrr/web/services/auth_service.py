"""User and session management for local authentication."""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..security import hash_password, verify_password, create_token, hash_token


class AuthError(Exception):
    """Raised when an auth operation fails (wrong creds, inactive user, etc.)."""


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
        INSERT INTO auth_sessions (user_id, token_hash, user_agent, ip_address)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, th, user_agent, ip_address),
    )
    return token


def get_user_by_token(conn: sqlite3.Connection, token: str) -> Optional[dict]:
    """Resolve a clear token to the active user, or return None."""
    th = hash_token(token)
    row = conn.execute(
        """
        SELECT u.*
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
          AND s.revoked_at IS NULL
          AND u.is_active = 1
        """,
        (th,),
    ).fetchone()
    return dict(row) if row else None


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
