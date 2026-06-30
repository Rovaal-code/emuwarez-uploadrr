"""Nomenclature proposal service.

SAFETY CONTRACT: This module never modifies the filesystem.
It only reads library_items from the database and generates proposals.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from ..database import connect, row_to_dict, get_state
from .filesystem_safety import safe_stat

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
    cleaned = re.sub(r'[<>:"/\\|?*]', "", normalized)
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
) -> str:
    parts = [_normalize_title_for_emu(title)]
    if year:
        parts.append(str(year))
    if media_type in ("tv", "series", "anime") and season is not None:
        season_str = f"S{season:02d}"
        if episode is not None:
            season_str += f"E{episode:02d}"
        parts.append(season_str)
    if resolution:
        parts.append(resolution)
    if source:
        parts.append(source)
    if video_codec:
        parts.append(video_codec)
    if audio_summary:
        parts.append(audio_summary)
    if subtitle_summary:
        parts.append(subtitle_summary)
    if release_tag:
        parts.append(f"- {release_tag}")
    return " ".join(p for p in parts if p)


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
    src = item.get("source")
    if src:
        return src
    quality = item.get("quality") or ""
    path = item.get("path") or ""
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
            row = _conn.execute("SELECT value FROM settings WHERE key = 'default_release_tag'").fetchone()
            if row and row["value"]:
                return row["value"]
        except Exception:
            pass
        tag = get_state(_conn, "release_tag") or get_state(_conn, "default_release_tag")
        return tag or "EMUWAREZ"
    except Exception:
        return "EMUWAREZ"
    finally:
        if own:
            _conn.close()


def validate_nomenclature_preconditions(library_item: dict) -> dict:
    errors = []
    warnings = []

    if not library_item:
        return {"ok": False, "errors": ["Item no encontrado."], "warnings": []}

    local_status = library_item.get("local_status", "")
    if local_status in ("Faltante", "Missing", "missing", "faltante"):
        errors.append("El ítem no está disponible localmente (faltante).")

    path = library_item.get("path")
    if not path:
        errors.append("El ítem no tiene ruta de archivo registrada.")
    elif not safe_stat(path)["exists"]:
        warnings.append(f"La ruta registrada no existe en disco: {path}")

    title = library_item.get("title")
    if not title:
        errors.append("El ítem no tiene título.")

    if not _infer_resolution_from_item(library_item):
        warnings.append("Resolución no detectada. Se usará campo vacío.")

    if not _infer_source_from_item(library_item):
        warnings.append("Source/medio no detectado. Se usará campo vacío.")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def build_nomenclature_proposal(item_id: int, *, force_refresh: bool = False, conn=None) -> dict:
    """Generate a nomenclature proposal for a library item. Never modifies the filesystem."""
    own = conn is None
    conn = conn or connect()
    try:
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

        preconditions = validate_nomenclature_preconditions(item)
        errors = preconditions["errors"]
        warnings = list(preconditions["warnings"])

        title = item.get("title") or "Sin título"
        year = item.get("year")
        media_type = item.get("item_type") or "movie"
        tmdb_id = item.get("tmdb_id")
        imdb_id = item.get("imdb_id")
        path = item.get("path")

        resolution = _infer_resolution_from_item(item)
        source = _infer_source_from_item(item)
        release_tag = _get_release_tag(conn=conn)

        stat_info = safe_stat(path) if path else {}
        current_name = stat_info.get("name") or (path.split("/")[-1] if path else None)

        quality = item.get("quality") or ""
        video_codec = None
        for codec in ("HEVC", "H.265", "x265", "AVC", "H.264", "x264", "AV1", "VP9"):
            if codec.lower() in quality.lower():
                video_codec = codec
                break
        if not video_codec:
            warnings.append("Codec de vídeo no detectado desde metadatos disponibles. MediaInfo no fue invocado.")

        proposed_filename = _build_proposed_filename(
            title=title,
            year=year,
            resolution=resolution,
            source=source,
            video_codec=video_codec,
            audio_summary=None,
            subtitle_summary=None,
            release_tag=release_tag,
            media_type=media_type,
        )

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
            "proposed_filename": proposed_filename,
            "proposed_folder": proposed_folder,
            "proposed_path": proposed_path,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "imdb_id": imdb_id,
            "resolution": resolution,
            "source": source,
            "video_codec": video_codec,
            "audio_summary": None,
            "subtitle_summary": None,
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
                proposed_title, proposed_filename, proposed_folder, proposed_path,
                media_type, tmdb_id, imdb_id, resolution, source,
                video_codec, audio_summary, subtitle_summary, release_tag,
                warnings_json, errors_json, raw_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal["library_item_id"],
                proposal["status"],
                proposal.get("current_name"),
                proposal.get("current_path"),
                proposal.get("proposed_title"),
                proposal.get("proposed_filename"),
                proposal.get("proposed_folder"),
                proposal.get("proposed_path"),
                proposal.get("media_type"),
                proposal.get("tmdb_id"),
                proposal.get("imdb_id"),
                proposal.get("resolution"),
                proposal.get("source"),
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
# Phase 6B — safe hardlink apply
# ---------------------------------------------------------------------------

CONFIRMATION_TOKEN = "APLICAR_NOMENCLATURA"


def _get_hardlink_base(conn=None) -> str | None:
    """Get configured hardlink_base from settings or app_state."""
    own = conn is None
    _conn = conn or connect()
    try:
        row = _conn.execute(
            "SELECT value FROM settings WHERE key = 'hardlink_base'"
        ).fetchone()
        if row:
            return row["value"]
        return get_state(_conn, "hardlink_base")
    except Exception:
        return None
    finally:
        if own:
            _conn.close()


def build_nomenclature_apply_plan(
    item_id: int,
    *,
    proposal_id: int | None = None,
    conn=None,
) -> dict:
    """Build a dry-run plan for applying nomenclature via hardlink. Never modifies filesystem."""
    from .filesystem_apply import build_safe_apply_plan
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

        if proposal_id:
            row = conn.execute(
                "SELECT * FROM nomenclature_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            proposal = row_to_dict(row)
        else:
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
                "source_path": item.get("path"),
                "destination_path": None,
            }

        source_path = item.get("path")
        hardlink_base = _get_hardlink_base(conn=conn)

        if not hardlink_base:
            return {
                "status": "blocked",
                "errors": [
                    "hardlink_base no configurado. "
                    "Configura la ruta de subidas en ajustes."
                ],
                "warnings": [],
                "proposal": proposal,
                "source_path": source_path,
                "destination_path": None,
            }

        proposed_filename = (
            proposal.get("proposed_filename")
            or proposal.get("proposed_title")
            or "archivo"
        )
        folder_name = proposal.get("proposed_folder") or proposed_filename
        ext = _os.path.splitext(source_path)[1] if source_path else ""
        destination_path = _os.path.join(
            hardlink_base, folder_name, proposed_filename + ext
        )

        plan = build_safe_apply_plan(source_path or "", destination_path, hardlink_base)
        plan["proposal"] = proposal
        plan["item"] = {"id": item_id, "title": item.get("title")}
        return plan
    finally:
        if own:
            conn.close()


def apply_nomenclature_proposal(
    item_id: int,
    *,
    proposal_id: int | None = None,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
    overwrite: bool = False,
    conn=None,
) -> dict:
    """Apply nomenclature proposal by creating a hardlink. Never modifies the original file."""
    from .filesystem_apply import apply_hardlink_plan

    own = conn is None
    conn = conn or connect()
    try:
        now = datetime.now(timezone.utc).isoformat()

        if dry_run:
            apply = False

        plan = build_nomenclature_apply_plan(
            item_id, proposal_id=proposal_id, conn=conn
        )

        base_result = {
            "dry_run": dry_run,
            "apply": apply,
            "source_path": plan.get("source_path"),
            "destination_path": plan.get("destination_path"),
            "proposal": plan.get("proposal"),
            "warnings": plan.get("warnings", []),
            "errors": list(plan.get("errors", [])),
        }

        if plan["status"] == "blocked":
            base_result["status"] = "blocked"
            base_result["message"] = "Plan bloqueado. Ver errors."
            return base_result

        if apply and not dry_run:
            if confirmation != CONFIRMATION_TOKEN:
                base_result["status"] = "blocked"
                base_result["errors"] = base_result["errors"] + [
                    f"Para aplicar cambios reales debes confirmar escribiendo "
                    f"{CONFIRMATION_TOKEN}."
                ]
                base_result["message"] = f"Confirmación requerida: {CONFIRMATION_TOKEN}"
                return base_result

        effective_dry_run = dry_run or not apply
        result = apply_hardlink_plan(plan, dry_run=effective_dry_run, overwrite=overwrite)

        fs_op_id = None
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
                    "nomenclature_hardlink",
                    result.get("status", "planned"),
                    item_id,
                    (plan.get("proposal") or {}).get("id"),
                    plan.get("source_path"),
                    plan.get("destination_path"),
                    plan.get("hardlink_base"),
                    1 if effective_dry_run else 0,
                    json.dumps(result.get("warnings", []), ensure_ascii=False),
                    json.dumps(result.get("errors", []), ensure_ascii=False),
                    json.dumps(
                        {k: v for k, v in result.items() if k != "proposal"},
                        ensure_ascii=False,
                        default=str,
                    ),
                    now,
                    now,
                    result.get("applied_at"),
                ),
            )
            fs_op_id = cursor.lastrowid

            if result.get("status") == "applied":
                proposal = plan.get("proposal") or {}
                pid = proposal.get("id")
                dst = plan.get("destination_path")
                if pid:
                    conn.execute(
                        """UPDATE nomenclature_proposals
                           SET status = 'applied', applied_path = ?,
                               applied_at = ?, operation_id = ?, updated_at = ?
                           WHERE id = ?""",
                        (dst, now, fs_op_id, now, pid),
                    )
                conn.execute(
                    """UPDATE library_items
                       SET prepared_path = ?, nomenclature_applied_at = ?,
                           nomenclature_status = 'Correcta', updated_at = ?
                       WHERE id = ?""",
                    (dst, now, now, item_id),
                )
            conn.commit()
        except Exception:
            pass

        result["operation_id"] = fs_op_id
        for k, v in base_result.items():
            if k not in result:
                result[k] = v
        result["dry_run"] = effective_dry_run
        result["apply"] = apply and not dry_run
        return result
    finally:
        if own:
            conn.close()
