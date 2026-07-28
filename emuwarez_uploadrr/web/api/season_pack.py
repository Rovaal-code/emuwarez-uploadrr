"""API endpoints for season-pack planning + per-episode views — one release
for a whole Temporada, mirroring the single-item nomenclature/mediainfo/
track-remux endpoints in web/api/nomenclature.py but scoped to a season_id.

Applying/uploading a season is NOT triggered here — that's the same
POST /library/{item_id}/upload/queue endpoint a single file uses
(web/api/uploads.py), pointed at the season's own library_items id;
services/upload_queue.py's season branch drives services/season_pack.py's
apply_season_pack() internally after the grace period."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...database import connect, init_db
from ...services.season_pack import (
    build_season_pack_plan,
    get_season_episode_mediainfo,
    get_season_episode_names,
    get_season_episode_remux_previews,
    get_season_plan_progress,
    preview_season_pack_title,
)
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import SeasonPackFieldsPreviewBody, SeasonPackPlanResponse

router = APIRouter(tags=["season-pack"])


def _get_conn():
    conn = connect(_db_path())
    init_db(conn)
    return conn


@router.get("/library/season/{season_id}/pack-preview", response_model=SeasonPackPlanResponse)
def preview_season_pack(season_id: int, current_user: dict = Depends(require_auth)):
    """Can take a while for a big season (real work per episode) — poll
    GET .../pack-preview/progress concurrently for a live "N de M" counter."""
    with _get_conn() as conn:
        plan = build_season_pack_plan(season_id, conn=conn)
    if plan["status"] == "blocked" and plan["errors"] == ["Temporada no encontrada."]:
        raise HTTPException(status_code=404, detail="Temporada no encontrada.")
    return SeasonPackPlanResponse(**plan)


@router.post("/library/season/{season_id}/pack-preview-fields")
def preview_season_pack_fields(
    season_id: int, body: SeasonPackFieldsPreviewBody, current_user: dict = Depends(require_auth),
) -> dict:
    """Cheap live preview of the season pack title while editing Source/
    Proveedor/Tag in the wizard (season_id unused — every value needed is
    already in the request body, no DB/disk work at all; kept in the URL
    only for consistency with the rest of this file's per-season routes)."""
    return preview_season_pack_title(body.model_dump())


@router.get("/library/season/{season_id}/pack-preview/progress")
def preview_season_pack_progress(season_id: int, current_user: dict = Depends(require_auth)) -> dict:
    """Live progress of a pack-preview build in flight for this season —
    {done, total, current_title}. Meant to be polled while the GET above is
    running; returns the empty/initial shape if none is running."""
    return get_season_plan_progress(season_id)


@router.get("/library/season/{season_id}/episode-names")
def season_episode_names(season_id: int, current_user: dict = Depends(require_auth)) -> dict:
    """Per-episode final torrent name + internal MKV title — backs "Ver
    nombre de todos los capítulos" (a season pack has no single "título del
    archivo interno", each episode file has its own)."""
    with _get_conn() as conn:
        return get_season_episode_names(season_id, conn=conn)


@router.get("/library/season/{season_id}/episode-mediainfo")
def season_episode_mediainfo(season_id: int, current_user: dict = Depends(require_auth)) -> dict:
    """Per-episode MediaInfo report — backs "Ver MediaInfo" for a season target."""
    with _get_conn() as conn:
        return get_season_episode_mediainfo(season_id, conn=conn)


@router.get("/library/season/{season_id}/episode-remux-preview")
def season_episode_remux_preview(season_id: int, current_user: dict = Depends(require_auth)) -> dict:
    """Per-episode track remux plan — backs "Ver Remux" for a season target
    (read-only preview; no manual per-track overrides for season packs)."""
    with _get_conn() as conn:
        return get_season_episode_remux_previews(season_id, conn=conn)
