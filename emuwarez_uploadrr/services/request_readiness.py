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
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..models import LocalStatus
from .compatibility import (
    classify_request_match,
    emu_override_status,
    match_request_to_library,
    parse_resolution,
    parse_source,
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

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

# Estados de preparación, el más accionable primero. Es el único orden: desempata entre los candidatos de una
# misma petición (select_best_candidate) y ordena la lista (list_request_readiness).
_STATUS_RANK: dict[str, int] = {
    "ready_to_upload": 0,
    "preflight_needed": 1,
    "needs_nomenclature": 2,
    "downloading": 3,
    "pending_import": 4,
    "uploading": 5,
    "partially_available": 6,
    "spec_mismatch": 7,
    "no_local_match": 8,
    "file_missing": 9,
    "import_error": 10,
    "claimed": 11,
    "filled": 12,
    "already_exists": 13,
    "uploaded": 14,
}

# Por qué una petición que ya no está abierta para ti no es «lista para subir».
_ESTADO_EMU_BLOQUEA = {
    "Reclamado": ("claimed", "petición reclamada en eMuwarez"),
    "Pendiente": ("claimed", "petición pendiente de aprobación en eMuwarez"),
    "Llena": ("filled", "petición ya llena en eMuwarez"),
}


def _evaluate_readiness(
    lib: Optional[dict],
    req: dict,
    cls: Optional[dict],
    compat_reasons: list[str],
    readiness_reasons: list[str],
    variante_en_emuwarez: bool = True,
) -> dict:
    """Apply readiness rules. Returns status, action, blockers, reasons.

    `cls` es la clasificación de classify_request_match (la misma que enseña la lista de peticiones).
    `variante_en_emuwarez`: si eMuwarez ya tiene la resolución y el tipo que pide la petición."""
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
    upload_status = lib.get("local_status") or ""

    # Already uploaded/uploading
    if upload_status in ("Subiendo", "uploading"):
        return {"status": "uploading", "action": "view_upload", "blockers": [], "reasons": reasons}
    if upload_status in ("Subido", "uploaded"):
        return {"status": "uploaded", "action": "view_upload", "blockers": [], "reasons": reasons}

    # La petición no está abierta para ti: otro la ha reclamado, espera aprobación o ya está llena.
    estado_emu = _ESTADO_EMU_BLOQUEA.get(emu_override_status(req.get("emu_status")) or "")
    if estado_emu:
        return {"status": estado_emu[0], "action": "none", "blockers": [estado_emu[1]], "reasons": reasons}

    # Ya está en eMuwarez y tu copia no aporta nada (ni resolución, ni fuente, ni idioma): sería un duplicado.
    # Pero una petición está abierta porque falta SU variante: si eMuwarez no la tiene, no es un duplicado.
    if (lib.get("emu_in_catalog") == 1 and not json.loads(lib.get("emu_aportes") or "[]")
            and variante_en_emuwarez):
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

    # La copia tiene que cumplir lo pedido (igual o mejor): una de 1080p WEB-DL no atiende un 2160p Remux.
    if cls and (cls["resolution_match"] is False or cls["source_match"] is False):
        faltan = [n for n, ok in (("resolución", cls["resolution_match"]), ("fuente", cls["source_match"])) if ok is False]
        blockers.append(f"la copia no cumple lo pedido ({', '.join(faltan)})")
        return {"status": "spec_mismatch", "action": "review_arr", "blockers": blockers, "reasons": reasons}

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

def score_request_candidate(
    req: dict, lib: dict, cls: Optional[dict] = None, variante_en_emuwarez: bool = True,
) -> dict:
    """Score a single (request, library_item) pair. `cls`: su clasificación, si ya se calculó con lo que de verdad
    tiene lo pedido (los capítulos de una temporada); si no, se clasifica `lib` tal cual."""
    if cls is None:
        cls = classify_request_match(req, lib)
    readiness_score, readiness_reasons = _compute_upload_readiness_score(lib)

    readiness_result = _evaluate_readiness(lib, req, cls, cls["reasons"], readiness_reasons, variante_en_emuwarez)

    return {
        "library_item_id": lib.get("id"),
        "match_status": cls["status"],
        "match_score": cls["confidence"],
        "compatibility_status": cls["status"],
        "compatibility_score": round(cls["confidence"] * 100, 1),
        "readiness_status": readiness_result["status"],
        "readiness_score": readiness_score,
        "blockers": readiness_result["blockers"],
        "reasons": readiness_result["reasons"],
        "recommended_action": readiness_result["action"],
    }


def select_best_candidate(candidates: list[dict]) -> Optional[dict]:
    """Pick the best candidate from a scored list: the surest match first (an ID
    match before a title one, so a wrong title match that happens to be ready
    never beats the right item), then the copy that meets more of what the
    request asks (resolution and source: with Radarr and Radarr 4K, a ready 1080p
    copy must not beat the 2160p one a 2160p request asks for), then real
    readiness status (most-actionable first, see _STATUS_RANK), and only then
    compatibility_score. This is candidate matching, not a "priority" ranking — no
    numeric priority score/bucket involved."""
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda c: (-c["match_confidence"], -c["cumple"], _STATUS_RANK.get(c["readiness_status"], 99),
                       -c["compatibility_score"]),
    )[0]


