"""Tests for emuwarez_uploadrr/integrations/emu.py: las peticiones reales de eMuwarez."""
from __future__ import annotations

import json
import pytest

from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.emu import (
    normalize_request,
    normalize_requests,
    EMU_BASE_URL,
)
from emuwarez_uploadrr.models import RequestItem


# Una fila tal como la devuelve /api/requests/filter (plana, con ids numéricos).
FILA = {
    "id": 1234, "name": "Dune", "description": "[b]texto[/b]",
    "category_id": 2, "type_id": 4, "resolution_id": 10,
    "user": "Nocturno", "tmdb": 1032, "imdb": 440981, "tvdb": None, "mal": None, "igdb": None,
    "bounty": "100.00", "status": "filled", "claimed": None, "filled_by": 77,
    "created": "2025-01-02T23:41:34+00:00", "updated_at": "2025-01-03T10:00:00+00:00",
}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_emu_base_url():
    assert EMU_BASE_URL == "https://emu-warez.com"


# ---------------------------------------------------------------------------
# normalize_request
# ---------------------------------------------------------------------------

def test_normalize_request_con_la_respuesta_real():
    item = normalize_request(FILA)
    assert isinstance(item, RequestItem)
    assert item.emu_id == "1234"
    assert item.title == "Dune"
    assert item.category == "Series"
    assert item.requested_source == "WEB-DL"
    assert item.requested_resolution == "Otras"
    assert item.emu_status == "filled"
    assert item.points == 100
    assert item.created_at == "2025-01-02T23:41:34+00:00"
    assert (item.tmdb_id, item.imdb_id, item.tvdb_id, item.mal_id) == ("1032", "tt0440981", None, None)
    assert item.url == f"{EMU_BASE_URL}/requests/1234"
    assert (item.author, item.author_visible) == ("Nocturno", True)
    assert (item.req_scope, item.req_season, item.req_episode) == (None, None, None)
    assert json.loads(item.raw_json) == FILA


@pytest.mark.parametrize("id_, nombre", [(1, "Películas"), (2, "Series"), (4, "Documentales")])
def test_categorias(id_, nombre):
    assert normalize_request({**FILA, "category_id": id_}).category == nombre


@pytest.mark.parametrize("id_, nombre", [
    (1, "Full Disc"), (2, "Remux"), (3, "Encode"), (4, "WEB-DL"),
    (5, "WEBRIP"), (6, "HDTV"), (7, "SD"), (8, "STEAMRIP"),
])
def test_tipos(id_, nombre):
    assert normalize_request({**FILA, "type_id": id_}).requested_source == nombre


@pytest.mark.parametrize("id_, nombre", [
    (1, "4320p"), (2, "2160p"), (3, "1080p"), (4, "1080i"), (5, "720p"),
    (6, "576p"), (7, "540p"), (8, "480p"), (10, "Otras"),
])
def test_resoluciones(id_, nombre):
    assert normalize_request({**FILA, "resolution_id": id_}).requested_resolution == nombre


def test_sin_resolucion_o_con_ids_desconocidos_no_hay_restriccion():
    """resolution_id falta cuando la petición no pide ninguna; un id nuevo del tracker tampoco rompe nada."""
    fila = {k: v for k, v in FILA.items() if k != "resolution_id"}
    assert normalize_request(fila).requested_resolution is None
    item = normalize_request({**FILA, "category_id": 99, "type_id": 99, "resolution_id": 99})
    assert (item.category, item.requested_source, item.requested_resolution) == (None, None, None)


def test_el_autor_anonimo_no_se_guarda():
    item = normalize_request({**FILA, "user": "anonymous"})
    assert (item.author, item.author_visible) == (None, False)
    item = normalize_request({k: v for k, v in FILA.items() if k != "user"})
    assert (item.author, item.author_visible) == (None, False)


@pytest.mark.parametrize("bounty, puntos", [("15000.00", 15000), ("100.00", 100), (250, 250), (None, None), ("x", None)])
def test_el_bounty_pasa_a_puntos_enteros(bounty, puntos):
    assert normalize_request({**FILA, "bounty": bounty}).points == puntos


