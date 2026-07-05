"""API endpoints for season-pack preview/apply (Phase 6 of the
Series/Season/Episode hierarchy batch) — one release for a whole
Temporada, mirroring the single-item nomenclature preview/apply endpoints
in web/api/nomenclature.py but scoped to a season_id."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...database import connect, init_db
from ...services.season_pack import apply_season_pack, build_season_pack_plan
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    AdaptSeasonPackBody,
    SeasonPackApplyResult,
    SeasonPackPlanResponse,
)

router = APIRouter(tags=["season-pack"])


def _get_conn():
    conn = connect(_db_path())
    init_db(conn)
    return conn


@router.get("/library/season/{season_id}/pack-preview", response_model=SeasonPackPlanResponse)
def preview_season_pack(season_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        plan = build_season_pack_plan(season_id, conn=conn)
    if plan["status"] == "blocked" and plan["errors"] == ["Temporada no encontrada."]:
        raise HTTPException(status_code=404, detail="Temporada no encontrada.")
    return SeasonPackPlanResponse(**plan)


@router.post("/library/season/{season_id}/adapt-pack", response_model=SeasonPackApplyResult)
def adapt_season_pack(
    season_id: int,
    body: AdaptSeasonPackBody,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        result = apply_season_pack(
            season_id,
            dry_run=body.dry_run,
            apply=body.apply,
            confirmation=body.confirmation,
            conn=conn,
        )
    return SeasonPackApplyResult(**result)
