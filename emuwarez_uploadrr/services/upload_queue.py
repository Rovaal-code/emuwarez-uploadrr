"""Queued upload orchestration.

Clicking "Subir a eMuwarez" no longer runs rename/remux/preflight/start
synchronously in the browser request — it creates an upload_jobs row in
status='queued' and returns immediately, so the UI can jump straight to
Subidas and watch it. The row sits queued for QUEUE_GRACE_SECONDS (a
cancel-if-you-regret-it window) before a background timer runs the real
work — integrity check, nomenclature rename, track remux, then handing off
to upload_execution.start_upload_job() — all against that SAME job row, so
what the user is watching in Subidas is the actual job, not a stand-in.

SAFETY CONTRACT: same as nomenclature.py / mkv_remux.py / upload_execution.py
— every real filesystem/subprocess step still goes through their own
confirmation-token-gated apply functions; this module only orchestrates them
in sequence and records progress/failure on the job row.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from ..database import connect, row_to_dict

logger = logging.getLogger("emuwarez.upload")

QUEUE_GRACE_SECONDS = 60

# job_id -> pending threading.Timer, so a cancel during the grace period can
# stop it before it fires. job_id -> remux overrides the user edited in the
# wizard's "Ver Remux" card, applied when the remux step actually runs.
# Single-process app, in-memory is enough (matches upload_checks.py's pattern).
_LOCK = threading.Lock()
_QUEUE_TIMERS: dict[int, threading.Timer] = {}
_PENDING_REMUX_OVERRIDES: dict[int, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue_upload_for_item(item_id: int, *, remux_overrides: dict | None = None, conn=None) -> dict:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        item = row_to_dict(row)
        if not item:
            return {"status": "blocked", "errors": ["Item no encontrado."], "job": None}

        now = datetime.now(timezone.utc)
        queued_until = (now + timedelta(seconds=QUEUE_GRACE_SECONDS)).isoformat()
        now_iso = now.isoformat()

        cursor = conn.execute(
            """
            INSERT INTO upload_jobs (
                library_item_id, status, stage, title, path, source_path,
                queued_until, created_at, updated_at
            ) VALUES (?, 'queued', 'queued', ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                item.get("title") or "Sin título",
                item.get("path") or "",
                item.get("path"),
                queued_until,
                now_iso, now_iso,
            ),
        )
        conn.commit()
        job_id = cursor.lastrowid

        with _LOCK:
            if remux_overrides:
                _PENDING_REMUX_OVERRIDES[job_id] = remux_overrides
            timer = threading.Timer(QUEUE_GRACE_SECONDS, _run_queued_job, args=(job_id,))
            timer.daemon = True
            _QUEUE_TIMERS[job_id] = timer
        timer.start()

        from .upload_execution import get_upload_job
        return {"status": "queued", "job": get_upload_job(job_id, conn=conn)}
    finally:
        if own:
            conn.close()


def cancel_queued_timer(job_id: int) -> bool:
    """Stop a still-pending grace-period timer. Returns whether one was
    found (False just means it already fired or never existed — callers
    still flip the job's status regardless)."""
    with _LOCK:
        timer = _QUEUE_TIMERS.pop(job_id, None)
        _PENDING_REMUX_OVERRIDES.pop(job_id, None)
    if timer:
        timer.cancel()
        return True
    return False


