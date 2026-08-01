"""eMuwarez request synchronization and matching."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import sqlite3
import unicodedata
from typing import Optional

from ..database import get_setting_canonical, get_state, set_state
from . import cli_config
from ..integrations import emu
from ..integrations.base import IntegrationError
from ..models import RequestItem, RequestStatus, TaskStatus
from .library import update_request_status, content_display_title
from .tasks import start_task, finish_task
from .compatibility import (
    match_request_to_library,
    classify_request_match,
    rank_request_matches,
    emu_override_status,
)

logger = logging.getLogger("emuwarez.requests")

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
            emu_status, points, comments, created_at, tmdb_id, imdb_id, tvdb_id, mal_id, url,
            author, author_visible, raw_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
            tvdb_id = excluded.tvdb_id,
            mal_id = excluded.mal_id,
            url = excluded.url,
            author = excluded.author,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            item.emu_id, item.title, item.category, item.requested_source,
            item.requested_resolution, item.emu_status, item.points, item.comments,
            item.created_at, item.tmdb_id, item.imdb_id, item.tvdb_id, item.mal_id, item.url, item.author,
            1 if item.author_visible else 0, item.raw_json,
        ),
    )
    row = conn.execute("SELECT id FROM request_items WHERE emu_id = ?", (item.emu_id,)).fetchone()
    conn.commit()
    return int(row["id"])


# ---------------------------------------------------------------------------
# Primary sync function — UNIT3D api_token auth (Phase 5B)
# ---------------------------------------------------------------------------

def _is_requests_endpoint_missing(exc: Exception) -> bool:
    m = str(exc).lower()
    return "404" in m and ("api/requests" in m or "could not be found" in m or "route" in m)


def _resolve_emu_api_key(conn: sqlite3.Connection) -> Optional[str]:
    """La API key de eMuwarez: la interfaz la guarda en la BD
    (settings.emu.api_key) y esa es la fuente; la configuración del CLI antiguo
    es solo un respaldo. Leer únicamente esta última hacía que la tarea de
    peticiones dijera "No hay API Key" teniéndola configurada.

    El respaldo se lee con services/cli_config, no con legacy.load_app_config:
    aquella podía terminar en SystemExit o pidiendo una contraseña por teclado
    desde el hilo del servidor. Ver la cabecera de cli_config.py."""
    key = get_setting_canonical(conn, "emu.api_key")
    if key:
        return key
    return cli_config.emu_api_key()


def sync_emu_requests(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
) -> dict[str, int | str]:
    """Sync EMU requests using UNIT3D ?api_token= auth. Rate-limited to 1/hour."""
    allowed, wait = can_sync_requests(conn, force=force)
    if not allowed:
        return {"status": "throttled", "wait_seconds": wait, "imported": 0, "matched": 0}

    task_id = start_task(conn, "sync-emu-requests", "Sincronizando peticiones EMU")
    api_key = _resolve_emu_api_key(conn)
    if not api_key:
        finish_task(conn, task_id, TaskStatus.FAILED.value, "No hay API Key de eMuwarez configurada")
        raise IntegrationError("No hay API Key de eMuwarez configurada")

    # Record the throttle at START (not at the end), so a slow fetch or a page
    # refresh mid-sync can't relaunch it. Restored if the sync fails / is
    # unavailable, so a failed run doesn't lock the user out for an hour.
    prev_sync = get_state(conn, SYNC_STATE_KEY)
    set_state(conn, SYNC_STATE_KEY, _utcnow().isoformat())
    conn.commit()

    def _restore_throttle() -> None:
        set_state(conn, SYNC_STATE_KEY, prev_sync or "")
        conn.commit()

    logger.info("Sincronización de peticiones iniciada")
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
        logger.info("Sincronización de peticiones terminada: %d importadas, %d cruzadas con tu biblioteca",
                    len(items), matched)
        return {"status": "ok", "imported": len(items), "matched": matched}
    except IntegrationError as exc:
        # eMuwarez (UNIT3D) does not expose /api/requests — the endpoint 404s.
        # That's a known tracker limitation, not a real failure: mark the task
        # SKIPPED with a clear message instead of a scary raw HTTP 404.
        _restore_throttle()
        if _is_requests_endpoint_missing(exc):
            detail = "eMuwarez no expone el endpoint de peticiones (/api/requests); función no disponible aún."
            finish_task(conn, task_id, TaskStatus.SKIPPED.value, "No implementado")
            logger.info("Sincronización de peticiones omitida: %s", detail)
            return {"status": "unavailable", "imported": 0, "matched": 0, "message": detail}
        finish_task(conn, task_id, TaskStatus.FAILED.value, str(exc))
        logger.warning("Sincronización de peticiones fallida: %s", exc)
        raise
    except Exception as exc:
        _restore_throttle()
        finish_task(conn, task_id, TaskStatus.FAILED.value, str(exc))
        logger.error("Sincronización de peticiones fallida: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Legacy sync (kept for backward compat with tests/CLI set-endpoint flow)
# ---------------------------------------------------------------------------

def sync_requests(
    conn: sqlite3.Connection,
    *,
    endpoint_url: Optional[str] = None,
    force: bool = False,
) -> dict[str, int | str]:
    """Legacy sync using explicit endpoint_url + Bearer header."""
    allowed, wait = can_sync_requests(conn, force=force)
    if not allowed:
        return {"status": "throttled", "wait_seconds": wait, "imported": 0}
    task_id = start_task(conn, "sync-emu-requests", "Sincronizando peticiones EMU")
    # Mismo resolutor que sync_emu_requests: la BD primero. Esta función leía
    # SOLO la configuración del CLI, así que decía "No hay API Key" a quien la
    # tuviera puesta en la interfaz — justo el fallo que el docstring de
    # _resolve_emu_api_key llevaba describiendo ochenta líneas más arriba.
    api_key = _resolve_emu_api_key(conn)
    if not api_key:
        finish_task(conn, task_id, TaskStatus.FAILED.value, "No hay API Key de eMuwarez configurada")
        raise IntegrationError("No hay API Key de eMuwarez configurada")
    try:
        raw = emu.get_requests(
            api_key,
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


_AVAILABLE = {"Disponible", "Subido", "Subiendo", "Parcial"}


def _uniq(values) -> Optional[str]:
    s = {v for v in values}
    return next(iter(s)) if len(s) == 1 else None


def _relevant_episodes(conn, matched_id, matched_type, scope, season, episode, ignore_specials):
    """Episode rows that a request's scope points at within the matched
    series/season (the single episode, the season's episodes, or all
    non-special episodes of the series)."""
    if matched_type == "series":
        if scope == "episode" and season is not None and episode is not None:
            return conn.execute(
                "SELECT e.* FROM library_items e JOIN library_items se ON e.parent_id = se.id "
                "WHERE se.parent_id = ? AND se.item_type = 'season' AND se.season_number = ? "
                "AND e.item_type = 'episode' AND e.episode_number = ?",
                (matched_id, season, episode)).fetchall()
        if scope == "season" and season is not None:
            return conn.execute(
                "SELECT e.* FROM library_items e JOIN library_items se ON e.parent_id = se.id "
                "WHERE se.parent_id = ? AND se.item_type = 'season' AND se.season_number = ? "
                "AND e.item_type = 'episode'",
                (matched_id, season)).fetchall()
        clause = " AND (se.season_number IS NULL OR se.season_number != 0)" if ignore_specials else ""
        return conn.execute(
            "SELECT e.* FROM library_items e JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'" + clause,
            (matched_id,)).fetchall()
    if matched_type == "season":
        if scope == "episode" and episode is not None:
            return conn.execute(
                "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode' AND episode_number = ?",
                (matched_id, episode)).fetchall()
        return conn.execute(
            "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode'",
            (matched_id,)).fetchall()
    return []


def _pack_blocked_reason(conn: sqlite3.Connection, matched_item: dict, req: dict) -> Optional[str]:
    """Por qué la temporada que pide esta petición no puede subirse como pack.

    None cuando sí puede, o cuando la petición no es de temporada/serie
    completa (un capítulo suelto no necesita pack).
    """
    if req.get("req_scope") == "episode":
        return None
    from .season_pack import can_pack_from_rollup

    season_id = _scoped_library_id(conn, matched_item, req)
    row = conn.execute(
        "SELECT * FROM library_items WHERE id = ? AND item_type = 'season'", (season_id,)
    ).fetchone()
    if not row:
        return None
    season = dict(row)
    if can_pack_from_rollup(season):
        return None
    if not season.get("resolution"):
        falta = "los capítulos no coinciden en resolución"
    elif not season.get("video_codec"):
        falta = "los capítulos no coinciden en códec de vídeo"
    else:
        falta = "algún capítulo no tiene castellano"
    return (f"La temporada no puede subirse como pack: {falta}. "
            "Sus capítulos sí se pueden subir uno a uno.")


def _scoped_library_id(conn: sqlite3.Connection, matched_item: dict, req: dict) -> int:
    """The library row the request actually refers to: the season row for a
    season-scoped request, the episode row for an episode-scoped one, and the
    matched row itself otherwise. Used for the links out of a request, so
    "Los Tudor (2007) - Temporada 2" opens that season and not the whole
    series."""
    matched_id = int(matched_item["id"])
    if matched_item.get("item_type") not in ("series", "season"):
        return matched_id
    season = req.get("req_season")
    episode = req.get("req_episode")
    if season is None:
        return matched_id

    season_id = matched_id
    if matched_item.get("item_type") == "series":
        row = conn.execute(
            "SELECT id FROM library_items WHERE parent_id = ? AND item_type = 'season' "
            "AND season_number = ?",
            (matched_id, season),
        ).fetchone()
        if not row:
            return matched_id
        season_id = int(row["id"])

    if req.get("req_scope") == "episode" and episode is not None:
        row = conn.execute(
            "SELECT id FROM library_items WHERE parent_id = ? AND item_type = 'episode' "
            "AND episode_number = ?",
            (season_id, episode),
        ).fetchone()
        if row:
            return int(row["id"])
    return season_id


def _effective_target(conn: sqlite3.Connection, matched_item: dict, req: dict) -> dict:
    """A copy of the matched library item with resolution/source/codecs/audio/
    subs/size/path/local_status reflecting the request's SCOPE, so a
    series/season rollup (which stores none of its own) is classified and shown
    against its real episodes: the specific episode, or the uniform value across
    the relevant episodes (None when they differ)."""
    it = dict(matched_item)
    if it.get("item_type") not in ("series", "season"):
        return it
    ignore_specials = (get_setting_canonical(conn, "series.ignore_specials") or "true") != "false"
    eps = [dict(e) for e in _relevant_episodes(
        conn, it["id"], it["item_type"], req.get("req_scope"),
        req.get("req_season"), req.get("req_episode"), ignore_specials)]
    if not eps:
        return it
    single = eps[0] if len(eps) == 1 else None
    for key in ("resolution", "source", "video_codec", "audio_languages", "subtitle_languages"):
        it[key] = single[key] if single else _uniq(e.get(key) for e in eps)
    if single:
        it["size_bytes"] = single.get("size_bytes")
        it["path"] = single.get("path")
        it["title"] = single.get("title") or it.get("title")
        it["local_status"] = single.get("local_status")
        it["id"] = single["id"]
    else:
        it["size_bytes"] = sum(e.get("size_bytes") or 0 for e in eps) or None
        statuses = [e.get("local_status") for e in eps]
        avail = [s for s in statuses if s in _AVAILABLE]
        it["local_status"] = "Disponible" if len(avail) == len(statuses) and avail else ("Parcial" if avail else "Faltante")
        paths = [e["path"] for e in eps if e.get("path")]
        if paths:
            dirs = {os.path.dirname(p) for p in paths}
            it["path"] = next(iter(dirs)) if len(dirs) == 1 else os.path.commonpath(paths)
    return it


def match_all_requests(conn: sqlite3.Connection, *, emu_api_key: Optional[str] = None) -> int:
    """Re-run compatibility matching for all request items. Returns updated count.

    `emu_api_key`: reuse an already-loaded key (e.g. from sync_emu_requests)
    when available; falls back to loading config independently so this can
    still be called standalone (CLI, "recompute matches" endpoint, etc.).
    """
    if emu_api_key is None:
        # Mismo resolutor que el resto: la BD primero. Antes leía SOLO la
        # configuración del CLI, así que a quien tuviera la clave puesta en la
        # interfaz le salía None y la comprobación contra el catálogo de
        # eMuwarez se saltaba en silencio.
        emu_api_key = _resolve_emu_api_key(conn)

    # Snapshot which requests already had compatible content, so afterwards we
    # only notify about the ones that *newly* became satisfiable this run.
    before_compatible = _compatible_request_ids(conn)

    # Se limpia antes de recalcular: sin esto, un estado se quedaba pegado en
    # la fila donde se escribió una vez y ya nadie lo movía. Con el arreglo de
    # arriba (escribir en la temporada y no en la serie), las series que ya
    # llevaban el estado de una petición de temporada se habrían quedado con
    # él para siempre.
    conn.execute(
        "UPDATE library_items SET request_status = 'Sin petición', request_id = NULL "
        "WHERE request_status != 'Sin petición' OR request_id IS NOT NULL"
    )
    conn.commit()

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
            _effective_target(conn, best["item"], req),
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
        # A la fila que la petición pide DE VERDAD, no a la que cruzó el
        # emparejador. Para una petición de temporada eso es la serie entera
        # (todas las temporadas comparten su tmdb_id), así que el estado
        # aterrizaba en la serie y la temporada seguía diciendo "Sin petición".
        update_request_status(
            conn, _scoped_library_id(conn, best["item"], req),
            classification["status"], int(req["id"]),
        )
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
                "SELECT title, url, req_scope, req_season, req_episode"
                " FROM request_items WHERE id = ?", (rid,)
            ).fetchone()
            title = (row["title"] if row else None) or f"Petición #{rid}"
            # request_items has neither a poster of its own nor a title that
            # says WHICH season or episode was asked for — both come from the
            # library item behind the very 'Compatible' match this
            # notification is about, so they're read from one single row.
            lib_row = conn.execute(
                """SELECT li.*
                   FROM request_matches rm JOIN library_items li ON li.id = rm.library_item_id
                   WHERE rm.request_item_id = ? AND rm.status = 'Compatible'
                   LIMIT 1""",
                (rid,),
            ).fetchone()
            if row is not None and lib_row is not None:
                # Same canonical title the rest of the app shows ("Serie (Año)
                # - Temporada 2", "Serie (Año) - S02E05", "Título (Año)"), via
                # the shared builder instead of a format of its own. Without
                # the season/episode, every season of the same series notified
                # under the bare series name and they were indistinguishable.
                title = content_display_title(
                    conn, dict(lib_row),
                    season=row["req_season"], episode=row["req_episode"],
                    scope=row["req_scope"],
                ) or title
            emit(
                conn, "request_match_found",
                "Contenido compatible",
                "Tienes contenido compatible con esta petición.",
                link=(row["url"] if row and row["url"] else "/requests"),
                level="info",
                entity_type="request_item",
                entity_id=rid,
                poster_url=lib_row["poster_url"] if lib_row is not None else None,
                content_title=title,
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
        # Mismo resolutor que el resto: la BD primero. Antes leía SOLO la
        # configuración del CLI, así que a quien tuviera la clave puesta en la
        # interfaz le salía None y la comprobación contra el catálogo de
        # eMuwarez se saltaba en silencio.
        emu_api_key = _resolve_emu_api_key(conn)
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
        _effective_target(conn, best["item"], req),
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
    update_request_status(
        conn, _scoped_library_id(conn, best["item"], req),
        classification["status"], int(req["id"]),
    )
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

_REQUEST_SORT = {
    "created_desc": "ri.created_at DESC, ri.updated_at DESC",
    "created_asc": "ri.created_at ASC, ri.updated_at ASC",
    "title": "ri.title COLLATE NOCASE ASC",
    "points_desc": "ri.points IS NULL, ri.points DESC, ri.created_at DESC",
    "points_asc": "COALESCE(ri.points, 0) ASC, ri.created_at DESC",      # menos coins pedidas
    "votes_desc": "COALESCE(ri.votes, 0) DESC, ri.created_at DESC",       # más me gusta
    "comments_desc": "COALESCE(ri.comments, 0) DESC, ri.created_at DESC", # más comentarios
}
_FILLED_STATUSES = ("filled", "1", "lleno", "llena")


def list_request_items(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    resolution: Optional[str] = None,
    source: Optional[str] = None,
    author: Optional[str] = None,
    emu_status: Optional[str] = None,
    sort: Optional[str] = None,
) -> dict:
    """Return paginated request items enriched with best match info."""
    where_clauses: list[str] = []
    params: list = []

    if search:
        where_clauses.append("ri.title LIKE ?")
        params.append(f"%{search}%")
    if status:
        # Mirrors compatibility.emu_override_status() — a request with zero
        # library candidates has no request_matches row at all, but can still
        # be Reclamado/Pendiente/Llena on the tracker itself; keep this SQL
        # fallback in sync with that function if its substring rules change.
        where_clauses.append("""
            COALESCE(
                rm.status,
                CASE
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%reclam%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%claim%' THEN 'Reclamado'
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%pend%' THEN 'Pendiente'
                    -- "Sin llenar" = petición abierta: no es un override, y
                    -- como aquí ya no hay cruce con la biblioteca (rm.status
                    -- es NULL), cae en el mismo 'Sin coincidencia' que
                    -- devuelve _safe_request_dict. Antes daba NULL, así que
                    -- estas filas se pintaban con un estado por el que luego
                    -- no se las podía filtrar. Va antes que '%llena%' porque
                    -- "llenar" contiene "llena".
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%sin llen%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%unfilled%'
                         OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%open%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%abiert%' THEN 'Sin coincidencia'
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%lleno%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%llena%'
                         OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%filled%' OR ri.emu_status = '1' THEN 'Llena'
                    ELSE 'Sin coincidencia'
                END
            ) = ?
        """)
        params.append(status)
    if category:
        where_clauses.append("ri.category = ?")
        params.append(category)
    if resolution:
        where_clauses.append("ri.requested_resolution = ?")
        params.append(resolution)
    if source:
        where_clauses.append("ri.requested_source = ?")
        params.append(source)
    if author:
        where_clauses.append("ri.author = ? AND ri.author_visible = 1")
        params.append(author)
    if emu_status == "filled":
        where_clauses.append(f"LOWER(COALESCE(ri.emu_status,'')) IN ({','.join('?' * len(_FILLED_STATUSES))})")
        params.extend(_FILLED_STATUSES)
    elif emu_status == "open":
        where_clauses.append(f"LOWER(COALESCE(ri.emu_status,'')) NOT IN ({','.join('?' * len(_FILLED_STATUSES))})")
        params.extend(_FILLED_STATUSES)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    order_sql = _REQUEST_SORT.get(sort or "created_desc", _REQUEST_SORT["created_desc"])

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
            li.year AS library_year,
            li.local_status,
            li.poster_url AS poster_url,
            li.backdrop_url AS backdrop_url,
            -- Origen: la instancia de Radarr/Sonarr donde tienes el contenido.
            -- Sale del item de biblioteca cruzado, así que una petición sin
            -- cruce (No importada) los trae en NULL y la columna pinta un
            -- guion. title_slug/tmdb_id son para el enlace directo a la
            -- instancia, igual que en Biblioteca y Subidas.
            li.instance_type,
            li.instance_name,
            li.instance_id,
            li.title_slug,
            li.tmdb_id AS library_tmdb_id
        FROM request_items ri
        LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
          AND rm.id = (
            SELECT id FROM request_matches rm2
            WHERE rm2.request_item_id = ri.id
            ORDER BY rm2.confidence DESC LIMIT 1
          )
        LEFT JOIN library_items li ON li.id = rm.library_item_id
        {where_sql}
        ORDER BY {order_sql}
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


def _series_title_year(conn, lib: dict) -> tuple:
    """Resolve the series title + premiere year for a library item (walking up
    parent_id from a season/episode to its series)."""
    if lib.get("item_type") == "series":
        return lib.get("title"), lib.get("year")
    pid = lib.get("parent_id")
    seen: set = set()
    while pid and pid not in seen:
        seen.add(pid)
        prow = conn.execute(
            "SELECT title, year, item_type, parent_id FROM library_items WHERE id = ?", (pid,)
        ).fetchone()
        if not prow:
            break
        prow = dict(prow)
        if prow.get("item_type") == "series":
            return prow.get("title"), prow.get("year")
        pid = prow.get("parent_id")
    return lib.get("title"), lib.get("year")


def _comparison_content_name(conn, lib: dict, req: dict) -> str:
    """Friendly name for the comparison table: "Serie (año) - Temporada N" and,
    for an episode request, "Serie (año) - Temporada N - SxxEyy"; "Título (año)"
    for a movie.

    "Temporada" and not "Season": this is the only place in the app that said it
    in English, so the same content read "Temporada 2" everywhere else and
    "Season 2" here."""
    scope, season, episode = req.get("req_scope"), req.get("req_season"), req.get("req_episode")
    if lib.get("item_type") in ("series", "season", "episode") or season is not None:
        title, year = _series_title_year(conn, lib)
        name = title or req.get("title") or ""
        if year:
            name += f" ({year})"
        if season is not None:
            name += f" - Temporada {season}"
            if scope == "episode" and episode is not None:
                try:
                    name += f" - S{int(season):02d}E{int(episode):02d}"
                except (TypeError, ValueError):
                    pass
        return name
    name = lib.get("title") or req.get("title") or ""
    if lib.get("year"):
        name += f" ({lib.get('year')})"
    return name


def get_request_detail(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    """Return request + best match info."""
    req_row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    if not req_row:
        return None
    result = _safe_request_dict(dict(req_row))
    match_row = conn.execute(
        """
        SELECT rm.*, li.title AS library_title, li.year AS library_year, li.local_status, li.resolution AS local_resolution,
               li.source AS local_source, li.path AS local_path, li.nomenclature_status,
               li.poster_url AS poster_url, li.backdrop_url AS backdrop_url, li.video_codec AS local_video_codec,
               li.audio_languages AS local_audio_languages, li.size_bytes AS local_size,
               li.tmdb_id AS local_tmdb_id, li.imdb_id AS local_imdb_id, li.tvdb_id AS local_tvdb_id,
               li.mal_id AS local_mal_id,
               li.instance_type, li.instance_name, li.instance_id, li.title_slug
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
        result["poster_url"] = md.get("poster_url")
        result["backdrop_url"] = md.get("backdrop_url")
        result["library_year"] = md.get("library_year")
        # Mismos nombres que en la lista, para que la columna Origen de la
        # tabla y el campo Origen de la ficha lean lo mismo.
        result["instance_type"] = md.get("instance_type")
        result["instance_name"] = md.get("instance_name")
        result["instance_id"] = md.get("instance_id")
        result["title_slug"] = md.get("title_slug")
        result["library_tmdb_id"] = md.get("local_tmdb_id")
        result["match"] = {
            "id": md["id"],
            "library_item_id": md["library_item_id"],
            "library_title": md.get("library_title"),
            "local_status": md.get("local_status"),
            "local_resolution": md.get("local_resolution"),
            "local_source": md.get("local_source"),
            "local_video_codec": md.get("local_video_codec"),
            "local_audio_languages": md.get("local_audio_languages"),
            "local_size": md.get("local_size"),
            "local_tmdb_id": md.get("local_tmdb_id"),
            "local_imdb_id": md.get("local_imdb_id"),
            "local_tvdb_id": md.get("local_tvdb_id"),
            "local_mal_id": md.get("local_mal_id"),
            "local_path": md.get("local_path"),
            "nomenclature_status": md.get("nomenclature_status"),
            "status": md["status"],
            "confidence": float(md["confidence"]),
            "resolution_match": bool(md["resolution_match"]) if md["resolution_match"] is not None else None,
            "source_match": bool(md["source_match"]) if md["source_match"] is not None else None,
            "id_match": bool(md.get("type_match")),
            "reasons": [r for r in reasons.splitlines() if r],
        }
        # The stored match was computed against the matched library item; for a
        # series/season rollup resolve the SCOPE's effective attributes (a
        # specific episode, or the uniform value across the relevant episodes)
        # and re-classify, so the comparison shows real data and the status is
        # consistent with those checks (e.g. a T2·E5 request that IS 1080p is
        # Compatible, not Parcial against an empty rollup).
        lib_row = conn.execute(
            "SELECT * FROM library_items WHERE id = ?", (md["library_item_id"],)
        ).fetchone()
        if lib_row:
            result["match"]["content_name"] = _comparison_content_name(conn, dict(lib_row), result)
            # Which library row this request is really about. The MATCH points
            # at whatever the matcher found — for a season request that is the
            # series row, because every season of a series shares the series'
            # tmdb_id — so following it landed you on the series instead of the
            # season you clicked. This resolves the scope's own row.
            result["match"]["library_target_id"] = _scoped_library_id(conn, dict(lib_row), result)
            # Same canonical "Serie (Año) - SxxEyy" title Biblioteca/Subidas'
            # own dedicated pages use — request's own scope (not the matched
            # row's) so a request matched against a series/season rollup still
            # shows the exact season/episode it's actually asking for.
            result["display_title"] = content_display_title(
                conn, dict(lib_row),
                season=result.get("req_season"), episode=result.get("req_episode"),
                scope=result.get("req_scope"),
            )
        if lib_row and dict(lib_row).get("item_type") in ("series", "season"):
            eff = _effective_target(conn, dict(lib_row), result)
            cls = classify_request_match(
                result, eff,
                id_match=bool(md.get("type_match")),
                base_confidence=float(md["confidence"]),
            )
            # Una petición de temporada o serie completa se cubre con un
            # PACK. Si ese pack no puede armarse (los capítulos no coinciden
            # en resolución o en códec de vídeo), "Compatible" prometería algo
            # que la subida va a rechazar: baja a Parcial y se dice por qué.
            #
            # Pasa cuando la petición no restringe la resolución: entonces la
            # comparación no tiene nada que exigir y salía Compatible aunque
            # la temporada estuviera descuadrada.
            #
            # Los capítulos sueltos SÍ se pueden subir, y el motivo lo dice.
            if cls["status"] == "Compatible":
                blocker = _pack_blocked_reason(conn, dict(lib_row), result)
                if blocker:
                    cls["status"] = "Parcial"
                    cls["reasons"] = list(cls.get("reasons") or []) + [blocker]
            result["match"].update({
                "status": cls["status"],
                "resolution_match": cls["resolution_match"],
                "source_match": cls["source_match"],
                "local_status": eff.get("local_status"),
                "local_resolution": eff.get("resolution"),
                "local_source": eff.get("source"),
                "local_video_codec": eff.get("video_codec"),
                "local_audio_languages": eff.get("audio_languages"),
                "local_size": eff.get("size_bytes"),
                "local_path": eff.get("path"),
            })
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
    """Remove author info if author_visible=0.

    Also fills in compatibility_status when there's no request_matches row at
    all (no library candidate ever matched this request) — Reclamado/
    Pendiente/Llena describe the request's own state on the tracker, true
    regardless of whether your library holds anything for it, so a request
    with zero candidates would otherwise silently read as "Sin coincidencia"
    even when eMuwarez itself already says it's Reclamado.

    Failing both, it settles on "Sin coincidencia" (shown as "No importada")
    rather than staying null. The status filter above already resolves this
    same case to that exact string, so leaving it null here made a row the
    UI could paint but not filter: it showed a bare dash and had no entry in
    the Compatibilidad dropdown."""
    if not d.get("author_visible"):
        d.pop("author", None)
    if not d.get("compatibility_status"):
        d["compatibility_status"] = emu_override_status(d.get("emu_status")) or "Sin coincidencia"
    return d


