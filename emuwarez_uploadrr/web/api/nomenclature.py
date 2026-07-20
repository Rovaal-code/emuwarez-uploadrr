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
    MkvTitleApplyBody,
    NomenclatureApplyResult,
    NomenclatureExistsResponse,
    NomenclatureFieldsPreviewBody,
    NomenclatureFieldsSaveBody,
    NomenclaturePreviewBody,
    NomenclatureProposalResponse,
    TrackRemuxApplyBody,
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
        provider=p.get("provider_final"),
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
               WHERE library_item_id = ? AND operation_type IN ('nomenclature_rename', 'nomenclature_hardlink')
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


# ---------------------------------------------------------------------------
# Phase 10A — Editable nomenclature fields, source assistant, MKV title
# ---------------------------------------------------------------------------

from ...services.source_assistant import (  # noqa: E402
    list_emu_sources,
    list_emu_providers,
    build_editable_nomenclature_fields,
    update_nomenclature_fields_preview,
    get_tmdb_available_providers,
    PROVIDER_SOURCES,
)
from ...services.mkv_title import (  # noqa: E402
    preview_internal_title_update,
    apply_internal_title_update,
)


@router.get("/nomenclature/sources")
def get_sources(current_user: dict = Depends(require_auth)):
    return {"sources": list_emu_sources()}


@router.get("/nomenclature/providers")
def get_providers(current_user: dict = Depends(require_auth)):
    return {"providers": list_emu_providers()}


@router.get("/library/{item_id}/nomenclature/fields")
def get_nomenclature_fields(item_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        result = build_editable_nomenclature_fields(item_id, conn=conn)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/library/{item_id}/nomenclature/preview-fields")
def preview_nomenclature_fields(
    item_id: int,
    body: NomenclatureFieldsPreviewBody,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        preview = update_nomenclature_fields_preview(item_id, body.fields, conn=conn)
        provider_options = []
        source = body.fields.get("source")
        if source in PROVIDER_SOURCES:
            item_row = conn.execute(
                "SELECT tmdb_id, item_type FROM library_items WHERE id = ?", (item_id,)
            ).fetchone()
            tmdb_codes: list[str] = []
            if item_row and item_row["tmdb_id"]:
                try:
                    tmdb_id = int(str(item_row["tmdb_id"]).split("/")[-1].strip())
                    region_row = conn.execute(
                        "SELECT value FROM settings WHERE key='tmdb_watch_region'"
                    ).fetchone()
                    region = region_row["value"] if region_row else "ES"
                    tmdb_codes = get_tmdb_available_providers(
                        tmdb_id, item_row["item_type"] or "movie", region=region
                    )
                except Exception:
                    pass
            tmdb_set = set(tmdb_codes)
            for p in list_emu_providers():
                provider_options.append({
                    "code": p["code"],
                    "name": p["name"],
                    "label": f"{p['code']} ({p['name']})",
                    "tmdb_available": p["code"] in tmdb_set,
                })
    return {
        "torrent_name": preview.get("torrent_name"),
        "internal_mkv_title": preview.get("internal_mkv_title"),
        "fields": body.fields,
        "provider_options": provider_options,
    }


@router.post("/library/{item_id}/nomenclature/save-fields")
def save_nomenclature_fields(
    item_id: int,
    body: NomenclatureFieldsSaveBody,
    current_user: dict = Depends(require_auth),
):
    """Save editable fields and recalculate proposed_filename."""
    import json as _json
    from datetime import datetime, timezone
    with _get_conn() as conn:
        preview = update_nomenclature_fields_preview(item_id, body.fields, conn=conn)
        torrent_name = preview.get("torrent_name") or ""
        internal_mkv_title = preview.get("internal_mkv_title") or ""
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE nomenclature_proposals SET status='expired', updated_at=? "
            "WHERE library_item_id=? AND status NOT IN ('applied','expired')",
            (now, item_id),
        )
        conn.execute(
            """INSERT INTO nomenclature_proposals
               (library_item_id, status, proposed_filename, proposed_title,
                fields_json, source_final, provider_final,
                internal_mkv_title, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id, "valid", torrent_name,
                body.fields.get("title"),
                _json.dumps(body.fields, ensure_ascii=False),
                body.fields.get("source"),
                body.fields.get("provider"),
                internal_mkv_title,
                now, now,
            ),
        )
        conn.commit()
    return {
        "ok": True,
        "torrent_name": torrent_name,
        "internal_mkv_title": internal_mkv_title,
        "fields": body.fields,
    }


@router.get("/library/{item_id}/mkv-title/preview")
def preview_mkv_title(item_id: int, current_user: dict = Depends(require_auth)):
    with _get_conn() as conn:
        result = preview_internal_title_update(item_id, conn=conn)
    return result


@router.post("/library/{item_id}/mkv-title/apply")
def apply_mkv_title(
    item_id: int,
    body: MkvTitleApplyBody,
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        result = apply_internal_title_update(
            item_id,
            dry_run=body.dry_run,
            apply=body.apply,
            confirmation=body.confirmation,
            conn=conn,
        )
    return result


@router.get("/library/{item_id}/track-remux/preview")
def preview_track_remux(item_id: int, current_user: dict = Depends(require_auth)):
    from ...services.mkv_remux import build_remux_plan
    with _get_conn() as conn:
        result = build_remux_plan(item_id, conn=conn)
    return result


@router.post("/library/{item_id}/track-remux/apply")
def apply_track_remux(
    item_id: int,
    body: TrackRemuxApplyBody,
    current_user: dict = Depends(require_auth),
):
    from ...services.mkv_remux import apply_remux
    overrides = None
    if body.overrides:
        overrides = {}
        for raw_id, ov in body.overrides.items():
            try:
                overrides[int(raw_id)] = {"new_name": ov.new_name, "default_after": ov.default_after}
            except (TypeError, ValueError):
                continue
    with _get_conn() as conn:
        result = apply_remux(
            item_id,
            dry_run=body.dry_run,
            apply=body.apply,
            confirmation=body.confirmation,
            overrides=overrides,
            conn=conn,
        )
    return result
