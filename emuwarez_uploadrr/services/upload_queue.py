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
# stop it before it fires. Single-process app, in-memory is enough (matches
# upload_checks.py's pattern). Remux overrides the user edited in the
# wizard's "Ver Remux" card are persisted on the job row itself
# (remux_overrides_json) instead of kept here — they need to survive a
# process restart during the grace window and be readable by a later retry.
_LOCK = threading.Lock()
_QUEUE_TIMERS: dict[int, threading.Timer] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_queue_positions(conn) -> dict[int, tuple[int, int]]:
    """1-based rank (and total) of every job currently in status='queued',
    ordered by id — i.e. creation order, which is also the order
    upload_execution._upload_concurrency_gate hands out slots in. Lets the
    UI show "Esperando (2/4)" instead of leaving several simultaneously-
    queued jobs indistinguishable from one another."""
    rows = conn.execute(
        "SELECT id FROM upload_jobs WHERE status = 'queued' ORDER BY id ASC"
    ).fetchall()
    total = len(rows)
    return {row["id"]: (i + 1, total) for i, row in enumerate(rows)}


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
    remux_snapshot: dict | None = None,
    checks: dict | None = None,
    nomenclature_proposal_id: int | None = None,
    nomenclature_snapshot: dict | None = None,
    season_overrides: dict | None = None,
) -> dict:
    """Shared by queue_upload_for_item() and queue_retry_for_job(): insert a
    fresh 'queued' row for `item` and arm its 60s grace-period timer.

    `checks` — the pre-upload checks result ({"checks": [...], "ready": bool})
    already computed by the manual wizard before the user confirmed, persisted
    verbatim as checks_snapshot_json so the job detail page can show exactly
    what the user saw and approved, without re-running anything.

    `nomenclature_proposal_id`/`nomenclature_snapshot` — for a manual upload,
    the exact nomenclature_proposals row the user confirmed in the wizard
    (looked up by the caller, queue_upload_for_item()): the id pins
    _run_queued_job()'s apply_nomenclature_proposal() call to THIS proposal
    instead of "whichever is latest", and the snapshot is written immediately
    so the job detail page doesn't show "Pendiente" until the pipeline
    actually reaches the nomenclature step. Left None for an automatic
    (staging-pipeline) job — that absence is what queue_retry_for_job() uses
    to tell manual from automatic jobs apart when carrying values forward.

    `remux_overrides`/`remux_snapshot` — same idea for the per-track manual
    edits (renamed persisted column, replacing the old in-memory
    _PENDING_REMUX_OVERRIDES dict) and the wizard's already-merged
    (base plan + edits) track table.

    `season_overrides` — {"source": ..., "provider": ..., "tag": ...} edited
    by hand in the wizard's now-editable season Source/Proveedor/Tag fields
    (None for a single movie/episode). _run_queued_job() reads this back and
    forwards it to season_pack.apply_season_pack() so the choice actually
    reaches the real renamed files, not just the staging preview.
    """
    now = datetime.now(timezone.utc)
    queued_until = (now + timedelta(seconds=QUEUE_GRACE_SECONDS)).isoformat()
    now_iso = now.isoformat()

    cursor = conn.execute(
        """
        INSERT INTO upload_jobs (
            library_item_id, request_item_id, status, stage, title, path, source_path,
            queued_until, retry_of_job_id, retry_count, checks_snapshot_json,
            nomenclature_proposal_id, nomenclature_snapshot_json,
            remux_overrides_json, remux_snapshot_json, season_overrides_json,
            created_at, updated_at
        ) VALUES (?, ?, 'queued', 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["id"], request_item_id,
            item.get("title") or "Sin título",
            item.get("path") or "",
            item.get("path"),
            queued_until,
            retry_of_job_id, retry_count,
            json.dumps(checks, ensure_ascii=False) if checks else None,
            nomenclature_proposal_id,
            json.dumps(nomenclature_snapshot, ensure_ascii=False, default=str) if nomenclature_snapshot else None,
            json.dumps(remux_overrides, ensure_ascii=False) if remux_overrides else None,
            json.dumps(remux_snapshot, ensure_ascii=False) if remux_snapshot else None,
            json.dumps(season_overrides, ensure_ascii=False) if season_overrides else None,
            now_iso, now_iso,
        ),
    )
    conn.commit()
    job_id = cursor.lastrowid

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
    item_id: int, *,
    remux_overrides: dict | None = None,
    remux_snapshot: dict | None = None,
    checks: dict | None = None,
    source_override: str | None = None,
    provider_override: str | None = None,
    tag_override: str | None = None,
    conn=None,
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

        # Manual upload: pin whichever nomenclature proposal the wizard's
        # nomenclature step already saved (saveNomenclatureFields(), before
        # queueUpload() is even called) — so _run_queued_job() applies THIS
        # exact one instead of "whichever is latest", and the job detail page
        # shows it immediately instead of "Pendiente" until the pipeline runs.
        is_season = item.get("item_type") == "season"
        proposal = None
        if not is_season:
            from .nomenclature import get_latest_nomenclature_proposal
            proposal = get_latest_nomenclature_proposal(item_id, conn=conn)

        season_overrides = None
        if is_season and (source_override or provider_override or tag_override):
            season_overrides = {"source": source_override, "provider": provider_override, "tag": tag_override}

        return _insert_and_start_queued_job(
            conn, item,
            remux_overrides=remux_overrides, remux_snapshot=remux_snapshot, checks=checks,
            nomenclature_proposal_id=proposal.get("id") if proposal else None,
            nomenclature_snapshot=proposal,
            retry_of_job_id=retry_of_job_id, retry_count=retry_count,
            season_overrides=season_overrides,
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

        # Carry forward the original job's manual choices, if it had any.
        # nomenclature_proposal_id is only ever set for a MANUAL upload
        # (queue_upload_for_item) — its absence here means the original was
        # automatic, so leaving it None makes this retry auto-detect from
        # scratch too, same as today. remux_snapshot/checks are copied purely
        # for display continuity (the pipeline always rewrites them for real
        # once it runs) — they play no part in re-derivation.
        def _load_json(column: str):
            raw = original.get(column)
            return json.loads(raw) if raw else None

        return _insert_and_start_queued_job(
            conn, item,
            request_item_id=original.get("request_item_id"),
            retry_of_job_id=original_job_id,
            retry_count=(original.get("retry_count") or 0) + 1,
            nomenclature_proposal_id=original.get("nomenclature_proposal_id"),
            nomenclature_snapshot=_load_json("nomenclature_snapshot_json"),
            remux_overrides=_load_json("remux_overrides_json"),
            remux_snapshot=_load_json("remux_snapshot_json"),
            checks=_load_json("checks_snapshot_json"),
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
                if source_override or provider_override:
                    # Previously this choice only ever affected THIS preview
                    # snapshot — the real apply step later (apply_season_pack,
                    # in _run_queued_job) recomputed from scratch with no
                    # override at all, silently discarding it. Persist it on
                    # the job row so it actually reaches the renamed files.
                    conn.execute(
                        "UPDATE upload_jobs SET season_overrides_json = ? WHERE id = ?",
                        (json.dumps({"source": source_override, "provider": provider_override}), job_id),
                    )
                    conn.commit()
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

        if not checks.get("ready"):
            failed = [c.get("message") or c.get("label") for c in checks.get("checks", []) if c.get("status") == "fail"]
            _fail(job_id, "; ".join(failed) or "Las comprobaciones previas a la subida no se han superado.")
            return

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


def _apply_mkv_title_best_effort(job_id: int, library_item_id: int, conn) -> None:
    """Set the MKV's own internal title (mkvpropedit) on the final renamed/
    remuxed file. Best-effort — logged either way, never fails the job over
    it: the video itself is fine regardless of whether this secondary
    metadata step succeeds, same principle as the Arr refresh in
    _run_queued_job. A non-.mkv file or a missing prepared_path (both
    reported as "blocked") is expected/skippable, not an error."""
    from .mkv_title import apply_internal_title_update, MKV_CONFIRMATION_TOKEN
    from .upload_execution import append_upload_log
    try:
        result = apply_internal_title_update(
            library_item_id, apply=True, dry_run=False,
            confirmation=MKV_CONFIRMATION_TOKEN, conn=conn,
        )
    except Exception as exc:
        append_upload_log(
            job_id, "warning", f"Error actualizando el título interno del MKV: {exc}",
            stream="system", conn=conn,
        )
        return
    status = result.get("status")
    if status == "applied":
        append_upload_log(
            job_id, "info", f"Título interno del MKV actualizado: {result.get('internal_mkv_title')}",
            stream="system", conn=conn,
        )
    elif status not in ("blocked",):
        append_upload_log(
            job_id, "warning",
            f"No se pudo actualizar el título interno del MKV: {'; '.join(result.get('errors') or []) or status}",
            stream="system", conn=conn,
        )


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


def _check_generic_upload_preconditions(job_id: int, item_id: int, is_season: bool, conn) -> bool:
    """Fail-fast subset of what _populate_ready() checks later, restricted to
    the parts that do NOT depend on the file already being renamed/remuxed —
    Uploadrr path/config, eMuwarez/TMDb keys (via _season_upload_preconditions,
    generic despite its name — reused here for both branches) and, for a
    single file, whether its current nomenclature proposal is blocked.

    Runs right after the integrity check, before nomenclature/remux, as part
    of the merged "verificacion_presubida" phase — so missing configuration
    fails immediately instead of after spending time on nomenclature/remux.
    The remaining, path-dependent checks (file existence, prepared_path,
    command preview) still run later, unchanged, in _populate_ready()."""
    errors = _season_upload_preconditions(conn)
    if not is_season:
        proposal_row = conn.execute(
            "SELECT status FROM nomenclature_proposals WHERE library_item_id = ? AND status != 'expired' "
            "ORDER BY created_at DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if proposal_row and proposal_row["status"] == "blocked":
            errors.append("Hay errores en la propuesta de nomenclatura que bloquean la subida.")
    if errors:
        _fail(job_id, "; ".join(errors))
        return False
    return True


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

    from .upload_execution import (
        get_upload_job, start_upload_job, append_upload_log,
        mark_phase_started, mark_phase_done, update_phase_progress,
        _upload_concurrency_gate,
    )
    from .upload_execution import CONFIRMATION_TOKEN as START_TOKEN
    from .nomenclature import apply_nomenclature_proposal, CONFIRMATION_TOKEN as NOM_TOKEN
    from .mkv_remux import (
        build_remux_plan, apply_remux, check_mkvmerge_available, read_tracks_json,
        REMUX_CONFIRMATION_TOKEN as REMUX_TOKEN,
    )
    from .media_info_service import mediainfo_available, read_media_info_summary
    from .path_mapping import resolve_local_path

    # Full serialization of "Subidas en paralelo": a queued job takes its
    # concurrency slot HERE, before any preprocessing (verificación
    # pre-subida/nomenclatura/remux) — not just around the heavy Uploadrr-EMU
    # subprocess like before. Ownership transfers to that subprocess's own
    # thread once it's actually spawned (owns_gate flips to False right
    # after start_upload_job succeeds, and pre_gated=True below tells that
    # thread not to double-acquire); every failure path before that point
    # falls through to the `finally` below and releases it immediately, so
    # a job that never gets that far can't deadlock the queue.
    _upload_concurrency_gate.acquire(job_id)
    owns_gate = True

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
        overrides = json.loads(job["remux_overrides_json"]) if job.get("remux_overrides_json") else None
        season_overrides = json.loads(job["season_overrides_json"]) if job.get("season_overrides_json") else {}

        # --- 1. Verificación presubida: integrity (accessible, MediaInfo reads
        # it, mkvtoolnix reads it) + generic preconditions (Uploadrr path/
        # config, eMuwarez/TMDb keys, blocked nomenclature) — everything that
        # does NOT depend on the file already being renamed/remuxed. Stays
        # "running" through nomenclature/remux below; only marked done once
        # the final, path-dependent check (_populate_ready) passes, right
        # before the real Uploadrr-EMU subprocess starts.
        _mark(job_id, stage="verificacion_presubida", started_at=_now_iso())
        mark_phase_started(job_id, "verificacion_presubida")
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

        append_upload_log(job_id, "info", "Comprobando configuración y requisitos previos…", stream="system", conn=conn)
        if not _check_generic_upload_preconditions(job_id, item_id, is_season, conn=conn):
            return

        # --- 2. Nomenclature (rename to the final eMuwarez name).
        _mark(job_id, stage="nomenclature")
        mark_phase_started(job_id, "nomenclature")
        append_upload_log(job_id, "info", "Aplicando nomenclatura…", stream="system", conn=conn)
        if is_season:
            from .season_pack import apply_season_pack
            try:
                applied = apply_season_pack(
                    item_id, conn=conn, job_id=job_id,
                    source_override=season_overrides.get("source"),
                    provider_override=season_overrides.get("provider"),
                    tag_override=season_overrides.get("tag"),
                )
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
                    item_id, proposal_id=job.get("nomenclature_proposal_id"),
                    apply=True, dry_run=False, confirmation=NOM_TOKEN, conn=conn,
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

        # --- Internal MKV title (mkvpropedit) — must run AFTER remux, not
        # before/instead: mkvmerge's remux rewrites the whole container and
        # atomically replaces the file, which would silently discard a title
        # set beforehand. Previously this was never wired into the real
        # pipeline at all (only reachable from Biblioteca's separate
        # "Adaptar nomenclatura" modal) — every real upload kept the
        # source release's own embedded title untouched (confirmed in
        # production: Chappie, 2026-07-30, still showed "Chappie
        # [www.newpct1.com]"). Best-effort like the Arr refresh above: logged
        # either way, never blocks an otherwise-successful upload over this
        # secondary metadata step. For a season, applied to every episode
        # individually (each has its own MKV file).
        append_upload_log(job_id, "info", "Aplicando título interno del MKV…", stream="system", conn=conn)
        if is_season:
            from ..models import LocalStatus
            from .season_pack import _get_season_episodes
            for ep in _get_season_episodes(item_id, conn=conn):
                if ep.get("local_status") == LocalStatus.AVAILABLE.value:
                    _apply_mkv_title_best_effort(job_id, ep["id"], conn=conn)
        else:
            _apply_mkv_title_best_effort(job_id, item_id, conn=conn)

        mark_phase_done(job_id, "remux")

        # --- 4. Final preflight (fresh preconditions + command preview,
        # against the now-final renamed/remuxed file) then start. Still part
        # of the "verificacion_presubida" displayed phase ("Inicio de
        # Uploadrr") — no mark_phase_done here anymore: since
        # queue_processing/video_processing/mediainfo_export/video_metadata/
        # duplicates (Uploadrr-EMU's own real output through its metadata-
        # processing step) are all folded into this same displayed phase
        # (uploadrr_progress.PHASE_KEY_ALIASES), it only actually closes once
        # that real subprocess output is seen — advance_running_phase()
        # marks it done retroactively when the NEXT raw trigger
        # (screenshots_generate) fires, same as every other merged phase.
        _mark(job_id, stage="verificacion_presubida")
        append_upload_log(job_id, "info", "Preparando la subida…", stream="system", conn=conn)
        if not _populate_ready(job_id, item_id, conn=conn):
            return  # _populate_ready already recorded the failure reason

        result = start_upload_job(job_id, dry_run=False, start=True, confirmation=START_TOKEN, conn=conn, pre_gated=True)
        if result.get("error"):
            _fail(job_id, result.get("message") or "; ".join(result.get("errors") or []) or "No se pudo iniciar la subida.")
        else:
            owns_gate = False  # transferred to the spawned Uploadrr-EMU subprocess thread
    except Exception as exc:
        # Last-resort net: every step above already has its own try/except
        # that fails the job with a specific reason, but anything genuinely
        # unanticipated here (a bug in the orchestration itself, a DB hiccup
        # under concurrent jobs, a KeyError from unexpected data shape...)
        # must still end with the job marked failed and the real traceback
        # in Activity — not a job silently stuck forever with nothing but a
        # stderr traceback nobody but the server console ever sees. Same
        # safety net _run_staging_job() and _run_uploadrr_subprocess()
        # already have; this was the one orchestrator missing it.
        logger.exception("Job %s: excepción inesperada en _run_queued_job", job_id)
        _fail(job_id, f"Error inesperado: {exc}")
    finally:
        conn.close()
        if owns_gate:
            _upload_concurrency_gate.release()
