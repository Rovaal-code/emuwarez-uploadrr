"""Tests for emuwarez_uploadrr/integrations/emu.py — Phase 5B."""
from __future__ import annotations

import json
import pytest

from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.emu import (
    normalize_request,
    normalize_requests,
    _flatten_unit3d,
    EMU_BASE_URL,
)
from emuwarez_uploadrr.models import RequestItem


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_emu_base_url():
    assert EMU_BASE_URL == "https://emu-warez.com"


# ---------------------------------------------------------------------------
# _flatten_unit3d
# ---------------------------------------------------------------------------

def test_flatten_unit3d_flat_passthrough():
    raw = {"id": "1", "title": "Movie"}
    assert _flatten_unit3d(raw) == raw


def test_flatten_unit3d_nested():
    raw = {
        "id": 5,
        "type": "requests",
        "attributes": {
            "name": "A Movie",
            "resolution": "1080p",
            "tmdb": "12345",
            "anon": True,
        },
        "links": {"self": "https://emu-warez.com/requests/5"},
    }
    flat = _flatten_unit3d(raw)
    assert flat["name"] == "A Movie"
    assert flat["resolution"] == "1080p"
    assert flat["tmdb"] == "12345"
    assert flat["url"] == "https://emu-warez.com/requests/5"


def test_flatten_unit3d_existing_url_preserved():
    raw = {
        "id": 1,
        "url": "https://emu-warez.com/requests/1",
        "attributes": {"name": "Foo"},
        "links": {"self": "https://emu-warez.com/api/requests/1"},
    }
    flat = _flatten_unit3d(raw)
    assert flat["url"] == "https://emu-warez.com/requests/1"


# ---------------------------------------------------------------------------
# normalize_request
# ---------------------------------------------------------------------------

def test_normalize_request_flat():
    raw = {
        "id": "42",
        "title": "Some Movie",
        "category": "Movies",
        "type": "BluRay",
        "resolution": "1080p",
        "tmdb_id": "12345",
        "imdb_id": "tt0000001",
        "bounty": "500",
        "comments": "3",
        "filled": False,
        "created_at": "2024-01-01T00:00:00Z",
        "url": "https://emu-warez.com/requests/42",
        "anon": True,
    }
    item = normalize_request(raw)
    assert isinstance(item, RequestItem)
    assert item.emu_id == "42"
    assert item.title == "Some Movie"
    assert item.category == "Movies"
    assert item.requested_source == "BluRay"
    assert item.requested_resolution == "1080p"
    assert item.tmdb_id == "12345"
    assert item.imdb_id == "tt0000001"
    assert item.points == 500
    assert item.comments == 3
    assert item.url == "https://emu-warez.com/requests/42"
    assert item.author is None  # anon=True
    assert item.author_visible is False


def test_normalize_request_unit3d_nested():
    raw = {
        "id": 7,
        "type": "requests",
        "attributes": {
            "name": "Película de Prueba",
            "resolution": "720p",
            "type": "WEB-DL",
            "tmdb": "99999",
            "imdb": "tt1234567",
            "bounty": 100,
            "comments": 0,
            "filled": False,
            "anon": False,
            "username": "usuario_emu",
            "created_at": "2025-06-01T12:00:00Z",
        },
        "links": {"self": "https://emu-warez.com/requests/7"},
    }
    item = normalize_request(raw)
    assert item.emu_id == "7"
    assert item.title == "Película de Prueba"
    assert item.requested_resolution == "720p"
    assert item.requested_source == "WEB-DL"
    assert item.tmdb_id == "99999"
    assert item.imdb_id == "tt1234567"
    assert item.url == "https://emu-warez.com/requests/7"
    # anon=False, so author should be set
    assert item.author == "usuario_emu"
    assert item.author_visible is False  # always hidden by default


def test_normalize_request_imdb_extraction():
    raw = {"id": "1", "title": "Test", "imdb_url": "https://imdb.com/title/tt9876543/"}
    item = normalize_request(raw)
    assert item.imdb_id == "tt9876543"


def test_normalize_request_auto_url():
    raw = {"id": "15", "title": "Test Movie"}
    item = normalize_request(raw)
    assert item.url == f"{EMU_BASE_URL}/requests/15"


def test_normalize_request_missing_title():
    raw = {"id": "3"}
    item = normalize_request(raw)
    assert item.title == "Sin título"


