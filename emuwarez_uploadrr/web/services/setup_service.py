"""Setup wizard service.

Orchestrates the multi-step first-run flow and delegates to auth_service /
settings_service for persistence. All functions receive an open connection
and do NOT commit — the caller commits.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from emuwarez_uploadrr.database import get_state, set_state
from emuwarez_uploadrr.services.instances import list_instances

from .auth_service import admin_exists, create_user
from .settings_service import get_configured, set_setting


class SetupError(Exception):
    """Raised when a setup step precondition fails."""


def get_setup_state(conn: sqlite3.Connection) -> dict:
    """Read all setup flags and return a unified state dict."""
    instances = list_instances(conn)
    radarr = sum(1 for i in instances if i.type == "radarr")
    sonarr = sum(1 for i in instances if i.type == "sonarr")
    return {
        "initialized": get_state(conn, "initialized") == "true",
        "admin_configured": admin_exists(conn),
        "tmdb_configured": get_configured(conn, "tmdb.api_key"),
        "emu_configured": get_configured(conn, "emu.api_key"),
        "radarr_instances": radarr,
        "sonarr_instances": sonarr,
        "jellyfin_configured": False,  # Jellyfin is explicitly out of scope
    }


def next_step(state: dict) -> Optional[str]:
    """Resume order: admin -> emu -> instances -> tmdb -> complete.
    'welcome' is frontend-only (shown once before an admin exists).
    eMuwarez/instances/TMDb/nomenclature are all skippable steps (each has
    its own skip control in the UI) — none of them, nor Uploadrr (no
    dedicated wizard step; configurable later from Settings), block
    completing setup. This resume order only decides which unconfigured
    step to land on if the wizard is reopened mid-flow.

    `initialized` is checked right after `admin_configured` (not last) —
    once setup has actually been completed, it must never route back into
    the wizard just because some skippable step (e.g. eMuwarez) was never
    configured; otherwise a skipped step would forever short-circuit this
    chain and make next_step() claim the wizard isn't done.
    """
    if not state["admin_configured"]:
        return "admin"
    if state["initialized"]:
        return None
    if not state["emu_configured"]:
        return "emu"
    if state["radarr_instances"] == 0 and state["sonarr_instances"] == 0:
        return "instances"
    if not state["tmdb_configured"]:
        return "tmdb"
    return "complete"


def setup_admin(conn: sqlite3.Connection, username: str, password: str) -> int:
    """Create the first admin user. Raises SetupError if one already exists."""
    if admin_exists(conn):
        raise SetupError("Ya existe un usuario administrador")
    user_id = create_user(conn, username, password, role="admin")
    return user_id


def setup_tmdb(
    conn: sqlite3.Connection,
    api_key: str,
    language: str = "es-ES",
    region: str = "ES",
    localize_series_titles: Optional[bool] = None,
) -> None:
    if not api_key.strip():
        raise SetupError("La API key de TMDb no puede estar vacía")
    set_setting(conn, "tmdb.api_key", api_key.strip())
    if language and language.strip():
        set_setting(conn, "tmdb_language", language.strip())
    if region and region.strip():
        set_setting(conn, "tmdb_watch_region", region.strip())
    if localize_series_titles is not None:
        set_setting(conn, "tmdb.localize_series_titles", "true" if localize_series_titles else "false")


def setup_qbit(
    conn: sqlite3.Connection,
    url: str,
    port: Optional[str] = "8080",
    username: Optional[str] = "",
    password: Optional[str] = "",
) -> None:
    """Store the qBittorrent WebUI config. Skippable — an empty url means the
    user didn't configure a torrent client in the wizard."""
    if not url or not url.strip():
        return
    set_setting(conn, "qbit.url", url.strip())
    set_setting(conn, "qbit.port", (port or "8080").strip())
    set_setting(conn, "qbit.username", (username or "").strip())
    if password:
        set_setting(conn, "qbit.password", password)


def setup_imghosts(
    conn: sqlite3.Connection,
    enabled: Optional[list] = None,
    keys: Optional[dict] = None,
) -> None:
    """Store the image-host selection. Skippable — imgbox is always the default
    fallback, so an empty selection is fine."""
    from ...services.image_hosts import set_config
    set_config(conn, enabled or [], keys or {})


def setup_emu(
    conn: sqlite3.Connection,
    api_key: str,
    endpoint_url: Optional[str] = None,
) -> None:
    if not api_key.strip():
        raise SetupError("La API key de eMuwarez no puede estar vacía")
    set_setting(conn, "emu.api_key", api_key.strip())
    if endpoint_url and endpoint_url.strip():
        set_setting(conn, "emu.endpoint_url", endpoint_url.strip())
        # Also update the app_state key used by the CLI requests sync
        set_state(conn, "emu_requests_endpoint", endpoint_url.strip())


def setup_add_instance(
    conn: sqlite3.Connection,
    instance_type: str,
    name: str,
    url: str,
    api_key: str,
    is_4k: bool = False,
    is_anime: bool = False,
) -> int:
    """Add a Radarr/Sonarr instance during setup."""
    from emuwarez_uploadrr.services.instances import add_instance
    instance_id = add_instance(conn, instance_type, name, url, api_key)
    if is_4k or is_anime:
        conn.execute(
            """
            UPDATE instances
            SET is_4k = ?, is_anime = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (int(is_4k), int(is_anime), instance_id),
        )
    return instance_id


NOMENCLATURE_DISABLE_HARDLINKS_TOKEN = "DESACTIVAR_HARDLINKS"


def setup_nomenclature(
    conn: sqlite3.Connection,
    default_release_tag: str,
    hardlink_base: Optional[str] = None,
    use_hardlinks: bool = True,
    provider_priority_order: Optional[list[str]] = None,
) -> None:
    """Persist the upload tag and hardlink strategy. Optional/skippable step.

    Callers MUST have already validated the confirmation token when
    use_hardlinks=False (see web/api/setup.py) — this function only persists
    the already-validated decision, it does not re-check the token.
    Provider codes in provider_priority_order must already be validated by the
    caller too (same _VALID_PROVIDER_CODES check as web/api/settings.py).
    """
    if default_release_tag and default_release_tag.strip():
        set_setting(conn, "default_release_tag", default_release_tag.strip())
    if hardlink_base and hardlink_base.strip():
        set_setting(conn, "hardlink_base", hardlink_base.strip())
    set_setting(conn, "nomenclature.use_hardlinks", "true" if use_hardlinks else "false")
    if provider_priority_order is not None:
        codes = [c.strip() for c in provider_priority_order]
        set_setting(conn, "provider_priority_order", json.dumps(codes, ensure_ascii=False))


def setup_complete(conn: sqlite3.Connection) -> None:
    """Mark setup as complete. The admin account is the only hard
    requirement — every other step (eMuwarez, instances, TMDb, Uploadrr,
    nomenclature) is optional/skippable and has its own skip control in
    the wizard UI, so none of them block finishing setup."""
    state = get_setup_state(conn)
    if not state["admin_configured"]:
        raise SetupError("Pasos pendientes: admin")
    set_state(conn, "initialized", "true")
