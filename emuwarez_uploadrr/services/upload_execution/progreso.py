"""Progreso por fases de un trabajo (progress_json) y avance de las subfases de la ejecución."""
from __future__ import annotations

import json

from ..eventos import EVENTO_SUBIDA_PROGRESO, publicar, publicar_agrupado
from ..uploadrr_progress import (
    RUNNING_DISPLAY_ORDER,
    RUNNING_SUB_PHASE_ORDER,
    build_phase_state,
    resolve_display_progress,
    with_phase_timestamps,
)
from .comun import _get_db_conn, _now


def _read_progress_state(job_id: int) -> dict:
    conn = _get_db_conn()
    try:
        row = conn.execute(
            "SELECT progress_json FROM upload_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["progress_json"]:
        return {"phases": [], "global_pct": 0}
    try:
        return json.loads(row["progress_json"])
    except (TypeError, ValueError):
        return {"phases": [], "global_pct": 0}


def _write_progress_json(job_id: int, state: dict) -> None:
    conn = _get_db_conn()
    try:
        conn.execute(
            "UPDATE upload_jobs SET progress_json = ? WHERE id = ?",
            (json.dumps(state, ensure_ascii=False), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_phase_started(job_id: int, stage_key: str) -> None:
    """Record the wall-clock start of a phase — call this right when a
    phase's real work begins (mark_phase_done when it completes), so the
    Fases table's Creado/Finalizado/Duración columns reflect real timing,
    not just the current status snapshot. Safe to call even if the phase
    finishes almost immediately (started_at/finished_at can be equal)."""
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    completed.discard(stage_key)
    new_state = build_phase_state(list(completed), current=stage_key, current_pct=0)
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))


def mark_phase_done(job_id: int, stage_key: str) -> None:
    """Mark a pipeline phase (integrity/nomenclature/remux/preflight/running)
    as fully complete, keeping whichever other phases were already done, and
    persist the recomputed job-wide percentage."""
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    completed.add(stage_key)
    new_state = build_phase_state(list(completed))
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))
    # Sin agrupar: es el último cambio de la fase, y el aviso de estado del job puede haber salido antes.
    publicar(EVENTO_SUBIDA_PROGRESO, {"job_id": job_id, "phase": stage_key})


def mark_phase_failed(job_id: int, stage_key: str) -> None:
    """Deja una fase como fallida aunque el job acabe bien (qBittorrent tras una subida que sí se hizo)."""
    state = _read_progress_state(job_id)
    for p in state.get("phases", []):
        if p["key"] == stage_key:
            p["status"] = "failed"
            p["finished_at"] = p.get("finished_at") or _now()
    _write_progress_json(job_id, state)
    publicar(EVENTO_SUBIDA_PROGRESO, {"job_id": job_id, "phase": stage_key})


def update_phase_progress(job_id: int, stage_key: str, pct: int) -> None:
    """Update the live in-progress percentage of one phase (remux via
    mkvmerge --gui-mode), keeping whatever phases were already marked done
    intact."""
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    completed.discard(stage_key)
    new_state = build_phase_state(list(completed), current=stage_key, current_pct=pct)
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))


def advance_running_phase(job_id: int, phase_key: str, pct: int) -> None:
    """Update progress_json as Uploadrr-EMU's own output reports a new
    internal sub-phase (queue -> video processing -> MediaInfo -> ... ->
    uploading to eMuwarez). Uploadrr-EMU reports these strictly in order.

    Several raw sub-phases now share one displayed PHASES row (see
    uploadrr_progress.PHASE_KEY_ALIASES) — resolve_display_progress() maps
    `phase_key`'s raw progress to that merged key + an interpolated pct, and
    every DISPLAYED phase before it is marked done, same retroactive
    safety net as before (just over merged keys instead of raw ones)."""
    if phase_key not in RUNNING_SUB_PHASE_ORDER:
        return
    display_key, display_pct = resolve_display_progress(phase_key, pct)
    state = _read_progress_state(job_id)
    completed = {p["key"] for p in state.get("phases", []) if p.get("status") == "done"}
    idx = RUNNING_DISPLAY_ORDER.index(display_key)
    completed.update(RUNNING_DISPLAY_ORDER[:idx])
    completed.discard(display_key)
    # Never regress the merged phase's displayed pct — a later raw member
    # firing at a lower interpolated pct than an earlier one already showed
    # (shouldn't normally happen, but stay defensive) must not roll it back.
    current_row = next((p for p in state.get("phases", []) if p["key"] == display_key), None)
    if current_row and current_row.get("status") == "running":
        display_pct = max(display_pct, current_row.get("pct", 0))
    new_state = build_phase_state(list(completed), current=display_key, current_pct=display_pct)
    _write_progress_json(job_id, with_phase_timestamps(new_state, state.get("phases")))

    # El progreso ya está escrito: ahora se puede avisar. Se agrupa por trabajo
    # porque el proceso reporta a mucha más resolución de la que un ojo
    # distingue, y recargar la tabla de subidas veinte veces por segundo sería
    # más caro que el sondeo de 2,5 s que esto viene a sustituir.
    publicar_agrupado(f"progreso-{job_id}", EVENTO_SUBIDA_PROGRESO,
                      {"job_id": job_id, "phase": display_key, "pct": display_pct},
                      cada=0.5)