def test_normalize_request_raw_json_stored():
    raw = {"id": "1", "title": "Movie", "extra_field": "value"}
    item = normalize_request(raw)
    stored = json.loads(item.raw_json)
    assert stored["extra_field"] == "value"


# ---------------------------------------------------------------------------
# normalize_requests
# ---------------------------------------------------------------------------

def test_normalize_requests_filters_non_dicts():
    raw = [
        {"id": "1", "title": "Movie 1"},
        "not a dict",
        None,
        {"id": "2", "title": "Movie 2"},
    ]
    items = normalize_requests(raw)
    assert len(items) == 2
    assert items[0].title == "Movie 1"
    assert items[1].title == "Movie 2"


def test_normalize_requests_empty():
    assert normalize_requests([]) == []


# ---------------------------------------------------------------------------
# emu_fetch_all_pages (with monkeypatched emu_get_requests)
# ---------------------------------------------------------------------------

def test_emu_fetch_all_pages_single(monkeypatch):
    page_data = {
        "data": [{"id": 1, "title": "M1"}, {"id": 2, "title": "M2"}],
        "meta": {"current_page": 1, "last_page": 1, "total": 2},
    }
    monkeypatch.setattr(emu, "emu_get_requests", lambda api_key, base_url=None, page=1, per_page=100: page_data)
    items = emu.emu_fetch_all_pages("test-key")
    assert len(items) == 2
    assert items[0]["id"] == 1


def test_emu_fetch_all_pages_multi(monkeypatch):
    def fake_get(api_key, base_url=None, page=1, per_page=100):
        pages = {
            1: {"data": [{"id": 1}], "meta": {"current_page": 1, "last_page": 2}},
            2: {"data": [{"id": 2}], "meta": {"current_page": 2, "last_page": 2}},
        }
        return pages.get(page, {"data": [], "meta": {"current_page": page, "last_page": 2}})
    monkeypatch.setattr(emu, "emu_get_requests", fake_get)
    items = emu.emu_fetch_all_pages("test-key")
    assert len(items) == 2
    assert {i["id"] for i in items} == {1, 2}


def test_emu_fetch_all_pages_list_response(monkeypatch):
    monkeypatch.setattr(emu, "emu_get_requests", lambda *a, **kw: [{"id": 1}, {"id": 2}])
    items = emu.emu_fetch_all_pages("test-key")
    assert len(items) == 2


def test_emu_fetch_all_pages_empty(monkeypatch):
    monkeypatch.setattr(emu, "emu_get_requests", lambda *a, **kw: {"data": [], "meta": {"current_page": 1, "last_page": 1}})
    items = emu.emu_fetch_all_pages("test-key")
    assert items == []


# ---------------------------------------------------------------------------
# create_request (should always raise)
# ---------------------------------------------------------------------------

def test_create_request_blocked():
    from emuwarez_uploadrr.integrations.base import IntegrationError
    with pytest.raises(IntegrationError):
        emu.create_request(title="Test")


# ---------------------------------------------------------------------------
# sync_emu_requests — API key resolution + missing /api/requests endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def test_sync_requests_reads_key_from_db_settings(db_conn, monkeypatch):
    """The key configured in the Settings UI (settings.emu.api_key) must be
    used — regression for the task reporting 'No hay API Key' when it was set."""
    from emuwarez_uploadrr.services.settings import set_setting
    from emuwarez_uploadrr.services import requests as reqs
    set_setting(db_conn, "emu.api_key", "configured-key-123")

    seen = {}
    def fake_fetch(api_key, *a, **kw):
        seen["key"] = api_key
        return []
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", fake_fetch)
    monkeypatch.setattr(reqs, "match_all_requests", lambda conn, emu_api_key=None: 0)

    result = reqs.sync_emu_requests(db_conn, force=True)
    assert seen["key"] == "configured-key-123"
    assert result["status"] == "ok"