def test_ids_externos():
    item = normalize_request({**FILA, "tmdb": 0, "tvdb": 81189, "mal": 0, "imdb": 0})
    assert (item.tmdb_id, item.tvdb_id, item.mal_id, item.imdb_id) == (None, "81189", None, None)
    assert normalize_request({**FILA, "imdb": None}).imdb_id is None
    # Siete cifras como mínimo, y las de ocho se quedan como son.
    assert normalize_request({**FILA, "imdb": 133093}).imdb_id == "tt0133093"
    assert normalize_request({**FILA, "imdb": 10872600}).imdb_id == "tt10872600"


def test_temporada_y_capitulo_dan_el_alcance():
    assert [normalize_request({**FILA, **extra}).req_scope for extra in (
        {}, {"season_number": 2}, {"season_number": 2, "episode_number": 5},
    )] == [None, "season", "episode"]
    item = normalize_request({**FILA, "season_number": 2, "episode_number": 5})
    assert (item.req_season, item.req_episode) == (2, 5)
    # Un capítulo 0 no es un capítulo: es la temporada entera.
    assert normalize_request({**FILA, "season_number": 2, "episode_number": 0}).req_scope == "season"


def test_temporada_0_sin_capitulo_es_la_serie_entera():
    """UNIT3D guarda 0 para «sin temporada»: leerlo como Especiales mandaba toda petición de serie a la T0."""
    item = normalize_request({**FILA, "season_number": 0})
    assert (item.req_scope, item.req_season, item.req_episode) == (None, None, None)
    item = normalize_request({**FILA, "season_number": 0, "episode_number": 0})
    assert (item.req_scope, item.req_season) == (None, None)


@pytest.mark.parametrize("nombre", ["Los Simpson - Especiales", "Doctor Who Specials", "Sherlock (specials)"])
def test_temporada_0_con_especiales_en_el_nombre_si_son_los_especiales(nombre):
    item = normalize_request({**FILA, "name": nombre, "season_number": 0})
    assert (item.req_scope, item.req_season) == ("season", 0)


def test_un_capitulo_de_la_temporada_0_sigue_siendo_un_capitulo():
    item = normalize_request({**FILA, "season_number": 0, "episode_number": 3})
    assert (item.req_scope, item.req_season, item.req_episode) == ("episode", 0, 3)


def test_una_fila_sin_casi_nada_no_falla():
    item = normalize_request({"id": 7})
    assert (item.emu_id, item.title, item.url) == ("7", "Sin título", f"{EMU_BASE_URL}/requests/7")
    assert normalize_request({}).title == "Sin título"


# ---------------------------------------------------------------------------
# normalize_requests
# ---------------------------------------------------------------------------

def test_normalize_requests_se_salta_lo_que_no_es_una_fila_con_id():
    raw = [{"id": 1, "name": "Movie 1"}, "not a dict", None, {"name": "sin id"}, {"id": 2, "name": "Movie 2"}]
    assert [i.title for i in normalize_requests(raw)] == ["Movie 1", "Movie 2"]


def test_normalize_requests_empty():
    assert normalize_requests([]) == []


# ---------------------------------------------------------------------------
# sync_emu_requests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _con_clave(conn, clave="configured-key-123"):
    from emuwarez_uploadrr.services.settings import set_setting
    set_setting(conn, "emu.api_key", clave)


@pytest.fixture
def sin_cruce(monkeypatch):
    """Estas pruebas son de lo que se importa, no de cruzarlo con la biblioteca."""
    from emuwarez_uploadrr.services import requests as reqs
    monkeypatch.setattr(reqs, "match_all_requests", lambda conn: 0)


def test_sync_requests_reads_key_from_db_settings(db_conn, monkeypatch, sin_cruce):
    """The key configured in the Settings UI (settings.emu.api_key) must be
    used — regression for the task reporting 'No hay API Key' when it was set."""
    from emuwarez_uploadrr.services import requests as reqs
    _con_clave(db_conn)

    seen = {}
    def fake_fetch(api_key, *a, **kw):
        seen["key"] = api_key
        return [], 0
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", fake_fetch)

    result = reqs.sync_emu_requests(db_conn, force=True)
    assert seen["key"] == "configured-key-123"
    assert result["status"] == "ok"


