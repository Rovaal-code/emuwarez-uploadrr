"""eMuwarez request synchronization and matching."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import sqlite3
import unicodedata
from typing import Optional

from ..config import load_app_config
from ..database import get_setting_canonical, get_state, set_state
from ..integrations import emu
from ..integrations.base import IntegrationError
from ..models import RequestItem, RequestStatus, TaskStatus
from .library import update_request_status
from .tasks import start_task, finish_task
from .compatibility import (
    match_request_to_library,
    classify_request_match,
    rank_request_matches,
)

SYNC_STATE_KEY = "last_emu_requests_sync_utc"
MIN_SYNC_SECONDS = 3600

# How long a "does this already exist on eMuwarez's own torrent catalog?"
# check stays cached before it's worth re-querying the real API again. A
# request's status on eMuwarez's catalog doesn't change minute to minute,
# and this is a live network call (unlike the rest of matching, which is
# pure in-memory comparison against already-synced local data) — so this
# is deliberately much coarser than MIN_SYNC_SECONDS.
EMU_CATALOG_CHECK_TTL_SECONDS = 24 * 3600


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


def get_request_sync_status(conn: sqlite3.Connection) -> dict:
    """Return sync status info: last_sync_at, wait_seconds, can_sync."""
    last_str = get_state(conn, SYNC_STATE_KEY)
    last = _parse_iso(last_str)
    wait = seconds_until_next_sync(conn)
    next_at = None
    if last:
        next_at = (last + dt.timedelta(seconds=MIN_SYNC_SECONDS)).isoformat()
    return {
        "last_sync_at": last_str,
        "next_sync_at": next_at,
        "can_sync": wait <= 0,
        "wait_seconds": wait,
        "min_interval_seconds": MIN_SYNC_SECONDS,
    }


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


# ---------------------------------------------------------------------------
# Primary sync function — UNIT3D api_token auth (Phase 5B)
# ---------------------------------------------------------------------------

def _resolve_emu_api_key(conn: sqlite3.Connection, passphrase: Optional[str] = None) -> Optional[str]:
    """The Settings UI stores the eMuwarez key in the DB (settings.emu.api_key);
    the legacy YAML config is only a fallback. Reading only load_app_config()
    made the requests task report "No hay API Key" even when it was configured."""
    key = get_setting_canonical(conn, "emu.api_key")
    if key:
        return key
    cfg = load_app_config(passphrase=passphrase)
    return getattr(cfg, "emu_api_key", None) if cfg else None


def sync_emu_requests(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
    passphrase: Optional[str] = None,
) -> dict[str, int | str]:
    """Sync EMU requests using UNIT3D ?api_token= auth. Rate-limited to 1/hour."""
    allowed, wait = can_sync_requests(conn, force=force)
    if not allowed:
        return {"status": "throttled", "wait_seconds": wait, "imported": 0, "matched": 0}

    task_id = start_task(conn, "sync-emu-requests", "Sincronizando peticiones EMU")
    api_key = _resolve_emu_api_key(conn, passphrase)
    if not api_key:
        finish_task(conn, task_id, TaskStatus.FAILED.value, "No hay API Key de eMuwarez configurada")
        raise IntegrationError("No hay API Key de eMuwarez configurada")

    try:
        raw_items = emu.emu_fetch_all_pages(api_key)
        items = emu.normalize_requests(raw_items)
        for item in items:
            upsert_request(conn, item)
        set_state(conn, SYNC_STATE_KEY, _utcnow().isoformat())
        conn.commit()
        matched = match_all_requests(conn, emu_api_key=api_key)
        summary = f"{len(items)} peticiones importadas, {matched} cruces"
        finish_task(conn, task_id, TaskStatus.COMPLETED.value, summary)
        return {"status": "ok", "imported": len(items), "matched": matched}
    except Exception as exc:
        finish_task(conn, task_id, TaskStatus.FAILED.value, str(exc))
        raise


# ---------------------------------------------------------------------------
# Legacy sync (kept for backward compat with tests/CLI set-endpoint flow)
# ---------------------------------------------------------------------------

def sync_requests(
    conn: sqlite3.Connection,
    *,
    endpoint_url: Optional[str] = None,
    force: bool = False,
    passphrase: Optional[str] = None,
) -> dict[str, int | str]:
    """Legacy sync using explicit endpoint_url + Bearer header."""
    allowed, wait = can_sync_requests(conn, force=force)
    if not allowed:
        return {"status": "throttled", "wait_seconds": wait, "imported": 0}
    task_id = start_task(conn, "sync-emu-requests", "Sincronizando peticiones EMU")
    cfg = load_app_config(passphrase=passphrase)
    if not cfg or not getattr(cfg, "emu_api_key", None):
        finish_task(conn, task_id, TaskStatus.FAILED.value, "No hay API Key de eMuwarez configurada")
        raise IntegrationError("No hay API Key de eMuwarez configurada")
    try:
        raw = emu.get_requests(
            cfg.emu_api_key,
            endpoint_url=endpoint_url or get_state(conn, "emu_requests_endpoint"),
        )
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


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _should_check_emu_catalog(req: dict, *, status: Optional[str]) -> bool:
    """Decide whether a request is worth an extra live check against
    eMuwarez's real torrent catalog (/api/torrents/filter by tmdbId).

    Only triggers for the cases that were flagged as likely false negatives:
    no library candidate at all, or the internal matcher classified it as
    "No compatible". Anything already Compatible/Parcial/Llena skips this —
    those already have a usable answer, so spending a network call (and
    eMuwarez API quota) on them would be waste, not signal.
    """
    if status not in (None, "No compatible"):
        return False
    if not req.get("tmdb_id"):
        # Without a tmdb_id this would fall back to free-text `name` search,
        # which has the exact same fuzziness problem this check exists to
        # avoid — not worth the network call.
        return False
    checked_at = _parse_iso(req.get("emu_catalog_checked_at"))
    if checked_at and (_utcnow() - checked_at).total_seconds() < EMU_CATALOG_CHECK_TTL_SECONDS:
        return False
    return True


def _check_emu_catalog_duplicate(conn: sqlite3.Connection, req: dict, emu_api_key: str) -> None:
    """Query eMuwarez's own torrent catalog directly by tmdb_id.

    Never raises: a network failure here must not break the rest of a
    sync/match run, so any error just gets cached as "error" (and will be
    retried after the TTL) instead of propagating.
    """
    try:
        response = emu.emu_search_existing(emu_api_key, tmdb_id=req.get("tmdb_id"))
        data = response.get("data") if isinstance(response, dict) else None
        result = "found" if isinstance(data, list) and data else "not_found"
    except Exception:
        result = "error"
    conn.execute(
        "UPDATE request_items SET emu_catalog_checked_at = ?, emu_catalog_result = ? WHERE id = ?",
        (_utcnow().isoformat(), result, req["id"]),
    )


def match_all_requests(conn: sqlite3.Connection, *, emu_api_key: Optional[str] = None) -> int:
    """Re-run compatibility matching for all request items. Returns updated count.

    `emu_api_key`: reuse an already-loaded key (e.g. from sync_emu_requests)
    when available; falls back to loading config independently so this can
    still be called standalone (CLI, "recompute matches" endpoint, etc.).
    """
    if emu_api_key is None:
        cfg = load_app_config()
        emu_api_key = getattr(cfg, "emu_api_key", None) if cfg else None

    # Snapshot which requests already had compatible content, so afterwards we
    # only notify about the ones that *newly* became satisfiable this run.
    before_compatible = _compatible_request_ids(conn)

    requests = [dict(r) for r in conn.execute("SELECT * FROM request_items").fetchall()]
    library = [dict(r) for r in conn.execute("SELECT * FROM library_items").fetchall()]
    updated = 0
    for req in requests:
        candidates = match_request_to_library(req, library)
        if not candidates:
            if emu_api_key and _should_check_emu_catalog(req, status=None):
                _check_emu_catalog_duplicate(conn, req, emu_api_key)
            continue
        best = candidates[0]
        classification = classify_request_match(
            req,
            best["item"],
            id_match=best["id_match"],
            title_match=best["title_match"],
            base_confidence=best["confidence"],
        )
        reasons_str = "\n".join(classification["reasons"])
        reasons_json = json.dumps(classification["reasons"], ensure_ascii=False)
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
                best["item"]["id"],
                req["id"],
                classification["status"],
                classification["confidence"],
                None if classification["resolution_match"] is None else int(bool(classification["resolution_match"])),
                None if classification["source_match"] is None else int(bool(classification["source_match"])),
                1 if best["id_match"] else 0,
                reasons_str,
            ),
        )
        update_request_status(conn, int(best["item"]["id"]), classification["status"], int(req["id"]))
        if emu_api_key and _should_check_emu_catalog(req, status=classification["status"]):
            _check_emu_catalog_duplicate(conn, req, emu_api_key)
        updated += 1
    conn.commit()
    _notify_new_compatible_matches(conn, before_compatible)
    return updated


def _compatible_request_ids(conn: sqlite3.Connection) -> set[int]:
    """request_item_ids that currently have at least one 'Compatible' match."""
    rows = conn.execute(
        "SELECT DISTINCT request_item_id FROM request_matches WHERE status = 'Compatible'"
    ).fetchall()
    return {int(r[0]) for r in rows}


def _notify_new_compatible_matches(conn: sqlite3.Connection, before_ids: set[int]) -> None:
    """Emit one notification per request that became satisfiable this run.
    Best-effort: never lets a notification failure break matching."""
    try:
        new_ids = _compatible_request_ids(conn) - before_ids
        if not new_ids:
            return
        from .notification_center import emit
        for rid in new_ids:
            row = conn.execute(
                "SELECT title, url FROM request_items WHERE id = ?", (rid,)
            ).fetchone()
            title = (row["title"] if row else None) or f"Petición #{rid}"
            emit(
                conn, "request_match_found",
                "Contenido compatible con una petición",
                f"Tienes contenido compatible con la petición «{title}».",
                link=(row["url"] if row and row["url"] else "/requests"),
                level="info",
                entity_type="request_item",
                entity_id=rid,
            )
    except Exception:
        logging.getLogger("emuwarez.notifications").exception(
            "No se pudieron emitir notificaciones de peticiones compatibles"
        )


# Keep old name as alias for backward compat
def match_requests(conn: sqlite3.Connection) -> int:
    return match_all_requests(conn)


def match_single_request(
    conn: sqlite3.Connection, request_id: int, *, emu_api_key: Optional[str] = None
) -> Optional[dict]:
    """Re-match a single request against library. Returns best match dict or None."""
    req_row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    if not req_row:
        return None
    req = dict(req_row)
    if emu_api_key is None:
        cfg = load_app_config()
        emu_api_key = getattr(cfg, "emu_api_key", None) if cfg else None
    library = [dict(r) for r in conn.execute("SELECT * FROM library_items").fetchall()]
    candidates = match_request_to_library(req, library)
    if not candidates:
        if emu_api_key and _should_check_emu_catalog(req, status=None):
            _check_emu_catalog_duplicate(conn, req, emu_api_key)
            conn.commit()
        return None
    best = candidates[0]
    classification = classify_request_match(
        req,
        best["item"],
        id_match=best["id_match"],
        title_match=best["title_match"],
        base_confidence=best["confidence"],
    )
    reasons_str = "\n".join(classification["reasons"])
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
            best["item"]["id"],
            req["id"],
            classification["status"],
            classification["confidence"],
            None if classification["resolution_match"] is None else int(bool(classification["resolution_match"])),
            None if classification["source_match"] is None else int(bool(classification["source_match"])),
            1 if best["id_match"] else 0,
            reasons_str,
        ),
    )
    update_request_status(conn, int(best["item"]["id"]), classification["status"], int(req["id"]))
    if emu_api_key and _should_check_emu_catalog(req, status=classification["status"]):
        _check_emu_catalog_duplicate(conn, req, emu_api_key)
    conn.commit()
    return {
        "library_item_id": best["item"]["id"],
        "library_title": best["item"].get("title"),
        **classification,
    }


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def list_request_items(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """Return paginated request items enriched with best match info."""
    where_clauses: list[str] = []
    params: list = []

    if search:
        where_clauses.append("ri.title LIKE ?")
        params.append(f"%{search}%")
    if status:
        where_clauses.append("COALESCE(rm.status, 'Sin coincidencia') = ?")
        params.append(status)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM request_items ri
        LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
          AND rm.id = (
            SELECT id FROM request_matches rm2
            WHERE rm2.request_item_id = ri.id
            ORDER BY rm2.confidence DESC LIMIT 1
          )
        {where_sql}
    """
    total_row = conn.execute(count_sql, params).fetchone()
    total = int(total_row["cnt"] if total_row else 0)

    items_sql = f"""
        SELECT
            ri.*,
            rm.status AS compatibility_status,
            rm.confidence AS compatibility_confidence,
            rm.resolution_match,
            rm.source_match,
            rm.type_match,
            rm.reasons AS match_reasons,
            rm.library_item_id,
            li.title AS library_title,
            li.local_status
        FROM request_items ri
        LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
          AND rm.id = (
            SELECT id FROM request_matches rm2
            WHERE rm2.request_item_id = ri.id
            ORDER BY rm2.confidence DESC LIMIT 1
          )
        LEFT JOIN library_items li ON li.id = rm.library_item_id
        {where_sql}
        ORDER BY ri.updated_at DESC, ri.title COLLATE NOCASE
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(items_sql, params + [limit, offset]).fetchall()
    return {
        "items": [_safe_request_dict(dict(r)) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_request_item(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    """Return a single request_item dict (no match info)."""
    row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    return _safe_request_dict(dict(row)) if row else None


def get_request_detail(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    """Return request + best match info."""
    req_row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    if not req_row:
        return None
    result = _safe_request_dict(dict(req_row))
    match_row = conn.execute(
        """
        SELECT rm.*, li.title AS library_title, li.local_status, li.resolution AS local_resolution,
               li.source AS local_source, li.path AS local_path, li.nomenclature_status
        FROM request_matches rm
        JOIN library_items li ON li.id = rm.library_item_id
        WHERE rm.request_item_id = ?
        ORDER BY rm.confidence DESC
        LIMIT 1
        """,
        (request_id,),
    ).fetchone()
    if match_row:
        md = dict(match_row)
        reasons = md.get("reasons") or ""
        result["match"] = {
            "id": md["id"],
            "library_item_id": md["library_item_id"],
            "library_title": md.get("library_title"),
            "local_status": md.get("local_status"),
            "local_resolution": md.get("local_resolution"),
            "local_source": md.get("local_source"),
            "local_path": md.get("local_path"),
            "nomenclature_status": md.get("nomenclature_status"),
            "status": md["status"],
            "confidence": float(md["confidence"]),
            "resolution_match": bool(md["resolution_match"]) if md["resolution_match"] is not None else None,
            "source_match": bool(md["source_match"]) if md["source_match"] is not None else None,
            "id_match": bool(md.get("type_match")),
            "reasons": [r for r in reasons.splitlines() if r],
        }
    else:
        result["match"] = None
    return result


def mark_request_reviewed(conn: sqlite3.Connection, request_id: int) -> bool:
    """Set reviewed_at = now on a request_item. Returns True if found."""
    row = conn.execute("SELECT id FROM request_items WHERE id = ?", (request_id,)).fetchone()
    if not row:
        return False
    try:
        conn.execute(
            "UPDATE request_items SET reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (request_id,),
        )
        conn.commit()
    except Exception:
        # reviewed_at column may not exist yet (pre-migration DB); silently succeed
        conn.rollback()
    return True


# ---------------------------------------------------------------------------
# Legacy query functions (backward compat)
# ---------------------------------------------------------------------------

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


def set_requests_endpoint(conn: sqlite3.Connection, url: str) -> None:
    set_state(conn, "emu_requests_endpoint", url)
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _safe_request_dict(d: dict) -> dict:
    """Remove author info if author_visible=0."""
    if not d.get("author_visible"):
        d.pop("author", None)
    return d
