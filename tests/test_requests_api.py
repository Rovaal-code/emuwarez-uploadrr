"""Tests for /api/requests endpoints (Phase 5B).

conftest.py provides: client, auth_headers, isolated_db.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Sync status
# ---------------------------------------------------------------------------

def test_requests_sync_status_requires_auth(client):
    resp = client.get("/api/requests/sync-status")
    assert resp.status_code == 401


def test_requests_sync_status_with_auth(client, auth_headers):
    resp = client.get("/api/requests/sync-status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "can_sync" in data
    assert "wait_seconds" in data
    assert isinstance(data["can_sync"], bool)
    assert isinstance(data["wait_seconds"], int)
    assert data["min_interval_seconds"] == 3600


def test_requests_sync_status_initially_can_sync(client, auth_headers):
    resp = client.get("/api/requests/sync-status", headers=auth_headers)
    assert resp.json()["can_sync"] is True


# ---------------------------------------------------------------------------
# GET /api/requests
# ---------------------------------------------------------------------------

def test_requests_list_requires_auth(client):
    resp = client.get("/api/requests")
    assert resp.status_code == 401


def test_requests_list_empty(client, auth_headers):
    resp = client.get("/api/requests", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_requests_list_with_data(client, auth_headers, isolated_db):
    """Seed a request item and check it appears in the list."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    item = RequestItem(
        id=None,
        emu_id="emu-test-1",
        title="Test Movie 5B",
        category="Movies",
        requested_resolution="1080p",
        requested_source="BluRay",
        emu_status="pending",
    )
    upsert_request(conn, item)
    conn.close()

    resp = client.get("/api/requests", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    titles = [i["title"] for i in data["items"]]
    assert "Test Movie 5B" in titles


def test_requests_list_shows_reclamado_with_no_library_match(client, auth_headers, isolated_db):
    """A request can be Reclamado on eMuwarez with zero library candidates
    (no request_matches row at all) — the tracker's own state must still
    surface instead of silently reading as 'Sin coincidencia'."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    item = RequestItem(
        id=None,
        emu_id="emu-reclamado-nomatch",
        title="Unmatched Reclamado Movie",
        category="Movies",
        requested_resolution="1080p",
        requested_source="BluRay",
        emu_status="Reclamado",
    )
    upsert_request(conn, item)
    conn.close()

    resp = client.get("/api/requests", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    row = next(i for i in items if i["title"] == "Unmatched Reclamado Movie")
    assert row["compatibility_status"] == "Reclamado"

    # The server-side status filter must find it too, not just the unfiltered list.
    resp2 = client.get("/api/requests?status=Reclamado", headers=auth_headers)
    titles = [i["title"] for i in resp2.json()["items"]]
    assert "Unmatched Reclamado Movie" in titles


def test_requests_expose_the_origin_instance(client, auth_headers, isolated_db):
    """Columna Origen de la tabla y campo Origen de la ficha: la instancia de
    Radarr/Sonarr del item cruzado. Sin cruce viene en None y la UI pinta un
    guion, que es el caso "No importada"."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    cur = conn.execute(
        """INSERT INTO library_items(item_type, title, year, local_status,
                                     instance_type, instance_name, instance_id,
                                     title_slug, tmdb_id)
           VALUES ('movie', 'Con Origen', 2020, 'Disponible',
                   'radarr', 'Radarr Pelis 4K', 7, NULL, '603')"""
    )
    lib_id = int(cur.lastrowid)
    for title, matched in (("Con Origen", True), ("Sin Origen", False)):
        upsert_request(conn, RequestItem(id=None, emu_id=f"origen-{title}", title=title,
                                         category="Movies"))
        if matched:
            rid = conn.execute("SELECT id FROM request_items WHERE title = ?", (title,)).fetchone()["id"]
            conn.execute(
                """INSERT INTO request_matches(library_item_id, request_item_id, status, confidence)
                   VALUES (?, ?, 'Compatible', 1.0)""", (lib_id, rid))
    conn.commit()
    conn.close()

    rows = {i["title"]: i for i in client.get("/api/requests", headers=auth_headers).json()["items"]}

    con = rows["Con Origen"]
    assert con["instance_name"] == "Radarr Pelis 4K"
    assert con["instance_type"] == "radarr"
    assert con["instance_id"] == 7
    assert con["library_tmdb_id"] == "603"      # el del item, para el enlace a la instancia

    sin = rows["Sin Origen"]
    assert sin["instance_name"] is None and sin["instance_type"] is None

    # La ficha lee los mismos campos que la tabla, no unos suyos.
    detail = client.get(f"/api/requests/{con['id']}", headers=auth_headers).json()
    assert detail["instance_name"] == "Radarr Pelis 4K"
    assert detail["instance_type"] == "radarr"


