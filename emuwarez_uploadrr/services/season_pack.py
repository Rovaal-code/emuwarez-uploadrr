"""Season pack: one single upload release for a whole Temporada row.

Ports (does not rewrite) legacy.py::build_plan()'s `season_pack` branch to
the modern service layer: each available episode gets its own individually
correct nomenclature-adapted filename (reusing
nomenclature.py::build_nomenclature_proposal() as-is — already computes
real codec/audio/provider per Phases 6A/6E), and the pack gets ONE overall
title (using the first available episode's own metadata as representative,
same as legacy). services/uploadrr_contract.py::build_uploadrr_emu_command()
already supports this exact shape (season set, episode=None -> only
`-season Sxx`, never `-episode`) — nothing there needs to change.

A pack requires every available episode to already live in the same
directory (the common Sonarr/Radarr convention: one folder per season) —
that shared folder becomes the pack folder and each episode is renamed in
place there, same technique nomenclature.py uses for a single file. There
is no way to unify episodes scattered across different folders into one
pack; the folder they already share IS the pack folder.

The whole season is required to be consistent (same video/audio codec,
audio/subtitle languages, resolution, source across every available
episode) and complete (every episode of the season must be Disponible) —
both are hard blocks, not warnings, since a mismatched or partial pack
would be a broken release.

SAFETY CONTRACT: identical to filesystem_apply.py — this module never
moves/deletes a source file, only renames it in place. It only calls the
existing generic build_safe_rename_plan()/apply_rename_plan() primitives
once per episode. Confirmation-token gating for a REAL apply happens once,
server-side, in services/upload_queue.py (same as the single-file
nomenclature step) — this module has no confirmation token of its own.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from ..database import connect, row_to_dict
from ..models import LocalStatus
from .filesystem_apply import apply_rename_plan, build_safe_rename_plan
from .nomenclature import (
    _get_release_tag,
    build_nomenclature_proposal,
)

# Progress reporting while build_season_pack_plan() churns through episodes
# (each one calls build_nomenclature_proposal, real work) — same in-memory
# dict+lock pattern as upload_checks.py's _CHECKS_PROGRESS, keyed by
# season_id so the wizard can poll "Comprobando N de M capítulos…" while a
# single slow request is in flight.
_PLAN_LOCK = threading.Lock()
_PLAN_PROGRESS: dict[int, dict] = {}


def get_season_plan_progress(season_id: int) -> dict:
    with _PLAN_LOCK:
        return dict(_PLAN_PROGRESS.get(season_id, {"done": 0, "total": 0, "current_title": None}))


def _set_season_plan_progress(season_id: int, *, done: int, total: int, current_title: Optional[str] = None) -> None:
    with _PLAN_LOCK:
        _PLAN_PROGRESS[season_id] = {"done": done, "total": total, "current_title": current_title}


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


# The 6 properties every available episode of a season pack must share.
# Compared on the RAW library_items columns (not the nomenclature
# proposal's already-combined display strings like audio_summary) for
# video_codec/audio_codec/audio_languages/subtitle_languages, and on the
# proposal's own resolved values for resolution/source (each episode's
# proposal already ran _infer_resolution_from_item/_infer_source_from_item).
_CONSISTENCY_FIELDS: list[tuple[str, str, Any]] = [
    ("video_codec", "códec de vídeo", lambda ep, prop: ep.get("video_codec")),
    ("audio_codec", "códec de audio", lambda ep, prop: ep.get("audio_codec")),
    ("audio_languages", "idiomas de audio", lambda ep, prop: ep.get("audio_languages")),
    ("subtitle_languages", "idiomas de subtítulos", lambda ep, prop: ep.get("subtitle_languages")),
    ("resolution", "resolución", lambda ep, prop: prop.get("resolution")),
    ("source", "source", lambda ep, prop: prop.get("source")),
]


def _consistency_errors(episode_entries: list[dict]) -> list[str]:
    """One message per (episode, field) that doesn't match the first
    available episode's value — names the differing episode so the user
    knows exactly what to fix."""
    if len(episode_entries) < 2:
        return []
    baseline_ep, baseline_prop = episode_entries[0]["episode"], episode_entries[0]["proposal"]
    errors: list[str] = []
    for _key, label, getter in _CONSISTENCY_FIELDS:
        baseline = getter(baseline_ep, baseline_prop)
        for entry in episode_entries[1:]:
            ep, prop = entry["episode"], entry["proposal"]
            value = getter(ep, prop)
            if value != baseline:
                errors.append(
                    f"El capítulo {ep.get('episode_number')} tiene {label} distinto "
                    f"({value or 'desconocido'}) al del capítulo {baseline_ep.get('episode_number')} "
                    f"({baseline or 'desconocido'})."
                )
    return errors


def build_season_pack_plan(
    season_id: int, conn=None,
    source_override: str | None = None, provider_override: str | None = None,
) -> dict[str, Any]:
    """Build a dry-run plan for a season-pack upload. Never modifies the
    filesystem. Blocks (status="blocked") on: season not found, no episode
    available, episodes not all in the same folder, incomplete season, or
    an episode-vs-episode consistency mismatch — a season pack has no
    "warning, upload anyway" state, unlike a single file.

    `source_override`/`provider_override` (set by the automated-upload
    source-disparity gate once the user picks by hand) are applied to every
    episode's own proposal — a pack requires every episode to share the same
    source anyway, so the override applies uniformly."""
    own = conn is None
    conn = conn or connect()
    try:
        empty = {
            "status": "blocked", "errors": [], "warnings": [],
            "season_pack_title": None, "pack_folder": None, "episodes": [],
        }

        season = _get_season_row(season_id, conn=conn)
        if not season:
            empty["errors"] = ["Temporada no encontrada."]
            return empty

        series = _get_series_row(season["parent_id"], conn=conn) if season.get("parent_id") else None
        series_title = (series or {}).get("title") or season.get("title") or "Serie"
        year = (series or {}).get("year") or season.get("year")

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available_ids = {
            e["id"] for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value
        }
        available_episodes = [e for e in all_episodes if e["id"] in available_ids]

        errors: list[str] = []

        if not available_episodes:
            errors.append("La temporada no tiene ningún episodio disponible.")
            empty["errors"] = errors
            return empty

        # Blocking (not just warning): an incomplete pack would silently
        # upload a partial season as if it were the whole thing.
        if len(available_episodes) < len(all_episodes):
            missing = sorted(
                e.get("episode_number") for e in all_episodes
                if e["id"] not in available_ids and e.get("episode_number") is not None
            )
            errors.append(
                f"Temporada incompleta: faltan {len(all_episodes) - len(available_episodes)} "
                f"episodio(s) por estar Disponible(s)"
                + (f" (capítulo(s) {', '.join(str(m) for m in missing)})" if missing else "") + "."
            )
            empty["errors"] = errors
            return empty

        # A season pack needs ONE shared destination folder: every available
        # episode must already live in the same directory (the common
        # Sonarr/Radarr convention: one folder per season) — that shared
        # folder becomes the pack folder and each episode is renamed in
        # place there, same technique the single-file path uses.
        # Radarr/Sonarr-reported paths (raw convention, e.g. /data/media/…)
        # need mapping to where this app actually reaches the file (e.g. an
        # SSHFS/NFS mount) for every real filesystem check/operation — same
        # convention nomenclature.py::build_nomenclature_apply_plan follows
        # for a single file. Resolved once per episode, reused below.
        from .path_mapping import resolve_local_path
        local_paths: dict[int, Optional[str]] = {
            e["id"]: (resolve_local_path(e.get("path"), conn=conn) or e.get("path"))
            for e in available_episodes
        }

        dirs = {os.path.dirname(p or "") for p in local_paths.values()}
        dirs.discard("")
        if len(dirs) != 1:
            errors.append(
                "Los episodios de esta temporada no están todos en la misma carpeta, así que no "
                "se puede unificar el pack. Muévelos a una carpeta común."
            )
            empty["errors"] = errors
            return empty
        common_dir = next(iter(dirs))
        if not os.access(common_dir, os.W_OK):
            errors.append(f"La carpeta de los episodios no es escribible: {common_dir}")
            empty["errors"] = errors
            return empty

        # Per-episode proposals — reused as-is, already compute real
        # codec/audio/provider (Phases 6A/6E), not recomputed here. Progress
        # published as each one completes so the wizard can show "Comprobando
        # N de M capítulos…" while this (possibly slow) request is in flight.
        total = len(available_episodes)
        _set_season_plan_progress(season_id, done=0, total=total)
        episode_entries = []
        for i, ep in enumerate(available_episodes):
            proposal = build_nomenclature_proposal(
                ep["id"], conn=conn,
                source_override=source_override, provider_override=provider_override,
            )
            episode_entries.append({"episode": ep, "proposal": proposal})
            _set_season_plan_progress(season_id, done=i + 1, total=total, current_title=ep.get("title"))

        errors.extend(_consistency_errors(episode_entries))

        first_proposal = episode_entries[0]["proposal"]
        release_tag = _get_release_tag(conn=conn)

        # Provider: each episode's own proposal already tried the filename
        # first (nomenclature.py's _infer_provider_from_item); if NONE
        # revealed one and the source is WEB-DL, ONE TMDb lookup for the
        # whole season — not repeated per episode.
        provider = first_proposal.get("provider_final")
        if not provider and (first_proposal.get("source") or "").upper() == "WEB-DL":
            from .source_assistant import suggest_provider_for_item
            suggestion = suggest_provider_for_item(available_episodes[0]["id"], conn=conn)
            provider = suggestion.get("suggested")

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

        # Rename-in-place: the episodes' own shared folder IS the pack folder,
        # nothing gets copied anywhere.
        pack_folder = common_dir

        episodes_out = []
        for entry in episode_entries:
            ep = entry["episode"]
            proposal = entry["proposal"]
            raw_source_path = ep.get("path")
            source_path = local_paths.get(ep["id"]) or raw_source_path
            proposed_filename = proposal.get("proposed_filename") or ep.get("title") or f"episode-{ep['id']}"
            ext = ""
            if source_path and os.path.isfile(source_path):
                ext = os.path.splitext(source_path)[1]
            destination_path = os.path.join(pack_folder, proposed_filename + ext)
            # Same raw dirname as the original (Radarr/Sonarr-reported) path —
            # what library_items.path should be updated to after the in-place
            # rename, mirroring nomenclature.py's raw_destination_path
            # convention for a single file, so future path-mapping stays
            # consistent.
            raw_destination_path = (
                os.path.join(os.path.dirname(raw_source_path), proposed_filename + ext)
                if raw_source_path else None
            )
            episodes_out.append({
                "episode_id": ep["id"],
                "title": ep.get("title"),
                "episode_number": ep.get("episode_number"),
                "source_path": source_path,
                "raw_source_path": raw_source_path,
                "raw_destination_path": raw_destination_path,
                "destination_path": destination_path,
                "proposed_filename": proposed_filename,
            })

        status = "blocked" if errors else "valid"

        return {
            "status": status,
            "errors": errors,
            "warnings": [],
            "season_pack_title": season_pack_title,
            "pack_folder": pack_folder,
            "episodes": episodes_out,
            # Not part of the public API schema — used internally to build
            # the upload_jobs row's Uploadrr command once queued for real
            # (services/upload_queue.py's season branch).
            "season_number": season.get("season_number"),
            "resolution": first_proposal.get("resolution"),
            "source": first_proposal.get("source"),
            "tmdb_id": (series or {}).get("tmdb_id"),
            "provider": provider,
            # Rest of the field breakdown used to build season_pack_title,
            # kept on the return dict so a caller (upload_queue.py) can
            # snapshot the full nomenclature breakdown for the job detail
            # page, not just the pieces build_season_pack_plan itself needs.
            "video_codec": first_proposal.get("video_codec"),
            "audio_summary": first_proposal.get("audio_summary"),
            "subtitle_summary": first_proposal.get("subtitle_summary"),
            "release_tag": release_tag,
            "series_title": series_title,
            "year": year,
        }
    finally:
        if own:
            conn.close()


def apply_season_pack(season_id: int, conn, *, job_id: int | None = None) -> dict[str, Any]:
    """Rename every available episode in place to its final pack filename AND
    record each episode's prepared_path on its own library_items row —
    mirrors what nomenclature.py::apply_nomenclature_proposal does for a
    single file right after its own apply_rename_plan() call. Without this
    UPDATE, mkv_remux._get_target_path (which reads library_items.
    prepared_path) can't find the file at its new path, and the remux step
    that runs right after this one in upload_queue.py would either touch the
    original source file (breaks the never-touch-the-original contract) or
    fail to find anything to remux.

    No confirmation-token gate here — the caller (upload_queue.py) already
    gates the whole prep sequence once, same as it does for a single file's
    apply_nomenclature_proposal call."""
    plan = build_season_pack_plan(season_id, conn=conn)
    if plan["status"] != "valid":
        return {
            "status": "blocked", "errors": plan["errors"], "episodes": [],
            "pack_folder": plan.get("pack_folder"),
            "season_pack_title": plan.get("season_pack_title"),
        }

    now = datetime.now(timezone.utc).isoformat()
    episode_results = []
    any_failed = False
    total = len(plan["episodes"])
    for idx, ep in enumerate(plan["episodes"]):
        if job_id is not None:
            from .upload_execution import append_upload_log
            append_upload_log(
                job_id, "info",
                f"Aplicando nomenclatura: capítulo {ep.get('episode_number')} ({idx + 1}/{total})…",
                stream="system", conn=conn,
            )
        file_plan = build_safe_rename_plan(ep["source_path"] or "", ep["destination_path"])
        result = apply_rename_plan(file_plan, dry_run=False)
        episode_results.append({
            "episode_id": ep["episode_id"],
            "title": ep["title"],
            "destination_path": ep["destination_path"],
            "status": result["status"],
            "message": result.get("message"),
            "errors": result.get("errors", []),
        })
        if result["status"] == "applied":
            # The original file was moved (renamed in place) — `path` must
            # follow it too (raw convention), same as nomenclature.py's
            # single-file rename branch.
            raw_dst = ep.get("raw_destination_path") or ep["destination_path"]
            conn.execute(
                "UPDATE library_items SET path = ?, prepared_path = ?, "
                "nomenclature_applied_at = ?, nomenclature_status = 'Correcta' WHERE id = ?",
                (raw_dst, ep["destination_path"], now, ep["episode_id"]),
            )
        else:
            any_failed = True
    conn.commit()

    return {
        "status": "failed" if any_failed else "applied",
        "errors": [] if not any_failed else ["Algunos episodios fallaron al renombrar. Ver episodes."],
        "episodes": episode_results,
        "pack_folder": plan["pack_folder"],
        "season_pack_title": plan.get("season_pack_title"),
        # Full field breakdown, for the job detail page's nomenclature
        # snapshot — mirrors what apply_nomenclature_proposal()'s "proposal"
        # already carries for a single file.
        "series_title": plan.get("series_title"),
        "year": plan.get("year"),
        "season_number": plan.get("season_number"),
        "tmdb_id": plan.get("tmdb_id"),
        "resolution": plan.get("resolution"),
        "source": plan.get("source"),
        "provider": plan.get("provider"),
        "video_codec": plan.get("video_codec"),
        "audio_summary": plan.get("audio_summary"),
        "subtitle_summary": plan.get("subtitle_summary"),
        "release_tag": plan.get("release_tag"),
    }


def get_season_episode_names(season_id: int, conn=None) -> dict:
    """Per-episode final torrent name + internal MKV title — backs the
    wizard's "Ver nombre de todos los capítulos" button (a season pack has
    no single "título del archivo interno", each episode file has its own)."""
    own = conn is None
    conn = conn or connect()
    try:
        from .source_assistant import build_editable_nomenclature_fields

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available = [e for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
        out = []
        for ep in available:
            fields = build_editable_nomenclature_fields(ep["id"], conn=conn)
            blocked = bool(fields.get("blocked"))
            out.append({
                "episode_id": ep["id"],
                "episode_number": ep.get("episode_number"),
                "title": ep.get("title"),
                "torrent_name": None if blocked else fields.get("torrent_name"),
                "internal_mkv_title": None if blocked else fields.get("internal_mkv_title"),
                "error": fields.get("error") if blocked else None,
            })
        return {"episodes": out}
    finally:
        if own:
            conn.close()


def get_season_episode_mediainfo(season_id: int, conn=None) -> dict:
    """Per-episode MediaInfo report — backs the wizard's "Ver MediaInfo"
    dropdown for a season target."""
    own = conn is None
    conn = conn or connect()
    try:
        from .media_info_service import build_mediainfo_report
        from .path_mapping import resolve_local_path
        from .source_assistant import build_editable_nomenclature_fields

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available = [e for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
        out = []
        # Name vs Radarr/Sonarr vs MediaInfo-bitrate cross-check (the
        # "Internal Source Tool" blinking link movies get) — computed ONCE,
        # from the first available episode, and reused for every episode
        # below. A season pack can only ever reach this screen when every
        # episode already agrees on source (build_season_pack_plan's
        # consistency check blocks the upload otherwise), so recomputing
        # this per episode would be redundant and re-run the engine's
        # (potentially slow) analysis needlessly.
        source_comparison = None
        if available:
            source_comparison = build_editable_nomenclature_fields(
                available[0]["id"], conn=conn,
            ).get("source_comparison")
        for ep in available:
            # Prefer prepared_path over the raw path — same convention
            # nomenclature.py/mkv_remux.py/mkv_title.py already follow: once
            # nomenclature has been applied before (e.g. a prior retry),
            # `path` may be stale (still the pre-rename name) while
            # prepared_path is the real current file. Reading raw `path`
            # here showed a stale Source (e.g. "WEBRIP" from the original
            # name) that disagreed with the actually-applied name (e.g.
            # "BluRay", from prepared_path) shown everywhere else.
            candidate_path = ep.get("prepared_path") or ep.get("path")
            local_path = resolve_local_path(candidate_path, conn=conn) or candidate_path
            report = build_mediainfo_report(local_path or "")
            out.append({
                "episode_id": ep["id"],
                "episode_number": ep.get("episode_number"),
                "title": ep.get("title"),
                "report": report,
                "source_comparison": source_comparison,
            })
        return {"episodes": out}
    finally:
        if own:
            conn.close()


def get_season_episode_remux_previews(season_id: int, conn=None) -> dict:
    """Per-episode track remux plan — backs the wizard's "Ver Remux"
    dropdown for a season target. Read-only preview only: manual per-track
    overrides aren't offered for season packs (each episode gets its own
    auto-computed plan applied as-is during the queued upload)."""
    own = conn is None
    conn = conn or connect()
    try:
        from .mkv_remux import build_remux_plan

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available = [e for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
        out = []
        for ep in available:
            plan = build_remux_plan(ep["id"], conn=conn)
            out.append({
                "episode_id": ep["id"],
                "episode_number": ep.get("episode_number"),
                "title": ep.get("title"),
                "plan": plan,
            })
        return {"episodes": out}
    finally:
        if own:
            conn.close()
