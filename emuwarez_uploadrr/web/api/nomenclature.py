"""API endpoints for nomenclature proposals (Phases 6A + 6B)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ...database import connect, init_db
from ...services.nomenclature import (
    apply_nomenclature_proposal,
    build_nomenclature_proposal,
    get_latest_nomenclature_proposal,
)
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    AdaptNomenclatureBody,
    NomenclatureApplyResult,
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


@router.post("/library/{item_id}/adapt-nomenclature", response_model=NomenclatureApplyResult)
def adapt_nomenclature(
    item_id: int,
    body: AdaptNomenclatureBody,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        result = apply_nomenclature_proposal(
            item_id,
            proposal_id=body.proposal_id,
            dry_run=body.dry_run,
            apply=body.apply,
            confirmation=body.confirmation,
            overwrite=body.overwrite,
            conn=conn,
        )

    proposal = result.get("proposal")
    proposal_resp = _proposal_to_response(proposal) if proposal else None

    return NomenclatureApplyResult(
        dry_run=result.get("dry_run", True),
        apply=result.get("apply", False),
        status=result.get("status", "blocked"),
        source_path=result.get("source_path"),
        destination_path=result.get("destination_path"),
        operation_id=result.get("operation_id"),
        proposal=proposal_resp,
        warnings=result.get("warnings", []),
        errors=result.get("errors", []),
        message=result.get("message"),
    )


@router.get("/library/{item_id}/nomenclature/operations")
def get_nomenclature_operations(item_id: int, current_user: dict = Depends(require_auth)):
    """Return filesystem operation history for a library item."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM filesystem_operations
               WHERE library_item_id = ? AND operation_type = 'nomenclature_hardlink'
               ORDER BY created_at DESC LIMIT 20""",
            (item_id,),
        ).fetchall()
    ops = []
    for r in rows:
        d = dict(r)
        warnings: list[str] = []
        errors: list[str] = []
        try:
            warnings = json.loads(d.get("warnings_json") or "[]")
        except Exception:
            pass
        try:
            errors = json.loads(d.get("errors_json") or "[]")
        except Exception:
            pass
        ops.append(
            {
                "id": d.get("id"),
                "operation_type": d.get("operation_type"),
                "status": d.get("status"),
                "library_item_id": d.get("library_item_id"),
                "proposal_id": d.get("proposal_id"),
                "source_path": d.get("source_path"),
                "destination_path": d.get("destination_path"),
                "base_path": d.get("base_path"),
                "dry_run": bool(d.get("dry_run", 1)),
                "warnings": warnings,
                "errors": errors,
                "created_at": d.get("created_at"),
                "applied_at": d.get("applied_at"),
            }
        )
    return ops
