"""API endpoints for the editable nomenclature fields, MKV title and track remux (Phase 10A)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import connect, init_db
from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import (
    MkvTitleApplyBody,
    NomenclatureFieldsPreviewBody,
    NomenclatureFieldsSaveBody,
    TrackRemuxApplyBody,
)

router = APIRouter(tags=["nomenclature"])


def _get_conn():
    conn = connect(_db_path())
    init_db(conn)
    return conn


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
def get_nomenclature_fields(
    item_id: int,
    # {"2": "spa"}: el idioma elegido en Ver Pistas para la pista de audio 2.
    idiomas: str | None = Query(None),
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        result = build_editable_nomenclature_fields(item_id, conn=conn, idiomas_audio=_idiomas_audio(idiomas))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


def _idiomas_audio(crudo: str | None) -> dict[int, str] | None:
    """{posición: código} del parámetro `idiomas`; lo que no sea una opción se ignora."""
    from ...services.mkv_remux import IDIOMAS_ELEGIBLES
    try:
        datos = json.loads(crudo) if crudo else {}
        return {int(k): v for k, v in datos.items() if v in IDIOMAS_ELEGIBLES} or None
    except (ValueError, TypeError, AttributeError):
        return None


@router.post("/library/{item_id}/nomenclature/preview-fields")
def preview_nomenclature_fields(
    item_id: int,
    body: NomenclatureFieldsPreviewBody,
    # El asistente de subida no usa los proveedores y llama en cada edición:
    # con false se salta la consulta a TMDb.
    con_proveedores: bool = Query(True, alias="provider_options"),
    current_user: dict = Depends(require_auth),
):
    with _get_conn() as conn:
        preview = update_nomenclature_fields_preview(item_id, body.fields, conn=conn)
        provider_options = []
        source = body.fields.get("source")
        if con_proveedores and source in PROVIDER_SOURCES:
            from ...services.nomenclature import item_tmdb_reference
            item_tmdb_id, item_tipo = item_tmdb_reference(item_id, conn=conn)
            tmdb_codes: list[str] = []
            if item_tmdb_id:
                try:
                    tmdb_id = int(str(item_tmdb_id).split("/")[-1].strip())
                    from ...services.settings import get_setting_canonical
                    region = get_setting_canonical(conn, "tmdb_watch_region") or "ES"
                    tmdb_codes = get_tmdb_available_providers(
                        tmdb_id, item_tipo or "movie", region=region
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
    from ...services.nomenclature import save_manual_nomenclature_fields
    with _get_conn() as conn:
        preview = update_nomenclature_fields_preview(item_id, body.fields, conn=conn)
        save_manual_nomenclature_fields(item_id, body.fields, preview, conn=conn)
    torrent_name = preview.get("torrent_name") or ""
    internal_mkv_title = preview.get("internal_mkv_title") or ""
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
                overrides[int(raw_id)] = {"new_name": ov.new_name, "default_after": ov.default_after,
                                          "language": ov.language}
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