# Lo que se puntúa de la fila que pide la petición; ids, título y tipo siguen siendo los de la fila emparejada.
_LEER_FILA_PEDIDA = (
    "SELECT item_type, local_status, resolution, source, nomenclature_status, prepared_path, file_exists, "
    "arr_queue_status, arr_history_status, arr_history_event_type, arr_history_error, emu_in_catalog, emu_aportes "
    "FROM library_items WHERE id = ?"
)


def _biblioteca(conn: sqlite3.Connection) -> list[dict]:
    """Las filas candidatas, sin los capítulos ni el raw_json. Recorre la tabla entera: un refresco la lee una vez."""
    return [dict(r) for r in conn.execute(
        """
        SELECT id, item_type, title, year, tmdb_id, imdb_id, tvdb_id, local_status,
               resolution, source, nomenclature_status, prepared_path,
               file_exists, arr_queue_status, arr_history_status,
               arr_history_event_type, arr_history_error, season_number,
               emu_in_catalog, emu_aportes
        FROM library_items
        WHERE item_type != 'episode'
        ORDER BY updated_at DESC
        """
    ).fetchall()]


def build_request_candidates(
    request_item_id: int, conn: sqlite3.Connection, library: Optional[list[dict]] = None,
) -> list[dict]:
    """Find and score all library candidates for a request."""
    req_row = conn.execute(
        "SELECT * FROM request_items WHERE id = ?", (request_item_id,)
    ).fetchone()
    if not req_row:
        return []
    req = dict(req_row)

    raw_matches = match_request_to_library(req, _biblioteca(conn) if library is None else library)
    if not raw_matches:
        return []

    from .emu_catalog import catalogo_cubre
    from .requests import _scoped_library_id, clasificar_peticion

    candidates = []
    for rank, m in enumerate(raw_matches[:10], start=1):
        lib = dict(m["item"])
        # La temporada o el capítulo pedidos se puntúan con sus propios datos, no con el resumen de la serie.
        destino = _scoped_library_id(conn, lib, req)
        pedida = dict(conn.execute(_LEER_FILA_PEDIDA, (destino,)).fetchone())
        if req.get("req_scope") in ("season", "episode") and pedida["item_type"] != req["req_scope"]:
            # Lo pedido no está en la biblioteca, solo su serie o su temporada: no hay nada que preparar.
            pedida.update(local_status="Faltante", emu_in_catalog=None)
        del pedida["item_type"]
        # «Compatible» lo decide la misma función que la lista de peticiones (resolución y fuente pedidas, y la
        # temporada por su peor capítulo); aquí solo se añade lo que hace falta para poder subirlo.
        _, cls = clasificar_peticion(conn, req, lib, id_match=m["id_match"], title_match=m["title_match"],
                                     base_confidence=m["confidence"])
        lib.update(pedida)
        variante = True
        if lib.get("emu_in_catalog") == 1 and not json.loads(lib.get("emu_aportes") or "[]"):
            pide_res = req.get("requested_resolution") if parse_resolution(req.get("requested_resolution")) else None
            pide_tipo = req.get("requested_source") if parse_source(req.get("requested_source")) else None
            variante = not (pide_res or pide_tipo) or catalogo_cubre(conn, destino, pide_res, pide_tipo)
        scored = score_request_candidate(req, lib, cls, variante)
        scored["candidate_rank"] = rank
        scored["library_item_id"] = lib["id"]
        scored["match_confidence"] = m["confidence"]
        # Cuántas de las dos cosas que se piden (resolución y fuente) cumple esta copia.
        scored["cumple"] = sum(r is not False for r in (cls["resolution_match"], cls["source_match"]))
        candidates.append(scored)

    return candidates


def evaluate_request_readiness(
    request_item_id: int, conn: sqlite3.Connection, library: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Compute and persist readiness for a single request."""
    req_row = conn.execute(
        "SELECT * FROM request_items WHERE id = ?", (request_item_id,)
    ).fetchone()
    if not req_row:
        return {"ok": False, "error": f"Request {request_item_id} no encontrada"}
    req = dict(req_row)

    candidates = build_request_candidates(request_item_id, conn, library)
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
    try:
        library = _biblioteca(conn)
    except Exception:
        # Como cuando se leía por petición: todas cuentan como error, en vez de un 500 en «Recalcular».
        logging.getLogger("emuwarez.requests").exception("No se pudo leer la biblioteca para calcular la preparación")
        return {"ok": True, "items_updated": 0, "errors": len(rows)}
    updated = 0
    errors = 0

    for row in rows:
        try:
            evaluate_request_readiness(row["id"], conn, library)
            updated += 1
        except Exception:
            # Lo que la petición rota llegara a escribir no se cuela en el commit de la siguiente.
            conn.rollback()
            logging.getLogger("emuwarez.requests").exception(
                "No se pudo calcular la preparación de la petición %s", row["id"])
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
    # Order by real readiness status (most-actionable first), con el mismo ranking que _STATUS_RANK.
    orden = " ".join(f"WHEN '{estado}' THEN {n}" for estado, n in _STATUS_RANK.items())
    sql = f"""
        SELECT rr.*, ri.title, ri.emu_id, ri.category, ri.points,
               ri.requested_resolution, ri.requested_source
        FROM request_readiness rr
        JOIN request_items ri ON ri.id = rr.request_item_id
        {where}
        ORDER BY
            CASE rr.status {orden} ELSE 99 END,
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
