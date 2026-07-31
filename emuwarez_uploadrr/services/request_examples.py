"""Demo requests built from the user's own library.

TEMPORARY. eMuwarez hasn't handed over the real requests endpoint yet, so
Peticiones and Recomendaciones can only be seen populated if the requests are
faked from library content. The whole module goes away when that endpoint
lands, and the version that ships it must delete any leftovers from its own
migration (see database.py::_migrate_request_items_is_example) — sync_requests
never deletes rows the tracker didn't send, so otherwise they would sit mixed
in with real requests forever.

The statuses are NOT chosen, they are computed: Compatible/Parcial/No
disponible come out of matching the request against the library
(services/compatibility.py::classify_request_match), while Reclamado/Llena/
Pendiente come from a free-text emu_status that overrides the verdict. So each
group here is built so that the real calculation lands on the intended answer,
rather than writing the answer down anywhere.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Optional

logger = logging.getLogger("emuwarez.request_examples")

EXAMPLE_ID_PREFIX = "ejemplo-"

# What the button generates, in the order the groups are filled. Each entry is
# (how many, which bucket) — see _build_group for what each bucket needs from
# the library to come out with that status.
EXAMPLE_PLAN: list[tuple[int, str]] = [
    (10, "compatible"),
    (5, "parcial"),
    (3, "reclamada"),
    (2, "llena"),
    (1, "pendiente"),
    (5, "no_disponible"),
    (3, "inventada"),
]

# Every example points at the requests page rather than at /requests/{id}: the
# ids are made up, so a per-request link would 404 on the tracker. This keeps
# "Ver Petición" going somewhere real until the endpoint exists.
_EXAMPLE_URL = "https://emuwarez.com/requests"

# Resolution ladder, used to ask for something HIGHER than what the library
# holds — that is what makes the resolution check fail and the verdict land on
# "Parcial" (one of the two checks failing, not both).
_HIGHER_RESOLUTION = {
    "480p": "720p", "576p": "720p", "720p": "1080p",
    "1080p": "2160p", "2160p": "4320p",
}

_INVENTED = [
    ("La sombra del viento", "movie", "1080p", "BluRay"),
    ("Crónicas del norte", "tv", "2160p", "WEB-DL"),
    ("El último invierno", "movie", "1080p", "WEB-DL"),
]


def count_examples(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM request_items WHERE is_example = 1").fetchone()
    return int(row["n"]) if row else 0


def delete_examples(conn: sqlite3.Connection) -> int:
    """Remove every generated example. request_matches rows go with them via
    the ON DELETE CASCADE on request_item_id."""
    n = conn.execute("DELETE FROM request_items WHERE is_example = 1").rowcount
    conn.commit()
    return int(n or 0)


def _library_pool(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Library rows usable as the basis for an example, split by what they can
    demonstrate. Only movies and seasons: those are the levels a request is
    actually about, and the ones Recomendaciones works with."""
    rows = [dict(r) for r in conn.execute(
        """SELECT id, item_type, title, year, tmdb_id, imdb_id, resolution, source, local_status
             FROM library_items
            WHERE item_type IN ('movie', 'season') AND (tmdb_id IS NOT NULL OR title IS NOT NULL)
            ORDER BY id"""
    ).fetchall()]
    held, missing = [], []
    for r in rows:
        (held if r.get("local_status") in ("Disponible", "Subido", "Subiendo") else missing).append(r)
    return {"held": held, "missing": missing, "all": rows}


def _category_for(item: dict) -> str:
    return "TV" if item.get("item_type") == "season" else "Movie"


def _row_for(item: dict, *, resolution: Optional[str], source: Optional[str],
             emu_status: Optional[str]) -> dict[str, Any]:
    return {
        "title": item.get("title") or "Sin título",
        "category": _category_for(item),
        "requested_resolution": resolution,
        "requested_source": source,
        "emu_status": emu_status,
        "tmdb_id": item.get("tmdb_id"),
        "imdb_id": item.get("imdb_id"),
    }