def test_requests_list_no_library_match_is_filterable(client, auth_headers, isolated_db):
    """A request with nothing matching in your library reads as
    'Sin coincidencia' (shown as "No importada") — and the status filter must
    return exactly those same rows.

    This used to disagree with itself: the list said 'Sin coincidencia' while
    the filter's SQL resolved an open request ("Sin llenar", the most common
    state) to NULL, so the row was visible under a status you couldn't filter
    by. 'Sin llenar' is the regression case; the others guard the branches
    around it.
    """
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    titles = {
        "Open Sin Llenar": "Sin llenar",
        "Open Unfilled": "unfilled",
        "No Emu Status": None,
        "Empty Emu Status": "",
    }
    for title, emu_status in titles.items():
        upsert_request(conn, RequestItem(
            id=None, emu_id=f"nomatch-{title.lower().replace(' ', '-')}",
            title=title, category="Movies", emu_status=emu_status,
        ))
    conn.close()

    listed = client.get("/api/requests", headers=auth_headers).json()["items"]
    shown = {i["title"]: i["compatibility_status"] for i in listed if i["title"] in titles}
    assert shown == {t: "Sin coincidencia" for t in titles}, shown

    filtered = client.get("/api/requests?status=Sin coincidencia", headers=auth_headers)
    assert filtered.status_code == 200
    found = {i["title"] for i in filtered.json()["items"]}
    assert set(titles) <= found, f"visibles pero no filtrables: {set(titles) - found}"


