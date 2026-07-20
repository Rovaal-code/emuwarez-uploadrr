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

# A job in any of these statuses is still "alive" for its library item — a
# new "Subir"/automático click must not create an unrelated second job while
# one of these is in flight, it has to wait or be told to view the existing
# one instead.
ACTIVE_JOB_STATUSES = {"queued", "staging", "preparing", "running"}

# job_id -> pending threading.Timer, so a cancel during the grace period can
# stop it before it fires. job_id -> remux overrides the user edited in the
# wizard's "Ver Remux" card, applied when the remux step actually runs.
# Single-process app, in-memory is enough (matches upload_checks.py's pattern).
_LOCK = threading.Lock()
_QUEUE_TIMERS: dict[int, threading.Timer] = {}
_PENDING_REMUX_OVERRIDES: dict[int, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_latest_job_for_item(conn, item_id: int) -> dict | None:
    """The tip of this item's retry chain: the job nobody else's
    retry_of_job_id points at. Every "Subir"/Automático click chains onto
    this instead of creating an unrelated row, so the item's full upload
    activity (including past Completado attempts) stays in one place."""
    row = conn.execute(
        "SELECT * FROM upload_jobs WHERE library_item_id = ? "
        "AND id NOT IN (SELECT retry_of_job_id FROM upload_jobs "
        "WHERE retry_of_job_id IS NOT NULL) ORDER BY id DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    return row_to_dict(row)


def _insert_and_start_queued_job(
    conn, item: dict, *,
    request_item_id: int | None = None,
    retry_of_job_id: int | None = None,
    retry_count: int = 0,
    remux_overrides: dict | None = None,
    checks: dict | None = None,
) -> dict:
    """Shared by queue_upload_for_item() and queue_retry_for_job(): insert a
    fresh 'queued' row for `item` and arm its 60s grace-period timer.

    `checks` — the pre-upload checks result ({"checks": [...], "ready": bool})
    already computed by the manual wizard before the user confirmed, persisted
    verbatim as checks_snapshot_json so the job detail page can show exactly
    what the user saw and approved, without re-running anything."""
    now = datetime.now(timezone.utc)
    queued_until = (now + timedelta(seconds=QUEUE_GRACE_SECONDS)).isoformat()
    now_iso = now.isoformat()

    cursor = conn.execute(
        """
        INSERT INTO upload_jobs (
            library_item_id, request_item_id, status, stage, title, path, source_path,
            queued_until, retry_of_job_id, retry_count, checks_snapshot_json, created_at, updated_at
        ) VALUES (?, ?, 'queued', 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"], request_item_id,
            item.get("title") or "Sin título",
            item.get("path") or "",
            item.get("path"),
            queued_until,
            retry_of_job_id, retry_count,
            json.dumps(checks, ensure_ascii=False) if checks else None,
            now_iso, now_iso,
        ),
    )
    conn.commit()
    job_id = cursor.lastrowid

    with _LOCK:
        if remux_overrides:
            _PENDING_REMUX_OVERRIDES[job_id] = remux_overrides
    _arm_queue_timer(job_id)

    from .upload_execution import get_upload_job
    return {"status": "queued", "job": get_upload_job(job_id, conn=conn)}


def _arm_queue_timer(job_id: int) -> None:
    """Start the QUEUE_GRACE_SECONDS cancel-if-you-regret-it timer for a job
    already sitting in status='queued' — shared by a fresh
    _insert_and_start_queued_job() insert and by _run_staging_job() promoting
    an Automático job from 'staging' once its previews are ready."""
    timer = threading.Timer(QUEUE_GRACE_SECONDS, _run_queued_job, args=(job_id,))
    timer.daemon = True
    with _LOCK:
        _QUEUE_TIMERS[job_id] = timer
    timer.start()


def queue_upload_for_item(
    item_id: int, *, remux_overrides: dict | None = None, checks: dict | None = None, conn=None
) -> dict:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        item = row_to_dict(row)
        if not item:
            return {"status": "blocked", "errors": ["Item no encontrado."], "job": None}

        latest = _find_latest_job_for_item(conn, item_id)
        if latest and latest.get("status") in ACTIVE_JOB_STATUSES:
            return {
                "status": "blocked",
                "errors": ["Ya hay una subida en curso para este contenido."],
                "job": latest,
            }
        retry_of_job_id = latest["id"] if latest else None
        retry_count = (latest.get("retry_count") or 0) + 1 if latest else 0
        return _insert_and_start_queued_job(
            conn, item, remux_overrides=remux_overrides, checks=checks,
            retry_of_job_id=retry_of_job_id, retry_count=retry_count,
        )
    finally:
        if own:
            conn.close()


def queue_retry_for_job(original_job_id: int, conn=None) -> dict:
    """Re-queue a failed/cancelled job straight into the same 60s
    cancel-if-you-regret-it countdown a fresh "Subir a eMuwarez" click uses —
    no confirmation token, since this only ever creates a brand new job row
    (the original is never touched, same as the old confirmation-gated retry)."""
    own = conn is None
    conn = conn or connect()
    try:
        from .upload_execution import get_upload_job

        original = get_upload_job(original_job_id, conn=conn)
        if not original:
            return {"status": "blocked", "errors": ["Job original no encontrado."], "job": None}
        if original.get("status") not in ("failed", "cancelled"):
            return {"status": "blocked", "errors": ["Solo se puede reintentar un job fallido o cancelado."], "job": None}
        item_id = original.get("library_item_id")
        if not item_id:
            return {"status": "blocked", "errors": ["El job original no tiene un elemento de biblioteca asociado."], "job": None}

        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        item = row_to_dict(row)
        if not item:
            return {"status": "blocked", "errors": ["El elemento ya no existe en la biblioteca."], "job": None}

        return _insert_and_start_queued_job(
            conn, item,
            request_item_id=original.get("request_item_id"),
            retry_of_job_id=original_job_id,
            retry_count=(original.get("retry_count") or 0) + 1,
        )
    finally:
        if own:
            conn.close()


def _insert_staging_job(
    conn, item: dict, *, retry_of_job_id: int | None = None, retry_count: int = 0,
) -> int:
    """Insert a job in status='staging' — appears in Subidas immediately for
    an Automático upload, before anything is computed. No queued_until/timer
    yet: those only get armed once _run_staging_job() finishes the previews
    and promotes it to 'queued'.

    stage starts at 'nomenclature' — the first of the three staging
    sub-steps (nomenclature -> remux -> checks) _run_staging_job() works
    through; the dedicated job page uses (status, stage) to show a spinner
    next to whichever of its "Nomenclatura"/"Reordenación de pistas"/
    "Verificación pre-subida" sections is currently being computed."""
    now_iso = _now_iso()
    cursor = conn.execute(
        """
        INSERT INTO upload_jobs (
            library_item_id, status, stage, title, path, source_path,
            retry_of_job_id, retry_count, created_at, updated_at
        ) VALUES (?, 'staging', 'nomenclature', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"], item.get("title") or "Sin título",
            item.get("path") or "", item.get("path"),
            retry_of_job_id, retry_count, now_iso, now_iso,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def queue_auto_upload_for_item(
    item_id: int, conn=None,
    source_override: str | None = None, provider_override: str | None = None,
) -> dict:
    """"Automático" upload: skips the wizard entirely. The job appears right
    away in Subidas as 'staging' ("Preparando") while nomenclature/remux/
    checks previews are computed server-side in a background thread; once
    ready it's promoted into the normal 'queued' 60s countdown and proceeds
    exactly like a manual upload from there. Same duplicate-chaining rule as
    queue_upload_for_item().

    `source_override`/`provider_override` come from the frontend's
    source-disparity gate (checked right before this call, via
    source_assistant.py::check_auto_upload_source) — when the user had to
    pick a source by hand, that choice is forced into the nomenclature build
    instead of the usual automatic inference."""
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        item = row_to_dict(row)
        if not item:
            return {"status": "blocked", "errors": ["Item no encontrado."], "job": None}

        latest = _find_latest_job_for_item(conn, item_id)
        if latest and latest.get("status") in ACTIVE_JOB_STATUSES:
            return {
                "status": "blocked",
                "errors": ["Ya hay una subida en curso para este contenido."],
                "job": latest,
            }
        retry_of_job_id = latest["id"] if latest else None
        retry_count = (latest.get("retry_count") or 0) + 1 if latest else 0

        job_id = _insert_staging_job(conn, item, retry_of_job_id=retry_of_job_id, retry_count=retry_count)

        thread = threading.Thread(
            target=_run_staging_job, args=(job_id,),
            kwargs={"source_override": source_override, "provider_override": provider_override},
            daemon=True,
        )
        thread.start()

        from .upload_execution import get_upload_job
        return {"status": "staging", "job": get_upload_job(job_id, conn=conn)}
    finally:
        if own:
            conn.close()


def _run_staging_job(
    job_id: int, *,
    source_override: str | None = None, provider_override: str | None = None,
) -> None:
    """Background computation for an Automático job: generates the same
    nomenclature/remux previews the manual wizard shows before the user
    confirms, and the same pre-upload checks — writes them as read-only
    snapshots and promotes the job to 'queued'. Never touches the
    filesystem (all preview-only calls, same functions the wizard's own
    preview endpoints use)."""
    from .upload_execution import get_upload_job, append_upload_log
    from .nomenclature import apply_nomenclature_proposal
    from .mkv_remux import build_remux_plan
    from .upload_checks import run_upload_checks

    conn = connect()
    try:
        job = get_upload_job(job_id, conn=conn)
        if not job or job.get("status") != "staging":
            return  # cancelled before we even started
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

        # Each of the three staging sub-steps below: compute -> bail out if
        # cancelled meanwhile -> write its snapshot immediately -> advance
        # `stage` for the NEXT one, rather than batching all three snapshots
        # until the very end — the dedicated job page uses (status, stage)
        # to show a spinner next to whichever section is currently active,
        # which needs each snapshot to land as soon as it's actually ready.
        append_upload_log(job_id, "info", "Generando nomenclatura para eMuwarez…", stream="system", conn=conn)
        try:
            if is_season:
                from .season_pack import build_season_pack_plan

                plan = build_season_pack_plan(
                    item_id, conn=conn,
                    source_override=source_override, provider_override=provider_override,
                )
                if plan.get("status") != "valid":
                    _fail(job_id, "; ".join(plan.get("errors") or ["No se pudo preparar el pack de temporada."]))
                    return
                nomenclature_snapshot = {
                    "media_type": "season",
                    "proposed_title": plan.get("season_pack_title"),
                    "proposed_filename": plan.get("season_pack_title"),
                    "series_title": plan.get("series_title"),
                    "year": plan.get("year"),
                    "season_number": plan.get("season_number"),
                    "tmdb_id": plan.get("tmdb_id"),
                    "resolution": plan.get("resolution"),
                    "source": plan.get("source"),
                    "provider_final": plan.get("provider"),
                    "video_codec": plan.get("video_codec"),
                    "audio_summary": plan.get("audio_summary"),
                    "subtitle_summary": plan.get("subtitle_summary"),
                    "release_tag": plan.get("release_tag"),
                }
            else:
                nom_result = apply_nomenclature_proposal(
                    item_id, conn=conn,  # dry_run default
                    source_override=source_override, provider_override=provider_override,
                )
                if nom_result.get("status") == "blocked":
                    _fail(job_id, "; ".join(nom_result.get("errors") or ["No se pudo generar la nomenclatura."]))
                    return
                nomenclature_snapshot = nom_result.get("proposal") or {}
        except Exception as exc:
            _fail(job_id, f"Error generando la nomenclatura: {exc}")
            return

        job = get_upload_job(job_id, conn=conn)
        if not job or job.get("status") != "staging":
            return  # cancelled while nomenclature was being computed
        _write_snapshot(job_id, "nomenclature_snapshot_json", nomenclature_snapshot, conn=conn)
        _update_staging_stage(job_id, "remux", conn)

        try:
            if is_season:
                from .season_pack import get_season_episode_remux_previews
                previews = get_season_episode_remux_previews(item_id, conn=conn)
                remux_snapshot = {
                    "episodes": [
                        {
                            "episode_id": ep.get("episode_id"),
                            "title": ep.get("title"),
                            "episode_number": ep.get("episode_number"),
                            "ordered_tracks": (ep.get("plan") or {}).get("ordered_tracks", []),
                        }
                        for ep in previews.get("episodes", [])
                    ]
                }
            else:
                remux_plan = build_remux_plan(item_id, conn=conn)
                remux_snapshot = {"ordered_tracks": remux_plan.get("ordered_tracks", [])}
        except Exception as exc:
            _fail(job_id, f"Error generando la reordenación de pistas: {exc}")
            return

        job = get_upload_job(job_id, conn=conn)
        if not job or job.get("status") != "staging":
            return  # cancelled while remux was being computed
        _write_snapshot(job_id, "remux_snapshot_json", remux_snapshot, conn=conn)
        _update_staging_stage(job_id, "checks", conn)

        checks = run_upload_checks(conn, item_id)

        # Re-check: the user may have cancelled while the checks above ran.
        job = get_upload_job(job_id, conn=conn)
        if not job or job.get("status") != "staging":
            return

        _write_snapshot(job_id, "checks_snapshot_json", checks, conn=conn)

        now = datetime.now(timezone.utc)
        queued_until = (now + timedelta(seconds=QUEUE_GRACE_SECONDS)).isoformat()
        conn.execute(
            "UPDATE upload_jobs SET status = 'queued', stage = 'queued', queued_until = ?, updated_at = ? WHERE id = ?",
            (queued_until, now.isoformat(), job_id),
        )
        conn.commit()
        append_upload_log(job_id, "info", "Nomenclatura generada. En cola.", stream="system", conn=conn)
        _arm_queue_timer(job_id)
    except Exception as exc:
        _fail(job_id, f"Error preparando la subida automática: {exc}")
    finally:
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


def _update_staging_stage(job_id: int, stage: str, conn) -> None:
    """Advance the staging sub-step ('nomenclature' -> 'remux' -> 'checks')
    while status stays 'staging' — only while the job hasn't been cancelled
    in the meantime (the WHERE guards against a stray write after a cancel)."""
    conn.execute(
        "UPDATE upload_jobs SET stage = ?, updated_at = ? WHERE id = ? AND status = 'staging'",
        (stage, _now_iso(), job_id),
    )
    conn.commit()


def _write_snapshot(job_id: int, column: str, data, conn) -> None:
    """Persist a read-only snapshot (nomenclature field breakdown or applied
    remux track plan) so the job detail page can show it after the fact —
    neither survives anywhere else once nomenclature.py/mkv_remux.py return."""
    conn.execute(
        f"UPDATE upload_jobs SET {column} = ? WHERE id = ?",
        (json.dumps(data, ensure_ascii=False, default=str), job_id),
    )
    conn.commit()


def _fail(job_id: int, message: str) -> None:
    from .upload_execution import append_upload_log, _notify_upload_failed
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
    _notify_upload_failed(job_id, message)


def _season_upload_preconditions(conn) -> list[str]:
    """The generic (not season-specific) preconditions
    upload_preflight.validate_upload_preconditions() checks for a single
    file — uploadrr path/script + eMuwarez/TMDb API keys. Season-specific
    concerns (episodes consistent, complete, all in the same folder) are
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
            "prepared_path": plan.get("pack_folder"),
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
            (plan.get("pack_folder"), json.dumps(command_preview, ensure_ascii=False), _now_iso(), job_id),
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
    from ..models import LocalStatus
    from .mkv_remux import check_mkvmerge_available, read_tracks_json
    from .media_info_service import mediainfo_available, read_media_info_summary
    from .path_mapping import resolve_local_path
    from .upload_execution import append_upload_log

    episodes = _get_season_episodes(season_id, conn=conn)
    available = [e for e in episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
    if not available:
        _fail(job_id, "La temporada no tiene ningún episodio disponible.")
        return False
    total = len(available)
    for idx, ep in enumerate(available):
        label = f"capítulo {ep.get('episode_number')}"
        append_upload_log(
            job_id, "info", f"Comprobando integridad: {label} ({idx + 1}/{total})…",
            stream="system", conn=conn,
        )
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


def _run_season_remux(job_id: int, season_id: int, conn) -> tuple[bool, list[dict]]:
    """Season equivalent of the single-file remux stage below — loops
    build_remux_plan()/apply_remux() per available episode. No manual
    per-track overrides for season packs (out of scope for v1): each
    episode's own auto-computed plan is applied as-is.

    Returns (ok, snapshot) — snapshot is one entry per episode with its
    final track plan, for the job detail page's read-only remux table
    (previously discarded; apply_remux()'s ordered_tracks never survived
    past this loop)."""
    from .season_pack import _get_season_episodes
    from ..models import LocalStatus
    from .mkv_remux import build_remux_plan, apply_remux, REMUX_CONFIRMATION_TOKEN as REMUX_TOKEN
    from .upload_execution import update_phase_progress, append_upload_log

    episodes = _get_season_episodes(season_id, conn=conn)
    available = [e for e in episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
    total = max(1, len(available))
    snapshot: list[dict] = []
    for idx, ep in enumerate(available):
        label = f"capítulo {ep.get('episode_number')}"
        append_upload_log(
            job_id, "info", f"Reordenando pistas: {label} ({idx + 1}/{total})…",
            stream="system", conn=conn,
        )
        try:
            plan = build_remux_plan(ep["id"], conn=conn)
            ordered_tracks = plan.get("ordered_tracks", [])
            if plan.get("status") == "ready":
                def _on_ep_progress(pct: int, _idx: int = idx) -> None:
                    overall = int(((_idx * 100) + pct) / total)
                    update_phase_progress(job_id, "remux", overall)

                remuxed = apply_remux(
                    ep["id"], apply=True, dry_run=False,
                    confirmation=REMUX_TOKEN, overrides=None, conn=conn,
                    on_progress=_on_ep_progress,
                )
                if remuxed.get("status") != "applied":
                    reason = "; ".join(remuxed.get("errors") or [])
                    _fail(job_id, f"No se pudieron reordenar/renombrar las pistas del {label}: {reason}")
                    return False, snapshot
                ordered_tracks = remuxed.get("ordered_tracks", ordered_tracks)
            snapshot.append({
                "episode_id": ep["id"],
                "title": ep.get("title"),
                "episode_number": ep.get("episode_number"),
                "ordered_tracks": ordered_tracks,
            })
        except Exception as exc:
            _fail(job_id, f"Error reordenando/renombrando las pistas del {label}: {exc}")
            return False, snapshot
    update_phase_progress(job_id, "remux", 100)
    return True, snapshot


def _run_queued_job(job_id: int) -> None:
    with _LOCK:
        _QUEUE_TIMERS.pop(job_id, None)
        overrides = _PENDING_REMUX_OVERRIDES.pop(job_id, None)

    from .upload_execution import (
        get_upload_job, start_upload_job, append_upload_log,
        mark_phase_started, mark_phase_done, update_phase_progress,
    )
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
        mark_phase_started(job_id, "integrity")
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
        mark_phase_done(job_id, "integrity")

        # --- 2. Nomenclature (rename to the final eMuwarez name).
        _mark(job_id, stage="nomenclature")
        mark_phase_started(job_id, "nomenclature")
        append_upload_log(job_id, "info", "Aplicando nomenclatura…", stream="system", conn=conn)
        if is_season:
            from .season_pack import apply_season_pack
            try:
                applied = apply_season_pack(item_id, conn=conn, job_id=job_id)
            except Exception as exc:
                _fail(job_id, f"Error aplicando la nomenclatura del pack de temporada: {exc}")
                return
            if applied.get("status") != "applied":
                reason = "; ".join(applied.get("errors") or []) or "estado desconocido"
                _fail(job_id, f"No se pudo aplicar la nomenclatura del pack de temporada: {reason}")
                return
            _write_snapshot(job_id, "nomenclature_snapshot_json", {
                "media_type": "season",
                "proposed_title": applied.get("season_pack_title"),
                "proposed_filename": applied.get("season_pack_title"),
                "series_title": applied.get("series_title"),
                "year": applied.get("year"),
                "season_number": applied.get("season_number"),
                "tmdb_id": applied.get("tmdb_id"),
                "resolution": applied.get("resolution"),
                "source": applied.get("source"),
                "provider_final": applied.get("provider"),
                "video_codec": applied.get("video_codec"),
                "audio_summary": applied.get("audio_summary"),
                "subtitle_summary": applied.get("subtitle_summary"),
                "release_tag": applied.get("release_tag"),
            }, conn=conn)
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
            if applied.get("proposal"):
                _write_snapshot(job_id, "nomenclature_snapshot_json", applied["proposal"], conn=conn)
        mark_phase_done(job_id, "nomenclature")

        # Best-effort: tell Radarr/Sonarr to refresh+rescan now and wait for
        # it, then resync just this item, so Radarr/Sonarr actually adopts
        # the renamed file (and our own ficha reflects whatever it reports)
        # instead of both staying stuck on the pre-rename filename until
        # Radarr/Sonarr's own next scheduled scan. Never blocks the upload:
        # every step is logged either way, failure or not.
        from .library import refresh_arr_and_resync
        refresh_arr_and_resync(
            conn, item_id,
            on_log=lambda level, message: append_upload_log(job_id, level, message, stream="system", conn=conn),
        )

        # --- 3. Track remux (reorder + rename audio/subs), on the final path.
        _mark(job_id, stage="remux")
        mark_phase_started(job_id, "remux")
        append_upload_log(job_id, "info", "Reordenando/renombrando pistas…", stream="system", conn=conn)
        if is_season:
            ok, episodes_snapshot = _run_season_remux(job_id, item_id, conn=conn)
            if not ok:
                return
            _write_snapshot(job_id, "remux_snapshot_json", {"episodes": episodes_snapshot}, conn=conn)
        else:
            try:
                plan = build_remux_plan(item_id, conn=conn)
                if plan.get("status") == "ready":
                    remuxed = apply_remux(
                        item_id, apply=True, dry_run=False,
                        confirmation=REMUX_TOKEN, overrides=overrides, conn=conn,
                        on_progress=lambda pct: update_phase_progress(job_id, "remux", pct),
                    )
                    if remuxed.get("status") != "applied":
                        reason = "; ".join(remuxed.get("errors") or [])
                        _fail(job_id, f"No se pudieron reordenar/renombrar las pistas: {reason}")
                        return
                    _write_snapshot(
                        job_id, "remux_snapshot_json",
                        {"ordered_tracks": remuxed.get("ordered_tracks", [])}, conn=conn,
                    )
                else:
                    _write_snapshot(
                        job_id, "remux_snapshot_json",
                        {"ordered_tracks": plan.get("ordered_tracks", [])}, conn=conn,
                    )
            except Exception as exc:
                _fail(job_id, f"Error reordenando/renombrando las pistas: {exc}")
                return
        mark_phase_done(job_id, "remux")

        # --- 4. Preflight (fresh preconditions + command preview) then start.
        _mark(job_id, stage="preflight")
        mark_phase_started(job_id, "preflight")
        append_upload_log(job_id, "info", "Preparando la subida…", stream="system", conn=conn)
        if not _populate_ready(job_id, item_id, conn=conn):
            return  # _populate_ready already recorded the failure reason
        mark_phase_done(job_id, "preflight")

        result = start_upload_job(job_id, dry_run=False, start=True, confirmation=START_TOKEN, conn=conn)
        if result.get("error"):
            _fail(job_id, result.get("message") or "; ".join(result.get("errors") or []) or "No se pudo iniciar la subida.")
    finally:
        conn.close()
