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

import os
import re
import sqlite3
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .eventos import EVENTO_TAREA, publicar

TASK_LIBRARY_SYNC = "sync-library"
TASK_EMU_SYNC = "sync-emu-requests"
TASK_CHECK_VERSION = "check-version"
TASK_BACKUP = "backup-config"
TASK_MAINTENANCE = "mantenimiento"

# task_key, name, description, default_interval_minutes, min_interval_minutes, manual_allowed, run_at (HH:MM o None)
DEFAULT_TASKS: list[tuple[str, str, str, int, int, int, Optional[str]]] = [
    (
        TASK_LIBRARY_SYNC,
        "Sincronizar bibliotecas",
        "Sincroniza las bibliotecas desde las instancias Radarr/Sonarr configuradas.",
        30, 15, 1, None,
    ),
    (
        TASK_EMU_SYNC,
        "Sincronizar peticiones eMuwarez",
        "Descarga las peticiones abiertas de eMuwarez y las cruza con tu biblioteca. Una vez al día, para gastar pocas llamadas de la API.",
        1440, 60, 1, None,
    ),
    (
        TASK_CHECK_VERSION,
        "Comprobar versión",
        "Consulta si hay una imagen más nueva publicada y avisa una sola vez por versión.",
        60, 60, 1, None,
    ),
    (
        TASK_BACKUP,
        "Copia de seguridad",
        "Guarda una copia de la configuración y la base de datos (sin claves, salvo que lo actives aquí) y retira las automáticas más antiguas. Las manuales y las subidas no se tocan.",
        1440, 60, 1, "03:30",
    ),
    (
        TASK_MAINTENANCE,
        "Mantenimiento",
        "Limpia lo antiguo (historial de tareas, registro de subidas ya terminadas, avisos leídos) y optimiza la base de datos. No toca las subidas ni lo que enlazan.",
        1440, 60, 1, "04:00",
    ),
]

# Las opciones (ajustes numéricos) que cada tarea enseña en Tareas; las define maintenance_service.
OPCIONES_DE_TAREA: dict[str, tuple[str, ...]] = {
    TASK_BACKUP: ("copias.conservar", "copias.incluir_claves"),
    TASK_MAINTENANCE: (
        "mantenimiento.dias_tareas", "mantenimiento.dias_registros",
        "mantenimiento.lineas_registro", "mantenimiento.dias_avisos",
    ),
}

_HORA_FIJA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Task keys that used to be scheduled but were removed — pruned on seed so they
# stop appearing in the Tareas page.
OBSOLETE_TASKS: list[str] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def zona_horaria() -> tzinfo:
    """La del servidor: TZ, o Europe/Madrid si no está o no existe en este sistema."""
    for nombre in (os.environ.get("TZ"), "Europe/Madrid"):
        if nombre:
            try:
                return ZoneInfo(nombre)
            except (ZoneInfoNotFoundError, ValueError, OSError):
                continue
    return datetime.now().astimezone().tzinfo or timezone.utc


def nombre_zona_horaria() -> str:
    zona = zona_horaria()
    return getattr(zona, "key", None) or str(zona)


def siguiente_a_hora_fija(run_at: str, desde: datetime, zona: Optional[tzinfo] = None) -> datetime:
    """La primera vez, estrictamente posterior a `desde`, que el reloj de `zona` marca HH:MM (en UTC)."""
    zona = zona or zona_horaria()
    desde = desde.astimezone(timezone.utc)
    hh, mm = (int(x) for x in run_at.split(":"))
    hoy = desde.astimezone(zona).date()
    for dia in (hoy, hoy + timedelta(days=1)):
        candidata = datetime.combine(dia, time(hh, mm), tzinfo=zona).astimezone(timezone.utc)
        if candidata > desde:
            break
    return candidata


def _proxima_ejecucion(task: dict, desde: datetime) -> datetime:
    if task.get("run_at"):
        return siguiente_a_hora_fija(task["run_at"], desde)
    return desde + timedelta(minutes=task["interval_minutes"])


