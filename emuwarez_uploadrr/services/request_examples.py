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
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger("emuwarez.request_examples")

EXAMPLE_ID_PREFIX = "ejemplo-"

# What the button generates, in the order the groups are filled. Each entry is
# (how many, which bucket) — see _build_group for what each bucket needs from
# the library to come out with that status.
EXAMPLE_PLAN: list[tuple[int, str]] = [
    (10, "compatible"),
    (5, "parcial"),
    (5, "no_compatible"),
    (3, "reclamada"),
    (2, "llena"),
    (1, "pendiente"),
    (5, "no_disponible"),
    (3, "inventada"),
]

# One of the "no disponible" ones is attributed to the user themselves, when
# they've filled in their eMuwarez username: seeing your own name on a request
# is the case that shows what the author column and the "es tuya" styling look
# like, and it can't be demonstrated any other way without the real endpoint.
_OWN_REQUEST_GROUP = "no_disponible"


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

# For "no compatible" BOTH checks have to fail, so the source is asked above
# the library's too. BDRemux tops _SOURCE_RANK; anything already at that top
# can't demonstrate this bucket and is skipped.
_TOP_SOURCE = "BDRemux"


def _higher_source(local: Optional[str]) -> Optional[str]:
    from .compatibility import compare_source
    if not (local or "").strip():
        return None
    # Ask for the best source there is; if the library already holds it, this
    # item can't make the source check fail.
    return None if compare_source(_TOP_SOURCE, local) else _TOP_SOURCE

_SHORTFALL_REASON = {
    "no_disponible": "no tienes contenido en estado Faltante",
    "parcial": "hace falta contenido con una resolución conocida por debajo del máximo",
    "no_compatible": "hace falta contenido con resolución y source por debajo del máximo",
}

# Filler that makes the table look like a real request list instead of a row
# of empty cells. None of it means anything — it exists so the votes, points,
# author and date columns can be seen doing their job.
_AUTHORS = [
    "Nocturno", "PixelHunter", "ElArchivista", "Marea", "Trece",
    "LumenHD", "CafeConBits", "Sombra", "Aurora", "ElColeccionista",
]

# eMuwarez bounties are never small change, so anything under 100 would read as
# broken. The range is wide on purpose: it's what makes sorting by points show
# something.
_POINTS_MIN, _POINTS_MAX = 1000, 30000
_VOTES_MAX = 15
# Requests all created at the same instant would make "Más recientes" useless.
_MAX_AGE_DAYS = 10


def _random_created_at(now: datetime) -> str:
    """A moment between now and _MAX_AGE_DAYS ago, to the minute."""
    delta = timedelta(minutes=random.randint(0, _MAX_AGE_DAYS * 24 * 60))
    return (now - delta).isoformat()


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
    # The parent series' own title comes along for season rows: a REAL request
    # names the series and carries the season in req_scope/req_season, it does
    # not put "Serie - Temporada 2" in the title field. Getting that wrong is
    # what made a season example show every season in its detail and drop the
    # season from the comparison table.
    rows = [dict(r) for r in conn.execute(
        """SELECT li.id, li.item_type, li.title, li.year, li.tmdb_id, li.imdb_id,
                  li.resolution, li.source, li.local_status, li.video_codec, li.audio_codec,
                  li.audio_languages, li.has_spanish_ok, li.season_number,
                  parent.title AS series_title, parent.year AS series_year
             FROM library_items li
             LEFT JOIN library_items parent ON parent.id = li.parent_id
            WHERE li.item_type IN ('movie', 'season')
              AND (li.tmdb_id IS NOT NULL OR li.title IS NOT NULL)
            ORDER BY li.id"""
    ).fetchall()]
    held, missing = [], []
    for r in rows:
        if r.get("local_status") in ("Disponible", "Subido", "Subiendo"):
            # A season only qualifies if it could actually go up as a pack.
            # Otherwise the demo produced requests for seasons the app itself
            # refuses to upload, which is the opposite of what these examples
            # are for. Same condition Recomendaciones and the Panel apply
            # (services/library.py's get_dashboard_summary).
            if r.get("item_type") == "season" and not _season_is_packable(r):
                continue
            held.append(r)
        else:
            missing.append(r)
    return {"held": _interleave(held), "missing": _interleave(missing), "all": rows}


def _season_is_packable(row: dict) -> bool:
    """Whether this season could be uploaded as a whole-season pack: todos sus
    capítulos con la misma resolución (la columna de rollup solo se rellena
    cuando coinciden) y castellano en todos.

    Es la misma regla que aplica season_pack._CONSISTENCY_FIELDS más
    _spanish_errors; el resto de campos dejó de bloquear."""
    return row.get("resolution") is not None and row.get("has_spanish_ok") == 1


def _interleave(rows: list[dict]) -> list[dict]:
    """Alternate films and seasons instead of taking them in id order.

    Radarr is usually synced before Sonarr, so plain id order handed the first
    groups nothing but films and the request list came out without a single
    season in it — which hides exactly the season-vs-film differences these
    examples exist to show."""
    movies = [r for r in rows if r.get("item_type") == "movie"]
    seasons = [r for r in rows if r.get("item_type") == "season"]
    out: list[dict] = []
    for i in range(max(len(movies), len(seasons))):
        if i < len(movies):
            out.append(movies[i])
        if i < len(seasons):
            out.append(seasons[i])
    return out


