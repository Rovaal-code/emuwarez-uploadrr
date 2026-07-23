"""On-disk cache for full analysis results (spec section 21).

Identity is (normalized path, size, mtime, engine version) — cheap `stat()`
fields, no content hash. A changed file, a changed engine version, or a
changed rule set all naturally produce a different key, so nothing needs
explicit invalidation logic beyond "look up this exact key".
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from ...database import connect
from .constants import ENGINE_VERSION

log = logging.getLogger("emuwarez.source_engine")


def _key(path: str) -> Optional[tuple[str, int, int]]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (os.path.realpath(path), st.st_size, int(st.st_mtime))


def get(path: str, *, conn=None) -> Optional[dict]:
    key = _key(path)
    if key is None:
        return None
    own = conn is None
    c = conn or connect()
    try:
        row = c.execute(
            "SELECT result_json FROM source_engine_cache WHERE path=? AND size_bytes=? AND mtime=? AND engine_version=?",
            (*key, ENGINE_VERSION),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["result_json"])
        except json.JSONDecodeError:
            return None
    except Exception as exc:  # noqa: BLE001 — cache is best-effort, never fatal
        log.warning("source_engine cache read failed: %s", exc)
        return None
    finally:
        if own:
            c.close()


def put(path: str, result: dict, *, conn=None) -> None:
    key = _key(path)
    if key is None:
        return
    own = conn is None
    c = conn or connect()
    try:
        c.execute(
            """INSERT OR REPLACE INTO source_engine_cache
               (path, size_bytes, mtime, engine_version, result_json)
               VALUES (?, ?, ?, ?, ?)""",
            (*key, ENGINE_VERSION, json.dumps(result, ensure_ascii=False)),
        )
        c.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("source_engine cache write failed: %s", exc)
    finally:
        if own:
            c.close()
