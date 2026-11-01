"""SQLite maintenance."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from .settings import get_setting_canonical, set_setting

VACUUM_CONFIRMATION = "MANTENIMIENTO_DB"


def _get_db_path() -> Path:
    env = os.environ.get("CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".config" / "emuwarez-renamer"
    return base / "emuwarez_uploadrr.db"


def _size_on_disk(db: Path) -> int:
    """The .db plus its -wal: committed changes may still live in the WAL."""
    wal = db.with_name(db.name + "-wal")
    return db.stat().st_size + (wal.stat().st_size if wal.exists() else 0)


def get_database_maintenance_status() -> dict:
    """Returns DB size, page count and freelist (read-only)."""
    db = _get_db_path()
    if not db.exists():
        return {"ok": False, "error": f"BD no encontrada: {db}"}
    try:
        conn = sqlite3.connect(str(db))
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        conn.close()
        size_bytes = db.stat().st_size
        return {
            "ok": True,
            "db_path": str(db),
            "size_bytes": size_bytes,
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist,
            "fragmentation_pct": round(freelist / page_count * 100, 1) if page_count else 0,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_database_integrity_check() -> dict:
    """Runs PRAGMA integrity_check — read-only, no confirmation needed."""
    db = _get_db_path()
    if not db.exists():
        return {"ok": False, "error": f"BD no encontrada: {db}"}
    try:
        conn = sqlite3.connect(str(db))
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        conn.close()
        results = [r[0] for r in rows]
        passed = results == ["ok"]
        return {
            "ok": passed,
            "db_path": str(db),
            "result": results,
            "message": "Integridad OK" if passed else f"Problemas encontrados: {results}",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_database_vacuum(
    *,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Runs VACUUM on the database to reclaim space.

    dry_run=True previews. apply=True requires confirmation=MANTENIMIENTO_DB.
    """
    do_apply = apply and not dry_run
    if do_apply and confirmation != VACUUM_CONFIRMATION:
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": f"Confirmación requerida: pasa confirmation='{VACUUM_CONFIRMATION}'",
        }

    db = _get_db_path()
    if not db.exists():
        return {"ok": False, "dry_run": dry_run, "error": f"BD no encontrada: {db}"}

    before = _size_on_disk(db)

    if dry_run or not do_apply:
        status = get_database_maintenance_status()
        freelist_count = status.get("freelist_count", 0)
        page_size = status.get("page_size", 0)
        estimated_bytes_freeable = freelist_count * page_size
        return {
            "ok": True,
            "dry_run": True,
            "action": "preview",
            "db_path": str(db),
            "size_bytes_before": before,
            "freelist_count": freelist_count,
            "page_size": page_size,
            "estimated_bytes_freeable": estimated_bytes_freeable,
            "message": f"Previsualización — ~{estimated_bytes_freeable:,} bytes liberables ({freelist_count:,} páginas libres). VACUUM no ejecutado.",
        }

    try:
        conn = sqlite3.connect(str(db))
        conn.execute("VACUUM")
        # WAL: sin esto el fichero no encoge mientras el servidor tenga conexiones abiertas
        busy = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
        conn.close()
    except Exception as exc:
        return {"ok": False, "dry_run": False, "error": str(exc)}

    after = _size_on_disk(db)
    saved = before - after
    return {
        "ok": True,
        "dry_run": False,
        "action": "vacuum",
        "db_path": str(db),
        "size_bytes_before": before,
        "size_bytes_after": after,
        "bytes_saved": saved,
        "message": (
            "VACUUM completado, pero una lectura en curso no ha dejado liberar el espacio. Vuelve a ejecutarlo en un momento"
            if busy else f"VACUUM completado. Liberados {saved:,} bytes"
        ),
    }