def ensure_default_tasks(conn: sqlite3.Connection) -> None:
    """Idempotent seed — safe to call on every request."""
    for task_key, name, description, interval, min_interval, manual_allowed, run_at in DEFAULT_TASKS:
        conn.execute(
            """INSERT OR IGNORE INTO scheduled_tasks
               (task_key, name, description, interval_minutes, min_interval_minutes, manual_allowed, run_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_key, name, description, interval, min_interval, manual_allowed, run_at),
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


def set_task_schedule(
    conn: sqlite3.Connection, task_key: str, *, interval_minutes: Optional[int] = None, run_at: Optional[str] = None,
) -> dict:
    """Con `run_at` (HH:MM) la tarea corre cada día a esa hora; sin ella, cada `interval_minutes`."""
    task = get_scheduled_task(conn, task_key)
    if not task:
        raise ValueError(f"Tarea desconocida: {task_key}")
    ahora = _now()
    if run_at:
        if not _HORA_FIJA.match(run_at):
            raise ValueError("La hora debe tener el formato HH:MM (de 00:00 a 23:59)")
        conn.execute(
            "UPDATE scheduled_tasks SET run_at = ?, next_run_at = ?, updated_at = CURRENT_TIMESTAMP WHERE task_key = ?",
            (run_at, siguiente_a_hora_fija(run_at, ahora).isoformat(), task_key),
        )
    else:
        if interval_minutes is None:
            raise ValueError("Indica un intervalo o una hora fija")
        if interval_minutes < task["min_interval_minutes"]:
            raise ValueError(
                f"El intervalo mínimo para esta tarea es {task['min_interval_minutes']} minutos"
            )
        proxima = task["next_run_at"]
        if task["run_at"]:
            # Venía de hora fija: su próxima ejecución era la de la hora, y ya no vale.
            desde = datetime.fromisoformat(task["last_run_at"]) if task["last_run_at"] else ahora
            proxima = (desde + timedelta(minutes=interval_minutes)).isoformat()
        conn.execute(
            """UPDATE scheduled_tasks SET interval_minutes = ?, run_at = NULL, next_run_at = ?,
               updated_at = CURRENT_TIMESTAMP WHERE task_key = ?""",
            (interval_minutes, proxima, task_key),
        )
    conn.commit()
    return get_scheduled_task(conn, task_key)


def set_task_interval(conn: sqlite3.Connection, task_key: str, interval_minutes: int) -> dict:
    return set_task_schedule(conn, task_key, interval_minutes=interval_minutes)


def opciones_de_tarea(conn: sqlite3.Connection, task_key: str) -> list[dict]:
    from .maintenance_service import leer_opciones
    return leer_opciones(conn, OPCIONES_DE_TAREA.get(task_key, ()))


def set_task_options(conn: sqlite3.Connection, task_key: str, valores: dict[str, int]) -> list[dict]:
    from .maintenance_service import guardar_opciones
    if not get_scheduled_task(conn, task_key):
        raise ValueError(f"Tarea desconocida: {task_key}")
    ajenas = [k for k in valores if k not in OPCIONES_DE_TAREA.get(task_key, ())]
    if ajenas:
        raise ValueError(f"Esta tarea no tiene la opción: {ajenas[0]}")
    guardar_opciones(conn, valores)
    return opciones_de_tarea(conn, task_key)


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
    return result.get("status", "completed"), summary


def _run_emu_sync(conn: sqlite3.Connection) -> tuple[str, str]:
    from .requests import sync_emu_requests
    result = sync_emu_requests(conn, force=False)
    if result.get("status") == "throttled":
        return "skipped", f"Esperando {result.get('wait_seconds', 0)}s (mínimo 1 hora entre sincronizaciones)"
    if result.get("status") == "busy":
        return "skipped", str(result["message"])
    return "completed", f"{result.get('imported', 0)} peticiones importadas, {result.get('matched', 0)} cruces"


# Clave donde se recuerda de qué versión ya se avisó, para no repetir el aviso
# cada hora mientras no actualices.
_ESTADO_ULTIMO_AVISO = "version_avisada_commit"


def _run_check_version(conn: sqlite3.Connection) -> tuple[str, str]:
    """Comprueba si hay una imagen más nueva publicada.

    Deja constancia en `task_runs`, que es lo que alimenta "Últimas tareas
    ejecutadas" del Panel: `run_scheduled_task` solo actualiza la fila de la
    tarea programada, así que cada tarea registra su propia ejecución (igual
    que hace la sincronización de biblioteca).

    Avisa UNA sola vez por versión: mientras no actualices, la tarea sigue
    corriendo cada hora y diciendo que hay novedad en su resumen, pero la
    notificación no se repite. Se vuelve a avisar cuando el manifiesto publica
    un commit distinto del ya avisado."""
    from .tasks import finish_task, start_task

    run_id = start_task(conn, TASK_CHECK_VERSION, "Comprobando versión…")
    try:
        estado, resumen = _comprobar_version(conn)
    except Exception as exc:
        finish_task(conn, run_id, "failed", str(exc))
        raise
    finish_task(conn, run_id, estado, resumen)
    return estado, resumen


def _comprobar_version(conn: sqlite3.Connection) -> tuple[str, str]:
    from ..database import get_state, set_state
    from .version_info import estado_de_version

    r = estado_de_version(forzar=True)

    if r["estado"] == "desconocido":
        # No es un fallo de la tarea: es que no se pudo comparar (sin
        # manifiesto, sin sellar, o la red). Se registra tal cual.
        return "skipped", r.get("motivo") or "No se pudo comprobar la versión."

    if r["estado"] == "al_dia":
        return "completed", f"Al día ({r.get('commit_corto') or r['version']})"

    ultimo = (r.get("ultima") or {}).get("commit")
    ya_avisado = get_state(conn, _ESTADO_ULTIMO_AVISO)
    if ya_avisado == ultimo:
        return "completed", "Hay una versión más nueva (ya avisado)"

    from .notification_center import emit
    version = (r.get("ultima") or {}).get("version") or r.get("version")
    emit(
        conn, "version_available",
        f"Hay una versión más nueva: v{version}",
        level="warning",
    )
    set_state(conn, _ESTADO_ULTIMO_AVISO, ultimo or "")
    conn.commit()
    return "completed", "Hay una versión más nueva: avisado"


def _con_registro(conn: sqlite3.Connection, task_key: str, trabajo: Callable[[], tuple[str, str]]) -> tuple[str, str]:
    """Deja constancia en `task_runs` (lo que enseña «Ver logs»), como la comprobación de versión."""
    from .tasks import finish_task, start_task

    run_id = start_task(conn, task_key, "En marcha…")
    try:
        estado, resumen = trabajo()
    except Exception as exc:
        finish_task(conn, run_id, "failed", str(exc))
        raise
    finish_task(conn, run_id, estado, resumen)
    return estado, resumen


def _run_backup(conn: sqlite3.Connection) -> tuple[str, str]:
    from .backup_service import crear_copia_automatica
    from .maintenance_service import valor_opcion

    def trabajo() -> tuple[str, str]:
        r = crear_copia_automatica(
            conservar=valor_opcion(conn, "copias.conservar"),
            incluir_claves=bool(valor_opcion(conn, "copias.incluir_claves")),
        )
        if not r["ok"]:
            return "failed", r["error"]
        resumen = f"Copia {r['archive_name']} ({r['size_bytes'] / 1_048_576:.1f} MB)"
        if r["include_secrets"]:
            resumen += " con claves"
        if r["retiradas"]:
            resumen += f"; {len(r['retiradas'])} automática(s) antigua(s) retirada(s)"
        return "completed", resumen

    return _con_registro(conn, TASK_BACKUP, trabajo)


def _run_maintenance(conn: sqlite3.Connection) -> tuple[str, str]:
    from .maintenance_service import ejecutar_mantenimiento

    return _con_registro(conn, TASK_MAINTENANCE, lambda: ejecutar_mantenimiento(conn))


_EXECUTORS = {
    TASK_LIBRARY_SYNC: _run_library_sync,
    TASK_EMU_SYNC: _run_emu_sync,
    TASK_CHECK_VERSION: _run_check_version,
    TASK_BACKUP: _run_backup,
    TASK_MAINTENANCE: _run_maintenance,
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

    task = get_scheduled_task(conn, task_key) or task  # el horario pudo cambiar mientras corría
    next_run_at = _proxima_ejecucion(task, _now()).isoformat()
    conn.execute(
        """UPDATE scheduled_tasks
           SET last_run_at = ?, last_status = ?, last_summary = ?, next_run_at = ?, updated_at = CURRENT_TIMESTAMP
           WHERE task_key = ?""",
        (_now_iso(), status, summary, next_run_at, task_key),
    )
    conn.commit()
    # "Últimas tareas ejecutadas" sondeaba cada 30 segundos. Aquí termina toda
    # tarea, la lance el reloj o el botón de Ejecutar ahora.
    publicar(EVENTO_TAREA, {"task_key": task_key, "status": status})
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
    "TASK_LIBRARY_SYNC", "TASK_EMU_SYNC", "TASK_CHECK_VERSION", "TASK_BACKUP", "TASK_MAINTENANCE", "DEFAULT_TASKS",
    "ensure_default_tasks", "list_scheduled_tasks", "get_scheduled_task",
    "set_task_interval", "set_task_schedule", "opciones_de_tarea", "set_task_options",
    "zona_horaria", "nombre_zona_horaria", "siguiente_a_hora_fija",
    "run_scheduled_task", "claim_due_tasks", "tick_due_tasks",
]
