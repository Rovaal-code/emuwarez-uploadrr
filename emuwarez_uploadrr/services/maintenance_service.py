"""SQLite maintenance."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

VACUUM_CONFIRMATION = "MANTENIMIENTO_DB"


def _get_db_path() -> Path:
    env = os.environ.get("CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".config" / "emuwarez-renamer"
    return base / "emuwarez_uploadrr.db"


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
