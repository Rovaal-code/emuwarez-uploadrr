"""Setup status endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from ..runtime import _db_path
from ..schemas import SetupStatusResponse

router = APIRouter(tags=["setup"])


def _read_setup_state() -> dict:
    defaults = {
        "initialized": False,
        "admin_configured": False,
        "tmdb_configured": False,
        "emu_configured": False,
        "uploadrr_configured": False,
        "radarr_instances": 0,
        "sonarr_instances": 0,
        "jellyfin_configured": False,
        "seerr_configured": False,
    }
    try:
        from emuwarez_uploadrr.database import connect, init_db, get_state
        from emuwarez_uploadrr.services.instances import list_instances
        with connect(_db_path()) as conn:
            init_db(conn)
            defaults["initialized"] = get_state(conn, "initialized") == "true"
            defaults["admin_configured"] = get_state(conn, "admin_configured") == "true"
            defaults["tmdb_configured"] = get_state(conn, "tmdb_configured") == "true"
            defaults["emu_configured"] = get_state(conn, "emu_configured") == "true"
            defaults["uploadrr_configured"] = get_state(conn, "uploadrr_configured") == "true"
            defaults["jellyfin_configured"] = get_state(conn, "jellyfin_configured") == "true"
            defaults["seerr_configured"] = get_state(conn, "seerr_configured") == "true"
            instances = list_instances(conn)
            defaults["radarr_instances"] = sum(1 for i in instances if i.type == "radarr")
            defaults["sonarr_instances"] = sum(1 for i in instances if i.type == "sonarr")
    except Exception:
        pass
    return defaults


def _next_step(state: dict) -> str | None:
    if not state["admin_configured"]:
        return "admin"
    if not state["uploadrr_configured"]:
        return "uploadrr"
    if not state["tmdb_configured"]:
        return "tmdb"
    if not state["emu_configured"]:
        return "emu"
    if state["radarr_instances"] == 0 and state["sonarr_instances"] == 0:
        return "instances"
    if not state["initialized"]:
        return "complete"
    return None


@router.get("/setup/status", response_model=SetupStatusResponse)
def setup_status() -> SetupStatusResponse:
    state = _read_setup_state()
    return SetupStatusResponse(
        **state,
        next_step=_next_step(state),
    )
