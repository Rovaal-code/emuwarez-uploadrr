"""Runtime information helpers — no FastAPI dependency."""
from __future__ import annotations

import os
from pathlib import Path


def _package_version() -> str:
    try:
        from importlib.metadata import version
        return version("emuwarez-uploadrr")
    except Exception:
        return "0.2.0"


def _config_dir() -> Path:
    env = os.environ.get("CONFIG_DIR")
    if env:
        return Path(env)
    try:
        from emuwarez_uploadrr.constants import CONFIG_DIR
        return CONFIG_DIR
    except Exception:
        return Path.home() / ".config" / "emuwarez-renamer"


def _db_path() -> Path:
    try:
        from emuwarez_uploadrr.database import db_path
        return db_path()
    except Exception:
        return _config_dir() / "emuwarez_uploadrr.db"


def _uploadrr_present() -> bool:
    candidates = [
        Path("Uploadrr") / "upload.py",
        Path(__file__).resolve().parents[3] / "Uploadrr" / "upload.py",
    ]
    return any(p.exists() for p in candidates)


def get_app_version() -> str:
    return _package_version()


def get_config_dir() -> str:
    return str(_config_dir())


def get_database_path() -> str:
    return str(_db_path())


def get_runtime_info() -> dict:
    db = _db_path()
    try:
        from emuwarez_uploadrr.database import connect, init_db
        with connect(db) as conn:
            init_db(conn)
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    return {
        "app_name": "eMuwarez Uploadrr",
        "version": get_app_version(),
        "config_dir": get_config_dir(),
        "database_path": get_database_path(),
        "database_status": db_status,
        "cli_available": True,
        "uploadrr_runtime_present": _uploadrr_present(),
    }