def _category_for(item: dict) -> str:
    return "TV" if item.get("item_type") == "season" else "Movie"


def _row_for(item: dict, *, resolution: Optional[str], source: Optional[str],
             emu_status: Optional[str]) -> dict[str, Any]:
    is_season = item.get("item_type") == "season"
    # A real request names the SERIES and says which season it wants through
    # req_scope/req_season. Everything downstream reads those two: the
    # comparison table only appends "- Season N" when req_season is set
    # (services/requests.py::_comparison_content_name), the detail narrows to
    # that one season through them (_effective_target), and the canonical
    # display title is built from them. Leaving them empty is what made a
    # season example list every season of the series.
    return {
        "title": (item.get("series_title") or item.get("title") or "Sin título") if is_season
                 else (item.get("title") or "Sin título"),
        "category": _category_for(item),
        "requested_resolution": resolution,
        "requested_source": source,
        "emu_status": emu_status,
        "tmdb_id": item.get("tmdb_id"),
        "imdb_id": item.get("imdb_id"),
        "req_scope": "season" if is_season else None,
        "req_season": item.get("season_number") if is_season else None,
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
            is_tv = item_type == "tv"
            out.append({
                "title": title, "category": "TV" if is_tv else "Movie",
                "requested_resolution": res, "requested_source": src,
                "emu_status": None, "tmdb_id": None, "imdb_id": None,
                "req_scope": "season" if is_tv else None,
                "req_season": 1 if is_tv else None,
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
    if kind == "no_compatible":
        # BOTH checks have to fail for "No compatible" — one alone is "Parcial".
        asked_res = _HIGHER_RESOLUTION.get((res or "").strip())
        asked_src = _higher_source(item.get("source"))
        if not asked_res or not asked_src:
            return None
        return _row_for(item, resolution=asked_res, source=asked_src, emu_status=None)
    if kind in ("reclamada", "llena", "pendiente"):
        # These three override the library verdict, so the spec can match
        # perfectly — the tracker state is what decides.
        emu_status = {"reclamada": "Reclamada", "llena": "Llena", "pendiente": "Pendiente"}[kind]
        return _row_for(item, resolution=res, source=item.get("source"), emu_status=emu_status)
    # compatible / no_disponible: ask for exactly what the item is.
    return _row_for(item, resolution=res, source=item.get("source"), emu_status=None)


def _own_username(conn: sqlite3.Connection) -> Optional[str]:
    from ..database import get_setting_canonical
    return (get_setting_canonical(conn, "emu.username") or "").strip() or None


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
    now = datetime.now(timezone.utc)
    own_user = _own_username(conn)
    own_assigned = False
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
                f"({_SHORTFALL_REASON.get(kind, 'no hay suficiente contenido en tu biblioteca')})"
            )
        for row in rows:
            created += 1
            # First row of its group gets the user's own name, so the list
            # shows what one of your own requests looks like.
            # Yours on one of them (when configured), a made-up name on the
            # rest: an empty author column shows nothing about how it behaves.
            if own_user and kind == _OWN_REQUEST_GROUP and not own_assigned:
                author, own_assigned = own_user, True
            else:
                author = random.choice(_AUTHORS)
            conn.execute(
                """INSERT INTO request_items(
                       emu_id, title, category, requested_source, requested_resolution,
                       emu_status, points, comments, votes, created_at, tmdb_id, imdb_id, url,
                       author, author_visible, raw_json, req_scope, req_season,
                       is_example, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP)""",
                (
                    f"{EXAMPLE_ID_PREFIX}{created}", row["title"], row["category"],
                    row["requested_source"], row["requested_resolution"], row["emu_status"],
                    random.randint(_POINTS_MIN, _POINTS_MAX), random.randint(0, 12),
                    random.randint(0, _VOTES_MAX), _random_created_at(now),
                    row["tmdb_id"], row["imdb_id"], _EXAMPLE_URL,
                    author, 1 if author else 0,
                    json.dumps({"example": True, "group": kind}, ensure_ascii=False),
                    row.get("req_scope"), row.get("req_season"),
                ),
            )
    conn.commit()

    # The statuses only exist once the matcher has run — nothing here writes a
    # verdict, it only sets up the inputs that produce one.
    try:
        match_requests(conn)
    except Exception:
        logger.exception("No se pudo emparejar las peticiones de ejemplo recién creadas")

    return {
        "created": created,
        "by_group": by_group,
        # What the matcher ACTUALLY decided, not what each group was aiming
        # for. They can differ: a request is matched against the whole library,
        # so it can land on a different item than the one it was built from —
        # every season of a series shares the series' tmdb_id, for instance.
        # Reporting the intent instead of the outcome would claim a
        # distribution that isn't on screen.
        "by_status": _actual_statuses(conn),
        "shortfalls": shortfalls,
    }


def _actual_statuses(conn: sqlite3.Connection) -> dict[str, int]:
    from .compatibility import emu_override_status

    counts: dict[str, int] = {}
    rows = conn.execute(
        """SELECT ri.emu_status, rm.status AS match_status
             FROM request_items ri
             LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
            WHERE ri.is_example = 1"""
    ).fetchall()
    for r in rows:
        # Same precedence the UI applies: the tracker state beats the library
        # verdict.
        status = emu_override_status(r["emu_status"]) or r["match_status"] or "Sin coincidencia"
        counts[status] = counts.get(status, 0) + 1
    return counts
