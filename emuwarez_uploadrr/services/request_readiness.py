"""Phase 8B — Request readiness evaluation and prioritization.

Computes per-request:
  - best local candidate
  - compatibility score
  - upload readiness score
  - priority bucket and score
  - recommended action
  - blockers

All operations are read-only against ARR and eMuwarez.
Only local tables (request_readiness, request_candidates, request_items) are written.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..models import LocalStatus
from .compatibility import (
    match_request_to_library,
    classify_request_match,
    normalize_title,
    parse_resolution,
    parse_source,
    _SOURCE_RANK,
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _compute_compatibility_score(req: dict, lib: dict) -> tuple[float, str, list[str]]:
    """
    Returns (score 0-100, compat_status, reasons).

    Scoring:
        +40  strong ID match (TMDb/IMDb)
        +20  title match
        +10  year match
        +10  type match (movie/series)
        +10  resolution compatible
        +10  source compatible
    """
    score = 0.0
    reasons: list[str] = []

    # ID match
    req_tmdb = str(req.get("tmdb_id") or "").strip()
    req_imdb = str(req.get("imdb_id") or "").strip()
    lib_tmdb = str(lib.get("tmdb_id") or "").strip()
    lib_imdb = str(lib.get("imdb_id") or "").strip()

    id_match = False
    if req_tmdb and lib_tmdb and req_tmdb == lib_tmdb:
        score += 40
        id_match = True
        reasons.append("TMDb match")
    elif req_imdb and lib_imdb and req_imdb == lib_imdb:
        score += 38
        id_match = True
        reasons.append("IMDb match")

    # Title match
    req_title = normalize_title(req.get("title"))
    lib_title = normalize_title(lib.get("title"))
    if not id_match:
        if req_title == lib_title:
            score += 18
            reasons.append("title exact match")
        elif req_title and lib_title and (req_title in lib_title or lib_title in req_title):
            score += 12
            reasons.append("title partial match")

    # Year match
    req_year = req.get("created_at", "")[:4] if req.get("created_at") else None
    lib_year = str(lib.get("year") or "")
    if req_year and lib_year and req_year == lib_year:
        score += 10
        reasons.append(f"year match ({lib_year})")

    # Type match
    req_cat = (req.get("category") or "").lower()
    lib_type = (lib.get("item_type") or "").lower()
    if req_cat and lib_type:
        cat_map = {"pelicula": "movie", "película": "movie", "movie": "movie",
                   "serie": "series", "series": "series"}
        req_type = cat_map.get(req_cat)
        if req_type and req_type == lib_type:
            score += 10
            reasons.append(f"type match ({lib_type})")

    # Resolution
    req_res = req.get("requested_resolution")
    lib_res = lib.get("resolution")
    if req_res:
        req_rank = parse_resolution(req_res)
        lib_rank = parse_resolution(lib_res)
        if req_rank and lib_rank and lib_rank >= req_rank:
            score += 10
            reasons.append(f"resolution ok ({lib_res} >= {req_res})")
        elif req_rank and lib_rank and lib_rank < req_rank:
            reasons.append(f"resolution low ({lib_res} < {req_res})")
    else:
        score += 10  # no restriction → ok
        reasons.append("no resolution restriction")

    # Source
    req_src = req.get("requested_source")
    lib_src = lib.get("source")
    if req_src:
        from .compatibility import parse_source as _ps
        req_can = _ps(req_src)
        lib_can = _ps(lib_src)
        if req_can and lib_can:
            if _SOURCE_RANK.get(lib_can, 0) >= _SOURCE_RANK.get(req_can, 0):
                score += 10
                reasons.append(f"source ok ({lib_src} >= {req_src})")
            else:
                reasons.append(f"source low ({lib_src} < {req_src})")
        else:
            score += 5
    else:
        score += 10  # no restriction
        reasons.append("no source restriction")

    score = min(100.0, score)

    # Derive compat_status
    emu_status = str(req.get("emu_status") or "").lower()
    if "lleno" in emu_status or "filled" in emu_status:
        compat_status = "Llena"
    elif score >= 70:
        compat_status = "Compatible"
    elif score >= 40:
        compat_status = "Parcial"
    else:
        compat_status = "No compatible"

    return round(score, 1), compat_status, reasons


def _compute_upload_readiness_score(lib: dict) -> tuple[float, list[str]]:
    """
    Returns (score 0-100, reasons).

    Scoring:
        +20  local_status available
        +20  file_exists true
        +15  no queue blockers
        +15  no history errors
        +15  nomenclature correct/prepared
        +15  preflight ready (prepared_path exists)
    """
    score = 0.0
    reasons: list[str] = []

    local_status = lib.get("local_status") or ""
    if local_status == "Disponible":
        score += 20
        reasons.append("disponible")

    file_exists = lib.get("file_exists")
    if file_exists is True or file_exists == 1:
        score += 20
        reasons.append("archivo en disco")

    queue_status = lib.get("arr_queue_status") or ""
    if queue_status not in ("import_error",):
        score += 15
        reasons.append("sin bloqueo de cola")

    history_status = lib.get("arr_history_status") or ""
    history_event = lib.get("arr_history_event_type") or ""
    history_error = lib.get("arr_history_error")
    has_history_error = history_status == "error" or "Fail" in history_event or bool(history_error)
    if not has_history_error:
        score += 15
        reasons.append("sin error historial")

    nomenclature = lib.get("nomenclature_status") or ""
    prepared_path = lib.get("prepared_path")
    if nomenclature in ("Correcta", "correct") or prepared_path:
        score += 15
        reasons.append("nomenclatura ok")

    if prepared_path:
        score += 15
        reasons.append("preflight listo")

    return round(min(100.0, score), 1), reasons


# ---------------------------------------------------------------------------
# Readiness rules
# ---------------------------------------------------------------------------

# Fixed ranking of real readiness statuses, most-actionable first. Used only
# internally by select_best_candidate() to break ties between several
# library-item candidates for the SAME request — this is match quality, not
# a user-facing "priority" ranking (the numeric priority_score/priority_bucket
# system was removed at the user's request; 'blocked'-style statuses like
# file_missing/import_error/already_exists still exist as real `status`
# values, just without a derived priority label on top).
_STATUS_RANK: dict[str, int] = {
    "ready_to_upload": 0,
    "preflight_needed": 1,
    "needs_nomenclature": 2,
    "downloading": 3,
    "pending_import": 4,
    "uploading": 5,
    "partially_available": 6,
    "no_local_match": 7,
    "file_missing": 8,
    "import_error": 9,
    "already_exists": 10,
    "uploaded": 11,
}

def _evaluate_readiness(
    lib: Optional[dict],
    compat_reasons: list[str],
    readiness_reasons: list[str],
) -> dict:
    """Apply readiness rules. Returns status, action, blockers, reasons."""
    blockers: list[str] = []
    reasons: list[str] = list(compat_reasons) + list(readiness_reasons)

    # No candidate at all
    if not lib:
        return {
            "status": "no_local_match",
            "action": "review_arr",
            "blockers": ["sin candidato local"],
            "reasons": reasons,
        }

    local_status = lib.get("local_status") or ""
    file_exists = lib.get("file_exists")
    nomenclature = lib.get("nomenclature_status") or ""
    prepared_path = lib.get("prepared_path")
    queue_status = lib.get("arr_queue_status") or ""
    history_error = lib.get("arr_history_error")
    history_status = lib.get("arr_history_status") or ""
    history_event = lib.get("arr_history_event_type") or ""
    has_history_error = history_status == "error" or "Fail" in history_event or bool(history_error)
    emu_exist = lib.get("emu_existence_status") or ""
    upload_status = lib.get("local_status") or ""

    # Already uploaded/uploading
    if upload_status in ("Subiendo", "uploading"):
        return {"status": "uploading", "action": "view_upload", "blockers": [], "reasons": reasons}
    if upload_status in ("Subido", "uploaded"):
        return {"status": "uploaded", "action": "view_upload", "blockers": [], "reasons": reasons}

    # Exists in eMuwarez
    if emu_exist in ("exists", "duplicate_confirmed"):
        blockers.append("ya existe en eMuwarez")
        return {"status": "already_exists", "action": "ignore_already_exists", "blockers": blockers, "reasons": reasons}

    # Queue states
    if queue_status == "downloading":
        return {"status": "downloading", "action": "wait_download", "blockers": [], "reasons": reasons}
    if queue_status == "queued":
        return {"status": "downloading", "action": "wait_download", "blockers": [], "reasons": reasons}
    if queue_status == "pending_import":
        blockers.append("pendiente de importación ARR")
        return {"status": "pending_import", "action": "review_arr", "blockers": blockers, "reasons": reasons}
    if queue_status == "import_error":
        blockers.append("error de importación ARR")
        return {"status": "import_error", "action": "review_arr", "blockers": blockers, "reasons": reasons}

    # File missing
    if local_status == "Disponible" and (file_exists is False or file_exists == 0):
        blockers.append("archivo no encontrado en disco")
        return {"status": "file_missing", "action": "verify_file", "blockers": blockers, "reasons": reasons}

    # History error + not available
    if has_history_error and local_status != "Disponible":
        blockers.append(f"error historial ARR: {history_error or history_event}")
        return {"status": "import_error", "action": "review_arr", "blockers": blockers, "reasons": reasons}

    # Partially available (some but not all children present, series/season
    # rollup only) — distinct from a true no-match: a real local candidate
    # exists, it's just incomplete.
    if local_status == LocalStatus.PARTIAL.value:
        blockers.append("serie/temporada parcialmente disponible")
        return {"status": "partially_available", "action": "review_arr", "blockers": blockers, "reasons": reasons}

    # Not locally available
    if local_status != "Disponible":
        return {"status": "no_local_match", "action": "review_arr", "blockers": [f"local_status={local_status}"], "reasons": reasons}

    # Available from here — file must exist or be unverified
    if file_exists is False or file_exists == 0:
        blockers.append("archivo no encontrado en disco")
        return {"status": "file_missing", "action": "verify_file", "blockers": blockers, "reasons": reasons}

    # Nomenclature
    if nomenclature in ("No adaptada", "not_adapted"):
        return {"status": "needs_nomenclature", "action": "adapt_nomenclature", "blockers": [], "reasons": reasons}

    # Preflight needed
    if nomenclature in ("Correcta", "correct") and not prepared_path:
        return {"status": "preflight_needed", "action": "run_preflight", "blockers": [], "reasons": reasons}

    # Ready to upload
    if prepared_path:
        return {"status": "ready_to_upload", "action": "upload", "blockers": [], "reasons": reasons}

    # Fallback available
    return {"status": "preflight_needed", "action": "run_preflight", "blockers": [], "reasons": reasons}


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def score_request_candidate(req: dict, lib: dict) -> dict:
    """Score a single (request, library_item) pair."""
    compat_score, compat_status, compat_reasons = _compute_compatibility_score(req, lib)
    readiness_score, readiness_reasons = _compute_upload_readiness_score(lib)

    readiness_result = _evaluate_readiness(lib, compat_reasons, readiness_reasons)

    return {
        "library_item_id": lib.get("id"),
        "match_status": compat_status,
        "match_score": compat_score / 100.0,
        "compatibility_status": compat_status,
        "compatibility_score": compat_score,
        "readiness_status": readiness_result["status"],
        "readiness_score": readiness_score,
        "blockers": readiness_result["blockers"],
        "reasons": readiness_result["reasons"],
        "recommended_action": readiness_result["action"],
    }


def select_best_candidate(candidates: list[dict]) -> Optional[dict]:
    """Pick the best candidate from a scored list — ties broken by real
    readiness status (most-actionable first, see _STATUS_RANK) then by
    match quality (compatibility_score). This is candidate matching, not a
    "priority" ranking — no numeric priority score/bucket involved."""
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda c: (_STATUS_RANK.get(c["readiness_status"], 99), -c["compatibility_score"]),
    )[0]


def build_request_candidates(request_item_id: int, conn: sqlite3.Connection) -> list[dict]:
    """Find and score all library candidates for a request."""
    req_row = conn.execute(
        "SELECT * FROM request_items WHERE id = ?", (request_item_id,)
    ).fetchone()
    if not req_row:
        return []
    req = dict(req_row)

    lib_rows = conn.execute(
        """
        SELECT id, item_type, title, year, tmdb_id, imdb_id, local_status,
               resolution, source, nomenclature_status, prepared_path,
               file_exists, arr_queue_status, arr_history_status,
               arr_history_event_type, arr_history_error
        FROM library_items
        ORDER BY updated_at DESC
        """
    ).fetchall()
    library = [dict(r) for r in lib_rows]

    raw_matches = match_request_to_library(req, library)
    if not raw_matches:
        return []

    candidates = []
    for rank, m in enumerate(raw_matches[:10], start=1):
        lib = m["item"]
        scored = score_request_candidate(req, lib)
        scored["candidate_rank"] = rank
        scored["library_item_id"] = lib["id"]
        candidates.append(scored)

    return candidates


def evaluate_request_readiness(request_item_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute and persist readiness for a single request."""
    req_row = conn.execute(
        "SELECT * FROM request_items WHERE id = ?", (request_item_id,)
    ).fetchone()
    if not req_row:
        return {"ok": False, "error": f"Request {request_item_id} no encontrada"}
    req = dict(req_row)

    candidates = build_request_candidates(request_item_id, conn)
    best = select_best_candidate(candidates)

    now = _now_utc()

    if best:
        best_lib_id = best["library_item_id"]
        status = best["readiness_status"]
        action = best["recommended_action"]
        compat_score = best["compatibility_score"]
        readiness_score = best["readiness_score"]
        blockers = best["blockers"]
        reasons = best["reasons"]
    else:
        best_lib_id = None
        status = "no_local_match"
        action = "review_arr"
        compat_score = 0.0
        readiness_score = 0.0
        blockers = ["sin candidato local"]
        reasons = ["sin candidato local en biblioteca"]

    candidate_summary = [
        {
            "rank": c["candidate_rank"],
            "library_item_id": c["library_item_id"],
            "compatibility_score": c["compatibility_score"],
            "readiness_status": c["readiness_status"],
        }
        for c in candidates[:5]
    ]

    # Upsert request_readiness
    existing = conn.execute(
        "SELECT id FROM request_readiness WHERE request_item_id = ?", (request_item_id,)
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE request_readiness SET
                best_library_item_id = ?, status = ?, recommended_action = ?,
                compatibility_score = ?, upload_readiness_score = ?,
                blockers_json = ?, reasons_json = ?,
                candidate_summary_json = ?, last_evaluated_at = ?, updated_at = ?
            WHERE request_item_id = ?
            """,
            (
                best_lib_id, status, action,
                compat_score, readiness_score,
                json.dumps(blockers, ensure_ascii=False),
                json.dumps(reasons, ensure_ascii=False),
                json.dumps(candidate_summary, ensure_ascii=False),
                now, now, request_item_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO request_readiness
            (request_item_id, best_library_item_id, status, recommended_action,
             compatibility_score, upload_readiness_score,
             blockers_json, reasons_json, candidate_summary_json, last_evaluated_at,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_item_id, best_lib_id, status, action,
                compat_score, readiness_score,
                json.dumps(blockers, ensure_ascii=False),
                json.dumps(reasons, ensure_ascii=False),
                json.dumps(candidate_summary, ensure_ascii=False),
                now, now, now,
            ),
        )

    # Delete old candidates then insert new
    conn.execute("DELETE FROM request_candidates WHERE request_item_id = ?", (request_item_id,))
    for c in candidates:
        conn.execute(
            """
            INSERT INTO request_candidates
            (request_item_id, library_item_id, candidate_rank, match_status,
             match_score, compatibility_status, compatibility_score,
             readiness_status, readiness_score, blockers_json, reasons_json,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_item_id, c["library_item_id"], c["candidate_rank"],
                c["match_status"], c["match_score"],
                c["compatibility_status"], c["compatibility_score"],
                c["readiness_status"], c["readiness_score"],
                json.dumps(c["blockers"], ensure_ascii=False),
                json.dumps(c["reasons"], ensure_ascii=False),
                now, now,
            ),
        )

    # Update request_items readiness columns
    conn.execute(
        """
        UPDATE request_items SET
            readiness_status = ?, readiness_action = ?,
            readiness_best_library_item_id = ?, readiness_updated_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (status, action, best_lib_id, now, now, request_item_id),
    )
    conn.commit()

    return {
        "ok": True,
        "request_item_id": request_item_id,
        "title": req.get("title"),
        "status": status,
        "recommended_action": action,
        "compatibility_score": compat_score,
        "upload_readiness_score": readiness_score,
        "best_library_item_id": best_lib_id,
        "blockers": blockers,
        "reasons": reasons,
        "candidates_count": len(candidates),
    }


def refresh_request_readiness(
    conn: sqlite3.Connection,
    filters: Optional[dict] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Recalculate readiness for all (or filtered) requests."""
    filters = filters or {}
    sql = "SELECT id FROM request_items ORDER BY updated_at DESC"
    params: list[Any] = []

    effective_limit = limit or filters.get("limit")
    if effective_limit:
        sql += " LIMIT ?"
        params.append(int(effective_limit))

    rows = conn.execute(sql, params).fetchall()
    updated = 0
    errors = 0

    for row in rows:
        try:
            evaluate_request_readiness(row["id"], conn)
            updated += 1
        except Exception:
            errors += 1

    return {"ok": True, "items_updated": updated, "errors": errors}


def get_request_readiness(request_item_id: int, conn: sqlite3.Connection) -> Optional[dict[str, Any]]:
    """Return stored readiness for a request."""
    row = conn.execute(
        """
        SELECT rr.*, ri.title, ri.emu_id
        FROM request_readiness rr
        JOIN request_items ri ON ri.id = rr.request_item_id
        WHERE rr.request_item_id = ?
        """,
        (request_item_id,),
    ).fetchone()
    if not row:
        return None
    r = dict(row)
    for field in ("blockers_json", "reasons_json", "candidate_summary_json"):
        try:
            r[field.replace("_json", "")] = json.loads(r.pop(field) or "[]")
        except Exception:
            r[field.replace("_json", "")] = []
    return r


def list_request_readiness(
    conn: sqlite3.Connection,
    filters: Optional[dict] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List all readiness records with optional filters."""
    filters = filters or {}
    clauses = []
    params: list[Any] = []

    if filters.get("status"):
        clauses.append("rr.status = ?")
        params.append(filters["status"])
    if filters.get("action"):
        clauses.append("rr.recommended_action = ?")
        params.append(filters["action"])
    if filters.get("search"):
        clauses.append("ri.title LIKE ?")
        params.append(f"%{filters['search']}%")

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    # Order by real readiness status (most-actionable first, same ranking as
    # _STATUS_RANK) — no numeric priority score/bucket involved anymore.
    sql = f"""
        SELECT rr.*, ri.title, ri.emu_id, ri.category, ri.points,
               ri.requested_resolution, ri.requested_source
        FROM request_readiness rr
        JOIN request_items ri ON ri.id = rr.request_item_id
        {where}
        ORDER BY
            CASE rr.status
                WHEN 'ready_to_upload' THEN 0
                WHEN 'preflight_needed' THEN 1
                WHEN 'needs_nomenclature' THEN 2
                WHEN 'downloading' THEN 3
                WHEN 'pending_import' THEN 4
                WHEN 'uploading' THEN 5
                WHEN 'no_local_match' THEN 6
                WHEN 'file_missing' THEN 7
                WHEN 'import_error' THEN 8
                WHEN 'already_exists' THEN 9
                WHEN 'uploaded' THEN 10
                ELSE 99
            END,
            rr.last_evaluated_at DESC
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]
    rows = conn.execute(sql, params).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        for field in ("blockers_json", "reasons_json", "candidate_summary_json"):
            try:
                r[field.replace("_json", "")] = json.loads(r.pop(field) or "[]")
            except Exception:
                r[field.replace("_json", "")] = []
        results.append(r)
    return results


def get_candidates_for_request(request_item_id: int, conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return scored candidate list for a request."""
    rows = conn.execute(
        """
        SELECT rc.*, li.title AS lib_title, li.local_status, li.resolution, li.source
        FROM request_candidates rc
        LEFT JOIN library_items li ON li.id = rc.library_item_id
        WHERE rc.request_item_id = ?
        ORDER BY rc.candidate_rank
        """,
        (request_item_id,),
    ).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        for field in ("blockers_json", "reasons_json"):
            try:
                r[field.replace("_json", "")] = json.loads(r.pop(field) or "[]")
            except Exception:
                r[field.replace("_json", "")] = []
        results.append(r)
    return results


def get_dashboard_readiness_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Aggregate readiness counts for the dashboard. requests_blocked is
    (and always was) status-based, not priority-based — removing the
    priority ranking system doesn't affect it."""
    try:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'ready_to_upload' THEN 1 ELSE 0 END) AS requests_ready_to_upload,
                SUM(CASE WHEN status = 'needs_nomenclature' THEN 1 ELSE 0 END) AS requests_need_nomenclature,
                SUM(CASE WHEN status IN ('downloading', 'pending_import') THEN 1 ELSE 0 END) AS requests_waiting_download,
                SUM(CASE WHEN status IN ('no_local_match', 'file_missing', 'import_error') THEN 1 ELSE 0 END) AS requests_blocked
            FROM request_readiness
            """
        ).fetchone()
        if row:
            return {k: (v or 0) for k, v in dict(row).items()}
    except Exception:
        pass
    return {
        "requests_ready_to_upload": 0,
        "requests_need_nomenclature": 0,
        "requests_waiting_download": 0,
        "requests_blocked": 0,
    }


__all__ = [
    "evaluate_request_readiness",
    "refresh_request_readiness",
    "get_request_readiness",
    "list_request_readiness",
    "build_request_candidates",
    "score_request_candidate",
    "select_best_candidate",
    "get_candidates_for_request",
    "get_dashboard_readiness_counts",
]


def request_exists(request_id: int, conn) -> bool:
    """Si la petición existe. Lo comprobaba el endpoint con su propio SELECT."""
    return conn.execute(
        "SELECT 1 FROM request_items WHERE id = ?", (request_id,)
    ).fetchone() is not None
