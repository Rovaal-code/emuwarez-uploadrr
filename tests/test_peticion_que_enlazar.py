"""La petición que se enlaza sin que nadie la elija (un lote desde Biblioteca): requests.peticion_que_enlazar.

Las mismas reglas que el Panel y la ficha: solo un cruce «Compatible», la petición va a la fila que pide de verdad
(`_scoped_library_id`) o a una temporada o serie de la que cuelga y la cubre (`_cubre`), gana la más cercana, y si
hay dos igual de cercanas no se enlaza ninguna.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.requests import peticion_que_enlazar


@pytest.fixture
def conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    c = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(c)
    yield c
    c.close()


def _fila(conn, item_type, title, *, parent_id=None, season=None, episode=None):
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, parent_id,
                                      season_number, episode_number, updated_at)
           VALUES (?, ?, 'Disponible', 'Sin petición', 'N/A', ?, ?, ?, CURRENT_TIMESTAMP)""",
        (item_type, title, parent_id, season, episode))
    return int(cur.lastrowid)


def _peticion(conn, emu_id, cruce, *, estado="Compatible", confianza=0.9, scope=None, season=None, episode=None):
    """Una petición guardada y su cruce con la fila `cruce` (la que encontró el emparejador)."""
    from emuwarez_uploadrr.models import RequestItem
    from emuwarez_uploadrr.services.requests import upsert_request
    rid = upsert_request(conn, RequestItem(
        id=None, emu_id=emu_id, title=f"Petición {emu_id}", emu_status="Sin llenar", req_scope=scope,
        req_season=season, req_episode=episode))
    conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status, confidence) "
                 "VALUES (?, ?, ?, ?)", (cruce, rid, estado, confianza))
    conn.commit()
    return rid


@pytest.fixture
def serie(conn):
    s = _fila(conn, "series", "Serie")
    t1 = _fila(conn, "season", "T1", parent_id=s, season=1)
    t2 = _fila(conn, "season", "T2", parent_id=s, season=2)
    e1 = _fila(conn, "episode", "E1", parent_id=t1, season=1, episode=1)
    e2 = _fila(conn, "episode", "E2", parent_id=t1, season=1, episode=2)
    conn.commit()
    return {"serie": s, "t1": t1, "t2": t2, "e1": e1, "e2": e2}


def test_una_pelicula_con_su_peticion_compatible(conn):
    peli = _fila(conn, "movie", "Dune")
    rid = _peticion(conn, "1", peli)
    assert peticion_que_enlazar(conn, peli) == rid


def test_sin_peticion_o_sin_cruce_compatible_no_enlaza(conn):
    peli = _fila(conn, "movie", "Dune")
    assert peticion_que_enlazar(conn, peli) is None
    _peticion(conn, "1", peli, estado="No compatible")
    _peticion(conn, "2", peli, estado="Parcial")
    assert peticion_que_enlazar(conn, peli) is None
    assert peticion_que_enlazar(conn, 999999) is None


def test_dos_peticiones_compatibles_de_la_misma_pelicula_es_ambiguo(conn):
    peli = _fila(conn, "movie", "Dune")
    _peticion(conn, "1", peli)
    _peticion(conn, "2", peli)
    assert peticion_que_enlazar(conn, peli) is None


def test_la_compatible_gana_a_la_que_no_lo_es(conn):
    peli = _fila(conn, "movie", "Dune")
    _peticion(conn, "1", peli, estado="No compatible")
    rid = _peticion(conn, "2", peli)
    assert peticion_que_enlazar(conn, peli) == rid


def test_solo_cuenta_el_cruce_mas_seguro_de_cada_peticion(conn):
    """Como en el Panel: si el cruce más seguro de la petición es otra copia, esta no es la suya."""
    peli = _fila(conn, "movie", "Dune")
    otra = _fila(conn, "movie", "Dune 4K")
    rid = _peticion(conn, "1", otra, confianza=0.95)
    conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status, confidence) "
                 "VALUES (?, ?, 'Compatible', 0.5)", (peli, rid))
    conn.commit()
    assert peticion_que_enlazar(conn, peli) is None
    assert peticion_que_enlazar(conn, otra) == rid


def test_una_temporada_con_la_peticion_de_esa_temporada(conn, serie):
    rid = _peticion(conn, "1", serie["serie"], scope="season", season=1)
    assert peticion_que_enlazar(conn, serie["t1"]) == rid
    assert peticion_que_enlazar(conn, serie["t2"]) is None  # pide otra temporada


def test_la_peticion_de_la_serie_entera_cubre_cada_temporada(conn, serie):
    rid = _peticion(conn, "1", serie["serie"])
    assert peticion_que_enlazar(conn, serie["t1"]) == rid
    assert peticion_que_enlazar(conn, serie["t2"]) == rid


def test_gana_la_mas_cercana(conn, serie):
    entera = _peticion(conn, "1", serie["serie"])
    de_t1 = _peticion(conn, "2", serie["serie"], scope="season", season=1)
    assert peticion_que_enlazar(conn, serie["t1"]) == de_t1
    assert peticion_que_enlazar(conn, serie["t2"]) == entera


def test_dos_peticiones_de_la_misma_temporada_es_ambiguo(conn, serie):
    _peticion(conn, "1", serie["serie"], scope="season", season=1)
    _peticion(conn, "2", serie["serie"], scope="season", season=1)
    assert peticion_que_enlazar(conn, serie["t1"]) is None


def test_la_peticion_de_un_capitulo_no_va_al_pack(conn, serie):
    """La de un capítulo no la cubre un pack, ni siquiera si el capítulo no está y la petición cae en la temporada."""
    _peticion(conn, "1", serie["serie"], scope="episode", season=1, episode=1)
    _peticion(conn, "2", serie["serie"], scope="episode", season=1, episode=9)  # E9 no está: va a la temporada
    assert peticion_que_enlazar(conn, serie["t1"]) is None


def test_un_capitulo_con_la_suya_o_la_de_su_temporada(conn, serie):
    del_e1 = _peticion(conn, "1", serie["serie"], scope="episode", season=1, episode=1)
    de_t1 = _peticion(conn, "2", serie["serie"], scope="season", season=1)
    assert peticion_que_enlazar(conn, serie["e1"]) == del_e1
    assert peticion_que_enlazar(conn, serie["e2"]) == de_t1


def test_la_peticion_de_una_temporada_que_no_esta_no_cubre_las_demas(conn, serie):
    """Sin la fila de la T3, la petición va a la serie, pero pide la T3: no es de la T1."""
    _peticion(conn, "1", serie["serie"], scope="season", season=3)
    assert peticion_que_enlazar(conn, serie["t1"]) is None
