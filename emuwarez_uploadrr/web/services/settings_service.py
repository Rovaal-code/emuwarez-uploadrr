"""CRUD for the `settings` table.

Keys use dotted namespaces: tmdb.api_key, emu.api_key, uploadrr.path, etc.
Secrets are stored with is_secret=1 and masked in API responses:
  masked_value = first_4 + "…" + last_4 for values longer than 8 chars.
"""
from __future__ import annotations

import sqlite3
from typing import Optional


_SECRET_KEYS: frozenset[str] = frozenset(
    ["tmdb.api_key", "emu.api_key", "emu.endpoint_url"]
)


def _is_secret(key: str) -> int:
    return 1 if key in _SECRET_KEYS else 0


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return value[:4] + "…" + value[-4:]


def get_setting(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a setting. Does NOT commit."""
    conn.execute(
        """
        INSERT INTO settings (key, value, is_secret, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            is_secret = excluded.is_secret,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value, _is_secret(key)),
    )


def get_configured(conn: sqlite3.Connection, key: str) -> bool:
    """Return True if key has a non-empty value in settings."""
    v = get_setting(conn, key)
    return bool(v and v.strip())


def get_settings_status(conn: sqlite3.Connection) -> dict:
    """Return a summary of each configuration section, with masked values."""
    def _entry(key: str) -> dict:
        value = get_setting(conn, key)
        configured = bool(value and value.strip())
        if configured and _is_secret(key):
            masked = mask_secret(value)  # type: ignore[arg-type]
        else:
            masked = value if configured else None
        return {"configured": configured, "masked_value": masked}

    return {
        "tmdb": _entry("tmdb.api_key"),
        "emu_api_key": _entry("emu.api_key"),
        "emu_endpoint": _entry("emu.endpoint_url"),
        "uploadrr_path": {
            "configured": get_configured(conn, "uploadrr.path"),
            "masked_value": get_setting(conn, "uploadrr.path"),
        },
        "app_name": {
            "configured": get_configured(conn, "app.name"),
            "masked_value": get_setting(conn, "app.name"),
        },
        "timezone": {
            "configured": get_configured(conn, "app.timezone"),
            "masked_value": get_setting(conn, "app.timezone"),
        },
    }
