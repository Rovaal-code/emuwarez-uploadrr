"""Season pack: one single upload release for a whole Temporada row.

Ports (does not rewrite) legacy.py::build_plan()'s `season_pack` branch to
the modern service layer: each available episode gets its own individually
correct nomenclature-adapted filename (reusing
nomenclature.py::build_nomenclature_proposal() as-is — already computes
real codec/audio/provider per Phases 6A/6E), but every episode is
hardlinked into ONE shared season folder, and the pack gets ONE overall
title (using the first available episode's own metadata as representative,
same as legacy). services/uploadrr_contract.py::build_uploadrr_emu_command()
already supports this exact shape (season set, episode=None -> only
`-season Sxx`, never `-episode`) — nothing there needs to change.

SAFETY CONTRACT: identical to filesystem_apply.py — this module never
renames/moves/deletes a source file. It only calls the existing generic
build_safe_apply_plan()/apply_hardlink_plan() primitives once per episode.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from ..database import connect, row_to_dict
from ..models import LocalStatus
from .filesystem_apply import apply_hardlink_plan, build_safe_apply_plan
from .nomenclature import (
    _get_hardlink_base,
    _get_release_tag,
    build_nomenclature_proposal,
)
from .upload_preflight import JOB_STATUS_READY, save_upload_job_preflight

CONFIRMATION_TOKEN = "APLICAR_SEASON_PACK"


def _get_season_row(season_id: int, conn) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM library_items WHERE id = ? AND item_type = 'season'", (season_id,)
    ).fetchone()
    return row_to_dict(row)


def _get_series_row(series_id: int, conn) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM library_items WHERE id = ? AND item_type = 'series'", (series_id,)
    ).fetchone()
    return row_to_dict(row)


def _get_season_episodes(season_id: int, conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode' "
        "ORDER BY episode_number",
        (season_id,),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def _build_season_pack_title(
    *,
    title: str,
    year: Optional[int],
    season_number: Optional[int],
    resolution: Optional[str],
    source: Optional[str],
    video_codec: Optional[str],
    audio_summary: Optional[str],
    subtitle_summary: Optional[str],
    release_tag: Optional[str],
) -> str:
    """Modern equivalent of legacy.py::build_emu_title(..., pack=True) — one
    representative title for the whole pack (season only, no per-episode
    numbering)."""
    prefix = f"{title} S{season_number:02d}" if season_number is not None else title
    parts = [prefix]
    if year:
        parts.append(str(year))
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
    text = " ".join(p for p in parts if p)
    return f"{text}-{release_tag}" if release_tag else text


def build_season_pack_plan(season_id: int, conn=None) -> dict[str, Any]:
    """Build a dry-run plan for a season-pack upload. Never modifies the
    filesystem."""
    own = conn is None
    conn = conn or connect()
    try:
        empty = {
            "status": "blocked", "errors": [], "warnings": [],
            "season_pack_title": None, "hardlink_base": None,
            "hardlink_folder": None, "episodes": [],
        }

        season = _get_season_row(season_id, conn=conn)
        if not season:
            empty["errors"] = ["Temporada no encontrada."]
            return empty

        series = _get_series_row(season["parent_id"], conn=conn) if season.get("parent_id") else None
        series_title = (series or {}).get("title") or season.get("title") or "Serie"
        year = (series or {}).get("year") or season.get("year")

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available_episodes = [e for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]

        warnings: list[str] = []
        errors: list[str] = []

        if not available_episodes:
            errors.append("La temporada no tiene ningún episodio disponible.")
            empty["errors"] = errors
            return empty

        if len(available_episodes) < len(all_episodes):
            warnings.append(
                f"Temporada incompleta: {len(available_episodes)} de {len(all_episodes)} "
                "episodios disponibles; el pack solo incluirá los disponibles."
            )

        hardlink_base = _get_hardlink_base(conn=conn)
        if not hardlink_base:
            errors.append("hardlink_base no configurado. Configura la ruta de subidas en ajustes.")
            empty["errors"] = errors
            empty["warnings"] = warnings
            return empty

        # Per-episode proposals — reused as-is, already compute real
        # codec/audio/provider (Phases 6A/6E), not recomputed here.
        episode_entries = []
        for ep in available_episodes:
            proposal = build_nomenclature_proposal(ep["id"], conn=conn)
            episode_entries.append({"episode": ep, "proposal": proposal})

        first_proposal = episode_entries[0]["proposal"]
        release_tag = _get_release_tag(conn=conn)
        season_pack_title = _build_season_pack_title(
            title=series_title,
            year=year,
            season_number=season.get("season_number"),
            resolution=first_proposal.get("resolution"),
            source=first_proposal.get("source"),
            video_codec=first_proposal.get("video_codec"),
            audio_summary=first_proposal.get("audio_summary"),
            subtitle_summary=first_proposal.get("subtitle_summary"),
            release_tag=release_tag,
        )

        series_folder_name = f"{series_title} ({year})" if year else series_title
        hardlink_folder = os.path.join(hardlink_base, series_folder_name, season_pack_title)

        episodes_out = []
        for entry in episode_entries:
            ep = entry["episode"]
            proposal = entry["proposal"]
            source_path = ep.get("path")
            proposed_filename = proposal.get("proposed_filename") or ep.get("title") or f"episode-{ep['id']}"
            ext = ""
            if source_path and os.path.isfile(source_path):
                ext = os.path.splitext(source_path)[1]
            destination_path = os.path.join(hardlink_folder, proposed_filename + ext)
            episodes_out.append({
                "episode_id": ep["id"],
                "title": ep.get("title"),
                "episode_number": ep.get("episode_number"),
                "source_path": source_path,
                "destination_path": destination_path,
                "proposed_filename": proposed_filename,
            })

        status = "blocked" if errors else ("warning" if warnings else "valid")

        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "season_pack_title": season_pack_title,
            "hardlink_base": hardlink_base,
            "hardlink_folder": hardlink_folder,
            "episodes": episodes_out,
            # Not part of the public API schema (SeasonPackPlanResponse
            # doesn't declare these) — used internally to build the
            # upload_jobs row's Uploadrr command once applied for real.
            "season_number": season.get("season_number"),
            "resolution": first_proposal.get("resolution"),
            "tmdb_id": (series or {}).get("tmdb_id"),
        }
    finally:
        if own:
            conn.close()


def apply_season_pack(
    season_id: int,
    *,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: Optional[str] = None,
    conn=None,
) -> dict[str, Any]:
    """Apply (or dry-run) a season-pack hardlink plan — one hardlink per
    available episode into a single shared season folder. Never modifies
    or deletes an original episode file; loops the existing single-file
    build_safe_apply_plan()/apply_hardlink_plan() primitives unchanged."""
    own = conn is None
    conn = conn or connect()
    try:
        if dry_run:
            apply = False

        plan = build_season_pack_plan(season_id, conn=conn)

        base_result = {
            "dry_run": dry_run,
            "apply": apply,
            "season_pack_title": plan.get("season_pack_title"),
            "hardlink_folder": plan.get("hardlink_folder"),
            "warnings": plan.get("warnings", []),
            "errors": list(plan.get("errors", [])),
            "episodes": [],
        }

        if plan["status"] == "blocked":
            base_result["status"] = "blocked"
            base_result["message"] = "Plan bloqueado. Ver errors."
            return base_result

        if apply and not dry_run:
            if confirmation != CONFIRMATION_TOKEN:
                base_result["status"] = "blocked"
                base_result["errors"] = base_result["errors"] + [
                    f"Para aplicar cambios reales debes confirmar escribiendo '{CONFIRMATION_TOKEN}'."
                ]
                return base_result

        hardlink_base = plan["hardlink_base"]
        episode_results = []
        any_blocked = False
        any_failed = False
        for ep in plan["episodes"]:
            file_plan = build_safe_apply_plan(ep["source_path"] or "", ep["destination_path"], hardlink_base)
            result = apply_hardlink_plan(file_plan, dry_run=dry_run)
            episode_results.append({
                "episode_id": ep["episode_id"],
                "title": ep["title"],
                "destination_path": ep["destination_path"],
                "status": result["status"],
                "message": result.get("message"),
                "errors": result.get("errors", []),
            })
            if result["status"] == "blocked":
                any_blocked = True
            elif result["status"] == "failed":
                any_failed = True

        base_result["episodes"] = episode_results
        if any_failed:
            base_result["status"] = "failed"
            base_result["message"] = "Algunos episodios fallaron al aplicar. Ver episodes."
        elif any_blocked:
            base_result["status"] = "blocked"
            base_result["message"] = "Algunos episodios están bloqueados. Ver episodes."
        elif dry_run:
            base_result["status"] = "ready"
            base_result["message"] = f"Dry-run: se crearían {len(episode_results)} hardlinks en '{plan['hardlink_folder']}'."
        else:
            base_result["status"] = "applied"
            base_result["message"] = f"{len(episode_results)} hardlinks creados en '{plan['hardlink_folder']}'."
            job = _create_season_pack_upload_job(season_id, plan, conn=conn)
            base_result["upload_job_id"] = job.get("id")

        return base_result
    finally:
        if own:
            conn.close()


def _create_season_pack_upload_job(season_id: int, plan: dict[str, Any], *, conn) -> dict:
    """Create a normal upload_jobs row for the season pack — library_item_id
    points at the SEASON row itself (already a real library_items row,
    zero schema change), prepared_path is the shared season folder.
    build_uploadrr_execution_command() (upload_execution.py) already reads
    season/episode/category/tmdb_id/resolution/title from this job's own
    stored uploadrr_command_json — nothing there needs to change, this just
    has to store that shape correctly."""
    command_data = {
        "category": "tv",
        "title": plan.get("season_pack_title"),
        "tmdb_id": plan.get("tmdb_id"),
        "resolution": plan.get("resolution"),
        "season": plan.get("season_number"),
        "episode": None,
    }
    now = datetime.now(timezone.utc).isoformat()
    return save_upload_job_preflight(
        {
            "library_item_id": season_id,
            "status": JOB_STATUS_READY,
            "stage": "preflight",
            "title": plan.get("season_pack_title") or "Season pack",
            "source_path": plan.get("hardlink_folder"),
            "uploadrr_command_json": json.dumps(command_data, ensure_ascii=False),
            "preflight_json": json.dumps({"season_pack": True, "created_at": now}, ensure_ascii=False),
        },
        conn=conn,
    )
