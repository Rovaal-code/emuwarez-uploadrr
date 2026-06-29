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


def check_hardlink_base_setting() -> dict:
    """Verifica si hardlink_base está configurado en settings (sin secretos)."""
    try:
        config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".config" / "emuwarez-renamer"))
        db_path = Path(config_dir) / "emuwarez_uploadrr.db"
        if not db_path.exists():
            return _check("hardlink_base", "warning", "BD no existe aún, hardlink_base no configurado", {})
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT value FROM settings WHERE key='hardlink_base' LIMIT 1").fetchone()
        conn.close()
        if row and row[0]:
            hb_path = Path(row[0])
            exists = hb_path.exists()
            suffix = "" if exists else " (directorio no existe)"
            return _check(
                "hardlink_base",
                "ok" if exists else "warning",
                f"hardlink_base configurado: {row[0]}{suffix}",
                {"exists": exists},
            )
        return _check("hardlink_base", "warning", "hardlink_base no configurado (configurable en setup)", {})
    except Exception:
        return _check("hardlink_base", "warning", "No se pudo leer hardlink_base de la BD", {})


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
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT key, value FROM settings WHERE key IN ('tmdb_api_key','emu_api_key')").fetchall()
        conn.close()
        found = {k: bool(v) for k, v in rows}
        tmdb_ok = found.get("tmdb_api_key", False)
        emu_ok = found.get("emu_api_key", False)
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


def get_runtime_diagnostics() -> dict:
    """Ejecuta todos los checks y devuelve diagnóstico completo."""
    checks = [
        check_environment(),
        check_config_dir(),
        check_database_path(),
        check_frontend_dist(),
        check_uploadrr_mount(),
        check_hardlink_base_setting(),
        check_required_secrets(),
        check_arr_instances_configuration(),
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
