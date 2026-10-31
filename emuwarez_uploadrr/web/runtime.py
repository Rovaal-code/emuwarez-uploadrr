"""Runtime information helpers — no FastAPI dependency."""
from __future__ import annotations

import os
from pathlib import Path


def _package_version() -> str:
    """La versión del paquete. La fuente es emuwarez_uploadrr.__version__, que
    es de donde pyproject.toml la lee también: estaba escrita en tres sitios y
    /api/health enseñaba una distinta de la del código."""
    from .. import __version__
    return __version__


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


def get_app_version() -> str:
    return _package_version()


def get_config_dir() -> str:
    return str(_config_dir())
