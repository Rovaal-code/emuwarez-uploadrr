"""Automatic background tasks scheduler — Phase 11D.

No external scheduler library (no APScheduler/cron) — this is a lightweight
in-process mechanism:
- `scheduled_tasks` table (database.py) tracks interval/last-run/next-run
  bookkeeping for a small, fixed set of task_keys.
- `claim_due_tasks()` + `run_scheduled_task()` are plain, synchronous,
  thread-safe (each caller uses its own sqlite3 connection) functions.
- The actual periodic trigger lives in `web/app.py`'s FastAPI lifespan,
  which calls `tick_due_tasks()` via `asyncio.to_thread(...)` every ~60s so
  a slow sync never blocks the event loop. This module has zero asyncio
  dependency itself, so it's trivially unit-testable synchronously.

Reuses existing sync functions/logging wherever they already exist:
- library sync reuses services.library.sync_all() (already logs to
  task_runs under the name "sync-library").
- eMuwarez request sync reuses services.requests.sync_emu_requests()
  (already logs to task_runs under "sync-emu-requests", and already
  enforces the 1-hour minimum via can_sync_requests()).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

TASK_LIBRARY_SYNC = "sync-library"
TASK_EMU_SYNC = "sync-emu-requests"

# task_key, name, description, default_interval_minutes, min_interval_minutes, manual_allowed
DEFAULT_TASKS: list[tuple[str, str, str, int, int, int]] = [
    (
        TASK_LIBRARY_SYNC,
        "Sincronizar bibliotecas",
        "Sincroniza las bibliotecas desde las instancias Radarr/Sonarr configuradas.",
        30, 15, 1,
    ),
    # NOTE: the eMuwarez request sync (TASK_EMU_SYNC) is intentionally NOT a
    # scheduled task — it runs only from the "Sincronizar peticiones" button.
    # The 1h throttle in services/requests.py still applies.
]

# Task keys that used to be scheduled but were removed — pruned on seed so they
# stop appearing in the Tareas page.
OBSOLETE_TASKS: list[str] = [TASK_EMU_SYNC]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def ensure_default_tasks(conn: sqlite3.Connection) -> None:
    """Idempotent seed — safe to call on every request."""
    for task_key, name, description, interval, min_interval, manual_allowed in DEFAULT_TASKS:
        conn.execute(
            """INSERT OR IGNORE INTO scheduled_tasks
               (task_key, name, description, interval_minutes, min_interval_minutes, manual_allowed)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_key, name, description, interval, min_interval, manual_allowed),
        )
    # Prune tasks that used to be scheduled but no longer are.
    for task_key in OBSOLETE_TASKS:
        conn.execute("DELETE FROM scheduled_tasks WHERE task_key = ?", (task_key,))
    conn.commit()


