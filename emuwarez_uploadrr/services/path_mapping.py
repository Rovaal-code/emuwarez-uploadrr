"""Remote path mapping — translate the paths Radarr/Sonarr report into the
paths where the media is actually reachable from where this app runs.

Like Radarr/Sonarr's "Remote Path Mappings": you mount the remote library
anywhere (SSHFS/NFS/SMB) and map the reported prefix to your local mount, so
MediaInfo / verification / upload can read the real file without having to
reproduce the exact `/data/...` layout locally.

Stored as JSON in the setting `library.path_mappings`:
    [{"from": "/data/media", "to": "/home/alvaro/mnt/emu-media"}, ...]
"""
from __future__ import annotations

import json

from ..database import connect, db_path, get_setting_canonical

_SETTING_KEY = "library.path_mappings"


def get_path_mappings(conn=None) -> list[dict]:
    own = conn is None
    conn = conn or connect(db_path())
    try:
        raw = get_setting_canonical(conn, _SETTING_KEY)
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [{"from": str(m["from"]), "to": str(m["to"])}
                for m in data if isinstance(m, dict) and m.get("from") and m.get("to")]
    except Exception:
        return []
    finally:
        if own:
            conn.close()


def resolve_local_path(path: str | None, conn=None) -> str | None:
    """Return `path` with the first matching mapping applied (longest prefix
    wins). Paths with no matching mapping are returned unchanged, so this is a
    no-op when no mappings are configured."""
    if not path:
        return path
    mappings = get_path_mappings(conn)
    for m in sorted(mappings, key=lambda x: len(x["from"]), reverse=True):
        frm = m["from"].rstrip("/")
        to = m["to"].rstrip("/")
        if path == m["from"] or path == frm:
            return to or "/"
        if path.startswith(frm + "/"):
            return to + path[len(frm):]
    return path
