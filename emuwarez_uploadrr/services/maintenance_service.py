"""SQLite maintenance and internal log cleanup."""
from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path

VACUUM_CONFIRMATION = "MANTENIMIENTO_DB"
CLEANUP_CONFIRMATION = "LIMPIAR_LOGS"


def _get_db_path() -> Path:
    env = os.environ.get("CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".config" / "emuwarez-renamer"
    return base / "emuwarez_uploadrr.db"


def _get_log_dir() -> Path:
    env = os.environ.get("CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".config" / "emuwarez-renamer"
    return base / "logs"


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

    before = db.stat().st_size

    if dry_run or not do_apply:
        status = get_database_maintenance_status()
        return {
            "ok": True,
            "dry_run": True,
            "action": "preview",
            "db_path": str(db),
            "size_bytes_before": before,
            "freelist_count": status.get("freelist_count", 0),
            "message": "Previsualización — VACUUM no ejecutado",
        }

    try:
        conn = sqlite3.connect(str(db))
        conn.execute("VACUUM")
        conn.close()
    except Exception as exc:
        return {"ok": False, "dry_run": False, "error": str(exc)}

    after = db.stat().st_size
    saved = before - after
    return {
        "ok": True,
        "dry_run": False,
        "action": "vacuum",
        "db_path": str(db),
        "size_bytes_before": before,
        "size_bytes_after": after,
        "bytes_saved": saved,
        "message": f"VACUUM completado. Liberados {saved:,} bytes",
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


def cleanup_old_logs(
    *,
    days: int = 30,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Deletes log files in CONFIG_DIR/logs/ older than `days` days.

    dry_run=True previews. apply=True requires confirmation=LIMPIAR_LOGS.
    """
    do_apply = apply and not dry_run
    if do_apply and confirmation != CLEANUP_CONFIRMATION:
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": f"Confirmación requerida: pasa confirmation='{CLEANUP_CONFIRMATION}'",
        }

    log_dir = _get_log_dir()
    if not log_dir.exists():
        return {
            "ok": True,
            "dry_run": dry_run,
            "files_found": 0,
            "files_deleted": 0,
            "bytes_freed": 0,
            "message": "Directorio de logs no existe",
        }

    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    candidates = []
    for f in log_dir.rglob("*"):
        if f.is_file():
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                candidates.append(f)

    total_bytes = sum(f.stat().st_size for f in candidates)

    if dry_run or not do_apply:
        return {
            "ok": True,
            "dry_run": True,
            "action": "preview",
            "days": days,
            "files_found": len(candidates),
            "files": [str(f.relative_to(log_dir)) for f in candidates[:50]],
            "bytes_to_free": total_bytes,
            "message": f"Previsualización — {len(candidates)} archivos a eliminar ({total_bytes:,} bytes)",
        }

    deleted = 0
    for f in candidates:
        try:
            f.unlink()
            deleted += 1
        except OSError:
            pass

    return {
        "ok": True,
        "dry_run": False,
        "action": "cleanup",
        "days": days,
        "files_deleted": deleted,
        "bytes_freed": total_bytes,
        "message": f"Limpieza completada: {deleted} archivos eliminados ({total_bytes:,} bytes liberados)",
    }
