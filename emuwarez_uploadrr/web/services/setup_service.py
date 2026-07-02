"""Setup wizard service.

Orchestrates the multi-step first-run flow and delegates to auth_service /
settings_service for persistence. All functions receive an open connection
and do NOT commit — the caller commits.
"""
from __future__ import annotations

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
    seerr = sum(1 for i in instances if i.type == "seerr")
    return {
        "initialized": get_state(conn, "initialized") == "true",
        "admin_configured": admin_exists(conn),
        "base_configured": get_configured(conn, "app.name"),
        "uploadrr_configured": get_configured(conn, "uploadrr.path"),
        "tmdb_configured": get_configured(conn, "tmdb.api_key"),
        "emu_configured": get_configured(conn, "emu.api_key"),
        "radarr_instances": radarr,
        "sonarr_instances": sonarr,
        "jellyfin_configured": False,  # Jellyfin is explicitly out of scope
        "seerr_configured": seerr > 0,  # Phase 11C — real value (was always False)
    }


def next_step(state: dict) -> Optional[str]:
    """Resume order (Phase 11C): admin -> base -> emu -> instances -> tmdb ->
    uploadrr -> complete. 'welcome' is frontend-only (shown once before an
    admin exists). 'seerr' and 'nomenclature' are optional/skippable steps —
    they are not gating conditions here, same treatment as the pre-existing
    optional-count-only gating on 'instances'."""
    if not state["admin_configured"]:
        return "admin"
    if not state["base_configured"]:
        return "base"
    if not state["emu_configured"]:
        return "emu"
    if state["radarr_instances"] == 0 and state["sonarr_instances"] == 0:
        return "instances"
    if not state["tmdb_configured"]:
        return "tmdb"
    if not state["uploadrr_configured"]:
        return "uploadrr"
    if not state["initialized"]:
        return "complete"
    return None


def setup_admin(conn: sqlite3.Connection, username: str, password: str) -> int:
    """Create the first admin user. Raises SetupError if one already exists."""
    if admin_exists(conn):
        raise SetupError("Ya existe un usuario administrador")
    user_id = create_user(conn, username, password, role="admin")
    return user_id


def setup_base(conn: sqlite3.Connection, app_name: str, timezone: str) -> None:
    """Persist base application settings."""
    set_setting(conn, "app.name", app_name.strip())
    set_setting(conn, "app.timezone", timezone.strip())


def setup_uploadrr(conn: sqlite3.Connection, uploadrr_path: str) -> None:
    """Persist the path to the Uploadrr runtime directory."""
    path = uploadrr_path.strip()
    if not path:
        raise SetupError("La ruta de Uploadrr no puede estar vacía")
    set_setting(conn, "uploadrr.path", path)


def setup_tmdb(
    conn: sqlite3.Connection,
    api_key: str,
    language: str = "es-ES",
    region: str = "ES",
) -> None:
    if not api_key.strip():
        raise SetupError("La API key de TMDb no puede estar vacía")
    set_setting(conn, "tmdb.api_key", api_key.strip())
    if language and language.strip():
        set_setting(conn, "tmdb_language", language.strip())
    if region and region.strip():
        set_setting(conn, "tmdb_watch_region", region.strip())


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


def setup_seerr(conn: sqlite3.Connection, name: str, url: str, api_key: str) -> int:
    """Add a Seerr (Overseerr/Jellyseerr-compatible) instance during setup.
    Optional/skippable step — request sync is not implemented yet (Phase
    11B); this only prepares the instance for when it is."""
    from emuwarez_uploadrr.services.instances import add_instance
    return add_instance(conn, "seerr", name or "Seerr", url, api_key)


NOMENCLATURE_DISABLE_HARDLINKS_TOKEN = "DESACTIVAR_HARDLINKS"


def setup_nomenclature(
    conn: sqlite3.Connection,
    default_release_tag: str,
    hardlink_base: Optional[str] = None,
    use_hardlinks: bool = True,
) -> None:
    """Persist the upload tag and hardlink strategy. Optional/skippable step.

    Callers MUST have already validated the confirmation token when
    use_hardlinks=False (see web/api/setup.py) — this function only persists
    the already-validated decision, it does not re-check the token.
    """
    if default_release_tag and default_release_tag.strip():
        set_setting(conn, "default_release_tag", default_release_tag.strip())
    if hardlink_base and hardlink_base.strip():
        set_setting(conn, "hardlink_base", hardlink_base.strip())
    set_setting(conn, "nomenclature.use_hardlinks", "true" if use_hardlinks else "false")


def setup_complete(conn: sqlite3.Connection) -> None:
    """Mark setup as complete. Raises SetupError if required steps are missing."""
    state = get_setup_state(conn)
    missing = []
    if not state["admin_configured"]:
        missing.append("admin")
    if not state["uploadrr_configured"]:
        missing.append("uploadrr")
    if not state["tmdb_configured"]:
        missing.append("tmdb")
    if not state["emu_configured"]:
        missing.append("emu")
    if state["radarr_instances"] == 0 and state["sonarr_instances"] == 0:
        missing.append("instances")
    if missing:
        raise SetupError(f"Pasos pendientes: {', '.join(missing)}")
    set_state(conn, "initialized", "true")