def run_database_analyze(*, dry_run: bool = True, apply: bool = False) -> dict:
    """Runs ANALYZE to update query planner statistics (no confirmation needed)."""
    do_apply = apply and not dry_run
    db = _get_db_path()
    if not db.exists():
        return {"ok": False, "dry_run": dry_run, "error": f"BD no encontrada: {db}"}

    if dry_run or not do_apply:
        return {
            "ok": True,
            "dry_run": True,
            "action": "preview",
            "message": "Previsualización — ANALYZE no ejecutado",
        }

    try:
        conn = sqlite3.connect(str(db))
        conn.execute("ANALYZE")
        conn.close()
        return {"ok": True, "dry_run": False, "action": "analyze", "message": "ANALYZE completado"}
    except Exception as exc:
        return {"ok": False, "dry_run": False, "error": str(exc)}


# --- Mantenimiento nocturno: limpiar lo antiguo y optimizar la base -----------------------------------------
# Solo toca task_runs, upload_job_logs y notifications. Nunca upload_jobs ni nada que una subida enlace.

# clave de ajuste -> (etiqueta, por defecto, mínimo, máximo, nota). Con rango 0-1 es un interruptor.
OPCIONES: dict[str, tuple[str, int, int, int, str]] = {
    "mantenimiento.dias_tareas": ("Historial de tareas: conservar (días)", 90, 7, 3650, ""),
    "mantenimiento.dias_registros": ("Registro de subidas terminadas: recortar pasados (días)", 30, 1, 3650, ""),
    "mantenimiento.lineas_registro": ("Registro recortado: líneas que se dejan", 200, 20, 100000, ""),
    "mantenimiento.dias_avisos": ("Avisos leídos: conservar (días)", 30, 1, 3650, ""),
    "copias.conservar": ("Copias automáticas que se guardan", 7, 1, 365, ""),
    "copias.incluir_claves": (
        "Incluir las claves en las copias automáticas", 0, 0, 1,
        "Quien pueda leer la carpeta de backups verá las claves (los archivos son solo legibles por su dueño).",
    ),
}


def valor_opcion(conn: sqlite3.Connection, clave: str) -> int:
    _, defecto, minimo, maximo, _ = OPCIONES[clave]
    try:
        valor = int(get_setting_canonical(conn, clave, str(defecto)))
    except (TypeError, ValueError):
        return defecto
    return min(max(valor, minimo), maximo)


def leer_opciones(conn: sqlite3.Connection, claves: Iterable[str]) -> list[dict]:
    return [
        {"clave": c, "etiqueta": OPCIONES[c][0], "valor": valor_opcion(conn, c), "minimo": OPCIONES[c][2],
         "maximo": OPCIONES[c][3], "nota": OPCIONES[c][4]}
        for c in claves
    ]


def guardar_opciones(conn: sqlite3.Connection, valores: dict[str, int]) -> None:
    """Todo o nada: si una opción no vale, no se guarda ninguna."""
    for clave, valor in valores.items():
        if clave not in OPCIONES:
            raise ValueError(f"Opción desconocida: {clave}")
        etiqueta, _, minimo, maximo, _ = OPCIONES[clave]
        if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
            raise ValueError(f"{etiqueta}: tiene que estar entre {minimo} y {maximo}")
    for clave, valor in valores.items():
        set_setting(conn, clave, str(valor))
    conn.commit()


def _dia_de_corte(ahora: datetime, dias: int) -> str:
    # Las fechas se guardan en dos formatos (con espacio o con T): se compara solo el día.
    return (ahora - timedelta(days=dias)).strftime("%Y-%m-%d")


def podar_tareas(conn: sqlite3.Connection, dias: int, ahora: Optional[datetime] = None) -> int:
    """Borra las ejecuciones de tareas más viejas que `dias`. De cada tarea quedan siempre la última
    y la última completada (de ahí salen «última sincronización» y el diagnóstico)."""
    corte = _dia_de_corte(ahora or datetime.now(timezone.utc), dias)
    n = conn.execute(
        """DELETE FROM task_runs
           WHERE substr(started_at, 1, 10) < ?
             AND id NOT IN (SELECT MAX(id) FROM task_runs GROUP BY name)
             AND id NOT IN (SELECT MAX(id) FROM task_runs WHERE status = 'completed' GROUP BY name)""",
        (corte,),
    ).rowcount
    conn.commit()
    return n