def list_scheduled_tasks(conn: sqlite3.Connection) -> list[dict]:
    ensure_default_tasks(conn)
    rows = conn.execute("SELECT * FROM scheduled_tasks ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_scheduled_task(conn: sqlite3.Connection, task_key: str) -> Optional[dict]:
    ensure_default_tasks(conn)
    row = conn.execute("SELECT * FROM scheduled_tasks WHERE task_key = ?", (task_key,)).fetchone()
    return dict(row) if row else None


def set_task_interval(conn: sqlite3.Connection, task_key: str, interval_minutes: int) -> dict:
    task = get_scheduled_task(conn, task_key)
    if not task:
        raise ValueError(f"Tarea desconocida: {task_key}")
    if interval_minutes < task["min_interval_minutes"]:
        raise ValueError(
            f"El intervalo mínimo para esta tarea es {task['min_interval_minutes']} minutos"
        )
    conn.execute(
        "UPDATE scheduled_tasks SET interval_minutes = ?, updated_at = CURRENT_TIMESTAMP WHERE task_key = ?",
        (interval_minutes, task_key),
    )
    conn.commit()
    return get_scheduled_task(conn, task_key)


def _run_library_sync(conn: sqlite3.Connection) -> tuple[str, str]:
    from .library import SyncAlreadyRunning, _lib_sync_guard, sync_all
    try:
        with _lib_sync_guard():
            result = sync_all(conn, include_episodes=True)
    except SyncAlreadyRunning:
        # The manual "sincronizar biblioteca" button (or another run of this
        # same task) is already in flight — sharing one active/done lifecycle
        # (see _lib_sync_guard) means they can't run concurrently. Skipping
        # this tick is harmless: the next one picks it up in min_interval_minutes.
        return "skipped", "Ya hay una sincronización de biblioteca en marcha"
    summary = f"{result['imported']} elementos importados, {result['missing']} no disponibles"
    if result.get("errors"):
        summary += f" ({len(result['errors'])} instancia(s) con error)"
    return "completed", summary


def _run_emu_sync(conn: sqlite3.Connection) -> tuple[str, str]:
    from .requests import sync_emu_requests
    result = sync_emu_requests(conn, force=False)
    if result.get("status") == "throttled":
        return "skipped", f"Esperando {result.get('wait_seconds', 0)}s (mínimo 1 hora entre sincronizaciones)"
    if result.get("status") == "unavailable":
        # eMuwarez no expone /api/requests todavía — no es un fallo, es que la
        # función aún no está disponible en el tracker.
        return "skipped", str(result.get("message") or "Sincronización de peticiones no disponible.")
    return "completed", f"{result.get('imported', 0)} peticiones importadas, {result.get('matched', 0)} cruces"


_EXECUTORS = {
    TASK_LIBRARY_SYNC: _run_library_sync,
    TASK_EMU_SYNC: _run_emu_sync,
}


def run_scheduled_task(conn: sqlite3.Connection, task_key: str, *, manual: bool = False) -> dict:
    """Execute one scheduled task. Never raises past this point for
    known failures — they're recorded as status='failed' and returned,
    not thrown, so a scheduler tick or a manual-run API call always gets
    a clean result. Raises ValueError only for programmer errors (unknown
    task_key, or a manual run attempted against a manual_allowed=0 task)."""
    task = get_scheduled_task(conn, task_key)
    if not task:
        raise ValueError(f"Tarea desconocida: {task_key}")
    if manual and not task["manual_allowed"]:
        raise ValueError("Esta tarea no admite ejecución manual, para no saturar el servicio.")

    executor = _EXECUTORS.get(task_key)
    if executor is None:
        raise ValueError(f"Sin ejecutor registrado para: {task_key}")

    try:
        status, summary = executor(conn)
    except Exception as exc:
        status, summary = "failed", str(exc)

    next_run_at = (_now() + timedelta(minutes=task["interval_minutes"])).isoformat()
    conn.execute(
        """UPDATE scheduled_tasks
           SET last_run_at = ?, last_status = ?, last_summary = ?, next_run_at = ?, updated_at = CURRENT_TIMESTAMP
           WHERE task_key = ?""",
        (_now_iso(), status, summary, next_run_at, task_key),
    )
    conn.commit()
    return {"task_key": task_key, "status": status, "summary": summary, "next_run_at": next_run_at}


def claim_due_tasks(conn: sqlite3.Connection) -> list[str]:
    """Return the task_keys that are due right now, and immediately push
    their next_run_at forward by a short grace window so a concurrent tick
    can't pick the same task up again while it's still running. The real
    next_run_at is set by run_scheduled_task() once the run finishes.

    Single-process scheduler (one asyncio loop per `web serve` process) —
    no cross-process race to worry about, only same-process re-entrancy,
    which this claim step prevents."""
    ensure_default_tasks(conn)
    now_iso = _now_iso()
    rows = conn.execute(
        "SELECT task_key FROM scheduled_tasks WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?)",
        (now_iso,),
    ).fetchall()
    claimed = [row["task_key"] for row in rows]
    if claimed:
        grace_until = (_now() + timedelta(minutes=5)).isoformat()
        conn.executemany(
            "UPDATE scheduled_tasks SET next_run_at = ? WHERE task_key = ?",
            [(grace_until, task_key) for task_key in claimed],
        )
        conn.commit()
    return claimed


def tick_due_tasks() -> list[dict]:
    """Open its own connection, claim + run whatever is due, close.
    Designed to be called from a worker thread (e.g. via
    `asyncio.to_thread(tick_due_tasks)`), never on the event loop thread —
    the sync functions it calls use blocking urllib/sqlite3 I/O."""
    from ..database import connect, db_path, init_db

    conn = connect(db_path())
    init_db(conn)
    results = []
    try:
        for task_key in claim_due_tasks(conn):
            try:
                results.append(run_scheduled_task(conn, task_key, manual=False))
            except Exception as exc:
                results.append({"task_key": task_key, "status": "failed", "summary": str(exc), "next_run_at": None})
    finally:
        conn.close()
    return results


__all__ = [
    "TASK_LIBRARY_SYNC", "TASK_EMU_SYNC", "DEFAULT_TASKS",
    "ensure_default_tasks", "list_scheduled_tasks", "get_scheduled_task",
    "set_task_interval", "run_scheduled_task", "claim_due_tasks", "tick_due_tasks",
]