def test_la_sync_guarda_las_filas_reales_de_una_vez(db_conn, monkeypatch, sin_cruce):
    from emuwarez_uploadrr.services import requests as reqs
    _con_clave(db_conn)
    filas = [FILA, {**FILA, "id": 1235, "name": "Los Tudor", "category_id": 2, "season_number": 2,
                    "user": "anonymous", "tmdb": 0}]
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: (filas, 2))
    vistas = []
    db_conn.set_trace_callback(vistas.append)

    result = reqs.sync_emu_requests(db_conn, force=True)
    db_conn.set_trace_callback(None)

    assert result["status"] == "ok" and result["imported"] == 2
    rows = {r["emu_id"]: dict(r) for r in db_conn.execute("SELECT * FROM request_items")}
    dune, tudor = rows["1234"], rows["1235"]
    assert (dune["title"], dune["category"], dune["points"], dune["author"], dune["author_visible"]) == (
        "Dune", "Series", 100, "Nocturno", 1)
    assert (tudor["req_scope"], tudor["req_season"], tudor["req_episode"]) == ("season", 2, None)
    assert (tudor["author"], tudor["author_visible"], tudor["tmdb_id"]) == (None, 0, None)
    # Un solo COMMIT para todos los upserts, no uno por fila.
    inserts = [i for i, s in enumerate(vistas) if s.lstrip().startswith("INSERT INTO request_items")]
    assert len(inserts) == 2 and "COMMIT" not in vistas[inserts[0]:inserts[-1] + 1]


def test_volver_a_sincronizar_actualiza_el_alcance_y_el_autor(db_conn, monkeypatch, sin_cruce):
    from emuwarez_uploadrr.services import requests as reqs
    _con_clave(db_conn)
    respuestas = [[FILA], [{**FILA, "season_number": 3, "user": "anonymous"}]]
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: (respuestas.pop(0), 1))

    reqs.sync_emu_requests(db_conn, force=True)
    reqs.sync_emu_requests(db_conn, force=True)

    fila = dict(db_conn.execute("SELECT * FROM request_items").fetchone())
    assert (fila["req_scope"], fila["req_season"], fila["author"], fila["author_visible"]) == ("season", 3, None, 0)


