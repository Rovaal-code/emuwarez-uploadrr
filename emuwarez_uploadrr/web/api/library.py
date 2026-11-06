"""Real library, missing, and sync endpoints (Phase 4)."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...integrations.base import texto_de_error
from ..dependencies import require_auth
from ..runtime import _db_path
from emuwarez_uploadrr.services.nomenclature import infer_provider_from_item
from emuwarez_uploadrr.services.library import content_display_title, episode_own_name



from ..schemas import (
    LibraryItemResponse, LibraryListResponse,
    MissingItemResponse, MissingListResponse, PeticionDeLaFichaResponse,
    SyncRequest, SyncResponse,
)
from ...services.library import (  # agregación y filtros, movidos aquí
    _nomenclature_rollup, _local_status_rollup, _size_rollup,
    _rollup_path, _child_quality_rollup, _batch_rollups,
    _ROLLUP_EMPTY, _provider_label,
)

router = APIRouter(tags=["library"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _ignore_specials(conn) -> bool:
    """User setting: exclude specials (season 0) from a Series' availability /
    nomenclature / eMuwarez rollups. Default True (specials rarely matter and
    are rarely on the tracker); only an explicit "false" turns it off."""
    if conn is None:
        return True
    from ...services.settings import leer_ajuste
    return leer_ajuste(conn, "series_ignore_specials")
















# ---------------------------------------------------------------------------
# Batched rollups for library_list() — the single-id helpers above are still
# used as-is for the single-item lookup (GET /api/library/{id}, one row, no
# N+1 concern), but calling them once PER season/series row in a list of many
# was the real cost behind a slow /api/library: ~5 extra queries per row, so
# a page with a few hundred series meant a few hundred round trips. These
# fetch every relevant episode row for ALL ids in the page in a couple of
# queries total, then do the exact same aggregation in Python, keyed by id.
# ---------------------------------------------------------------------------













def _to_lib_response(row: dict, conn=None, rollups: Optional[dict] = None) -> LibraryItemResponse:
    return LibraryItemResponse(**_campos_de_fila(row, conn, rollups))


# Lo que enseña la fila, sin montar el modelo: los filtros por columna lo miran
# en la biblioteca entera y solo se monta lo que se devuelve.
def _campos_de_fila(row: dict, conn=None, rollups: Optional[dict] = None) -> dict:
    file_exists_raw = row.get("file_exists")
    nomenclature_status = row["nomenclature_status"]
    local_status = row["local_status"]
    size_bytes = row.get("size_bytes")
    provider = infer_provider_from_item(row)
    resolution = row.get("resolution")
    source = row.get("source")
    release_group = row.get("release_group")
    path = row.get("path")
    prepared_path = row.get("prepared_path")
    video_codec = row.get("video_codec")
    audio_codec = row.get("audio_codec")
    audio_languages = row.get("audio_languages")
    subtitle_languages = row.get("subtitle_languages")
    release_groups = None
    if row["item_type"] in ("season", "series"):
        if rollups is not None:
            # library_list() already batched every season/series' rollup in
            # a couple of queries total — reuse it instead of hitting the DB
            # again for this one row (this dict simply won't have an entry
            # for an id with no episodes at all, same as the live helpers
            # below returning None/empty for it).
            precomputed = rollups.get(row["id"], {})
        else:
            ignore_specials = _ignore_specials(conn)
            precomputed = {
                "nomenclature": _nomenclature_rollup(conn, row["id"], row["item_type"], ignore_specials),
                "size": _size_rollup(conn, row["id"], row["item_type"], ignore_specials),
                # Availability now rolls up from real episodes (Sonarr's own
                # status reports 'Disponible' even with missing episodes).
                "local_status": _local_status_rollup(conn, row["id"], row["item_type"], ignore_specials),
                "quality": _child_quality_rollup(conn, row["id"], row["item_type"], ignore_specials),
                "path": _rollup_path(conn, row["id"], row["item_type"], ignore_specials) if not path else None,
            }
        rollup = precomputed.get("nomenclature")
        if rollup is not None:
            nomenclature_status = rollup
        rolled_size = precomputed.get("size")
        if rolled_size is not None:
            size_bytes = rolled_size
        loc = precomputed.get("local_status")
        if loc is not None:
            local_status = loc
        # Provider/quality/codecs/audio/subs: show the value shared by every
        # episode (else blank), so a uniform season/series reflects it.
        rq = precomputed.get("quality") or dict(_ROLLUP_EMPTY)
        provider = provider or rq["provider"]
        resolution = resolution or rq["resolution"]
        source = source or rq["source"]
        release_group = release_group or rq["release_group"]
        # Los de todos los capítulos (la columna de arriba solo se rellena si coinciden todos).
        release_groups = rq.get("release_groups") or None
        video_codec = rq["video_codec"]
        audio_codec = rq["audio_codec"]
        audio_languages = rq["audio_languages"]
        subtitle_languages = rq["subtitle_languages"]
        # A season/series rollup has no file of its own — show its folder path
        # derived from the episodes (e.g. '…/Attack on Titan/Season 2').
        if not path:
            path = precomputed.get("path")
    # Only computed for the single-item detail response (rollups is None) —
    # a per-row parent-walk query for every list row would be wasteful there.
    display_title = None
    if rollups is None and conn is not None:
        display_title = content_display_title(conn, row)
        if row["item_type"] == "episode":
            own_name = episode_own_name(row)
            if own_name:
                display_title = f"{display_title} - {own_name}"
    return dict(
        id=row["id"],
        item_type=row["item_type"],
        title=row["title"],
        display_title=display_title,
        year=row.get("year"),
        original_title=row.get("original_title"),
        instance_type=row.get("instance_type"),
        instance_name=row.get("instance_name"),
        instance_id=row.get("instance_id"),
        external_id=row.get("external_id"),
        tmdb_id=row.get("tmdb_id"),
        imdb_id=row.get("imdb_id"),
        tvdb_id=row.get("tvdb_id"),
        tvmaze_id=row.get("tvmaze_id"),
        mal_id=row.get("mal_id"),
        title_slug=row.get("title_slug"),
        season_number=row.get("season_number"),
        episode_number=row.get("episode_number"),
        parent_id=row.get("parent_id"),
        path=path,
        prepared_path=prepared_path,
        quality=row.get("quality"),
        resolution=resolution,
        source=source,
        release_group=release_group,
        release_groups=release_groups,
        provider=provider,
        provider_label=_provider_label(provider),
        video_codec=video_codec,
        audio_codec=audio_codec,
        audio_languages=audio_languages,
        subtitle_languages=subtitle_languages,
        # Already rolled up and stored per row (recompute_spanish_flags), so
        # unlike the audio_languages above they need no per-row rollup here.
        has_spanish_audio=row.get("has_spanish_audio"),
        has_spanish_subs=row.get("has_spanish_subs"),
        has_spanish_ok=row.get("has_spanish_ok"),
        size_bytes=size_bytes,
        local_status=local_status,
        request_status=row["request_status"],
        nomenclature_status=nomenclature_status,
        updated_at=row.get("updated_at"),
        file_exists=bool(file_exists_raw) if file_exists_raw is not None else None,
        file_verified_at=row.get("file_verified_at"),
        diagnostic_status=row.get("diagnostic_status"),
        diagnostic_summary=row.get("diagnostic_summary"),
        recommended_action=row.get("recommended_action"),
        arr_queue_status=row.get("arr_queue_status"),
        arr_history_status=row.get("arr_history_status"),
        poster_url=row.get("poster_url"),
        backdrop_url=row.get("backdrop_url"),
        emu_in_catalog=row.get("emu_in_catalog"),
        emu_aportes=_parse_aportes(row.get("emu_aportes")),
    )


def _parse_aportes(raw) -> Optional[list]:
    if not raw:
        return None
    import json as _json
    try:
        return _json.loads(raw)
    except (ValueError, TypeError):
        return None


def _to_missing_response(row: dict) -> MissingItemResponse:
    file_exists_raw = row.get("file_exists")
    import json as _json
    try:
        rec_reasons = _json.loads(row.get("recommendation_reasons_json") or "[]")
    except Exception:
        rec_reasons = []
    return MissingItemResponse(
        id=row["id"],
        item_type=row["item_type"],
        title=row["title"],
        year=row.get("year"),
        instance_type=row.get("instance_type"),
        instance_name=row.get("instance_name"),
        tmdb_id=row.get("tmdb_id"),
        imdb_id=row.get("imdb_id"),
        local_status=row["local_status"],
        request_status=row["request_status"],
        updated_at=row.get("updated_at"),
        arr_queue_status=row.get("arr_queue_status"),
        arr_queue_progress=row.get("arr_queue_progress"),
        arr_queue_timeleft=row.get("arr_queue_timeleft"),
        arr_queue_error=row.get("arr_queue_error"),
        arr_history_error=row.get("arr_history_error"),
        file_exists=bool(file_exists_raw) if file_exists_raw is not None else None,
        diagnostic_status=row.get("diagnostic_status"),
        recommended_action=row.get("recommended_action"),
        recommendation_reasons=rec_reasons,
    )


# ---------------------------------------------------------------------------
# POST /api/sync — sync all instances
# ---------------------------------------------------------------------------

@router.post("/library/sync-start")
def library_sync_start(
    body: Optional[SyncRequest] = None,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Start the Radarr/Sonarr library sync in the background (poll
    /library/sync-progress for the live element count)."""
    from emuwarez_uploadrr.services.library import start_library_sync_background
    include_episodes = body.include_episodes if body else True
    return start_library_sync_background(include_episodes=include_episodes)


