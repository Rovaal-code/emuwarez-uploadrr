"""Setup wizard service.

Orchestrates the multi-step first-run flow and delegates to auth_service /
services/settings.py for persistence. All functions receive an open connection
and do NOT commit — the caller commits.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from emuwarez_uploadrr.database import get_state, set_state
from emuwarez_uploadrr.services.instances import list_instances

from .auth_service import admin_exists, create_user
from ...services.settings import get_configured, set_setting


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
    eMuwarez and TMDb are mandatory — both setup_emu()/setup_tmdb() and
    setup_complete() require a live-tested, working key, so neither can be
    skipped or bypassed. Instances and Uploadrr (no dedicated wizard step;
    configurable later from Settings) remain optional/skippable. This
    resume order only decides which unconfigured step to land on if the
    wizard is reopened mid-flow.

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
    region: str = "ES",
    localize_series_titles: Optional[bool] = None,
) -> None:
    if not api_key.strip():
        raise SetupError("La API key de TMDb no puede estar vacía")
    api_key = api_key.strip()
    from emuwarez_uploadrr.services.integration_tests import test_tmdb_connection
    result = test_tmdb_connection(api_key=api_key, conn=conn)
    if not result.get("ok"):
        raise SetupError(result.get("message") or "API key de TMDb inválida")
    set_setting(conn, "tmdb.api_key", api_key)
    if region and region.strip():
        set_setting(conn, "tmdb_watch_region", region.strip())
    if localize_series_titles is not None:
        set_setting(conn, "tmdb.localize_series_titles", "true" if localize_series_titles else "false")


def setup_qbit(
    conn: sqlite3.Connection,
    url: str,
    username: Optional[str] = "",
    password: Optional[str] = "",
    tag: Optional[str] = "",
) -> None:
    """Store the qBittorrent WebUI config. Skippable — an empty url means the
    user didn't configure a torrent client in the wizard.

    The port goes INSIDE the url (http://host:8080); it stopped being a field
    of its own because having it apart only meant typing it twice and made
    "the port in the url doesn't match the WebUI's" a real, invisible failure.
    `tag` is the label qBittorrent puts on the torrent so you can tell your
    uploads apart; empty means don't tag."""
    if not url or not url.strip():
        return
    set_setting(conn, "qbit.url", url.strip())
    set_setting(conn, "qbit.username", (username or "").strip())
    set_setting(conn, "qbit.tag", (tag or "").strip())
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
    api_key = api_key.strip()
    from emuwarez_uploadrr.services.integration_tests import test_emuwarez_connection
    result = test_emuwarez_connection(api_key=api_key, base_url=endpoint_url, conn=conn, enforce_rate_limit=False)
    if not result.get("ok"):
        raise SetupError(result.get("message") or "API key de eMuwarez inválida")
    set_setting(conn, "emu.api_key", api_key)
    if endpoint_url and endpoint_url.strip():
        set_setting(conn, "emu.endpoint_url", endpoint_url.strip())


def setup_add_instance(
    conn: sqlite3.Connection,
    instance_type: str,
    name: str,
    url: str,
    api_key: str,
    is_4k: bool = False,
    is_anime: bool = False,
) -> int:
    """Add a Radarr/Sonarr instance during setup.

    Verifies the connection before persisting, same as the main app's
    POST /instances (services/instances.py::add_instance) — the wizard's
    frontend already re-tests before calling this, but this is the real
    guarantee: a well-formed but unreachable/unauthorized instance must
    never be saved, from either entry point."""
    from emuwarez_uploadrr.services.instances import add_instance
    instance_id = add_instance(conn, instance_type, name, url, api_key, test_connection=True)
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




def setup_complete(conn: sqlite3.Connection) -> None:
    """Mark setup as complete. admin/eMuwarez/TMDb are hard requirements —
    setup_tmdb()/setup_emu() already live-test the key before it's ever
    marked configured, so this is a second, server-side guarantee that
    can't be bypassed by calling this endpoint directly without going
    through those steps. Instances/Uploadrr/nomenclature stay optional,
    each with its own skip control in the wizard UI."""
    state = get_setup_state(conn)
    missing = [
        name for name, ok in (
            ("admin", state["admin_configured"]),
            ("emu", state["emu_configured"]),
            ("tmdb", state["tmdb_configured"]),
        ) if not ok
    ]
    if missing:
        raise SetupError(f"Pasos pendientes: {', '.join(missing)}")
    set_state(conn, "initialized", "true")
