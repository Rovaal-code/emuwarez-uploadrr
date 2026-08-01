"""Runtime diagnostics — read-only checks for Docker and local runtime health."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _check(name: str, status: str, message: str, details: dict | None = None) -> dict:
    return {"name": name, "status": status, "message": message, "details": details or {}}


def check_config_dir() -> dict:
    """Verifica que CONFIG_DIR existe y es escribible."""
    config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".config" / "emuwarez-renamer"))
    path = Path(config_dir)
    if not path.exists():
        return _check("config_dir", "warning", f"{config_dir} no existe (se creará al arrancar)")
    if not path.is_dir():
        return _check("config_dir", "error", f"{config_dir} existe pero no es directorio")
    if not os.access(path, os.W_OK):
        return _check("config_dir", "error", f"{config_dir} no es escribible")
    return _check("config_dir", "ok", f"{config_dir} existe y es escribible", {"path": str(path)})


def check_database_path() -> dict:
    """Verifica que la BD SQLite existe o puede crearse."""
    config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".config" / "emuwarez-renamer"))
    db_path = Path(config_dir) / "emuwarez_uploadrr.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            conn.close()
            return _check("database", "ok", f"BD accesible en {db_path}", {"path": str(db_path)})
        except Exception as e:
            return _check("database", "error", f"BD no accesible: {e}", {"path": str(db_path)})
    else:
        return _check(
            "database",
            "warning",
            f"BD no existe aún en {db_path} (se creará en db init)",
            {"path": str(db_path)},
        )


def check_frontend_dist() -> dict:
    """Verifica que frontend/dist existe y contiene index.html."""
    candidates = [
        Path(__file__).parent.parent.parent / "frontend" / "dist",  # repo dev + Docker /app
        Path("/app/frontend/dist"),  # Docker fallback explícito
    ]
    for path in candidates:
        if path.exists() and (path / "index.html").exists():
            return _check("frontend_dist", "ok", f"frontend/dist encontrado en {path}", {"path": str(path)})
    return _check("frontend_dist", "warning", "frontend/dist no encontrado (API sigue disponible)", {})


def check_uploadrr_mount() -> dict:
    """Verifica que Uploadrr esté montado/configurado."""
    uploadrr_env = os.environ.get("UPLOADRR_PATH", "")
    candidates = [Path("/opt/Uploadrr")]
    if uploadrr_env:
        candidates.append(Path(uploadrr_env))
    for path in candidates:
        if path.exists() and path.is_dir():
            return _check("uploadrr_mount", "ok", f"Uploadrr encontrado en {path}", {"path": str(path)})
    return _check(
        "uploadrr_mount",
        "warning",
        "Uploadrr no montado en /opt/Uploadrr (configurable en setup)",
        {},
    )


def check_allowed_roots_setting() -> dict:
    """Verifica uploadrr.allowed_roots en settings (sin secretos) — cuando
    nunca se ha configurado, get_allowed_roots() usa DEFAULT_ALLOWED_ROOTS
    ("/data", la misma convención de montaje que Radarr/Sonarr), así que
    esto comprueba ESE default en vez de avisar de un bloqueo que ya no
    existe (ver services/uploadrr_contract.py::get_allowed_roots)."""
    from .uploadrr_contract import DEFAULT_ALLOWED_ROOTS
    try:
        config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".config" / "emuwarez-renamer"))
        db_path = Path(config_dir) / "emuwarez_uploadrr.db"
        if not db_path.exists():
            roots = list(DEFAULT_ALLOWED_ROOTS)
            source = "por defecto"
        else:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute("SELECT value FROM settings WHERE key='uploadrr.allowed_roots' LIMIT 1").fetchone()
            conn.close()
            if row and row[0]:
                import json as _json
                try:
                    roots = [r for r in _json.loads(row[0]) if r]
                except Exception:
                    roots = []
                source = "configurado"
            else:
                roots = list(DEFAULT_ALLOWED_ROOTS)
                source = "por defecto"

        if not roots:
            return _check(
                "allowed_roots", "warning",
                "uploadrr.allowed_roots configurado como vacío — las subidas reales se bloquearán hasta configurarlo en Ajustes",
                {},
            )
        missing = [r for r in roots if not Path(r).exists()]
        if missing:
            return _check(
                "allowed_roots", "warning",
                f"uploadrr.allowed_roots ({source}), pero no existe: {', '.join(missing)}",
                {"roots": roots},
            )
        return _check("allowed_roots", "ok", f"uploadrr.allowed_roots ({source}): {', '.join(roots)}", {"roots": roots})
    except Exception:
        return _check("allowed_roots", "warning", "No se pudo leer uploadrr.allowed_roots de la BD", {})


def check_environment() -> dict:
    """Verifica variables de entorno relevantes (sin secretos)."""
    config_dir = os.environ.get("CONFIG_DIR", "(no establecido, usando default)")
    tz = os.environ.get("TZ", "(no establecido)")
    details = {
        "CONFIG_DIR": config_dir,
        "TZ": tz,
        "PYTHONUNBUFFERED": os.environ.get("PYTHONUNBUFFERED", "(no establecido)"),
    }
    return _check("environment", "ok", "Variables de entorno leídas", details)


def check_required_secrets() -> dict:
    """Verifica que los secretos obligatorios estén configurados (sin exponerlos)."""
    try:
        config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".config" / "emuwarez-renamer"))
        db_path = Path(config_dir) / "emuwarez_uploadrr.db"
        if not db_path.exists():
            return _check("required_secrets", "warning", "BD no existe aún, secretos sin verificar", {})
        # get_setting_canonical y no un SELECT a pelo: la clave canónica es la
        # de punto ('tmdb.api_key'), que es la única que escriben el asistente
        # y la interfaz, y el guion bajo es el alias antiguo que solo tienen
        # las instalaciones que vienen del CLI. Preguntando solo por el alias,
        # esto decía "Secretos sin configurar" a todo el mundo.
        from ..database import connect as _connect, get_setting_canonical
        conn = _connect(db_path)
        try:
            tmdb_ok = bool((get_setting_canonical(conn, "tmdb.api_key") or "").strip())
            emu_ok = bool((get_setting_canonical(conn, "emu.api_key") or "").strip())
        finally:
            conn.close()
        if tmdb_ok and emu_ok:
            return _check("required_secrets", "ok", "Secretos de TMDb y eMuwarez configurados", {
                "tmdb": "configurado",
                "emu": "configurado",
            })
        missing_count = (0 if tmdb_ok else 1) + (0 if emu_ok else 1)
        services = []
        if not tmdb_ok:
            services.append("TMDb")
        if not emu_ok:
            services.append("eMuwarez")
        label = " y ".join(services)
        return _check("required_secrets", "warning", f"Secretos sin configurar: {label}", {
            "missing_count": missing_count,
            "tmdb": "configurado" if tmdb_ok else "no configurado",
            "emu": "configurado" if emu_ok else "no configurado",
        })
    except Exception:
        return _check("required_secrets", "warning", "No se pudieron verificar los secretos", {})


def check_arr_instances_configuration() -> dict:
    """Verifica que haya al menos una instancia de Radarr o Sonarr configurada."""
    try:
        config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".config" / "emuwarez-renamer"))
        db_path = Path(config_dir) / "emuwarez_uploadrr.db"
        if not db_path.exists():
            return _check("arr_instances", "warning", "BD no existe aún, instancias sin verificar", {})
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT COUNT(*) FROM arr_instances WHERE enabled=1").fetchone()
            count = row[0] if row else 0
        except Exception:
            count = 0
        finally:
            conn.close()
        if count > 0:
            return _check("arr_instances", "ok", f"{count} instancia(s) Arr habilitada(s)", {"count": count})
        return _check("arr_instances", "warning", "No hay instancias Radarr/Sonarr habilitadas", {"count": 0})
    except Exception:
        return _check("arr_instances", "warning", "No se pudieron verificar las instancias Arr", {})


def check_arr_health_configuration() -> dict:
    """Devuelve resumen de instancias Radarr/Sonarr: count, enabled, last_sync, last_diagnostics."""
    try:
        config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".config" / "emuwarez-renamer"))
        db_path = Path(config_dir) / "emuwarez_uploadrr.db"
        if not db_path.exists():
            return _check("arr_health_config", "warning", "BD no existe, configuración ARR sin verificar", {})
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT type, COUNT(*) AS cnt, SUM(enabled) AS enabled_cnt FROM instances GROUP BY type"
            ).fetchall()
            radarr_total = 0
            radarr_enabled = 0
            sonarr_total = 0
            sonarr_enabled = 0
            for r in rows:
                if r[0] == "radarr":
                    radarr_total = r[1]
                    radarr_enabled = int(r[2] or 0)
                elif r[0] == "sonarr":
                    sonarr_total = r[1]
                    sonarr_enabled = int(r[2] or 0)

            last_sync_row = conn.execute(
                "SELECT started_at FROM task_runs WHERE name='sync-library' AND status='completed' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            last_sync = last_sync_row[0] if last_sync_row else None

            last_diag_row = conn.execute(
                "SELECT started_at FROM library_diagnostic_runs ORDER BY id DESC LIMIT 1"
            ).fetchone() if _table_exists(conn, "library_diagnostic_runs") else None
            last_diag = last_diag_row[0] if last_diag_row else None
        finally:
            conn.close()

        total_enabled = radarr_enabled + sonarr_enabled
        status = "ok" if total_enabled > 0 else "warning"
        return _check(
            "arr_health_config",
            status,
            f"Radarr: {radarr_enabled}/{radarr_total} habilitadas, Sonarr: {sonarr_enabled}/{sonarr_total} habilitadas",
            {
                "radarr_total": radarr_total,
                "radarr_enabled": radarr_enabled,
                "sonarr_total": sonarr_total,
                "sonarr_enabled": sonarr_enabled,
                "last_sync": last_sync,
                "last_diagnostics_run": last_diag,
            },
        )
    except Exception as exc:
        return _check("arr_health_config", "warning", f"No se pudo verificar configuración ARR: {exc}", {})


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return bool(row and row[0])


def get_runtime_diagnostics() -> dict:
    """Ejecuta todos los checks y devuelve diagnóstico completo."""
    checks = [
        check_environment(),
        check_config_dir(),
        check_database_path(),
        check_frontend_dist(),
        check_uploadrr_mount(),
        check_allowed_roots_setting(),
        check_required_secrets(),
        check_arr_instances_configuration(),
        check_arr_health_configuration(),
    ]
    warnings = [c["message"] for c in checks if c["status"] == "warning"]
    errors = [c["message"] for c in checks if c["status"] == "error"]
    ok = len(errors) == 0
    return {
        "ok": ok,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }
