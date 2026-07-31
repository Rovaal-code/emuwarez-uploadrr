"""Tests for the demo requests generated from the user's own library.

TEMPORARY feature (see services/request_examples.py) — but the is_example
marker it hangs on is what makes its eventual removal safe, so it's the part
these tests pin down hardest.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import request_examples as ex


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _lib(conn, title, *, item_type="movie", status="Disponible",
         resolution="1080p", source="WEB-DL", tmdb_id=None, packable=True):
    # Seasons only qualify as example material when they could actually go up
    # as a pack, which means every rollup field filled in and Castilian
    # present — `packable=False` builds one that can't.
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            resolution, source, tmdb_id, year, video_codec, audio_codec,
            audio_languages, has_spanish_ok, updated_at)
           VALUES (?,?,?,'Sin petición','N/A',?,?,?,2020,?,?,?,?,CURRENT_TIMESTAMP)""",
        (item_type, title, status, resolution, source, tmdb_id,
         "x264" if packable else None, "AC3" if packable else None,
         "spa" if packable else None, 1 if packable else 0),
    )
    conn.commit()


def _seed_library(conn, held=25, missing=8):
    # Films first and seasons after, on purpose: that's the real shape (Radarr
    # is usually synced before Sonarr) and it's what used to leave the request
    # list without a single season.
    for i in range(held):
        _lib(conn, f"Peli {i}", tmdb_id=str(1000 + i))
    for i in range(held):
        _lib(conn, f"Serie {i} - Temporada 1", item_type="season", tmdb_id=str(3000 + i))
    for i in range(missing):
        _lib(conn, f"Falta {i}", status="Faltante", tmdb_id=str(2000 + i))
    for i in range(missing):
        _lib(conn, f"Serie falta {i} - Temporada 1", item_type="season",
             status="Faltante", tmdb_id=str(4000 + i))


def _statuses(conn):
    """Computed compatibility status per example, as the UI would show it."""
    rows = conn.execute(
        """SELECT ri.emu_id, ri.emu_status, rm.status AS match_status
             FROM request_items ri
             LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
            WHERE ri.is_example = 1"""
    ).fetchall()
    return [dict(r) for r in rows]


# --- The marker, which is what makes removal safe ---------------------------

def test_every_generated_request_is_marked(db_conn):
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    total = db_conn.execute("SELECT COUNT(*) AS n FROM request_items").fetchone()["n"]
    marked = ex.count_examples(db_conn)
    assert marked == total > 0


def test_delete_removes_only_examples(db_conn):
    """A real request sitting next to them must survive — this is the whole
    reason the flag exists."""
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem

    _seed_library(db_conn)
    upsert_request(db_conn, RequestItem(
        id=None, emu_id="real-1", title="Petición de verdad", category="Movie",
        requested_source=None, requested_resolution=None, emu_status=None, points=None,
        comments=None, created_at=None, tmdb_id=None, imdb_id=None, tvdb_id=None,
        mal_id=None, url=None, author=None, author_visible=False, raw_json=None,
    ))
    db_conn.commit()
    ex.generate_examples(db_conn)

    deleted = ex.delete_examples(db_conn)
    assert deleted > 0
    assert ex.count_examples(db_conn) == 0
    remaining = [r["emu_id"] for r in db_conn.execute("SELECT emu_id FROM request_items").fetchall()]
    assert remaining == ["real-1"]


def test_example_ids_cannot_collide_with_real_ones(db_conn):
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    ids = [r["emu_id"] for r in db_conn.execute(
        "SELECT emu_id FROM request_items WHERE is_example = 1").fetchall()]
    assert all(i.startswith(ex.EXAMPLE_ID_PREFIX) for i in ids)
    assert len(set(ids)) == len(ids)


def test_generating_twice_is_refused(db_conn):
    """Otherwise a page reload (or an impatient second click) doubles them."""
    _seed_library(db_conn)
    first = ex.generate_examples(db_conn)
    assert first["created"] > 0
    second = ex.generate_examples(db_conn)
    assert second["created"] == 0 and second["error"]
    assert ex.count_examples(db_conn) == first["created"]


# --- The statuses are computed, not written down ----------------------------

def test_groups_land_on_their_intended_status(db_conn):
    """Nothing here writes a verdict: each group is built so the real matcher
    (services/compatibility.py) arrives at the intended one."""
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    by_status: dict[str, int] = {}
    for row in _statuses(db_conn):
        # Same precedence the UI applies: the tracker state wins over the
        # library verdict.
        from emuwarez_uploadrr.services.compatibility import emu_override_status
        status = emu_override_status(row["emu_status"]) or row["match_status"] or "Sin coincidencia"
        by_status[status] = by_status.get(status, 0) + 1

    assert by_status.get("Compatible") == 10
    assert by_status.get("Parcial") == 5
    assert by_status.get("No compatible") == 5
    assert by_status.get("Reclamado") == 3
    assert by_status.get("Llena") == 2
    assert by_status.get("Pendiente") == 1
    assert by_status.get("No disponible") == 5
    assert by_status.get("Sin coincidencia") == 3


def test_invented_ones_match_nothing_in_the_library(db_conn):
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    invented = db_conn.execute(
        """SELECT ri.id FROM request_items ri
             LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
            WHERE ri.is_example = 1 AND ri.tmdb_id IS NULL AND rm.id IS NULL"""
    ).fetchall()
    assert len(invented) == 3


def test_a_thin_library_still_fills_every_group_by_reusing_items(db_conn):
    """Only three films to work with, but the point of the feature is seeing
    every status, so items get reused rather than leaving groups empty."""
    _seed_library(db_conn, held=3, missing=1)
    result = ex.generate_examples(db_conn)
    assert result["by_group"]["compatible"] == 10
    assert result["by_group"]["reclamada"] == 3
    assert result["by_group"]["no_disponible"] == 5


def test_a_group_with_nothing_to_work_from_reports_the_shortfall(db_conn):
    """Padding it with something that isn't what it claims would misrepresent
    what you're looking at, so it comes out short and says so."""
    _seed_library(db_conn, held=3, missing=0)     # nothing Faltante at all
    result = ex.generate_examples(db_conn)
    assert result["by_group"]["no_disponible"] == 0
    assert any("no_disponible" in s for s in result["shortfalls"])


def test_no_library_at_all_still_generates_the_invented_ones(db_conn):
    result = ex.generate_examples(db_conn)
    assert result["by_group"]["inventada"] == 3
    assert result["created"] == 3


def test_a_roomy_library_does_not_repeat_titles(db_conn):
    """Reuse is the fallback, not the default: with enough content each group
    takes fresh items so the list doesn't read as the same three titles."""
    _seed_library(db_conn, held=25, missing=8)
    ex.generate_examples(db_conn)
    tmdbs = [r["tmdb_id"] for r in db_conn.execute(
        "SELECT tmdb_id FROM request_items WHERE is_example = 1 AND tmdb_id IS NOT NULL").fetchall()]
    assert len(set(tmdbs)) == len(tmdbs)


# --- API --------------------------------------------------------------------