def _build_group(kind: str, count: int, pool: dict[str, list[dict]], used: set[int]) -> list[dict]:
    """Rows for one bucket.

    Prefers library items no other group has taken, so the list doesn't read as
    the same three titles over and over — but falls back to reusing them once
    the pool runs dry, because starving the later groups would be worse. With
    the requested distribution needing 21 held items, refusing to reuse meant a
    normal library got ten "Compatible" and nothing else: no Reclamada, no
    Llena, no Pendiente, which are the states you most want to see. A real
    request list has several requests for the same title anyway.
    """
    out: list[dict] = []

    if kind == "inventada":
        # No library counterpart at all → the matcher finds no candidate and the
        # request shows up with no compatibility verdict.
        for title, item_type, res, src in _INVENTED[:count]:
            out.append({
                "title": title, "category": "TV" if item_type == "tv" else "Movie",
                "requested_resolution": res, "requested_source": src,
                "emu_status": None, "tmdb_id": None, "imdb_id": None,
            })
        return out

    # "No disponible" needs an entry you DON'T hold: same spec compatibility,
    # but no file on disk. Everything else works off content you do hold.
    source_pool = pool["missing"] if kind == "no_disponible" else pool["held"]
    # Only the items that can actually demonstrate this bucket — "parcial"
    # needs a known resolution to ask above, for instance.
    usable = [it for it in source_pool if _row_for_kind(kind, it) is not None]
    if not usable:
        return []
    # Untouched first, then the rest; cycling from there once they run out, so
    # the count is met whatever the library size.
    ordered = ([it for it in usable if it["id"] not in used]
               + [it for it in usable if it["id"] in used])
    for i in range(count):
        item = ordered[i % len(ordered)]
        used.add(item["id"])
        out.append(_row_for_kind(kind, item))
    return out


def _row_for_kind(kind: str, item: dict) -> Optional[dict[str, Any]]:
    """The request row that makes `item` come out as `kind`, or None when this
    item can't demonstrate it."""
    res = item.get("resolution")
    if kind == "parcial":
        # Ask for one step ABOVE what the library has: the resolution check
        # fails while the source one still passes, which is exactly what
        # "Parcial" means. An item with no resolution can't demonstrate it —
        # there'd be nothing to outrank.
        asked = _HIGHER_RESOLUTION.get((res or "").strip())
        if not asked:
            return None
        return _row_for(item, resolution=asked, source=item.get("source"), emu_status=None)
    if kind in ("reclamada", "llena", "pendiente"):
        # These three override the library verdict, so the spec can match
        # perfectly — the tracker state is what decides.
        emu_status = {"reclamada": "Reclamada", "llena": "Llena", "pendiente": "Pendiente"}[kind]
        return _row_for(item, resolution=res, source=item.get("source"), emu_status=emu_status)
    # compatible / no_disponible: ask for exactly what the item is.
    return _row_for(item, resolution=res, source=item.get("source"), emu_status=None)


def generate_examples(conn: sqlite3.Connection) -> dict[str, Any]:
    """Create the demo requests and re-run matching so their statuses appear.

    Returns {"created": n, "by_group": {...}, "shortfalls": [...]}. Groups the
    library can't supply come out short ON PURPOSE, and say so: padding them
    with invented entries to hit the requested count would misrepresent what
    you are looking at.
    """
    from .requests import match_requests

    if count_examples(conn):
        return {"created": 0, "by_group": {}, "shortfalls": [],
                "error": "Ya hay peticiones de ejemplo. Bórralas antes de generar otras."}

    pool = _library_pool(conn)
    used: set[int] = set()
    by_group: dict[str, int] = {}
    shortfalls: list[str] = []
    created = 0

    for count, kind in EXAMPLE_PLAN:
        rows = _build_group(kind, count, pool, used)
        by_group[kind] = len(rows)
        if len(rows) < count:
            shortfalls.append(
                f"{kind}: {len(rows)} de {count} "
                f"({'no hay suficiente contenido faltante' if kind == 'no_disponible' else 'no hay suficiente contenido en tu biblioteca'})"
            )
        for row in rows:
            created += 1
            conn.execute(
                """INSERT INTO request_items(
                       emu_id, title, category, requested_source, requested_resolution,
                       emu_status, points, comments, created_at, tmdb_id, imdb_id, url,
                       author, author_visible, raw_json, is_example, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP)""",
                (
                    f"{EXAMPLE_ID_PREFIX}{created}", row["title"], row["category"],
                    row["requested_source"], row["requested_resolution"], row["emu_status"],
                    10 * created % 90, created % 7, None,
                    row["tmdb_id"], row["imdb_id"], _EXAMPLE_URL,
                    None, 0, json.dumps({"example": True, "group": kind}, ensure_ascii=False),
                ),
            )
    conn.commit()

    # The statuses only exist once the matcher has run — nothing here writes a
    # verdict, it only sets up the inputs that produce one.
    try:
        match_requests(conn)
    except Exception:
        logger.exception("No se pudo emparejar las peticiones de ejemplo recién creadas")

    return {"created": created, "by_group": by_group, "shortfalls": shortfalls}