def test_si_el_recorrido_falla_no_se_toca_nada_y_se_devuelve_el_turno(db_conn, monkeypatch, sin_cruce):
    from emuwarez_uploadrr.database import get_state
    from emuwarez_uploadrr.integrations.base import IntegrationError
    from emuwarez_uploadrr.services import requests as reqs
    _con_clave(db_conn)
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: ([FILA], 1))
    reqs.sync_emu_requests(db_conn, force=True)
    antes = get_state(db_conn, reqs.SYNC_STATE_KEY)

    def roto(*a, **kw):
        raise IntegrationError("eMuwarez ha limitado las peticiones; prueba en unos minutos", status=429)
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", roto)
    with pytest.raises(IntegrationError):
        reqs.sync_emu_requests(db_conn, force=True)

    assert db_conn.execute("SELECT COUNT(*) FROM request_items").fetchone()[0] == 1
    assert get_state(db_conn, reqs.SYNC_STATE_KEY) == antes
    row = db_conn.execute(
        "SELECT status, summary FROM task_runs WHERE name='sync-emu-requests' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (row["status"], row["summary"]) == ("failed", "eMuwarez ha limitado las peticiones; prueba en unos minutos")


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


def test_una_temporada_que_no_tienes_no_sale_compatible(db_conn):
    """La petición de la Temporada 3 casa con la serie; si la serie estaba «Disponible», salía «Compatible»."""
    from emuwarez_uploadrr.services.requests import match_all_requests, upsert_request
    from emuwarez_uploadrr.models import RequestItem
    serie = db_conn.execute("INSERT INTO library_items(item_type,title,year,local_status,tmdb_id) "
                            "VALUES ('series','Serie',2019,'Disponible','555')").lastrowid
    temporada = db_conn.execute("INSERT INTO library_items(item_type,title,local_status,parent_id,season_number) "
                                "VALUES ('season','Serie - Temporada 1','Disponible',?,1)", (serie,)).lastrowid
    db_conn.execute("INSERT INTO library_items(item_type,title,local_status,parent_id,season_number,episode_number,"
                    "resolution,source) VALUES ('episode','Serie S01E01','Disponible',?,1,1,'1080p','WEB-DL')",
                    (temporada,))
    db_conn.commit()
    upsert_request(db_conn, RequestItem(id=None, emu_id="req-t3", title="Serie", category="TV", tmdb_id="555"))
    db_conn.execute("UPDATE request_items SET req_scope='season', req_season=3")
    db_conn.commit()

    match_all_requests(db_conn)
    assert db_conn.execute("SELECT status FROM request_matches").fetchone()["status"] == "No disponible"


def test_una_peticion_de_serie_con_temporada_0_se_cruza_con_la_serie_y_no_con_los_especiales(db_conn):
    """F3: la serie completa tiene su fila de Especiales y la petición de toda la serie (season_number 0) caía allí."""
    from emuwarez_uploadrr.services.requests import match_all_requests, upsert_request
    serie = db_conn.execute("INSERT INTO library_items(item_type,title,year,local_status,tmdb_id) "
                            "VALUES ('series','Serie',2019,'Disponible','77')").lastrowid
    ids = {}
    for n in (0, 1):
        ids[n] = db_conn.execute(
            "INSERT INTO library_items(item_type,title,local_status,parent_id,season_number,tmdb_id) "
            "VALUES ('season','T','Disponible',?,?,'77')", (serie, n)).lastrowid
        db_conn.execute("INSERT INTO library_items(item_type,title,local_status,parent_id,season_number,"
                        "episode_number,resolution,source) VALUES ('episode','E','Disponible',?,?,1,'1080p','WEB-DL')",
                        (ids[n], n))
    db_conn.commit()
    upsert_request(db_conn, emu.normalize_request(
        {**FILA, "id": 77, "name": "Serie", "category_id": 2, "tmdb": 77, "status": "unfilled", "resolution_id": 3,
         "type_id": 4, "season_number": 0}))

    match_all_requests(db_conn)

    fila = db_conn.execute("SELECT library_item_id, status FROM request_matches").fetchone()
    assert (fila["library_item_id"], fila["status"]) == (serie, "Compatible")
    estado = lambda i: db_conn.execute("SELECT request_status FROM library_items WHERE id = ?", (i,)).fetchone()[0]
    assert (estado(serie), estado(ids[0]), estado(ids[1])) == ("Compatible", "Sin petición", "Sin petición")


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


def test_con_dos_instancias_gana_la_copia_que_atiende_la_peticion(db_conn):
    """Con Radarr y Radarr 4K la película sale dos veces con el mismo tmdb y ganaba la primera de la tabla: una
    petición de 2160p quedaba «Parcial» contra la copia de 1080p aunque la de 4K la atendiera."""
    from emuwarez_uploadrr.services.requests import match_all_requests, match_single_request, upsert_request
    from emuwarez_uploadrr.models import RequestItem
    fila = ("INSERT INTO library_items(item_type,title,local_status,tmdb_id,resolution,source) "
            "VALUES ('movie','Dune','Disponible','438631',?,'WEB-DL')")
    db_conn.execute(fila, ("1080p",))
    cuatro_k = db_conn.execute(fila, ("2160p",)).lastrowid
    db_conn.commit()
    rid = upsert_request(db_conn, RequestItem(id=None, emu_id="dune-4k", title="Dune", category="Películas",
                                              tmdb_id="438631", requested_resolution="2160p"))

    match_all_requests(db_conn)
    casamiento = lambda: tuple(db_conn.execute("SELECT library_item_id, status FROM request_matches").fetchone())
    assert casamiento() == (cuatro_k, "Compatible")
    match_single_request(db_conn, rid)
    assert casamiento() == (cuatro_k, "Compatible")


def test_la_temporada_pedida_compite_con_la_serie(db_conn):
    """La serie va primero, pero si no tiene la temporada pedida y la fila de esa temporada sí la atiende, gana la
    temporada: antes solo competían las series entre sí."""
    from emuwarez_uploadrr.services.requests import match_all_requests, upsert_request
    from emuwarez_uploadrr.models import RequestItem
    db_conn.execute("INSERT INTO library_items(item_type,title,local_status,tmdb_id) "
                    "VALUES ('series','Serie','Disponible','77')")
    temporada = db_conn.execute(
        "INSERT INTO library_items(item_type,title,local_status,tmdb_id,season_number,resolution,source) "
        "VALUES ('season','Serie - Temporada 2','Disponible','77',2,'1080p','WEB-DL')").lastrowid
    db_conn.commit()
    upsert_request(db_conn, RequestItem(id=None, emu_id="t2", title="Serie", category="Series", tmdb_id="77",
                                        req_scope="season", req_season=2))
    match_all_requests(db_conn)
    fila = db_conn.execute("SELECT library_item_id, status FROM request_matches").fetchone()
    assert (fila["library_item_id"], fila["status"]) == (temporada, "Compatible")


def test_un_capitulo_que_no_esta_no_sale_compatible_por_su_temporada(db_conn):
    """Con las temporadas compitiendo, una temporada «Disponible» sin el capítulo pedido salía «Compatible»."""
    from emuwarez_uploadrr.services.requests import match_all_requests, upsert_request
    from emuwarez_uploadrr.models import RequestItem
    db_conn.execute("INSERT INTO library_items(item_type,title,local_status,tmdb_id) "
                    "VALUES ('series','Serie','Disponible','77')")
    db_conn.execute("INSERT INTO library_items(item_type,title,local_status,tmdb_id,season_number,resolution,source) "
                    "VALUES ('season','Serie - Temporada 2','Disponible','77',2,'1080p','WEB-DL')")
    db_conn.commit()
    upsert_request(db_conn, RequestItem(id=None, emu_id="s2e5", title="Serie", category="Series", tmdb_id="77",
                                        req_scope="episode", req_season=2, req_episode=5))
    match_all_requests(db_conn)
    assert db_conn.execute("SELECT status FROM request_matches").fetchone()["status"] == "No disponible"


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


# ---------------------------------------------------------------------------
# Cruzar peticiones no llama a eMuwarez
# ---------------------------------------------------------------------------

def test_cruzar_peticiones_no_llama_a_emuwarez(db_conn, monkeypatch):
    """Cada petición sin cruce hacía una llamada en vivo a la API, sin pausa: con cientos de
    peticiones eran cientos de llamadas seguidas contra las 30 por minuto de la clave."""
    from emuwarez_uploadrr.services.requests import match_all_requests, match_single_request
    _con_clave(db_conn)
    llamadas = []
    monkeypatch.setattr(emu, "request_json", lambda *a, **kw: llamadas.append(a) or {})
    ids = [
        db_conn.execute(
            "INSERT INTO request_items(emu_id, title, tmdb_id, emu_status) VALUES (?, ?, ?, 'unfilled')",
            (f"x{i}", f"Sin cruce {i}", str(900 + i)),
        ).lastrowid
        for i in range(5)
    ]
    db_conn.commit()

    assert match_all_requests(db_conn) == 0
    assert all(match_single_request(db_conn, i) is None for i in ids)
    assert llamadas == []


def test_una_sync_entera_solo_pide_las_paginas_de_peticiones(db_conn, monkeypatch):
    """Con peticiones que no cruzan con nada, lo único que sale a la red son las páginas del listado."""
    import types
    from emuwarez_uploadrr.services import requests as reqs
    _con_clave(db_conn)
    paginas = [
        {"data": [{"id": i, "name": f"Peli {i}", "category_id": 1, "tmdb": 500 + i} for i in (1, 2)],
         "meta": {"last_page": 2, "total": 3}},
        {"data": [{"id": 3, "name": "Peli 3", "category_id": 1, "tmdb": 503}],
         "meta": {"last_page": 2, "total": 3}},
    ]
    pedidas = []
    monkeypatch.setattr(emu, "request_json", lambda method, url, **kw: pedidas.append(url) or paginas.pop(0))
    monkeypatch.setattr(emu, "time", types.SimpleNamespace(sleep=lambda s: None))

    result = reqs.sync_emu_requests(db_conn, force=True)

    assert (result["status"], result["imported"], result["matched"]) == ("ok", 3, 0)
    assert len(pedidas) == 2 and all("/api/requests/filter" in u for u in pedidas)
