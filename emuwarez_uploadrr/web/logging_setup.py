"""Application-wide logging capture.

Wires the ROOT logger so *everything* any module logs is captured into an
in-memory ring buffer (served by GET /api/logs), a rotating file under
CONFIG_DIR/logs/app.log and stdout (what `docker logs` shows). uvicorn's own
loggers are made to propagate here too, so HTTP access/errors are logged as well.
"""
from __future__ import annotations

import logging
import sys
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .runtime import get_config_dir

_RING_MAX = 5000
_ring: deque[dict] = deque(maxlen=_RING_MAX)

_LEVEL_ORDER = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class RingBufferHandler(logging.Handler):
    """Keeps the most recent log records in memory as plain dicts."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _ring.append({
                "ts": record.created,
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            })
        except Exception:
            pass


class _StdoutHandler(logging.StreamHandler):
    """stdout, for `docker logs`."""


def _levels_at_or_above(level: str) -> set[str]:
    level = (level or "").upper()
    if level not in _LEVEL_ORDER:
        return set(_LEVEL_ORDER)
    return set(_LEVEL_ORDER[_LEVEL_ORDER.index(level):])


def get_recent_logs(limit: int = 500, level: Optional[str] = None, search: Optional[str] = None) -> list[dict]:
    """Return recent log records (newest first), filtered by min level and text."""
    items = list(_ring)
    if level:
        wanted = _levels_at_or_above(level)
        items = [r for r in items if r["level"] in wanted]
    if search:
        s = search.lower()
        items = [r for r in items if s in r["message"].lower() or s in r["logger"].lower()]
    return items[-limit:][::-1]


_configured = False


def setup_app_logging() -> None:
    """Idempotently attach the ring buffer + rotating file handler to root."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
        root.addHandler(RingBufferHandler())

    log_dir = Path(get_config_dir()) / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
            fh = RotatingFileHandler(
                log_dir / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
            )
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            root.addHandler(fh)
    except Exception:
        pass  # file logging is best-effort; the ring buffer always works

    if not any(isinstance(h, _StdoutHandler) for h in root.handlers):
        sh = _StdoutHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(sh)

    # Make uvicorn/fastapi loggers flow into our root handlers too.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(name).propagate = True
    # Drop uvicorn's own console handlers, or every line would print twice.
    for name in ("uvicorn", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()

    # Noise control:
    #  • uvicorn.access duplicates our own request middleware line-for-line, so
    #    mute it (only its warnings/errors get through, still via root).
    #  • httpx/httpcore log every outgoing call to Radarr/Sonarr/TMDB/eMuwarez/
    #    qBittorrent at INFO — per-request noise; keep only warnings+.
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True
