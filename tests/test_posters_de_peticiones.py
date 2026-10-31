"""Las peticiones que no casan con nada de la biblioteca traen el póster de TMDb.

Nada aquí habla con TMDb: `request_json` del cliente se sustituye por lo que respondería."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations import tmdb
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.models import RequestItem
from emuwarez_uploadrr.services import requests as reqs
from emuwarez_uploadrr.services.settings import set_setting

IMG = "https://image.tmdb.org/t/p/original"


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    set_setting(conn, "tmdb.api_key", "clave")
    return conn


@pytest.fixture
def tmdb_falso(monkeypatch):
    """Responde según la ruta pedida; `respuestas` se rellena en cada test. Guarda las rutas pedidas."""
    estado = {"pedidas": [], "respuestas": {}}

    def falso(method, url, **kw):
        ruta = url.split("api.themoviedb.org/3")[1].split("?")[0]
        estado["pedidas"].append(ruta)
        respuesta = estado["respuestas"].get(ruta, {})
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(tmdb, "request_json", falso)
    return estado


def _peticion(conn, emu_id, category="Películas", tmdb_id=None, imdb_id=None, scope=None):
    return reqs.upsert_request(conn, RequestItem(id=None, emu_id=emu_id, title=f"Petición {emu_id}", category=category,
                                                 tmdb_id=tmdb_id, imdb_id=imdb_id, req_scope=scope,
                                                 req_season=1 if scope else None))


def _poster(conn, rid):
    return reqs.get_request_detail(conn, rid)["poster_url"]


def test_una_peticion_sin_cruce_trae_el_poster_de_tmdb(db_conn, tmdb_falso):
    rid = _peticion(db_conn, "1", tmdb_id="603")
    serie = _peticion(db_conn, "2", category="Series", tmdb_id="1399", scope="season")
    tmdb_falso["respuestas"] = {"/movie/603": {"poster_path": "/matrix.jpg", "backdrop_path": "/fondo.jpg"},
                                "/tv/1399": {"poster_path": "/got.jpg"}}

    assert reqs.rellenar_posters(db_conn) == 2
    assert _poster(db_conn, rid) == IMG + "/matrix.jpg"
    assert reqs.get_request_detail(db_conn, rid)["backdrop_url"] == IMG + "/fondo.jpg"
    assert _poster(db_conn, serie) == IMG + "/got.jpg"
    lista = {i["id"]: i["poster_url"] for i in reqs.list_request_items(db_conn)["items"]}
    assert lista == {rid: IMG + "/matrix.jpg", serie: IMG + "/got.jpg"}


def test_con_cruce_manda_el_poster_de_la_biblioteca_y_no_se_pide_a_tmdb(db_conn, tmdb_falso):
    rid = _peticion(db_conn, "1", tmdb_id="603")
    peli = db_conn.execute("INSERT INTO library_items (item_type, title, local_status, tmdb_id, poster_url) "
                           "VALUES ('movie', 'Matrix', 'Disponible', '603', 'http://radarr/matrix.jpg')").lastrowid
    db_conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status, confidence) "
                    "VALUES (?, ?, 'Compatible', 1.0)", (peli, rid))
    db_conn.commit()

    assert reqs.rellenar_posters(db_conn) == 0
    assert tmdb_falso["pedidas"] == []
    assert _poster(db_conn, rid) == "http://radarr/matrix.jpg"
    assert reqs.list_request_items(db_conn)["items"][0]["poster_url"] == "http://radarr/matrix.jpg"


def test_un_documental_sin_temporada_se_busca_por_imdb(db_conn, tmdb_falso):
    """TMDb numera aparte películas y series: con el tmdb de un documental se podría coger el póster de otra cosa."""
    rid = _peticion(db_conn, "1", category="Documentales", tmdb_id="77", imdb_id="tt0000077")
    sin_imdb = _peticion(db_conn, "2", category="Documentales", tmdb_id="78")
    tmdb_falso["respuestas"] = {"/find/tt0000077": {"movie_results": [], "tv_results": [{"poster_path": "/doc.jpg"}]}}

    reqs.rellenar_posters(db_conn)
    assert tmdb_falso["pedidas"] == ["/find/tt0000077"]
    assert _poster(db_conn, rid) == IMG + "/doc.jpg"
    assert _poster(db_conn, sin_imdb) is None


def test_sin_poster_en_tmdb_se_apunta_y_no_se_vuelve_a_pedir(db_conn, tmdb_falso):
    rid = _peticion(db_conn, "1", tmdb_id="603")
    no_existe = _peticion(db_conn, "2", tmdb_id="999")
    tmdb_falso["respuestas"] = {"/movie/603": {"poster_path": None},
                                "/movie/999": IntegrationError("no existe", status=404)}

    assert reqs.rellenar_posters(db_conn) == 0
    reqs.rellenar_posters(db_conn)
    assert tmdb_falso["pedidas"] == ["/movie/603", "/movie/999"]
    assert _poster(db_conn, rid) is None and _poster(db_conn, no_existe) is None


def test_si_tmdb_falla_no_se_guarda_y_se_para_al_tercer_fallo(db_conn, tmdb_falso):
    ids = [_peticion(db_conn, str(i), tmdb_id=str(100 + i)) for i in range(5)]
    tmdb_falso["respuestas"] = {f"/movie/{100 + i}": IntegrationError("caído", status=503) for i in range(5)}

    assert reqs.rellenar_posters(db_conn) == 0
    assert len(tmdb_falso["pedidas"]) == 3
    assert all(db_conn.execute("SELECT tmdb_poster_url FROM request_items WHERE id = ?", (i,)).fetchone()[0] is None
               for i in ids)


def test_mientras_espera_a_tmdb_no_bloquea_la_base_de_datos(db_conn, isolated_db, monkeypatch):
    """La primera vez son unos 300 pósters: con la base de datos bloqueada hasta el final, lo que escribiera a la vez
    (una subida) fallaría con «database is locked»."""
    from emuwarez_uploadrr.database import connect
    ids = [_peticion(db_conn, str(i), tmdb_id=str(100 + i)) for i in range(2)]
    otra = connect(isolated_db / "emuwarez_uploadrr.db")
    otra.execute("PRAGMA busy_timeout = 0")

    def escribe_a_la_vez(method, url, **kw):
        otra.execute("UPDATE request_items SET title = 'cambiado' WHERE id = ?", (ids[0],))
        otra.commit()
        return {"poster_path": "/p.jpg"}

    monkeypatch.setattr(tmdb, "request_json", escribe_a_la_vez)
    assert reqs.rellenar_posters(db_conn) == 2
    otra.close()


def test_sin_clave_de_tmdb_no_se_pide_nada(db_conn, tmdb_falso):
    set_setting(db_conn, "tmdb.api_key", "")
    _peticion(db_conn, "1", tmdb_id="603")
    assert reqs.rellenar_posters(db_conn) == 0
    assert tmdb_falso["pedidas"] == []


def test_la_sincronizacion_trae_los_posters(db_conn, tmdb_falso, monkeypatch):
    set_setting(db_conn, "emu.api_key", "clave-emu")
    fila = {"id": 1, "name": "Matrix", "category_id": 1, "tmdb": 603, "status": "unfilled",
            "created": "2025-01-01T00:00:00+00:00"}
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: ([fila], 1))
    tmdb_falso["respuestas"] = {"/movie/603": {"poster_path": "/matrix.jpg"}}

    assert reqs.sync_emu_requests(db_conn, force=True)["status"] == "ok"
    assert reqs.list_request_items(db_conn)["items"][0]["poster_url"] == IMG + "/matrix.jpg"
