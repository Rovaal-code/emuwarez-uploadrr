"""eMuwarez request synchronization and matching."""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import unicodedata
from typing import Optional

from ..config import load_app_config
from ..database import get_state, set_state
from ..integrations import emu
from ..integrations.base import IntegrationError
from ..models import RequestItem, RequestStatus, TaskStatus
from .library import update_request_status
from .tasks import start_task, finish_task

SYNC_STATE_KEY = "last_emu_requests_sync_utc"
MIN_SYNC_SECONDS = 3600


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def seconds_until_next_sync(conn: sqlite3.Connection) -> int:
    last = _parse_iso(get_state(conn, SYNC_STATE_KEY))
    if not last:
        return 0
    elapsed = (_utcnow() - last).total_seconds()
    return max(0, int(MIN_SYNC_SECONDS - elapsed))


def can_sync_requests(conn: sqlite3.Connection, *, force: bool = False) -> tuple[bool, int]:
    if force:
        return True, 0
    wait = seconds_until_next_sync(conn)
    return wait <= 0, wait


def upsert_request(conn: sqlite3.Connection, item: RequestItem) -> int:
    conn.execute(
        """
        INSERT INTO request_items(
            emu_id, title, category, requested_source, requested_resolution,
            emu_status, points, comments, created_at, tmdb_id, imdb_id, url,
            author, author_visible, raw_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(emu_id) DO UPDATE SET
            title = excluded.title,
            category = excluded.category,
            requested_source = excluded.requested_source,
            requested_resolution = excluded.requested_resolution,
            emu_status = excluded.emu_status,
            points = excluded.points,
            comments = excluded.comments,
            created_at = excluded.created_at,
            tmdb_id = excluded.tmdb_id,
            imdb_id = excluded.imdb_id,
            url = excluded.url,
            author = excluded.author,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            item.emu_id, item.title, item.category, item.requested_source,
            item.requested_resolution, item.emu_status, item.points, item.comments,
            item.created_at, item.tmdb_id, item.imdb_id, item.url, item.author,
            1 if item.author_visible else 0, item.raw_json,
        ),
    )
    row = conn.execute("SELECT id FROM request_items WHERE emu_id = ?", (item.emu_id,)).fetchone()
    conn.commit()
    return int(row["id"])


def sync_requests(conn: sqlite3.Connection, *, endpoint_url: Optional[str] = None, force: bool = False, passphrase: Optional[str] = None) -> dict[str, int | str]:
    allowed, wait = can_sync_requests(conn, force=force)
    if not allowed:
        return {"status": "throttled", "wait_seconds": wait, "imported": 0}
    task_id = start_task(conn, "sync-emu-requests", "Sincronizando peticiones EMU")
    cfg = load_app_config(passphrase=passphrase)
    if not cfg or not getattr(cfg, "emu_api_key", None):
        finish_task(conn, task_id, TaskStatus.FAILED.value, "No hay API key EMU configurada")
        raise IntegrationError("No hay API key EMU configurada")
    try:
        raw = emu.get_requests(cfg.emu_api_key, endpoint_url=endpoint_url or get_state(conn, "emu_requests_endpoint"))
        items = emu.normalize_requests(raw)
        for item in items:
            upsert_request(conn, item)
        set_state(conn, SYNC_STATE_KEY, _utcnow().isoformat())
        conn.commit()
        match_requests(conn)
        summary = f"{len(items)} peticiones importadas"
        finish_task(conn, task_id, TaskStatus.COMPLETED.value, summary)
        return {"status": "ok", "imported": len(items)}
    except Exception as exc:
        finish_task(conn, task_id, TaskStatus.FAILED.value, str(exc))
        raise


def list_requests(conn: sqlite3.Connection, *, limit: int = 50, search: Optional[str] = None) -> list[dict]:
    params: list = []
    sql = "SELECT * FROM request_items"
    if search:
        sql += " WHERE title LIKE ?"
        params.append(f"%{search}%")
    sql += " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ?"
    params.append(limit)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_request(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    return dict(row) if row else None


def set_requests_endpoint(conn: sqlite3.Connection, url: str) -> None:
    set_state(conn, "emu_requests_endpoint", url)
    conn.commit()


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _source_matches(requested: str | None, local: str | None) -> Optional[bool]:
    if not requested or requested.lower() in {"any", "cualquiera", "todos"}:
        return True
    if not local:
        return False
    return normalize_title(requested) == normalize_title(local)


def _resolution_matches(requested: str | None, local: str | None) -> Optional[bool]:
    if not requested or requested.lower() in {"any", "cualquiera", "todos"}:
        return True
    if not local:
        return False
    return requested.lower().replace(" ", "") == local.lower().replace(" ", "")


def _classify_match(req: dict, item: dict) -> tuple[str, float, bool | None, bool | None, list[str]]:
    req_res = req.get("requested_resolution")
    req_src = req.get("requested_source")
    local_res = item.get("resolution")
    local_src = item.get("source")
    res_match = _resolution_matches(req_res, local_res)
    src_match = _source_matches(req_src, local_src)
    reasons: list[str] = []
    if res_match:
        reasons.append(f"Resolución compatible: {local_res or 'sin restricción'}")
    else:
        reasons.append(f"Resolución diferente: EMU pide {req_res or 'N/D'} y local es {local_res or 'N/D'}")
    if src_match:
        reasons.append(f"Source compatible: {local_src or 'sin restricción'}")
    else:
        reasons.append(f"Source diferente: EMU pide {req_src or 'N/D'} y local es {local_src or 'N/D'}")
    status_text = str(req.get("emu_status") or "").lower()
    if "lleno" in status_text or "filled" in status_text or status_text == "1":
        return RequestStatus.FILLED.value, 1.0, res_match, src_match, reasons
    if res_match and src_match:
        return RequestStatus.COMPATIBLE.value, 1.0, res_match, src_match, reasons
    if res_match is False or src_match is False:
        return RequestStatus.PARTIAL.value, 0.75, res_match, src_match, reasons
    return RequestStatus.NOT_COMPATIBLE.value, 0.25, res_match, src_match, reasons


def match_requests(conn: sqlite3.Connection) -> int:
    requests = [dict(r) for r in conn.execute("SELECT * FROM request_items").fetchall()]
    library = [dict(r) for r in conn.execute("SELECT * FROM library_items").fetchall()]
    updated = 0
    for req in requests:
        candidates: list[dict] = []
        if req.get("tmdb_id"):
            candidates.extend([i for i in library if i.get("tmdb_id") and str(i.get("tmdb_id")) == str(req.get("tmdb_id"))])
        if not candidates and req.get("imdb_id"):
            candidates.extend([i for i in library if i.get("imdb_id") and str(i.get("imdb_id")) == str(req.get("imdb_id"))])
        if not candidates:
            req_title = normalize_title(req.get("title"))
            candidates.extend([i for i in library if normalize_title(i.get("title")) == req_title])
        if not candidates:
            continue
        item = candidates[0]
        status, confidence, res_match, src_match, reasons = _classify_match(req, item)
        conn.execute(
            """
            INSERT INTO request_matches(
                library_item_id, request_item_id, status, confidence,
                resolution_match, source_match, type_match, reasons, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(library_item_id, request_item_id) DO UPDATE SET
                status = excluded.status,
                confidence = excluded.confidence,
                resolution_match = excluded.resolution_match,
                source_match = excluded.source_match,
                type_match = excluded.type_match,
                reasons = excluded.reasons,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                item["id"], req["id"], status, confidence,
                None if res_match is None else int(bool(res_match)),
                None if src_match is None else int(bool(src_match)),
                1, "\n".join(reasons),
            ),
        )
        update_request_status(conn, int(item["id"]), status, int(req["id"]))
        updated += 1
    conn.commit()
    return updated


def get_match_for_request(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT rm.*, li.title AS library_title, li.local_status, li.resolution AS local_resolution,
               li.source AS local_source, li.path AS local_path
        FROM request_matches rm
        JOIN library_items li ON li.id = rm.library_item_id
        WHERE rm.request_item_id = ?
        ORDER BY rm.confidence DESC
        LIMIT 1
        """,
        (request_id,),
    ).fetchone()
    return dict(row) if row else None