def recortar_registros_de_subidas(
    conn: sqlite3.Connection, dias: int, lineas: int, ahora: Optional[datetime] = None,
) -> int:
    """De las subidas terminadas sin fallo (completadas o canceladas) y más viejas que `dias`, deja las
    últimas `lineas` del registro. Las fallidas conservan el registro entero; las vivas, también."""
    corte = _dia_de_corte(ahora or datetime.now(timezone.utc), dias)
    trabajos = [r[0] for r in conn.execute(
        """SELECT j.id FROM upload_jobs j
           WHERE j.status IN ('completed', 'cancelled') AND substr(j.updated_at, 1, 10) < ?
             AND (SELECT COUNT(*) FROM upload_job_logs l WHERE l.upload_job_id = j.id) > ?""",
        (corte, lineas),
    )]
    borradas = 0
    for job_id in trabajos:
        borradas += conn.execute(
            """DELETE FROM upload_job_logs WHERE upload_job_id = ? AND id NOT IN (
                   SELECT id FROM upload_job_logs WHERE upload_job_id = ?
                   ORDER BY sequence DESC, id DESC LIMIT ?)""",
            (job_id, job_id, lineas),
        ).rowcount
        conn.commit()  # una transacción corta por subida: las que están escribiendo su registro no esperan
    return borradas


def podar_avisos_leidos(conn: sqlite3.Connection, dias: int, ahora: Optional[datetime] = None) -> int:
    """Borra los avisos ya leídos más viejos que `dias`; los sin leer no se tocan."""
    corte = _dia_de_corte(ahora or datetime.now(timezone.utc), dias)
    n = conn.execute(
        "DELETE FROM notifications WHERE read_at IS NOT NULL AND substr(created_at, 1, 10) < ?", (corte,),
    ).rowcount
    conn.commit()
    return n


def optimizar_base(conn: sqlite3.Connection) -> bool:
    """PRAGMA optimize y vaciar el WAL. False si una lectura en curso no ha dejado vaciarlo del todo."""
    conn.commit()
    conn.execute("PRAGMA optimize")
    return conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def ejecutar_mantenimiento(conn: sqlite3.Connection, ahora: Optional[datetime] = None) -> tuple[str, str]:
    """La tarea nocturna. Cada paso es independiente: si uno falla, los demás se hacen igual y el resumen lo dice."""
    ahora = ahora or datetime.now(timezone.utc)
    dias_tareas, dias_registros, lineas, dias_avisos = (valor_opcion(conn, c) for c in (
        "mantenimiento.dias_tareas", "mantenimiento.dias_registros",
        "mantenimiento.lineas_registro", "mantenimiento.dias_avisos"))
    pasos = (
        ("ejecuciones de tareas", lambda: podar_tareas(conn, dias_tareas, ahora)),
        ("líneas de registro de subidas", lambda: recortar_registros_de_subidas(conn, dias_registros, lineas, ahora)),
        ("avisos leídos", lambda: podar_avisos_leidos(conn, dias_avisos, ahora)),
    )
    borrados: list[str] = []
    fallos: list[str] = []
    for nombre, paso in pasos:
        try:
            borrados.append(f"{paso()} {nombre}")
        except sqlite3.Error as exc:
            conn.rollback()
            fallos.append(f"{nombre}: {exc}")
    resumen = "Borradas " + ", ".join(borrados) if borrados else "No se ha borrado nada"
    try:
        if not optimizar_base(conn):
            resumen += ". WAL pendiente de vaciar: hay lecturas en curso"
    except sqlite3.Error as exc:
        fallos.append(f"optimizar: {exc}")
    if fallos:
        return "failed", f"{resumen}. Fallos: " + "; ".join(fallos)
    return "completed", resumen
