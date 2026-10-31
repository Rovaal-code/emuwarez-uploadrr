"""Nomenclature proposal service.

SAFETY CONTRACT: This module never modifies the filesystem.
It only reads library_items from the database and generates proposals.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from ..database import connect, row_to_dict, get_state
from .filesystem_safety import safe_stat
from .source_assistant import EMU_PROVIDERS, PROVIDER_SOURCES

logger = logging.getLogger("emuwarez.nomenclature")

STATUS_DRAFT = "draft"
STATUS_VALID = "valid"
STATUS_WARNING = "warning"
STATUS_BLOCKED = "blocked"
STATUS_APPLIED = "applied"   # reserved for future phase
STATUS_EXPIRED = "expired"


def get_library_item_for_nomenclature(item_id: int, conn=None) -> dict | None:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        return row_to_dict(row)
    finally:
        if own:
            conn.close()


def _normalize_title_for_emu(title: str) -> str:
    if not title:
        return ""
    normalized = unicodedata.normalize("NFC", title)
    # «:» y «?» se quedan: eMuwarez los conserva en el título («Anacleto: Agente secreto»).
    # El nombre de archivo los quita en to_filesystem_name.
    cleaned = re.sub(r'[<>"/\\|*]', "", normalized)
    return cleaned.strip()


def _build_proposed_filename(
    title: str,
    year: int | None,
    resolution: str | None,
    source: str | None,
    video_codec: str | None,
    audio_summary: str | None,
    subtitle_summary: str | None,
    release_tag: str | None,
    media_type: str,
    season: int | None = None,
    episode: int | None = None,
    provider: str | None = None,
    dynamic_range: str | None = None,
) -> str:
    from .emu_format import format_resolution, format_hdr
    from .source_assistant import _build_source_string

    parts = [_normalize_title_for_emu(title)]
    # SxxExx comes right after the title, BEFORE the year — matches
    # source_assistant.py's update_nomenclature_fields_preview() (the
    # wizard's own live preview), which the two must stay in sync with.
    if media_type in ("tv", "series", "anime", "season", "episode") and season is not None:
        season_str = f"S{season:02d}"
        if episode is not None:
            season_str += f"E{episode:02d}"
        parts.append(season_str)
    if year:
        parts.append(str(year))
    if resolution:
        # eMuwarez suffixes 4K/8K with UHD/FUHD ("2160p UHD"), not just "2160p".
        parts.append(format_resolution(resolution) or resolution)
    # Provider (AMZN/NF/DSNP...) attaches to Source, in front of it — "AMZN
    # WEB-DL", never after — matching the eMuwarez nomenclature guide. Reuses
    # source_assistant's own combiner so the two never drift apart again.
    source_str = _build_source_string(source, provider)
    if source_str:
        parts.append(source_str)
    # HDR/Dolby Vision goes right before the video codec.
    hdr = format_hdr(dynamic_range) if dynamic_range else None
    if hdr:
        parts.append(hdr)
    if video_codec:
        parts.append(video_codec)
    if audio_summary:
        parts.append(audio_summary)
    if subtitle_summary:
        parts.append(subtitle_summary)
    name = " ".join(p for p in parts if p)
    if release_tag:
        # Tag attaches to the hyphen with no surrounding spaces, e.g.
        # "... SUBS-EMUWAREZ" (matches legacy.py::build_emu_title).
        name = f"{name}-{release_tag}"
    return name


# Alternate spellings uploaders use in filenames for a platform whose canonical
# EMU code is different, mapped to that code so detection recognises them too
# (found by auditing the real library + eMuwarez catalog).
_PROVIDER_FILENAME_ALIASES: dict[str, str] = {
    "HBOMAX": "HMAX",
    "APTV": "ATVP", "APTV+": "ATVP", "ATPV": "ATVP",
    "DNSP": "DSNP", "DSN+": "DSNP", "DSNY": "DSNP",
    "AMZ": "AMZN", "AMZNP": "AMZN",
}

# token -> canonical EMU code, for every real code (token == code) plus the
# aliases above. Ordered longest-first so a longer token/alias is matched
# before a shorter code contained inside it (e.g. "HBOMAX" before "MAX").
_PROVIDER_TOKEN_MAP: dict[str, str] = {
    **{p["code"]: p["code"] for p in EMU_PROVIDERS},
    **_PROVIDER_FILENAME_ALIASES,
}
_PROVIDER_TOKENS_BY_LENGTH: list[str] = sorted(
    _PROVIDER_TOKEN_MAP, key=len, reverse=True
)


def _infer_provider_from_item(item: dict, source: str | None) -> str | None:
    """Detect an EMU provider code (AMZN, NF, DSNP...) already present in the
    item's current filename/path — e.g. a file already named
    '...WEB-DL AMZN x265...' keeps that same AMZN tag in the proposal,
    instead of the proposed filename silently dropping it. Read-only,
    string-matching only: no TMDb call, no re-recommendation (that's a
    separate, not-yet-built feature — see 'editar campos' for the
    TMDb-driven suggestion flow).

    Only attempted when `source` is a provider-carrying source (WEB-DL,
    same PROVIDER_SOURCES gate source_assistant.py already uses) — several
    EMU_PROVIDERS codes are short/generic (IT, HS, SL, M+) and would
    false-positive far too easily against an arbitrary BluRay/HDTV/DVD
    filename that was never tagged with a streaming provider at all."""
    if source not in PROVIDER_SOURCES:
        return None
    haystack = f"{item.get('path') or ''}"
    if not haystack:
        return None
    for token in _PROVIDER_TOKENS_BY_LENGTH:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", haystack):
            return _PROVIDER_TOKEN_MAP[token]
    return None


def infer_provider_from_item(item: dict) -> str | None:
    """Public: detect the EMU provider code (AMZN/NF/DSNP…) from an item's
    filename, inferring the source first (provider is only meaningful for
    provider-carrying sources like WEB-DL). Returns None when not detectable."""
    return _proveedor_de(item.get("path"), item.get("source"), item.get("quality"))


# En caché: Biblioteca lo pide para cada fila y cada capítulo en cada carga.
@functools.lru_cache(maxsize=131072)
def _proveedor_de(path: str | None, source: str | None, quality: str | None) -> str | None:
    item = {"path": path, "source": source, "quality": quality}
    return _infer_provider_from_item(item, _infer_source_from_item(item))


def _infer_resolution_from_item(item: dict) -> str | None:
    res = item.get("resolution")
    if res:
        return res
    quality = item.get("quality") or ""
    for marker in ("2160p", "4K", "1080p", "720p", "480p"):
        if marker.lower() in quality.lower():
            return marker
    path = item.get("path") or ""
    for marker in ("2160p", "4K", "1080p", "720p", "480p"):
        if marker.lower() in path.lower():
            return marker
    return None


def _infer_source_from_item(item: dict) -> str | None:
    """Source for the item, in priority order: 1) the file/folder NAME (most
    reliable, and free — pure text match, no file access); 2) Radarr/Sonarr's
    own reported source; 3) a loose text match over quality profile + path as
    a last resort. Radarr/Sonarr used to win outright even when the name said
    otherwise (e.g. reporting "BluRay" for an actual MicroHD rip) — the name
    is checked first now so it isn't silently overridden. A further fallback,
    MediaInfo's bitrate/audio estimate, needs to actually read the file — too
    expensive to do here (this must stay cheap, called even for whole-season
    batches); it's applied downstream instead, only where that I/O is already
    being paid for (source_assistant.py's field editor)."""
    path = item.get("path") or ""
    if path:
        from pathlib import Path
        from .media_probe import _detect_source_by_name
        by_name = _detect_source_by_name(Path(path))
        if by_name:
            return by_name
    src = item.get("source")
    if src:
        return src
    quality = item.get("quality") or ""
    combined = (quality + " " + path).lower()
    source_map = [
        ("bluray", "BluRay"), ("blu-ray", "BluRay"), ("blu_ray", "BluRay"),
        ("bdremux", "BDReMux"), ("webdl", "WEB-DL"), ("web-dl", "WEB-DL"),
        ("webrip", "WEBRip"), ("web_dl", "WEB-DL"),
        ("hdtv", "HDTV"), ("dvd", "DVD"),
    ]
    for key, canonical in source_map:
        if key in combined:
            return canonical
    return None


def _get_release_tag(conn=None) -> str:
    own = conn is None
    _conn = conn or connect()
    try:
        # Phase 10A: prefer settings table
        try:
            from .settings import get_setting_canonical
            raw = get_setting_canonical(_conn, "default_release_tag")
            if raw:
                return raw
        except Exception:
            pass
        tag = get_state(_conn, "release_tag") or get_state(_conn, "default_release_tag")
        return tag or "EMUWAREZ"
    except Exception:
        return "EMUWAREZ"
    finally:
        if own:
            _conn.close()


def tag_por_defecto(grupos, conn=None) -> str:
    """El grupo de release que comparten los archivos (la columna Grupo de
    Biblioteca) o, si no tienen uno solo, el tag de Ajustes."""
    distintos = {(g or "").strip() for g in grupos}
    if len(distintos) == 1 and "" not in distintos:
        return distintos.pop()
    return _get_release_tag(conn=conn)


def validate_nomenclature_preconditions(library_item: dict, conn=None) -> dict:
    errors = []
    warnings = []

    if not library_item:
        return {"ok": False, "errors": ["Item no encontrado."], "warnings": []}

    local_status = library_item.get("local_status", "")
    if local_status in ("Faltante", "Missing", "missing", "faltante"):
        errors.append("El ítem no está disponible localmente (faltante).")

    # Cuál de las dos rutas se lee: path_mapping.py::ruta_de_lectura.
    from .path_mapping import ruta_de_lectura
    path = ruta_de_lectura(library_item)
    if not path:
        errors.append("El ítem no tiene ruta de archivo registrada.")
    else:
        stat_info = safe_stat(path)
        if not stat_info["exists"]:
            warnings.append(f"La ruta registrada no existe en disco: {path}")
        else:
            # Applying the proposal renames the original file in place, so the
            # containing folder must be writable NOW. Being readable/accessible
            # isn't enough — a read-only mount (e.g. sshfs -o ro) passes the
            # exists() check above but rejects the rename later, and that
            # failure was only surfacing deep inside "Ver MediaInfo"/"Ver
            # remux" instead of here.
            from .path_mapping import resolve_local_path
            resolved = resolve_local_path(path, conn=conn) or path
            parent = os.path.dirname(resolved)
            if parent and not os.access(parent, os.W_OK):
                errors.append(f"La carpeta del archivo no es escribible: {parent}")

    title = library_item.get("title")
    if not title:
        errors.append("El ítem no tiene título.")

    if not _infer_resolution_from_item(library_item):
        warnings.append("Resolución no detectada. Se usará campo vacío.")

    if not _infer_source_from_item(library_item):
        warnings.append("Source/medio no detectado. Se usará campo vacío.")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def build_nomenclature_proposal(
    item_id: int, *, force_refresh: bool = False, conn=None,
    source_override: str | None = None, provider_override: str | None = None,
    tag_override: str | None = None, title_override: str | None = None,
) -> dict:
    """Generate a nomenclature proposal for a library item. Never modifies the
    filesystem.

    `source_override`/`provider_override`/`tag_override`/`title_override` let a
    caller that already resolved an ambiguity by hand (the automated-upload
    source-disparity gate, or a season pack's own field overrides) force
    that choice instead of the usual name -> Radarr/Sonarr -> bitrate-tool
    inference — an override always forces a fresh build (a cached proposal
    predates the user's choice and must not be reused).

    `title_override` is the Título dropdown's pick. A season pack passes it to
    EVERY episode so the files inside end up named after the same title as the
    pack itself — without it the torrent read "The Tudors S02" while the files
    inside stayed "Los.Tudor.S02E01"."""
    own = conn is None
    conn = conn or connect()
    try:
        if (source_override is not None or provider_override is not None
                or tag_override is not None or title_override is not None):
            force_refresh = True
        if not force_refresh:
            existing = get_latest_nomenclature_proposal(item_id, conn=conn)
            if existing and existing.get("status") not in (STATUS_EXPIRED,):
                return existing

        item = get_library_item_for_nomenclature(item_id, conn=conn)
        if not item:
            return {
                "library_item_id": item_id,
                "status": STATUS_BLOCKED,
                "errors_json": json.dumps(["Item no encontrado."]),
                "warnings_json": json.dumps([]),
            }

        preconditions = validate_nomenclature_preconditions(item, conn=conn)
        errors = preconditions["errors"]
        warnings = list(preconditions["warnings"])

        title = item.get("title") or "Sin título"
        year = item.get("year")
        media_type = item.get("item_type") or "movie"
        tmdb_id = item.get("tmdb_id")
        imdb_id = item.get("imdb_id")
        # Cuál de las dos rutas se lee: path_mapping.py::ruta_de_lectura.
        from .path_mapping import ruta_de_lectura
        path = ruta_de_lectura(item, conn=conn)

        # For episodes/seasons the eMuwarez title must be the SERIES name
        # (not the per-episode title Sonarr stores, e.g. "Serie S01E01 -
        # Nombre del capítulo") — same resolution
        # build_editable_nomenclature_fields() (the wizard's live preview)
        # already does; without this the REAL applied name diverged from
        # what the wizard showed and the user approved.
        if media_type in ("season", "episode"):
            from .source_assistant import _resolve_series_row
            srow = _resolve_series_row(item, conn)
            if srow:
                title = srow.get("title") or title
                tmdb_id = srow.get("tmdb_id") or tmdb_id
        from .tmdb_titles import resolve_localized_title
        title, _title_warning = resolve_localized_title(conn, media_type, tmdb_id, title)
        if _title_warning:
            warnings.append(_title_warning)
        # An explicit pick wins over whatever TMDb resolved: the user chose it
        # in the Título dropdown precisely to override the default.
        if (title_override or "").strip():
            title = title_override.strip()
        # `title` above is already the series name for season/episode (see the
        # resolution above) — surfaced again under its own key so consumers
        # that show "Serie" and "Título propuesto" as separate rows (the
        # automated upload job's nomenclature snapshot table) have both.
        series_title = title if media_type in ("season", "episode") else None

        resolution = _infer_resolution_from_item(item)
        source = source_override or _infer_source_from_item(item)
        release_tag = tag_override or tag_por_defecto([item.get("release_group")], conn=conn)

        stat_info = safe_stat(path) if path else {}
        current_name = stat_info.get("name") or (path.split("/")[-1] if path else None)

        # Phase 6A: real values parsed from Radarr/Sonarr's own movieFile/
        # episodeFile mediaInfo at sync time (integrations/base.py::
        # extract_media_info), not a guess against the quality profile NAME —
        # the starting point/fallback. Real MediaInfo of the actual file
        # (below) wins when it's reachable, since it has proper per-track
        # codec labels and the DUAL/MULTI-aware audio summary the eMuwarez
        # guide expects — Radarr/Sonarr's own columns are coarser.
        video_codec = item.get("video_codec")
        if video_codec is None:
            quality = item.get("quality") or ""
            for codec in ("HEVC", "H.265", "x265", "AVC", "H.264", "x264", "AV1", "VP9"):
                if codec.lower() in quality.lower():
                    video_codec = codec
                    break
        if not video_codec:
            warnings.append("Codec de vídeo no detectado. Sincroniza de nuevo la biblioteca o invoca MediaInfo desde 'Adaptar nomenclatura'.")

        audio_codec = item.get("audio_codec")
        audio_languages = item.get("audio_languages")
        audio_summary = " ".join(p for p in (audio_codec, audio_languages) if p) or None
        subtitle_summary = item.get("subtitle_languages")
        dynamic_range = item.get("dynamic_range")

        # Real MediaInfo read of the actual file (cached per file by mtime+
        # size, so repeat calls for the same unchanged file are instant) —
        # same source build_editable_nomenclature_fields() uses. Best-effort:
        # any failure just keeps the Radarr/Sonarr-derived values above.
        if path:
            from .path_mapping import resolve_local_path
            from .media_info_service import build_mediainfo_report
            local_path = resolve_local_path(path, conn=conn) or path
            mi_report = build_mediainfo_report(local_path)
            if mi_report.get("available"):
                emu_by_field = {
                    r["field"]: (None if r["emu"] in (None, "—", "") else r["emu"])
                    for r in mi_report.get("rows", [])
                }
                video_codec = emu_by_field.get("Códec de vídeo") or video_codec
                audio_summary = mi_report.get("audio_summary") or audio_summary
                subtitle_summary = emu_by_field.get("Subtítulos") or subtitle_summary
                dynamic_range = emu_by_field.get("HDR/DV") or dynamic_range

        # Phase 6E — provider (AMZN/NF/DSNP...) already present in the
        # current filename, kept in the proposal instead of silently
        # dropped. Detection only, no TMDb re-recommendation here.
        provider = provider_override or _infer_provider_from_item(item, source)

        # Full nomenclature with spaces + accents = the torrent/aporte title.
        proposed_torrent_name = _build_proposed_filename(
            title=title,
            year=year,
            resolution=resolution,
            source=source,
            video_codec=video_codec,
            audio_summary=audio_summary,
            subtitle_summary=subtitle_summary,
            release_tag=release_tag,
            media_type=media_type,
            provider=provider,
            season=item.get("season_number"),
            episode=item.get("episode_number"),
            dynamic_range=dynamic_range,
        )
        # File name (and folder) use the cleaned, accent-free, dotted form.
        from .mkv_title import to_filesystem_name
        proposed_filename = to_filesystem_name(proposed_torrent_name)

        proposed_folder = proposed_filename
        proposed_path = None
        if path and proposed_filename:
            parent = os.path.dirname(path)
            ext = os.path.splitext(path)[1] if os.path.isfile(path) else ""
            proposed_path = os.path.join(parent, proposed_filename + ext) if ext else os.path.join(parent, proposed_filename)

        if errors:
            status = STATUS_BLOCKED
        elif warnings:
            status = STATUS_WARNING
        else:
            status = STATUS_VALID

        proposal = {
            "library_item_id": item_id,
            "status": status,
            "current_name": current_name,
            "current_path": path,
            "proposed_title": title,
            "proposed_torrent_name": proposed_torrent_name,
            "proposed_filename": proposed_filename,
            "proposed_folder": proposed_folder,
            "proposed_path": proposed_path,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "imdb_id": imdb_id,
            "year": year,
            "series_title": series_title,
            "season_number": item.get("season_number"),
            "resolution": resolution,
            "source": source,
            # Stored under the same provider_final column name the 'editar
            # campos' flow already uses (web/api/nomenclature.py's
            # save-fields endpoint) — same underlying table, same meaning.
            "provider_final": provider,
            "video_codec": video_codec,
            "audio_summary": audio_summary,
            "subtitle_summary": subtitle_summary,
            "release_tag": release_tag,
            "warnings_json": json.dumps(warnings, ensure_ascii=False),
            "errors_json": json.dumps(errors, ensure_ascii=False),
            "raw_json": json.dumps({"item_id": item_id, "title": title}, ensure_ascii=False),
        }

        return save_nomenclature_proposal(proposal, conn=conn)
    finally:
        if own:
            conn.close()


def save_nomenclature_proposal(proposal: dict, conn=None) -> dict:
    own = conn is None
    conn = conn or connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE nomenclature_proposals SET status = 'expired', updated_at = ? "
            "WHERE library_item_id = ? AND status NOT IN ('applied', 'expired')",
            (now, proposal["library_item_id"]),
        )
        cursor = conn.execute(
            """
            INSERT INTO nomenclature_proposals (
                library_item_id, status, current_name, current_path,
                proposed_title, proposed_torrent_name, proposed_filename, proposed_folder, proposed_path,
                media_type, tmdb_id, imdb_id, year, series_title, season_number,
                resolution, source, provider_final,
                video_codec, audio_summary, subtitle_summary, release_tag,
                warnings_json, errors_json, raw_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal["library_item_id"],
                proposal["status"],
                proposal.get("current_name"),
                proposal.get("current_path"),
                proposal.get("proposed_title"),
                proposal.get("proposed_torrent_name"),
                proposal.get("proposed_filename"),
                proposal.get("proposed_folder"),
                proposal.get("proposed_path"),
                proposal.get("media_type"),
                proposal.get("tmdb_id"),
                proposal.get("imdb_id"),
                proposal.get("year"),
                proposal.get("series_title"),
                proposal.get("season_number"),
                proposal.get("resolution"),
                proposal.get("source"),
                proposal.get("provider_final"),
                proposal.get("video_codec"),
                proposal.get("audio_summary"),
                proposal.get("subtitle_summary"),
                proposal.get("release_tag"),
                proposal.get("warnings_json", "[]"),
                proposal.get("errors_json", "[]"),
                proposal.get("raw_json"),
                now, now,
            ),
        )
        conn.commit()
        proposal["id"] = cursor.lastrowid
        proposal["created_at"] = now
        proposal["updated_at"] = now
        return proposal
    finally:
        if own:
            conn.close()


def get_latest_nomenclature_proposal(item_id: int, conn=None) -> dict | None:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM nomenclature_proposals
            WHERE library_item_id = ? AND status != 'expired'
            ORDER BY created_at DESC LIMIT 1
            """,
            (item_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        if own:
            conn.close()


def mark_nomenclature_status(item_id: int, status: str, conn=None) -> None:
    own = conn is None
    conn = conn or connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE nomenclature_proposals SET status = ?, updated_at = ?
            WHERE library_item_id = ? AND id = (
                SELECT id FROM nomenclature_proposals
                WHERE library_item_id = ? AND status != 'expired'
                ORDER BY created_at DESC LIMIT 1
            )
            """,
            (status, now, item_id, item_id),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------------------
# Phase 6B — el nombre que lleva el enlace de la carpeta de subidas
# ---------------------------------------------------------------------------

CONFIRMATION_TOKEN = "APLICAR_NOMENCLATURA"


def _refresh_media_info_from_real_file(item: dict, *, conn) -> None:
    """Phase 6B: overwrite library_items' video_codec/audio_codec/
    audio_languages/subtitle_languages with a real MediaInfo read of the
    actual file, when it disagrees with what's there (usually Radarr/
    Sonarr's own sync-time mediaInfo, or nothing at all for older rows).
    Silently does nothing if MediaInfo is unavailable/fails — the existing
    Phase 6A values (or lack thereof) are always a safe fallback."""
    from .media_info_service import read_media_info_summary

    # Cuál de las dos rutas se lee: path_mapping.py::ruta_de_lectura. Esta
    # función existe para corregir con el fichero real lo que dice
    # Radarr/Sonarr, así que leer de una ruta muerta la deja sin sentido.
    from .path_mapping import ruta_de_lectura
    path = ruta_de_lectura(item)
    if not path:
        return
    real = read_media_info_summary(path)
    if not real:
        return

    changed = any(item.get(k) != real.get(k) for k in real)
    if not changed:
        return

    conn.execute(
        """UPDATE library_items SET video_codec = ?, audio_codec = ?,
           audio_languages = ?, subtitle_languages = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (real.get("video_codec"), real.get("audio_codec"),
         real.get("audio_languages"), real.get("subtitle_languages"), item.get("id")),
    )
    conn.commit()

    # audio_languages/subtitle_languages just changed from a real file read,
    # which is exactly what the Español column and the season pack's subtitle
    # rule are derived from — refresh them (and the season/series rollups above
    # this item) instead of leaving them stale until the next library sync.
    # Best-effort: a failure here must not break the nomenclature proposal
    # that's actually being built.
    try:
        from .library import recompute_spanish_flags
        recompute_spanish_flags(conn)
    except Exception:
        logger.warning("No se pudo recalcular el castellano (audio/subtítulos) tras leer el MediaInfo real", exc_info=True)

    # A manually-edited proposal (fields_json is only ever written by the
    # field editor's save_nomenclature_fields()) must not be silently
    # discarded just because the corrected codec/audio metadata differs from
    # what was stored — force_refresh=True below recomputes EVERY field from
    # scratch, including `source` from the raw filename, which overwrote a
    # user's own manual "BluRay" choice back to "BDReMux" in production the
    # moment any of the four narrow fields above disagreed even slightly.
    latest = get_latest_nomenclature_proposal(item.get("id"), conn=conn)
    if latest and latest.get("fields_json"):
        return
    build_nomenclature_proposal(item.get("id"), force_refresh=True, conn=conn)


def build_nomenclature_apply_plan(
    item_id: int,
    *,
    proposal_id: int | None = None,
    conn=None,
    source_override: str | None = None,
    provider_override: str | None = None,
) -> dict:
    """Con qué nombre de eMuwarez va el archivo a la carpeta de subidas. No toca nada.

    Devuelve la propuesta, el archivo (`source_path`, ruta local) y el nombre
    de eMuwarez (`nombre`, con extensión). Un archivo de la biblioteca conserva
    el nombre de Radarr/Sonarr y el de eMuwarez lo lleva su enlace; solo uno que
    ya está en la carpeta de subidas (`renombrable`) se renombra en su sitio,
    a `destination_path`."""
    from .carpeta_subida import en_carpeta_de_subidas
    from .path_mapping import ruta_de_lectura
    import os as _os

    own = conn is None
    conn = conn or connect()
    try:
        item = get_library_item_for_nomenclature(item_id, conn=conn)
        if not item:
            return {
                "status": "blocked",
                "errors": ["Item no encontrado."],
                "warnings": [],
                "source_path": None,
                "destination_path": None,
            }

        if source_override is not None or provider_override is not None:
            # The user already resolved a source-disparity by hand (the
            # automated-upload gate) — that choice must win over whatever
            # proposal_id/cached-latest would otherwise be reused, and forces
            # a fresh build (see build_nomenclature_proposal's own guard).
            proposal = build_nomenclature_proposal(
                item_id, conn=conn, source_override=source_override, provider_override=provider_override,
            )
        elif proposal_id:
            row = conn.execute(
                "SELECT * FROM nomenclature_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            proposal = row_to_dict(row)
        else:
            # Phase 6B: invoke real MediaInfo against the actual file at
            # apply time (never during the cheap 6A preview) — its result
            # wins over Radarr/Sonarr's own mediaInfo when it disagrees,
            # since it inspects the file directly rather than trusting
            # whatever the *arr app reported at sync time. Best-effort: a
            # missing `mediainfo` binary or a parse failure just leaves the
            # Phase 6A values in place, it never blocks the apply flow.
            _refresh_media_info_from_real_file(item, conn=conn)
            proposal = get_latest_nomenclature_proposal(item_id, conn=conn)

        if not proposal:
            proposal = build_nomenclature_proposal(item_id, conn=conn)

        if proposal.get("status") == "blocked":
            prop_errors: list[str] = []
            try:
                prop_errors = json.loads(proposal.get("errors_json") or "[]")
            except Exception:
                pass
            return {
                "status": "blocked",
                "errors": ["La propuesta de nomenclatura está bloqueada."] + prop_errors,
                "warnings": [],
                "proposal": proposal,
                "source_path": ruta_de_lectura(item, conn=conn),
                "destination_path": None,
            }

        # La ruta de Radarr/Sonarr (/data/media/…) traducida a donde esta app
        # llega al fichero (un montaje SSHFS/NFS, por ejemplo).
        from .path_mapping import resolve_local_path
        elegida = ruta_de_lectura(item, conn=conn)
        source_path = (resolve_local_path(elegida, conn=conn) or elegida) if elegida else elegida
        if not source_path:
            return {
                "status": "blocked",
                "errors": ["El elemento no tiene ruta de archivo."],
                "warnings": [], "proposal": proposal,
                "source_path": None, "destination_path": None,
            }
        proposed_filename = (
            proposal.get("proposed_filename")
            or proposal.get("proposed_title")
            or "archivo"
        )
        nombre = proposed_filename + _os.path.splitext(source_path)[1]
        renombrable = en_carpeta_de_subidas(source_path)
        # `path` se guarda en el convenio de Radarr/Sonarr: tras renombrar, la misma carpeta.
        raw_source = item.get("path")
        return {
            "status": "ready",
            "errors": [],
            "warnings": [],
            "proposal": proposal,
            "item": {"id": item_id, "title": item.get("title")},
            "source_path": source_path,
            "nombre": nombre,
            "renombrable": renombrable,
            "destination_path": _os.path.join(_os.path.dirname(source_path), nombre) if renombrable else None,
            "raw_destination_path": (_os.path.join(_os.path.dirname(raw_source), nombre)
                                     if renombrable and raw_source else None),
        }
    finally:
        if own:
            conn.close()


def renombrar_en_subidas(item_id: int, origen: str, destino: str, *, conn,
                         raw_destino: str | None = None, proposal_id: int | None = None,
                         dry_run: bool = False) -> dict:
    """Renombra en su sitio un archivo de la carpeta de subidas (filesystem_apply
    veta cualquier otro) y apunta la fila de la biblioteca al nombre nuevo."""
    from .filesystem_apply import apply_rename_plan, build_safe_rename_plan

    now = datetime.now(timezone.utc).isoformat()
    plan = build_safe_rename_plan(origen, destino)
    result = apply_rename_plan(plan, dry_run=dry_run)
    if dry_run:
        return result
    if result.get("status") == "applied":
        logger.info("Renombrado en la carpeta de subidas: %s → %s", origen, destino)
    else:
        logger.warning("No se renombró %s [%s]: %s", origen, result.get("status"),
                       "; ".join(result.get("errors", [])) or result.get("message") or "")
    try:
        cursor = conn.execute(
            """
            INSERT INTO filesystem_operations (
                operation_type, status, library_item_id, proposal_id,
                source_path, destination_path, base_path,
                dry_run, warnings_json, errors_json, result_json,
                created_at, updated_at, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.get("operation_type", "nomenclature_rename"), result.get("status", "planned"),
                item_id, proposal_id, origen, destino, None, 0,
                json.dumps(result.get("warnings", []), ensure_ascii=False),
                json.dumps(result.get("errors", []), ensure_ascii=False),
                json.dumps(result, ensure_ascii=False, default=str),
                now, now, result.get("applied_at"),
            ),
        )
        result["operation_id"] = cursor.lastrowid
        if result.get("status") == "applied":
            # `path` en el convenio de Radarr/Sonarr; prepared_path, el archivo local.
            conn.execute(
                """UPDATE library_items
                   SET path = ?, prepared_path = ?, nomenclature_applied_at = ?,
                       nomenclature_status = 'Correcta', updated_at = ?
                   WHERE id = ?""",
                (raw_destino or destino, destino, now, now, item_id),
            )
        conn.commit()
    except Exception:
        logger.warning("No se pudo registrar el renombrado de %s", origen, exc_info=True)
    return result


def apply_nomenclature_proposal(
    item_id: int,
    *,
    proposal_id: int | None = None,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
    conn=None,
    source_override: str | None = None,
    provider_override: str | None = None,
) -> dict:
    """Renombra en su sitio, solo si el archivo está en la carpeta de subidas.

    Uno de la biblioteca no se renombra nunca (Jellyfin lo lee con el nombre de
    Radarr/Sonarr): para ese queda en vista previa, con `renombrable` a False."""
    from .filesystem_apply import SOLO_EN_SUBIDAS

    own = conn is None
    conn = conn or connect()
    try:
        if dry_run:
            apply = False
        plan = build_nomenclature_apply_plan(
            item_id, proposal_id=proposal_id, conn=conn,
            source_override=source_override, provider_override=provider_override,
        )
        base_result = {
            "dry_run": True,
            "apply": False,
            "status": plan["status"],
            "source_path": plan.get("source_path"),
            "destination_path": plan.get("destination_path"),
            "nombre": plan.get("nombre"),
            "renombrable": bool(plan.get("renombrable")),
            "proposal": plan.get("proposal"),
            "warnings": plan.get("warnings", []),
            "errors": list(plan.get("errors", [])),
            "message": None,
            "operation_id": None,
        }
        if plan["status"] == "blocked":
            base_result["message"] = "Plan bloqueado. Ver errors."
            return base_result
        if not plan.get("renombrable"):
            base_result["status"] = "blocked"
            base_result["message"] = SOLO_EN_SUBIDAS
            if apply:
                base_result["errors"].append(SOLO_EN_SUBIDAS)
            return base_result
        if apply and confirmation != CONFIRMATION_TOKEN:
            base_result["status"] = "blocked"
            base_result["errors"].append(
                f"Para aplicar cambios reales debes confirmar escribiendo {CONFIRMATION_TOKEN}.")
            base_result["message"] = f"Confirmación requerida: {CONFIRMATION_TOKEN}"
            return base_result

        pid = (plan.get("proposal") or {}).get("id")
        result = renombrar_en_subidas(
            item_id, plan["source_path"], plan["destination_path"], conn=conn,
            raw_destino=plan.get("raw_destination_path"), proposal_id=pid, dry_run=not apply,
        )
        if apply and result.get("status") == "applied" and pid:
            marcar_nombre_aplicado(item_id, plan["destination_path"], conn=conn, proposal_id=pid)
        return {**base_result, **{k: v for k, v in result.items() if k != "proposal"},
                "dry_run": not apply, "apply": apply,
                "destination_path": plan["destination_path"]}
    finally:
        if own:
            conn.close()


def marcar_nombre_aplicado(item_id: int, ruta: str, *, conn, proposal_id: int | None = None) -> None:
    """La propuesta se aplicó a `ruta`, en la carpeta de subidas: el enlace, la
    copia o el propio archivo renombrado.

    Solo la propuesta: la fila de un archivo de la biblioteca sigue describiendo
    el de Radarr/Sonarr, que no cambia de nombre (su nomenclature_status es el
    veredicto sobre ESE nombre)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE nomenclature_proposals SET status = 'applied', applied_path = ?,
               applied_at = ?, updated_at = ?
           WHERE id = COALESCE(?, (SELECT id FROM nomenclature_proposals
                                   WHERE library_item_id = ? AND status != 'expired'
                                   ORDER BY created_at DESC LIMIT 1))""",
        (ruta, now, now, proposal_id, item_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Consultas que vivían dentro de los endpoints (auditoría, hallazgo 6.2)
# ---------------------------------------------------------------------------

def list_filesystem_operations(item_id: int, *, limit: int = 20, conn=None) -> list[dict]:
    """El historial de operaciones de fichero de un elemento, lo más reciente
    primero. Solo las de nomenclatura: el resto del historial no es de esta
    pantalla."""
    own = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute(
            """SELECT * FROM filesystem_operations
               WHERE library_item_id = ?
                 AND operation_type IN ('nomenclature_rename', 'nomenclature_hardlink')
               ORDER BY created_at DESC LIMIT ?""",
            (item_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def item_tmdb_reference(item_id: int, *, conn=None) -> tuple[str | None, str | None]:
    """(tmdb_id, item_type) de un elemento, para consultar sus proveedores en
    TMDb. Devuelve (None, None) si no existe."""
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT tmdb_id, item_type FROM library_items WHERE id = ?", (item_id,)
        ).fetchone()
        return (row["tmdb_id"], row["item_type"]) if row else (None, None)
    finally:
        if own:
            conn.close()


def save_manual_nomenclature_fields(item_id: int, fields: dict, preview: dict, *, conn) -> None:
    """Guarda una propuesta editada a mano, expirando la anterior.

    Vivía dentro del endpoint: un INSERT de dieciséis columnas escrito en el
    controlador HTTP, con seis líneas de comentario explicando en qué columna
    escribir y por qué la de al lado era huérfana. Eso es conocimiento de
    dominio y este es su sitio."""
    import json as _json
    from datetime import datetime, timezone

    ahora = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE nomenclature_proposals SET status='expired', updated_at=? "
        "WHERE library_item_id=? AND status NOT IN ('applied','expired')",
        (ahora, item_id),
    )
    conn.execute(
        """INSERT INTO nomenclature_proposals
           (library_item_id, status, proposed_torrent_name, proposed_filename, proposed_title,
            fields_json, year, resolution, source, provider_final,
            video_codec, audio_summary, subtitle_summary, release_tag,
            internal_mkv_title, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item_id, "valid",
            preview.get("torrent_name") or "",
            # Con esta columna se renombra el archivo, así que va en la forma de archivo.
            preview.get("internal_mkv_title") or "",
            fields.get("title"),
            _json.dumps(fields, ensure_ascii=False),
            fields.get("year"),
            fields.get("resolution"),
            # La columna `source`, la misma que escriben build_nomenclature_proposal
            # y save_nomenclature_proposal y la que lee la ficha de la subida —
            # NO la columna source_final, huérfana que nadie más lee y en la que
            # esto escribía por error, dejando `source` (y todos los demás campos
            # técnicos) a NULL en una propuesta editada a mano.
            fields.get("source"),
            fields.get("provider"),
            fields.get("video_codec"),
            fields.get("audio_summary"),
            fields.get("subs"),
            fields.get("tag"),
            preview.get("internal_mkv_title") or "",
            ahora, ahora,
        ),
    )
    conn.commit()