@router.get("/library/sync-progress")
def library_sync_progress(current_user: dict = Depends(require_auth)) -> dict:
    """Live progress of the Radarr/Sonarr library sync, for the process card."""
    from emuwarez_uploadrr.services.library import get_lib_sync_progress
    return get_lib_sync_progress()


@router.post("/sync", response_model=SyncResponse)
def sync_all(
    body: Optional[SyncRequest] = None,
    current_user: dict = Depends(require_auth),
) -> SyncResponse:
    from emuwarez_uploadrr.services.library import SyncAlreadyRunning, _lib_sync_guard
    from emuwarez_uploadrr.services.library import sync_all as _sync_all
    include_episodes = body.include_episodes if body else True
    with _get_conn() as conn:
        try:
            with _lib_sync_guard():
                result = _sync_all(conn, include_episodes=include_episodes)
        except SyncAlreadyRunning:
            raise HTTPException(status_code=429, detail="Ya hay una sincronización de biblioteca en marcha")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error en sync: {texto_de_error(exc)}")
    return SyncResponse(
        imported=result.get("imported", 0),
        missing=result.get("missing", 0),
        instances=result.get("instances", 0),
        errors=result.get("errors", []),
        message=(
            f"Sincronizadas {result.get('instances', 0)} instancias: "
            f"{result.get('imported', 0)} elementos, {result.get('missing', 0)} no disponibles"
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/library
# ---------------------------------------------------------------------------

@router.get("/library", response_model=LibraryListResponse)
def library_list(
    current_user: dict = Depends(require_auth),
    # Los filtros de columna se repiten para elegir varios valores (?type=movie&type=series).
    item_type: Optional[list[str]] = Query(None, alias="type"),
    origin: Optional[list[str]] = Query(None),
    instance_id: Optional[list[int]] = Query(None),
    parent_id: Optional[int] = Query(None),
    status: Optional[list[str]] = Query(None),
    request_status: Optional[list[str]] = Query(None, alias="request_status"),
    nomenclature: Optional[list[str]] = Query(None),
    search: Optional[str] = Query(None),
    # Los cinco estados de la columna Español: uno desconocido es un 422, no
    # un filtro que en silencio no devuelve nada.
    spanish: Optional[list[Literal["ambos", "audio", "subs", "no", "desconocido"]]] = Query(None),
    # Filtran por lo que enseña la columna (en series y temporadas, lo que
    # comparten sus capítulos), así que van después de montar las filas.
    provider: Optional[list[str]] = Query(None),
    resolution: Optional[list[str]] = Query(None),
    source: Optional[list[str]] = Query(None),
    release_group: Optional[list[str]] = Query(None),
    emu: Optional[list[Literal["candidate", "present"]]] = Query(None),
    aporte: Optional[Literal["yes", "no"]] = Query(None),
    sort: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=20000),
    offset: int = Query(0, ge=0),
) -> LibraryListResponse:
    from emuwarez_uploadrr.services.library import (
        list_library, list_library_agrupada, count_library, contar_archivos,
        filtrar_por_lo_que_se_ve, subir_a_su_serie, _valores)
    por_lo_que_se_ve = dict(provider=provider, resolution=resolution, source=source,
                            release_group=release_group, emu=emu, aporte=aporte)
    filtra_lo_que_se_ve = any(por_lo_que_se_ve.values())
    # Filtrando en plano, lo que cumple sale agrupado bajo su serie. Con un Tipo
    # elegido sale ese tipo tal cual, y sin filtros, en plano sigue saliendo todo.
    agrupa = parent_id is None and not _valores(item_type) and any(_valores(v) for v in (
        origin, instance_id, status, request_status, nomenclature, search, spanish,
        *por_lo_que_se_ve.values()))
    recorta_despues = filtra_lo_que_se_ve or agrupa
    with _get_conn() as conn:
        ignora_especiales = _ignore_specials(conn)

        def rollups_de(filas: list[dict], ya: Optional[dict] = None) -> dict:
            ya = ya or {}
            series_ids = [r["id"] for r in filas if r["item_type"] == "series" and r["id"] not in ya]
            season_ids = [r["id"] for r in filas if r["item_type"] == "season" and r["id"] not in ya]
            return {**ya, **(_batch_rollups(conn, series_ids, season_ids, ignora_especiales)
                             if (series_ids or season_ids) else {})}

        filtros_sql = dict(
            status=status, nomenclature=nomenclature, origin=origin, instance_id=instance_id, search=search,
            spanish=spanish)
        archivos = contar_archivos(conn)
        if agrupa and not filtra_lo_que_se_ve:
            # Todo en SQL: solo se leen y se montan las filas de la página.
            rows, total = list_library_agrupada(
                conn, request=request_status, sort=sort, limit=limit, offset=offset,
                ignore_specials=ignora_especiales, **filtros_sql)
            rollups = rollups_de(rows)
            items = [_to_lib_response(r, conn, rollups) for r in rows]
        else:
            rows = list_library(
                conn,
                request=request_status,
                item_type=item_type,
                parent_id=parent_id,
                sort=sort,
                # Sin tope (LIMIT -1): el recorte va después de filtrar.
                limit=-1 if recorta_despues else limit,
                offset=0 if recorta_despues else offset,
                ignore_specials=ignora_especiales,
                provider=provider, resolution=resolution, source=source, release_group=release_group, emu=emu,
                **filtros_sql,
            )
            # Recortando después, el total sale de contar lo que queda.
            total = 0 if recorta_despues else count_library(
                conn, request=request_status, item_type=item_type, parent_id=parent_id, **filtros_sql)
            rollups = {}
            if filtra_lo_que_se_ve:
                rollups = rollups_de(rows)
                filas = filtrar_por_lo_que_se_ve(
                    [_campos_de_fila(r, conn, rollups) for r in rows], **por_lo_que_se_ve)
            if agrupa:
                # Solo se montan las series y películas que salen en la página.
                rows, total = subir_a_su_serie(
                    conn, filas if filtra_lo_que_se_ve else rows, sort=sort, ignore_specials=ignora_especiales,
                    limit=limit, offset=offset)
                rollups = rollups_de(rows, rollups)
                items = [_to_lib_response(r, conn, rollups) for r in rows]
            elif filtra_lo_que_se_ve:
                total = len(filas)
                items = [LibraryItemResponse(**f) for f in filas[offset:offset + limit]]
            else:
                rollups = rollups_de(rows)
                items = [_to_lib_response(r, conn, rollups) for r in rows]
        # La petición de la serie o temporada que cubre una fila sin la suya: una consulta para la página.
        from emuwarez_uploadrr.services.requests import peticiones_heredadas
        heredadas = peticiones_heredadas(conn, [it.id for it in items if it.item_type in ("season", "episode")])
        for it in items:
            it.peticion_heredada = heredadas.get(it.id)
    return LibraryListResponse(
        items=items,
        total=total,
        archivos=archivos,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/library/{item_id}
# ---------------------------------------------------------------------------

@router.get("/library/filter-options")
def library_filter_options(current_user: dict = Depends(require_auth)) -> dict:
    """Valores presentes en la biblioteca para los filtros de columna."""
    from ...services.library import valores_de_filtro
    with _get_conn() as conn:
        return valores_de_filtro(conn)


@router.get("/library/emu-sync-status")
def library_emu_sync_status(current_user: dict = Depends(require_auth)) -> dict:
    """Throttle status for the eMuwarez catalog comparison (1/hour)."""
    from emuwarez_uploadrr.services.emu_catalog import get_sync_status
    with _get_conn() as conn:
        return get_sync_status(conn)


@router.post("/library/emu-sync")
def library_emu_sync(mode: str = "incremental", current_user: dict = Depends(require_auth)) -> dict:
    """Start the eMuwarez catalog sync in the background (poll emu-sync-progress
    for the live status). Throttled 1/hour. mode="incremental" (only new
    torrents) or "full" (re-download the whole catalog and reconcile deletions)."""
    from emuwarez_uploadrr.services.emu_catalog import start_emu_sync_background
    mode = "full" if mode == "full" else "incremental"
    result = start_emu_sync_background(mode=mode)
    if result.get("status") == "throttled":
        raise HTTPException(
            status_code=429,
            detail=f"Espera {result['wait_seconds']}s antes de volver a sincronizar con eMuwarez",
        )
    return result


@router.get("/library/emu-sync-progress")
def library_emu_sync_progress(current_user: dict = Depends(require_auth)) -> dict:
    """Live progress of the eMuwarez catalog sync, for the process card."""
    from emuwarez_uploadrr.services.emu_catalog import get_sync_progress
    return get_sync_progress()


@router.get("/library/{item_id}/emu-comparison")
def library_emu_comparison(item_id: int, resolution: Optional[str] = None, source: Optional[str] = None,
                           current_user: dict = Depends(require_auth)) -> dict:
    """Your copy vs eMuwarez's matching torrents, for the detail-card table. `resolution` y `source`
    sustituyen a los de tu copia (lo que el asistente de subida va a poner en el nombre)."""
    from emuwarez_uploadrr.services.emu_catalog import get_item_comparison
    with _get_conn() as conn:
        return get_item_comparison(conn, item_id, resolution=resolution, source=source)


@router.get("/library/{item_id}", response_model=LibraryItemResponse)
def library_detail(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> LibraryItemResponse:
    from emuwarez_uploadrr.services.library import get_library_item
    with _get_conn() as conn:
        row = get_library_item(conn, item_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        from emuwarez_uploadrr.services.library import rollup_all_values
        response = _to_lib_response(row, conn)
        # Solo en la ficha: la lista no lo necesita y son una consulta por fila.
        todos = rollup_all_values(conn, row) or {}
        # Los proveedores salen como lista de códigos; la etiqueta legible
        # ("Amazon (AMZN)") la construye este módulo, no el servicio.
        codigos = todos.pop("provider_codes", None)
        if codigos:
            response.providers_all = [{"code": c, "label": _provider_label(c)} for c in codigos]
        response.rollup_all = todos or None
        # Quién la pidió y el enlace: también solo en la ficha.
        from emuwarez_uploadrr.services.requests import peticiones_de_la_ficha
        peticiones = peticiones_de_la_ficha(conn, row)
        if peticiones["peticion"]:
            response.peticion = PeticionDeLaFichaResponse(**peticiones["peticion"])
        response.peticiones_debajo = [
            PeticionDeLaFichaResponse(**p) for p in peticiones["peticiones_debajo"]] or None
        return response


@router.get("/library/{item_id}/mediainfo")
def library_mediainfo(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Run MediaInfo on demand for a single item and return, per field, the raw
    MediaInfo value and the value that would go to eMuwarez."""
    from emuwarez_uploadrr.services.library import get_library_item
    from emuwarez_uploadrr.services.media_info_service import build_mediainfo_report

    with _get_conn() as conn:
        row = get_library_item(conn, item_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        path = row["path"] if "path" in row.keys() else None
        radarr_source = row["source"] if "source" in row.keys() else None
    return build_mediainfo_report(path, radarr_source=radarr_source)


@router.get("/library/{item_id}/suggest-provider")
def library_suggest_provider(
    item_id: int,
    current_user: dict = Depends(require_auth),
) -> dict:
    """Suggest the EMU provider for a WEB-DL item via TMDb watch providers +
    the configured priority. This is the on-demand call the upload wizard makes
    when Source=WEB-DL and no provider was detected from the filename.

    Returns {suggested, tmdb_providers, reason}. Never raises on TMDb issues —
    a missing/invalid TMDb key just yields suggested=None."""
    from emuwarez_uploadrr.services.library import get_library_item
    from emuwarez_uploadrr.services.source_assistant import suggest_provider_for_item

    with _get_conn() as conn:
        row = get_library_item(conn, item_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Item {item_id} no encontrado")
        return suggest_provider_for_item(item_id, conn=conn)


# ---------------------------------------------------------------------------
# GET /api/missing
# ---------------------------------------------------------------------------

@router.get("/missing", response_model=MissingListResponse)
def missing_list(
    current_user: dict = Depends(require_auth),
    limit: int = Query(50, ge=1, le=20000),
    offset: int = Query(0, ge=0),
) -> MissingListResponse:
    from emuwarez_uploadrr.services.library import count_missing, list_missing
    with _get_conn() as conn:
        rows = list_missing(conn, limit=limit, offset=offset)
        total = count_missing(conn)
    return MissingListResponse(
        items=[_to_missing_response(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