def test_endpoints_round_trip(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    _seed_library(conn)

    assert client.get("/api/requests/examples", headers=auth_headers).json()["count"] == 0
    created = client.post("/api/requests/examples", headers=auth_headers).json()
    assert created["created"] > 0
    assert client.get("/api/requests/examples", headers=auth_headers).json()["count"] == created["created"]

    # Second attempt is refused rather than doubling them.
    assert client.post("/api/requests/examples", headers=auth_headers).status_code == 409

    listed = client.get("/api/requests", headers=auth_headers).json()
    assert all(i["is_example"] for i in listed["items"])

    deleted = client.delete("/api/requests/examples", headers=auth_headers).json()
    assert deleted["deleted"] == created["created"]
    assert client.get("/api/requests/examples", headers=auth_headers).json()["count"] == 0


def test_examples_route_is_not_swallowed_by_the_id_route(client, auth_headers):
    """/requests/{request_id} sits right next to it — "examples" must not be
    parsed as an id."""
    r = client.get("/api/requests/examples", headers=auth_headers)
    assert r.status_code == 200 and "count" in r.json()


def test_requests_mix_films_and_seasons(db_conn):
    """Plain id order handed the first groups nothing but films (Radarr syncs
    before Sonarr), so the list came out without a single season — hiding
    exactly the film-vs-season differences these examples exist to show."""
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    cats = [r["category"] for r in db_conn.execute(
        "SELECT category FROM request_items WHERE is_example = 1").fetchall()]
    assert cats.count("Movie") >= 5
    assert cats.count("TV") >= 5


def test_no_compatible_fails_both_checks_not_just_one(db_conn):
    """One check failing is "Parcial"; this bucket only exists when the
    resolution AND the source both fall short."""
    from emuwarez_uploadrr.services.compatibility import compare_resolution, compare_source
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    rows = db_conn.execute(
        """SELECT ri.requested_resolution, ri.requested_source, li.resolution, li.source
             FROM request_items ri
             JOIN request_matches rm ON rm.request_item_id = ri.id
             JOIN library_items li ON li.id = rm.library_item_id
            WHERE ri.is_example = 1 AND rm.status = 'No compatible'"""
    ).fetchall()
    assert len(rows) == 5
    for r in rows:
        assert compare_resolution(r["requested_resolution"], r["resolution"]) is False
        assert compare_source(r["requested_source"], r["source"]) is False


def test_reports_the_matcher_s_verdict_not_the_intent(db_conn):
    """A request is matched against the WHOLE library, so it can land on a
    different item than the one it was built from — every season of a series
    shares the series' tmdb_id, for one. Reporting the intended distribution
    would claim numbers that aren't on screen."""
    _seed_library(db_conn)
    result = ex.generate_examples(db_conn)
    assert sum(result["by_status"].values()) == result["created"]
    # And it agrees with what the table itself would show.
    live = {}
    from emuwarez_uploadrr.services.compatibility import emu_override_status
    for row in _statuses(db_conn):
        st = emu_override_status(row["emu_status"]) or row["match_status"] or "Sin coincidencia"
        live[st] = live.get(st, 0) + 1
    assert result["by_status"] == live


def test_seasons_that_could_not_be_uploaded_are_not_used(db_conn):
    """The demo existed to show what the app can work with, so generating
    requests for seasons the app itself refuses to upload as a pack was the
    opposite of useful."""
    _lib(db_conn, "Serie buena - Temporada 1", item_type="season", tmdb_id="7001", packable=True)
    _lib(db_conn, "Serie rota - Temporada 1", item_type="season", tmdb_id="7002", packable=False)
    ex.generate_examples(db_conn)
    titles = [r["title"] for r in db_conn.execute(
        "SELECT title FROM request_items WHERE is_example = 1").fetchall()]
    assert any("Serie buena" in t for t in titles)
    assert not any("Serie rota" in t for t in titles)


def test_one_request_carries_your_own_username(db_conn):
    """Seeing your own name on a request is the one case the author column and
    its styling can't be demonstrated without the real endpoint."""
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    set_setting(db_conn, "emu.username", "Alvaro")
    db_conn.commit()
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    mine = db_conn.execute(
        "SELECT title, author, author_visible FROM request_items WHERE author = 'Alvaro'"
    ).fetchall()
    assert len(mine) == 1
    assert mine[0]["author_visible"] == 1


def test_no_username_configured_means_no_authored_request(db_conn):
    _seed_library(db_conn)
    ex.generate_examples(db_conn)
    authored = db_conn.execute(
        "SELECT COUNT(*) AS n FROM request_items WHERE is_example = 1 AND author IS NOT NULL"
    ).fetchone()["n"]
    assert authored == 0


def test_season_examples_carry_the_request_scope(db_conn):
    """The bug this fixes: a real request names the SERIES and says which season
    it wants through req_scope/req_season. Putting "Serie - Temporada 2" in the
    title and leaving those empty meant the detail listed every season of the
    series (_effective_target couldn't narrow it), the comparison table dropped
    the season entirely (_comparison_content_name only appends it when
    req_season is set), and the canonical display title came out wrong."""
    _lib(db_conn, "Los Tudor", item_type="series", tmdb_id="1399")
    series_id = db_conn.execute("SELECT id FROM library_items WHERE item_type='series'").fetchone()["id"]
    db_conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status, parent_id,
            season_number, resolution, source, video_codec, audio_codec, audio_languages,
            has_spanish_ok, tmdb_id, year, updated_at)
           VALUES ('season','Los Tudor - Temporada 2','Disponible','Sin petición','N/A',?,
                   2,'1080p','WEB-DL','x264','AC3','spa',1,'1399',2007,CURRENT_TIMESTAMP)""",
        (series_id,),
    )
    db_conn.commit()

    ex.generate_examples(db_conn)
    row = db_conn.execute(
        "SELECT title, req_scope, req_season FROM request_items "
        "WHERE is_example = 1 AND category = 'TV' AND req_season IS NOT NULL LIMIT 1"
    ).fetchone()
    assert row is not None
    # The title is the SERIES name, not "Serie - Temporada 2".
    assert row["title"] == "Los Tudor"
    assert row["req_scope"] == "season"
    assert row["req_season"] == 2


def test_the_comparison_name_spells_out_the_season(db_conn):
    """End of the same chain: with the scope set, the comparison table says
    which season — and says it in Spanish."""
    from emuwarez_uploadrr.services.requests import _comparison_content_name
    lib = {"item_type": "season", "title": "Los Tudor - Temporada 2", "year": 2007}
    req = {"req_scope": "season", "req_season": 2, "title": "Los Tudor"}
    name = _comparison_content_name(db_conn, lib, req)
    assert "Temporada 2" in name
    assert "Season" not in name