def test_requests_list_search(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    for title in ["Alpha Movie", "Beta Series", "Gamma Film"]:
        upsert_request(conn, RequestItem(id=None, emu_id=f"id-{title.lower().replace(' ','-')}", title=title))
    conn.close()

    resp = client.get("/api/requests?search=Beta", headers=auth_headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Beta Series"


def test_requests_list_pagination(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    for i in range(10):
        upsert_request(conn, RequestItem(id=None, emu_id=f"pag-{i}", title=f"Movie {i:02d}"))
    conn.close()

    resp1 = client.get("/api/requests?limit=5&offset=0", headers=auth_headers)
    resp2 = client.get("/api/requests?limit=5&offset=5", headers=auth_headers)
    assert resp1.json()["total"] == 10
    assert len(resp1.json()["items"]) == 5
    assert len(resp2.json()["items"]) == 5
    ids1 = {i["id"] for i in resp1.json()["items"]}
    ids2 = {i["id"] for i in resp2.json()["items"]}
    assert not (ids1 & ids2)  # no overlap


def test_requests_list_column_filters_take_several_values(client, auth_headers, isolated_db):
    """Los filtros de columna de Peticiones, como los de Biblioteca: varios valores en una columna
    suman (OR), columnas distintas restringen (AND). «Cualquiera» es la petición sin resolución
    o source pedidos, que antes no se podía filtrar, y Origen filtra por la instancia del cruce."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    filas = {
        "A": ("Movies", "1080p", "WEB-DL", "ana"),
        "B": ("Movies", "2160p", None, "ana"),
        "C": ("TV", None, "Remux", "bea"),
        "D": ("TV", "720p", "WEB-DL", "carla"),
    }
    for title, (cat, res, src, autor) in filas.items():
        upsert_request(conn, RequestItem(id=None, emu_id=f"col-{title}", title=title, category=cat,
                                         requested_resolution=res, requested_source=src,
                                         author=autor, author_visible=True))
    for title, inst in (("A", 3), ("C", 4)):
        lib = conn.execute("""INSERT INTO library_items(item_type, title, local_status, instance_type, instance_id)
                              VALUES ('movie', ?, 'Disponible', 'radarr', ?)""", (title, inst)).lastrowid
        rid = conn.execute("SELECT id FROM request_items WHERE title = ?", (title,)).fetchone()["id"]
        conn.execute("""INSERT INTO request_matches(library_item_id, request_item_id, status, confidence)
                        VALUES (?, ?, 'Compatible', 1.0)""", (lib, rid))
    conn.commit()
    conn.close()

    def titulos(qs: str) -> tuple[list[str], int]:
        data = client.get(f"/api/requests?{qs}", headers=auth_headers).json()
        return [i["title"] for i in data["items"]], data["total"]

    assert titulos("resolution=1080p&resolution=720p&sort=title") == (["A", "D"], 2)
    assert titulos("resolution=Cualquiera&sort=title") == (["C"], 1)
    assert titulos("source=Cualquiera&source=Remux&sort=title") == (["B", "C"], 2)
    assert titulos("category=TV&source=WEB-DL") == (["D"], 1)
    assert titulos("author=ana&author=bea&sort=title") == (["A", "B", "C"], 3)
    assert titulos("instance_id=3&instance_id=4&sort=title") == (["A", "C"], 2)
    assert titulos("status=Compatible&status=Sin coincidencia&category=Movies&sort=title") == (["A", "B"], 2)


# ---------------------------------------------------------------------------
# POST /api/requests/sync
# ---------------------------------------------------------------------------

def test_requests_sync_requires_auth(client):
    resp = client.post("/api/requests/sync", json={})
    assert resp.status_code == 401


def test_requests_sync_no_api_key_returns_502(client, auth_headers):
    """Without EMU api key configured, sync should fail gracefully (502)."""
    resp = client.post("/api/requests/sync", json={})
    # Without auth
    assert resp.status_code == 401

    resp = client.post("/api/requests/sync", json={}, headers=auth_headers)
    # No EMU api key → 502 IntegrationError
    assert resp.status_code == 502


def test_requests_sync_throttled(client, auth_headers, isolated_db, monkeypatch):
    """After a successful sync, a second sync without force should be throttled."""
    import os, datetime as dt
    from emuwarez_uploadrr.database import connect, init_db, set_state, get_state
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    # Simulate a recent sync
    recent = dt.datetime.now(dt.timezone.utc).isoformat()
    set_state(conn, "last_emu_requests_sync_utc", recent)
    conn.commit()
    conn.close()

    # Now try to sync — should be throttled
    from emuwarez_uploadrr.services.requests import can_sync_requests
    conn2 = connect()
    init_db(conn2)
    can, wait = can_sync_requests(conn2, force=False)
    conn2.close()
    assert can is False
    assert wait > 0


def test_requests_sync_force_body(client, auth_headers):
    """force=True is accepted as body param."""
    resp = client.post("/api/requests/sync", json={"force": True}, headers=auth_headers)
    # No api key → 502, but body was parsed correctly
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /api/requests/{id}
# ---------------------------------------------------------------------------

def test_requests_detail_requires_auth(client):
    resp = client.get("/api/requests/1")
    assert resp.status_code == 401


def test_requests_detail_not_found(client, auth_headers):
    resp = client.get("/api/requests/99999", headers=auth_headers)
    assert resp.status_code == 404


def _seed_matched_request(isolated_db, *, title="One Piece", year=1999, req_scope="season", req_season=1):
    """Seed a library item + request + request_matches row linking them —
    same shape as a real request matched against Biblioteca content."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, year) VALUES (?,?,?,?)",
        (title, "series", "Disponible", year),
    )
    conn.commit()
    lib_id = conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]
    req_id = upsert_request(conn, RequestItem(
        id=None, emu_id="matched-year-test", title=title,
        requested_resolution="1080p", requested_source="WEB-DL",
    ))
    conn.execute(
        "UPDATE request_items SET req_scope = ?, req_season = ? WHERE id = ?",
        (req_scope, req_season, req_id),
    )
    conn.execute(
        "INSERT INTO request_matches (library_item_id, request_item_id, status, confidence) VALUES (?,?,?,?)",
        (lib_id, req_id, "Compatible", 0.9),
    )
    conn.commit()
    conn.close()
    return req_id


def test_requests_list_includes_library_year_for_matched_item(client, auth_headers, isolated_db):
    """Regression: _row_to_item() (web/api/requests.py) used to rebuild
    RequestItemResponse field-by-field without library_year, so the API
    response silently dropped it even though the SQL query and the schema
    both already had it — the year never reached the frontend."""
    _seed_matched_request(isolated_db, title="One Piece", year=1999)

    resp = client.get("/api/requests", headers=auth_headers)
    assert resp.status_code == 200
    row = next(i for i in resp.json()["items"] if i["title"] == "One Piece")
    assert row["library_year"] == 1999


def test_requests_detail_includes_library_year_and_display_title(client, auth_headers, isolated_db):
    req_id = _seed_matched_request(isolated_db, title="One Piece", year=1999, req_scope="season", req_season=1)

    resp = client.get(f"/api/requests/{req_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["library_year"] == 1999
    assert data["display_title"] == "One Piece (1999) - Temporada 1"


def test_requests_detail_found(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    req_id = upsert_request(conn, RequestItem(
        id=None, emu_id="detail-test-1", title="Detail Movie",
        requested_resolution="1080p", requested_source="WEB-DL",
    ))
    conn.close()

    resp = client.get(f"/api/requests/{req_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == req_id
    assert data["title"] == "Detail Movie"
    assert data["requested_resolution"] == "1080p"
    assert "match" in data


# ---------------------------------------------------------------------------
# POST /api/requests/{id}/match
# ---------------------------------------------------------------------------

def test_requests_match_requires_auth(client):
    resp = client.post("/api/requests/1/match")
    assert resp.status_code == 401


def test_requests_match_not_found(client, auth_headers):
    resp = client.post("/api/requests/99999/match", headers=auth_headers)
    assert resp.status_code == 404


def test_requests_match_runs_matching(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.services.library import upsert_library_item
    from emuwarez_uploadrr.models import RequestItem, LibraryItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    # Seed matching pair
    lib_item = LibraryItem(
        id=None, item_type="movie", title="Matrix",
        tmdb_id="603", local_status="Disponible",
        instance_id=1, external_id="ext-603",
    )
    upsert_library_item(conn, lib_item)
    req_id = upsert_request(conn, RequestItem(id=None, emu_id="match-1", title="Matrix", tmdb_id="603"))
    conn.close()

    resp = client.post(f"/api/requests/{req_id}/match", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == req_id
    assert data["match"] is not None
    assert data["match"]["status"] in ("Compatible", "Parcial", "No compatible", "Llena")


# ---------------------------------------------------------------------------
# POST /api/requests/{id}/mark-reviewed
# ---------------------------------------------------------------------------

def test_requests_mark_reviewed_requires_auth(client):
    resp = client.post("/api/requests/1/mark-reviewed")
    assert resp.status_code == 401


def test_requests_mark_reviewed_not_found(client, auth_headers):
    resp = client.post("/api/requests/99999/mark-reviewed", headers=auth_headers)
    assert resp.status_code == 404


def test_requests_mark_reviewed_found(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.requests import upsert_request
    from emuwarez_uploadrr.models import RequestItem
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    conn = connect()
    init_db(conn)
    req_id = upsert_request(conn, RequestItem(id=None, emu_id="review-1", title="Review Me"))
    conn.close()

    resp = client.post(f"/api/requests/{req_id}/mark-reviewed", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# Dashboard summary includes EMU fields
# ---------------------------------------------------------------------------

def test_dashboard_summary_has_requests_fields(client, auth_headers):
    resp = client.get("/api/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "requests_total" in data
    assert "requests_compatible" in data
    assert "requests_filled" in data
    assert isinstance(data["requests_total"], int)


# ---------------------------------------------------------------------------
# Una temporada con datos mezclados frente a una petición
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pide_res,pide_src,tengo_res,tengo_src,esperado,por_que", [
    # Campo mezclado = el rollup llega en None. "No lo sé" no satisface nada
    # concreto, pero tampoco falla contra una petición que no lo restringe.
    ("1080p", "WEB-DL", None, "WEB-DL", "Parcial",     "resolución mezclada"),
    ("1080p", None,     None, "WEB-DL", "Parcial",     "resolución mezclada, source libre"),
    ("720p",  None,     None, "WEB-DL", "Parcial",     "ni pidiendo la más baja"),
    ("1080p", "WEB-DL", "1080p", None,  "Parcial",     "source mezclado"),
    ("1080p", None,     "1080p", None,  "Compatible",  "source mezclado pero no se pide"),
    ("1080p", "WEB-DL", "1080p", "WEB-DL", "Compatible", "coincidencia perfecta"),
    ("720p",  None,     "1080p", "WEB-DL", "Compatible", "1080p supera lo pedido"),
    ("2160p", None,     "1080p", "WEB-DL", "Parcial",     "falla la resolución"),
    ("2160p", "BluRay", "1080p", "WEB-DL", "No compatible", "fallan las dos"),
])
def test_mixed_season_values_against_a_request(pide_res, pide_src, tengo_res, tengo_src, esperado, por_que):
    """Una temporada puede tener varios sources (ya no bloquean) y, si está
    descuadrada, varias resoluciones. Contra una petición, un campo mezclado
    se comporta como "no lo sé": no puede prometerse.

    Esto funcionaba ya, pero no lo fijaba ningún test y es fácil de romper sin
    querer tocando los comparadores."""
    from emuwarez_uploadrr.services.compatibility import classify_request_match
    req = {"title": "X", "requested_resolution": pide_res, "requested_source": pide_src, "tmdb_id": "1"}
    item = {"title": "X", "resolution": tengo_res, "source": tengo_src,
            "tmdb_id": "1", "local_status": "Disponible"}
    assert classify_request_match(req, item)["status"] == esperado, por_que