def dashboard_request_counters(conn: sqlite3.Connection) -> dict[str, int | str | None]:
    """Los contadores de peticiones del Panel.

    Vivían dentro del endpoint (auditoría, hallazgo 6.2), y no eran consultas
    tontas: "Compatible" cuenta peticiones cuya MEJOR coincidencia lo es, no
    filas de coincidencia; "Mías" exige author_visible porque una fila sin
    autor visible no es tuya aunque el texto coincida por casualidad; y
    "Reclamadas" busca por subcadena porque eMuwarez no dice si la reclamación
    es tuya. Ese criterio es de dominio, no de HTTP."""
    from .settings import get_setting_canonical

    def _cuenta(sql: str, params: tuple = ()) -> int:
        try:
            row = conn.execute(sql, params).fetchone()
            return int(row["cnt"] or 0) if row else 0
        except Exception:
            return 0

    try:
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN LOWER(COALESCE(emu_status,'')) IN ('filled','llena','lleno','1')
                               THEN 1 ELSE 0 END) AS filled
               FROM request_items"""
        ).fetchone()
        total, filled = (int(row["total"] or 0), int(row["filled"] or 0)) if row else (0, 0)
    except Exception:
        total = filled = 0

    def _mejor(status: str) -> int:
        return _cuenta(
            """SELECT COUNT(*) AS cnt FROM request_items ri
               WHERE (SELECT rm.status FROM request_matches rm
                      WHERE rm.request_item_id = ri.id
                      ORDER BY rm.confidence DESC LIMIT 1) = ?""",
            (status,),
        )

    mias = 0
    usuario = get_setting_canonical(conn, "emu.username")
    if usuario:
        mias = _cuenta(
            "SELECT COUNT(*) AS cnt FROM request_items WHERE author_visible = 1 AND author = ?",
            (usuario,),
        )

    return {
        "requests_total": total,
        "requests_filled": filled,
        "requests_compatible": _mejor("Compatible"),
        "requests_partial": _mejor("Parcial"),
        "requests_mine": mias,
        "requests_reclaimed": _cuenta(
            "SELECT COUNT(*) AS cnt FROM request_items "
            "WHERE LOWER(COALESCE(emu_status,'')) LIKE '%reclam%' "
            "   OR LOWER(COALESCE(emu_status,'')) LIKE '%claim%'"
        ),
        "requests_last_sync_at": get_state(conn, "last_emu_requests_sync_utc"),
    }
