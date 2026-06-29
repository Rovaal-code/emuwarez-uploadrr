"""API endpoints for nomenclature proposals (Phase 6A)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ...database import connect, init_db
from ...services.nomenclature import (
    build_nomenclature_proposal,
    get_latest_nomenclature_proposal,
)
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    AdaptNomenclatureBody,
    NomenclatureExistsResponse,
    NomenclaturePreviewBody,
    NomenclatureProposalResponse,
)

router = APIRouter(tags=["nomenclature"])


def _get_conn():
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _proposal_to_response(p: dict) -> NomenclatureProposalResponse:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        w = p.get("warnings_json")
        warnings = json.loads(w) if w else []
    except Exception:
        pass
    try:
        e = p.get("errors_json")
        errors = json.loads(e) if e else []
    except Exception:
        pass
    return NomenclatureProposalResponse(
        id=p.get("id"),
        library_item_id=p["library_item_id"],
        status=p.get("status", "draft"),
        current_name=p.get("current_name"),
        current_path=p.get("current_path"),
        proposed_title=p.get("proposed_title"),
        proposed_filename=p.get("proposed_filename"),
        proposed_folder=p.get("proposed_folder"),
        proposed_path=p.get("proposed_path"),
        media_type=p.get("media_type"),
        tmdb_id=p.get("tmdb_id"),
        imdb_id=p.get("imdb_id"),
        resolution=p.get("resolution"),
        source=p.get("source"),
        video_codec=p.get("video_codec"),
        audio_summary=p.get("audio_summary"),
        subtitle_summary=p.get("subtitle_summary"),
        release_tag=p.get("release_tag"),
        warnings=warnings,
        errors=errors,
        created_at=p.get("created_at"),
        updated_at=p.get("updated_at"),
    )


@router.get("/library/{item_id}/nomenclature", response_model=NomenclatureExistsResponse)
def get_nomenclature(item_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        proposal = get_latest_nomenclature_proposal(item_id, conn=conn)
    if not proposal:
        return NomenclatureExistsResponse(
            exists=False,
            message="No hay propuesta de nomenclatura generada todavía.",
        )
    return NomenclatureExistsResponse(
        exists=True,
        proposal=_proposal_to_response(proposal),
    )


@router.post("/library/{item_id}/nomenclature/preview", response_model=NomenclatureProposalResponse)
def preview_nomenclature(
    item_id: int,
    body: NomenclaturePreviewBody,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        proposal = build_nomenclature_proposal(item_id, force_refresh=body.force_refresh, conn=conn)
    if not proposal.get("library_item_id"):
        raise HTTPException(status_code=404, detail="Item no encontrado.")
    return _proposal_to_response(proposal)


@router.post("/library/{item_id}/adapt-nomenclature")
def adapt_nomenclature(
    item_id: int,
    body: AdaptNomenclatureBody,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        proposal = get_latest_nomenclature_proposal(item_id, conn=conn)

    if body.apply and not body.dry_run:
        return {
            "implemented": False,
            "stub": True,
            "blocked": True,
            "message": (
                "La aplicación real de nomenclatura queda pendiente de una fase posterior. "
                "Esta fase solo genera previsualizaciones seguras."
            ),
            "proposal": _proposal_to_response(proposal) if proposal else None,
        }

    if not proposal:
        with _get_conn() as conn:
            proposal = build_nomenclature_proposal(item_id, force_refresh=False, conn=conn)

    return {
        "dry_run": True,
        "applied": False,
        "message": "Modo previsualización. No se ha modificado ningún archivo.",
        "proposal": _proposal_to_response(proposal) if proposal else None,
    }