def test_sync_requests_missing_endpoint_is_skipped_not_failed(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.settings import set_setting
    from emuwarez_uploadrr.integrations.base import IntegrationError
    from emuwarez_uploadrr.services import requests as reqs
    set_setting(db_conn, "emu.api_key", "configured-key-123")

    def fake_fetch(*a, **kw):
        raise IntegrationError(
            "HTTP 404 en https://emu-warez.com/api/requests: The route api/requests could not be found."
        )
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", fake_fetch)

    result = reqs.sync_emu_requests(db_conn, force=True)
    assert result["status"] == "unavailable"
    row = db_conn.execute(
        "SELECT status FROM task_runs WHERE name='sync-emu-requests' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["status"] == "skipped"


# ---------------------------------------------------------------------------
# "Contenido compatible" notifications name the season / episode
# ---------------------------------------------------------------------------

def _add_library_item(conn, *, item_type, title, year=None, parent_id=None,
                      season_number=None, episode_number=None):
    cur = conn.execute(
        """INSERT INTO library_items(item_type, title, year, parent_id, season_number,
                                     episode_number, local_status, poster_url)
           VALUES (?, ?, ?, ?, ?, ?, 'Disponible', 'http://poster')""",
        (item_type, title, year, parent_id, season_number, episode_number),
    )
    return int(cur.lastrowid)


def _add_compatible_request(conn, *, title, library_item_id, scope=None,
                            season=None, episode=None):
    cur = conn.execute(
        """INSERT INTO request_items(emu_id, title, req_scope, req_season, req_episode)
           VALUES (?, ?, ?, ?, ?)""",
        (f"emu-{title}", title, scope, season, episode),
    )
    rid = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO request_matches(library_item_id, request_item_id, status, confidence)
           VALUES (?, ?, 'Compatible', 1.0)""",
        (library_item_id, rid),
    )
    conn.commit()
    return rid


def _notify_and_read(conn):
    from emuwarez_uploadrr.services.requests import _notify_new_compatible_matches
    from emuwarez_uploadrr.services.notification_center import list_notifications
    _notify_new_compatible_matches(conn, set())
    return list_notifications(conn)


def test_compatible_notification_names_the_season(db_conn):
    """A season request notified under the bare series name, so three seasons
    of the same show all arrived as the same indistinguishable line."""
    series = _add_library_item(db_conn, item_type="series", title="Serie", year=2019)
    season = _add_library_item(db_conn, item_type="season", title="Serie Season 2",
                               parent_id=series, season_number=2)
    _add_compatible_request(db_conn, title="Serie S2", library_item_id=season,
                            scope="season", season=2)

    notes = _notify_and_read(db_conn)
    assert len(notes) == 1
    assert notes[0]["content_title"] == "Serie (2019) - Temporada 2"


def test_compatible_notification_names_the_episode_as_sxxeyy(db_conn):
    """An episode request says SxxEyy, and NOT "Temporada 2 - S02E05" — the
    canonical format never carries both suffixes at once."""
    series = _add_library_item(db_conn, item_type="series", title="Serie", year=2019)
    season = _add_library_item(db_conn, item_type="season", title="Serie Season 2",
                               parent_id=series, season_number=2)
    ep = _add_library_item(db_conn, item_type="episode", title="Serie S02E05 - Piloto",
                           parent_id=season, season_number=2, episode_number=5)
    _add_compatible_request(db_conn, title="Serie S2E5", library_item_id=ep,
                            scope="episode", season=2, episode=5)

    notes = _notify_and_read(db_conn)
    assert len(notes) == 1
    assert notes[0]["content_title"] == "Serie (2019) - S02E05"


def test_compatible_notification_for_a_movie_has_no_season_suffix(db_conn):
    movie = _add_library_item(db_conn, item_type="movie", title="Pelicula", year=2020)
    _add_compatible_request(db_conn, title="Pelicula", library_item_id=movie)

    notes = _notify_and_read(db_conn)
    assert len(notes) == 1
    assert notes[0]["content_title"] == "Pelicula (2020)"


def test_compatible_notification_keeps_the_matched_poster(db_conn):
    """The poster and the title must come from the SAME matched row, or the
    notification could show one season's art next to another's name."""
    movie = _add_library_item(db_conn, item_type="movie", title="Pelicula", year=2020)
    _add_compatible_request(db_conn, title="Pelicula", library_item_id=movie)

    notes = _notify_and_read(db_conn)
    assert notes[0]["poster_url"] == "http://poster"


def test_muchas_compatibles_de_golpe_dan_un_solo_aviso(db_conn):
    """La primera sincronización encuentra de golpe todo lo compatible: un aviso por petición llenaba la campana
    (y Discord/Telegram)."""
    movie = _add_library_item(db_conn, item_type="movie", title="Pelicula", year=2020)
    for i in range(6):
        _add_compatible_request(db_conn, title=f"Pelicula {i}", library_item_id=movie)

    notes = _notify_and_read(db_conn)
    assert len(notes) == 1
    assert notes[0]["body"] == "Tienes contenido compatible con 6 peticiones."


# ---------------------------------------------------------------------------
# El estado de la petición aterriza en la fila que la petición pide
# ---------------------------------------------------------------------------

def test_a_season_request_marks_the_season_not_the_series(db_conn):
    """Una petición de la Temporada 2 tiene que marcar ESA temporada. El
    emparejador cruza contra la SERIE (todas las temporadas comparten su
    tmdb_id), así que el estado aterrizaba allí y la ficha de la temporada
    seguía diciendo "Sin petición"."""
    from emuwarez_uploadrr.services.requests import match_all_requests, upsert_request
    from emuwarez_uploadrr.models import RequestItem

    cur = db_conn.execute(
        "INSERT INTO library_items(item_type,title,year,local_status,tmdb_id) "
        "VALUES ('series','Serie',2019,'Disponible','555')")
    series_id = cur.lastrowid
    cur = db_conn.execute(
        "INSERT INTO library_items(item_type,title,local_status,parent_id,season_number,"
        "resolution,source,video_codec,has_spanish_ok) "
        "VALUES ('season','Serie - Temporada 2','Disponible',?,2,'1080p','WEB-DL','x264',1)",
        (series_id,))
    season_id = cur.lastrowid
    db_conn.commit()

    upsert_request(db_conn, RequestItem(
        id=None, emu_id="req-t2", title="Serie", category="TV", tmdb_id="555",
        requested_resolution="1080p", requested_source="WEB-DL",
    ))
    db_conn.execute("UPDATE request_items SET req_scope='season', req_season=2")
    db_conn.commit()

    match_all_requests(db_conn)

    estado = lambda i: db_conn.execute(
        "SELECT request_status FROM library_items WHERE id = ?", (i,)).fetchone()["request_status"]
    assert estado(season_id) != "Sin petición", "la temporada tiene que llevar el estado"
    assert estado(series_id) == "Sin petición", "la serie no: la petición no es de la serie entera"


def test_recalcular_borra_el_casamiento_que_ya_no_vale(db_conn):
    """El «Compatible» de antes (Dune de 1984 para la petición de la de 2021) se quedaba en request_matches y la
    lista lo seguía enseñando."""
    from emuwarez_uploadrr.services.requests import match_all_requests, match_single_request
    peli = db_conn.execute("INSERT INTO library_items(item_type,title,local_status,request_status,request_id,tmdb_id) "
                           "VALUES ('movie','Dune','Disponible','Compatible',1,'841')").lastrowid
    rid = db_conn.execute("INSERT INTO request_items(emu_id,title,category,tmdb_id) "
                          "VALUES ('d21','Dune','Movie','438631')").lastrowid
    viejo = ("INSERT INTO request_matches(library_item_id, request_item_id, status, confidence) "
             "VALUES (?, ?, 'Compatible', 0.9)")
    db_conn.execute(viejo, (peli, rid))
    db_conn.commit()

    match_all_requests(db_conn)
    assert db_conn.execute("SELECT COUNT(*) AS n FROM request_matches").fetchone()["n"] == 0

    db_conn.execute(viejo, (peli, rid))
    db_conn.execute("UPDATE library_items SET request_status = 'Compatible', request_id = ? WHERE id = ?", (rid, peli))
    db_conn.commit()
    match_single_request(db_conn, rid)
    assert db_conn.execute("SELECT COUNT(*) AS n FROM request_matches").fetchone()["n"] == 0
    fila = db_conn.execute("SELECT request_status, request_id FROM library_items WHERE id = ?", (peli,)).fetchone()
    assert (fila["request_status"], fila["request_id"]) == ("Sin petición", None)


def test_rematching_clears_a_status_left_on_the_wrong_row(db_conn):
    """Recalcular limpia antes: si no, un estado escrito una vez se quedaba
    pegado en esa fila para siempre, porque nadie lo volvía a tocar."""
    from emuwarez_uploadrr.services.requests import match_all_requests
    cur = db_conn.execute(
        "INSERT INTO library_items(item_type,title,local_status,request_status,request_id) "
        "VALUES ('movie','Peli','Disponible','Compatible',999)")
    item_id = cur.lastrowid
    db_conn.commit()

    match_all_requests(db_conn)          # sin ninguna petición que lo respalde

    row = db_conn.execute(
        "SELECT request_status, request_id FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["request_status"] == "Sin petición"
    assert row["request_id"] is None