def _mark(job_id: int, *, stage: str, status: str = "preparing", **extra) -> None:
    conn = connect()
    try:
        fields = {"status": status, "stage": stage, "updated_at": _now_iso(), **extra}
        set_clauses = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [job_id]
        conn.execute(f"UPDATE upload_jobs SET {set_clauses} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def _fail(job_id: int, message: str) -> None:
    from .upload_execution import append_upload_log
    conn = connect()
    try:
        conn.execute(
            "UPDATE upload_jobs SET status = 'failed', stage = 'failed', "
            "error_message = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            (message, _now_iso(), _now_iso(), job_id),
        )
        conn.commit()
        append_upload_log(job_id, "error", message, stream="system", conn=conn)
    finally:
        conn.close()
    logger.warning("Job %s en cola falló durante la preparación: %s", job_id, message)


def _season_upload_preconditions(conn) -> list[str]:
    """The generic (not season-specific) preconditions
    upload_preflight.validate_upload_preconditions() checks for a single
    file — uploadrr path/script + eMuwarez/TMDb API keys. Season-specific
    concerns (episodes consistent, complete, hardlink_base configured) are
    already covered by build_season_pack_plan() before this ever runs."""
    from ..database import get_setting_canonical
    from .uploadrr_contract import DEFAULT_UPLOADRR_PATH

    errors: list[str] = []
    uploadrr_path = get_setting_canonical(conn, "uploadrr.path") or DEFAULT_UPLOADRR_PATH
    if not uploadrr_path:
        errors.append("Ruta de Uploadrr no configurada (uploadrr.path).")
    elif not os.path.exists(uploadrr_path):
        errors.append(f"Ruta de Uploadrr no existe: {uploadrr_path}")
    if not get_setting_canonical(conn, "emu.api_key"):
        errors.append("API key de eMuwarez no configurada.")
    if not get_setting_canonical(conn, "tmdb.api_key"):
        errors.append("API key de TMDb no configurada.")
    return errors


def _populate_ready(job_id: int, item_id: int, conn) -> bool:
    """Recompute preconditions + command preview NOW (after rename/remux, so
    prepared_path reflects the final file) and, if ok, flip the SAME job row
    to 'ready' — mirrors upload_preflight.build_upload_preflight() but UPDATEs
    in place instead of inserting a second row."""
    from .upload_preflight import validate_upload_preconditions, build_uploadrr_command_preview

    row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    item = row_to_dict(row)
    if not item:
        _fail(job_id, "El elemento ya no existe en la biblioteca.")
        return False

    if item.get("item_type") == "season":
        # validate_upload_preconditions() hard-blocks on `if not path`, and a
        # season row has no `path` of its own (only its episodes do) — a
        # season-specific precondition check replaces it.
        from .season_pack import build_season_pack_plan

        plan = build_season_pack_plan(item_id, conn=conn)
        if plan["status"] != "valid":
            _fail(job_id, "; ".join(plan.get("errors") or ["No se pudo preparar el pack de temporada."]))
            return False

        errors = _season_upload_preconditions(conn)
        if errors:
            _fail(job_id, "; ".join(errors))
            return False

        # A synthetic item-like dict so build_uploadrr_command_preview() (and,
        # inside it, uploadrr_contract.validate_uploadrr_emu_contract) runs
        # the SAME safety checks (allowed_roots, python_path, script
        # existence) a single file's command preview gets, instead of
        # hand-building the command dict and skipping them.
        synthetic_item = {
            "path": None,
            "prepared_path": plan.get("hardlink_folder"),
            "item_type": "season",
            "title": plan.get("season_pack_title"),
            "tmdb_id": plan.get("tmdb_id"),
            "resolution": plan.get("resolution"),
            "season": plan.get("season_number"),
            "episode": None,
        }
        command_preview = build_uploadrr_command_preview(synthetic_item, None, None, conn=conn)
        conn.execute(
            "UPDATE upload_jobs SET status = 'ready', stage = 'preflight', "
            "prepared_path = ?, uploadrr_command_json = ?, error_message = NULL, updated_at = ? "
            "WHERE id = ?",
            (plan.get("hardlink_folder"), json.dumps(command_preview, ensure_ascii=False), _now_iso(), job_id),
        )
        conn.commit()
        return True

    proposal_row = conn.execute(
        "SELECT * FROM nomenclature_proposals WHERE library_item_id = ? AND status != 'expired' "
        "ORDER BY created_at DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    proposal = row_to_dict(proposal_row)

    preconditions = validate_upload_preconditions(item, proposal=proposal, conn=conn)
    if not preconditions["ok"]:
        _fail(job_id, "; ".join(preconditions["errors"]))
        return False

    command_preview = build_uploadrr_command_preview(item, proposal, None, conn=conn)
    conn.execute(
        "UPDATE upload_jobs SET status = 'ready', stage = 'preflight', "
        "prepared_path = ?, uploadrr_command_json = ?, error_message = NULL, updated_at = ? "
        "WHERE id = ?",
        (item.get("prepared_path"), json.dumps(command_preview, ensure_ascii=False), _now_iso(), job_id),
    )
    conn.commit()
    return True


def _check_season_integrity(job_id: int, season_id: int, conn) -> bool:
    """Season equivalent of the single-file integrity stage below — same
    three checks (accessible / MediaInfo reads it / mkvtoolnix reads it),
    run per available episode, failing with the specific episode's number
    so the user knows which file to fix."""
    from .season_pack import _get_season_episodes
    from .models import LocalStatus
    from .mkv_remux import check_mkvmerge_available, read_tracks_json
    from .media_info_service import mediainfo_available, read_media_info_summary
    from .path_mapping import resolve_local_path

    episodes = _get_season_episodes(season_id, conn=conn)
    available = [e for e in episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
    if not available:
        _fail(job_id, "La temporada no tiene ningún episodio disponible.")
        return False
    for ep in available:
        label = f"capítulo {ep.get('episode_number')}"
        ep_path = resolve_local_path(ep.get("path"), conn=conn) or ep.get("path")
        if not ep_path or not os.path.isfile(ep_path):
            _fail(job_id, f"El archivo del {label} no es accesible: {ep_path or ep.get('path') or '(sin ruta)'}")
            return False
        if mediainfo_available():
            info = read_media_info_summary(ep_path)
            if not info:
                _fail(job_id, f"MediaInfo no pudo leer el archivo del {label} (posible corrupción).")
                return False
        if ep_path.lower().endswith(".mkv") and check_mkvmerge_available().get("available"):
            tracks = read_tracks_json(ep_path)
            if not tracks.get("ok"):
                _fail(job_id, f"mkvtoolnix no pudo leer el archivo del {label}: {tracks.get('error') or 'error desconocido'}")
                return False
    return True


def _run_season_remux(job_id: int, season_id: int, conn) -> bool:
    """Season equivalent of the single-file remux stage below — loops
    build_remux_plan()/apply_remux() per available episode. No manual
    per-track overrides for season packs (out of scope for v1): each
    episode's own auto-computed plan is applied as-is."""
    from .season_pack import _get_season_episodes
    from .models import LocalStatus
    from .mkv_remux import build_remux_plan, apply_remux, REMUX_CONFIRMATION_TOKEN as REMUX_TOKEN

    episodes = _get_season_episodes(season_id, conn=conn)
    available = [e for e in episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
    for ep in available:
        label = f"capítulo {ep.get('episode_number')}"
        try:
            plan = build_remux_plan(ep["id"], conn=conn)
            if plan.get("status") == "ready":
                remuxed = apply_remux(
                    ep["id"], apply=True, dry_run=False,
                    confirmation=REMUX_TOKEN, overrides=None, conn=conn,
                )
                if remuxed.get("status") != "applied":
                    reason = "; ".join(remuxed.get("errors") or [])
                    _fail(job_id, f"No se pudieron reordenar/renombrar las pistas del {label}: {reason}")
                    return False
        except Exception as exc:
            _fail(job_id, f"Error reordenando/renombrando las pistas del {label}: {exc}")
            return False
    return True


def _run_queued_job(job_id: int) -> None:
    with _LOCK:
        _QUEUE_TIMERS.pop(job_id, None)
        overrides = _PENDING_REMUX_OVERRIDES.pop(job_id, None)

    from .upload_execution import get_upload_job, start_upload_job, append_upload_log
    from .upload_execution import CONFIRMATION_TOKEN as START_TOKEN
    from .nomenclature import apply_nomenclature_proposal, CONFIRMATION_TOKEN as NOM_TOKEN
    from .mkv_remux import (
        build_remux_plan, apply_remux, check_mkvmerge_available, read_tracks_json,
        REMUX_CONFIRMATION_TOKEN as REMUX_TOKEN,
    )
    from .media_info_service import mediainfo_available, read_media_info_summary
    from .path_mapping import resolve_local_path

    conn = connect()
    try:
        job = get_upload_job(job_id, conn=conn)
        if not job or job.get("status") != "queued":
            return  # cancelled during the grace period, or the job is gone
        item_id = job.get("library_item_id")
        if not item_id:
            _fail(job_id, "El job no tiene un elemento de biblioteca asociado.")
            return

        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        item = row_to_dict(row)
        if not item:
            _fail(job_id, "El elemento ya no existe en la biblioteca.")
            return
        is_season = item.get("item_type") == "season"

        # --- 1. Integrity: accessible, MediaInfo reads it, mkvtoolnix reads it.
        # These used to be separate pre-upload checks, but the nomenclature
        # and remux steps right below already invoke MediaInfo/mkvmerge on
        # each real file — running the check here means real (not
        # duplicated) work, and a failure lands with a specific reason
        # instead of a generic "no accesible".
        _mark(job_id, stage="integrity", started_at=_now_iso())
        append_upload_log(job_id, "info", "Comprobando integridad del archivo…", stream="system", conn=conn)
        if is_season:
            if not _check_season_integrity(job_id, item_id, conn=conn):
                return
        else:
            # Prefer prepared_path over the raw path — same convention
            # mkv_remux.py/mkv_title.py already use: once nomenclature has
            # been applied before, `path` may be stale (the original file
            # was renamed/hardlinked away) while prepared_path is the real
            # current file.
            candidate_path = item.get("prepared_path") or item.get("path")
            local_path = resolve_local_path(candidate_path) or candidate_path
            if not local_path or not os.path.isfile(local_path):
                _fail(job_id, f"El archivo no es accesible: {local_path or candidate_path or '(sin ruta)'}")
                return
            if mediainfo_available():
                info = read_media_info_summary(local_path)
                if not info:
                    _fail(job_id, "MediaInfo no pudo leer el fichero (posible corrupción).")
                    return
            if local_path.lower().endswith(".mkv") and check_mkvmerge_available().get("available"):
                tracks = read_tracks_json(local_path)
                if not tracks.get("ok"):
                    _fail(job_id, f"mkvtoolnix no pudo leer el fichero: {tracks.get('error') or 'error desconocido'}")
                    return

        # --- 2. Nomenclature (rename/hardlink to the final eMuwarez name).
        _mark(job_id, stage="nomenclature")
        append_upload_log(job_id, "info", "Aplicando nomenclatura…", stream="system", conn=conn)
        if is_season:
            from .season_pack import apply_season_hardlinks
            try:
                applied = apply_season_hardlinks(item_id, conn=conn)
            except Exception as exc:
                _fail(job_id, f"Error aplicando la nomenclatura del pack de temporada: {exc}")
                return
            if applied.get("status") != "applied":
                reason = "; ".join(applied.get("errors") or []) or "estado desconocido"
                _fail(job_id, f"No se pudo aplicar la nomenclatura del pack de temporada: {reason}")
                return
        else:
            try:
                applied = apply_nomenclature_proposal(
                    item_id, apply=True, dry_run=False, confirmation=NOM_TOKEN, conn=conn,
                )
            except Exception as exc:
                _fail(job_id, f"Error aplicando la nomenclatura: {exc}")
                return
            if applied.get("status") != "applied":
                reason = "; ".join(applied.get("errors") or []) or applied.get("message") or "estado desconocido"
                _fail(job_id, f"No se pudo aplicar la nomenclatura: {reason}")
                return

        # Best-effort: tell Radarr/Sonarr to rescan now, so its own DB picks
        # up the new filename immediately instead of only at its next
        # scheduled scan — otherwise a later "Sincronizar biblioteca" here
        # just re-imports the same stale path Radarr/Sonarr still has on
        # file. Never blocks the upload: logged either way, failure or not.
        from .library import trigger_arr_rescan
        rescan_result = trigger_arr_rescan(conn, item_id)
        if rescan_result.get("ok"):
            append_upload_log(job_id, "info", "Radarr/Sonarr avisado para que actualice la ficha.", stream="system", conn=conn)
        else:
            append_upload_log(
                job_id, "warning",
                f"No se pudo avisar a Radarr/Sonarr para que actualice la ficha: {rescan_result.get('message')}",
                stream="system", conn=conn,
            )

        # --- 3. Track remux (reorder + rename audio/subs), on the final path.
        _mark(job_id, stage="remux")
        append_upload_log(job_id, "info", "Reordenando/renombrando pistas…", stream="system", conn=conn)
        if is_season:
            if not _run_season_remux(job_id, item_id, conn=conn):
                return
        else:
            try:
                plan = build_remux_plan(item_id, conn=conn)
                if plan.get("status") == "ready":
                    remuxed = apply_remux(
                        item_id, apply=True, dry_run=False,
                        confirmation=REMUX_TOKEN, overrides=overrides, conn=conn,
                    )
                    if remuxed.get("status") != "applied":
                        reason = "; ".join(remuxed.get("errors") or [])
                        _fail(job_id, f"No se pudieron reordenar/renombrar las pistas: {reason}")
                        return
            except Exception as exc:
                _fail(job_id, f"Error reordenando/renombrando las pistas: {exc}")
                return

        # --- 4. Preflight (fresh preconditions + command preview) then start.
        _mark(job_id, stage="preflight")
        append_upload_log(job_id, "info", "Preparando la subida…", stream="system", conn=conn)
        if not _populate_ready(job_id, item_id, conn=conn):
            return  # _populate_ready already recorded the failure reason

        result = start_upload_job(job_id, dry_run=False, start=True, confirmation=START_TOKEN, conn=conn)
        if result.get("error"):
            _fail(job_id, result.get("message") or "; ".join(result.get("errors") or []) or "No se pudo iniciar la subida.")
    finally:
        conn.close()
