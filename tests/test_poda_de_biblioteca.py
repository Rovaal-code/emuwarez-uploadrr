"""La sincronización de biblioteca borra lo que Radarr y Sonarr ya no tienen, pero solo tras un recorrido completo.

Nada aquí habla con Radarr ni con Sonarr: sus listados se sustituyen por lo que devolverían."""
from __future__ import annotations

import sqlite3

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.integrations import radarr, sonarr
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import library
from emuwarez_uploadrr.services.instances import get_instance, remove_instance

RADARR, RADARR_4K, SONARR = 1, 2, 3
URL = {RADARR: "http://radarr", RADARR_4K: "http://radarr-4k", SONARR: "http://sonarr"}


@pytest.fixture
def conn(isolated_db):
    c = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(c)
    for id_, tipo, nombre in ((RADARR, "radarr", "Radarr"), (RADARR_4K, "radarr", "Radarr 4K"), (SONARR, "sonarr", "Sonarr")):
        c.execute("INSERT INTO instances (id, type, name, url, api_key) VALUES (?, ?, ?, ?, 'clave')",
                  (id_, tipo, nombre, URL[id_]))
    c.commit()
    yield c
    c.close()


def _peli(id_, titulo, tmdb, calidad="WEB-DL-1080p"):
    return {"id": id_, "title": titulo, "year": 1999, "tmdbId": tmdb,
            "movieFile": {"id": id_, "path": f"/movies/{titulo}.mkv", "size": 1000,
                          "quality": {"quality": {"name": calidad}}}}


def _serie(id_):
    return {"id": id_, "title": f"Serie {id_}", "year": 2010, "tvdbId": id_ + 1000, "path": f"/tv/Serie {id_}"}


def _capitulo(serie, numero):
    return {"id": serie * 100 + numero, "seriesId": serie, "seasonNumber": 1, "episodeNumber": numero,
            "title": f"Capítulo {numero}", "hasFile": False, "episodeFileId": 0}


def _o_falla(valor):
    if isinstance(valor, Exception):
        raise valor
    return valor


@pytest.fixture
def arr(monkeypatch):
    """Lo que lista cada instancia: películas en Radarr y {serie: [capítulos]} en Sonarr. Una excepción hace fallar
    ese listado; en Sonarr, la de una serie falla al pedir sus capítulos."""
    listados: dict = {RADARR: [], RADARR_4K: [], SONARR: {}}
    de = {url: instancia for instancia, url in URL.items()}
    monkeypatch.setattr(radarr, "get_queue", lambda *a: [])
    monkeypatch.setattr(sonarr, "get_queue", lambda *a: [])
    monkeypatch.setattr(sonarr, "get_episode_files", lambda *a: [])
    monkeypatch.setattr(radarr, "get_movies", lambda url, _clave: _o_falla(listados[de[url]]))
    monkeypatch.setattr(sonarr, "get_series", lambda url, _clave: [_serie(s) for s in _o_falla(listados[de[url]])])
    monkeypatch.setattr(sonarr, "get_episodes", lambda url, _clave, s: [
        _capitulo(s, n) for n in _o_falla(listados[de[url]][s])])
    return listados


def _sincroniza(conn, instancia, **kw):
    return library.sync_instance(conn, get_instance(conn, instancia), **kw)


def _externos(conn, instancia):
    return {r[0] for r in conn.execute("SELECT external_id FROM library_items WHERE instance_id = ?", (instancia,))}


def _id(conn, instancia, externo):
    return conn.execute("SELECT id FROM library_items WHERE instance_id = ? AND external_id = ?",
                        (instancia, externo)).fetchone()[0]


def test_lo_que_radarr_ya_no_tiene_se_borra_con_lo_que_colgaba(conn, arr):
    arr[RADARR] = [_peli(1, "Matrix", 603), _peli(2, "Dune", 438631)]
    _sincroniza(conn, RADARR)
    matrix, dune = _id(conn, RADARR, "1"), _id(conn, RADARR, "2")
    peticion = conn.execute("INSERT INTO request_items (emu_id, title, tmdb_id) VALUES ('7', 'Matrix', '603')").lastrowid
    conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status) VALUES (?, ?, 'Compatible')",
                 (matrix, peticion))
    conn.execute("INSERT INTO request_candidates (request_item_id, library_item_id, candidate_rank, match_status)"
                 " VALUES (?, ?, 1, 'Compatible')", (peticion, matrix))
    for item in (matrix, dune):
        conn.execute("INSERT INTO nomenclature_proposals (library_item_id) VALUES (?)", (item,))
        conn.execute("INSERT INTO filesystem_operations (operation_type, library_item_id) VALUES ('rename', ?)", (item,))
        conn.execute("INSERT INTO operational_queue_items (queue_key, item_type, entity_type, library_item_id)"
                     " VALUES (?, 'library_recommendation', 'library_item', ?)", (f"library:{item}", item))
    subida = conn.execute("INSERT INTO upload_jobs (library_item_id, title, path, status)"
                          " VALUES (?, 'Matrix', '/movies/Matrix.mkv', 'completed')", (matrix,)).lastrowid
    conn.commit()

    arr[RADARR] = [_peli(2, "Dune", 438631)]
    _sincroniza(conn, RADARR)

    assert _externos(conn, RADARR) == {"2"}
    for tabla in ("request_matches", "request_candidates"):
        assert conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0, tabla
    for tabla in ("nomenclature_proposals", "filesystem_operations", "operational_queue_items"):
        assert [r[0] for r in conn.execute(f"SELECT library_item_id FROM {tabla}")] == [dune], tabla
    # La subida sigue en el historial, sin enlace a lo que ya no está.
    assert conn.execute("SELECT library_item_id FROM upload_jobs WHERE id = ?", (subida,)).fetchone()[0] is None


def test_una_serie_o_un_capitulo_que_sonarr_ya_no_tiene_se_borra(conn, arr):
    arr[SONARR] = {20: [1, 2], 30: [1]}
    _sincroniza(conn, SONARR, include_episodes=True)
    assert len(_externos(conn, SONARR)) == 7

    arr[SONARR] = {20: [1]}
    _sincroniza(conn, SONARR, include_episodes=True)

    # La serie 30 se va con su temporada y su capítulo; de la 20 solo el capítulo 2.
    assert _externos(conn, SONARR) == {"20", "season:20:1", "episode:2001"}


def test_sin_capitulos_solo_se_borran_las_series_que_ya_no_estan(conn, arr):
    """Sin capítulos no se recorren temporadas ni capítulos: no haberlos visto no dice que ya no estén."""
    arr[SONARR] = {20: [1, 2], 30: [1]}
    _sincroniza(conn, SONARR, include_episodes=True)

    arr[SONARR] = {20: [1]}
    _sincroniza(conn, SONARR, include_episodes=False)

    assert _externos(conn, SONARR) == {"20", "season:20:1", "episode:2001", "episode:2002"}


def test_una_instancia_que_falla_no_borra_nada_y_las_demas_si(conn, arr):
    arr[RADARR] = [_peli(1, "Matrix", 603), _peli(2, "Dune", 438631)]
    arr[RADARR_4K] = [_peli(3, "Matrix", 603, "WEB-DL-2160p")]
    arr[SONARR] = {20: [1, 2], 30: [1]}
    library.sync_all(conn, include_episodes=True)

    arr[RADARR] = IntegrationError("Radarr no responde")
    arr[RADARR_4K] = [_peli(4, "Dune", 438631, "WEB-DL-2160p")]
    # La serie 20 ha perdido un capítulo, pero la 30 falla: la que no falla se pone al día, la que falla se queda igual.
    arr[SONARR] = {20: [1], 30: IntegrationError("Sonarr no responde")}
    resultado = library.sync_all(conn, include_episodes=True)

    assert len(resultado["errors"]) == 2
    assert _externos(conn, RADARR) == {"1", "2"}
    assert _externos(conn, SONARR) == {"20", "season:20:1", "episode:2001", "30", "season:30:1", "episode:3001"}
    assert _externos(conn, RADARR_4K) == {"4"}


@pytest.mark.parametrize("listado", [
    lambda: radarr.get_movies(URL[RADARR], "clave"),
    lambda: sonarr.get_series(URL[SONARR], "clave"),
    lambda: sonarr.get_episodes(URL[SONARR], "clave", 20),
], ids=["películas", "series", "capítulos"])
@pytest.mark.parametrize("respuesta", [
    {}, {"message": "Unauthorized"}, None, [{"id": 1}, {"title": "Sin id"}], [{"id": 0}], [{"id": ""}], [{"id": True}],
])
def test_un_listado_raro_es_un_error_y_no_una_biblioteca_vacia(monkeypatch, listado, respuesta):
    """Devolvía [] y la sincronización, al no ver nada, habría borrado todo lo de la instancia. Las fichas sin id se
    guardaban todas en una sola fila («None»), que era lo único visto."""
    monkeypatch.setattr(radarr, "request_json", lambda *a, **kw: respuesta)
    monkeypatch.setattr(sonarr, "request_json", lambda *a, **kw: respuesta)
    with pytest.raises(IntegrationError):
        listado()


def test_la_peticion_pasa_a_casar_con_la_copia_que_queda(conn, arr):
    """La sincronización de peticiones es diaria: hasta entonces, la petición se quedaba sin cruce teniendo la de 4K."""
    from emuwarez_uploadrr.services.request_readiness import refresh_request_readiness
    from emuwarez_uploadrr.services.requests import match_all_requests
    arr[RADARR] = [_peli(1, "Matrix", 603), _peli(2, "Dune", 438631)]
    arr[RADARR_4K] = [_peli(3, "Matrix", 603, "WEB-DL-2160p")]
    library.sync_all(conn)
    # Casan igual de bien y desempata la más reciente: la de 4K, más antigua, para no depender del segundo en que se guardó.
    conn.execute("UPDATE library_items SET updated_at = '2000-01-01 00:00:00' WHERE instance_id = ?", (RADARR_4K,))
    conn.execute("INSERT INTO request_items (emu_id, title, tmdb_id, requested_resolution)"
                 " VALUES ('7', 'Matrix', '603', '1080p')")
    conn.commit()
    match_all_requests(conn)
    refresh_request_readiness(conn)
    cruce = lambda: conn.execute("SELECT library_item_id FROM request_matches").fetchone()[0]
    assert cruce() == _id(conn, RADARR, "1")

    arr[RADARR] = [_peli(2, "Dune", 438631)]
    _sincroniza(conn, RADARR)

    copia_4k = _id(conn, RADARR_4K, "3")
    assert cruce() == copia_4k
    assert conn.execute("SELECT readiness_best_library_item_id FROM request_items").fetchone()[0] == copia_4k


def test_la_peticion_que_se_queda_sin_cruce_trae_el_poster_de_tmdb(conn, arr, monkeypatch):
    """El póster de la biblioteca se va con la película, y el de TMDb solo lo pedía la sincronización de peticiones.
    Se pide solo el suyo: tras actualizar, todas las que no casan esperan aún el primero, una llamada a TMDb cada una."""
    from emuwarez_uploadrr.integrations import tmdb
    from emuwarez_uploadrr.services.requests import get_request_detail, match_all_requests
    from emuwarez_uploadrr.services.settings import set_setting
    set_setting(conn, "tmdb.api_key", "clave")
    monkeypatch.setattr(tmdb, "request_json",
                        lambda _m, url, **kw: {"poster_path": "/matrix.jpg"} if "/movie/603?" in url else {})
    arr[RADARR] = [_peli(1, "Matrix", 603), _peli(2, "Dune", 438631)]
    _sincroniza(conn, RADARR)
    peticion, otra = (conn.execute("INSERT INTO request_items (emu_id, title, tmdb_id, category)"
                                   " VALUES (?, ?, ?, 'Películas')", fila).lastrowid
                      for fila in (("7", "Matrix", "603"), ("8", "Otra que no casa", "999")))
    conn.commit()
    match_all_requests(conn)

    arr[RADARR] = [_peli(2, "Dune", 438631)]
    _sincroniza(conn, RADARR)

    assert get_request_detail(conn, peticion)["poster_url"] == "https://image.tmdb.org/t/p/original/matrix.jpg"
    assert conn.execute("SELECT tmdb_poster_url FROM request_items WHERE id = ?", (otra,)).fetchone()[0] is None


def test_la_subida_sigue_ensenando_lo_que_tenia_de_la_ficha(conn, arr, client, auth_headers):
    """Subidas sacaba el póster, el año y el Origen de la ficha: al borrarla, la subida se quedaba sin ellos."""
    peli = _peli(1, "Matrix", 603)
    peli["images"] = [{"coverType": "poster", "remoteUrl": "https://image.tmdb.org/t/p/original/matrix.jpg"},
                      {"coverType": "fanart", "remoteUrl": "https://image.tmdb.org/t/p/original/fondo.jpg"}]
    arr[RADARR] = [peli]
    _sincroniza(conn, RADARR)
    subida = conn.execute("INSERT INTO upload_jobs (library_item_id, title, path, status)"
                          " VALUES (?, 'Matrix', '/movies/Matrix.mkv', 'completed')", (_id(conn, RADARR, "1"),)).lastrowid
    conn.commit()
    antes = client.get(f"/api/uploads/{subida}", headers=auth_headers).json()
    assert antes["instance_id"] == RADARR

    arr[RADARR] = [_peli(2, "Dune", 438631)]
    _sincroniza(conn, RADARR)

    for despues in (client.get(f"/api/uploads/{subida}", headers=auth_headers).json(),
                    client.get("/api/uploads", headers=auth_headers).json()[0]):
        assert despues["library_item_id"] is None
        for campo in ("media_type", "poster_url", "backdrop_url", "year", "instance_type", "instance_name"):
            assert antes[campo] is not None and despues[campo] == antes[campo], campo
        # El enlace a Radarr llevaría a una ficha que ya no existe.
        assert despues["instance_id"] is None


def test_tambien_se_vuelve_a_cruzar_la_peticion_que_llevaba_su_estado_en_lo_borrado(conn):
    """Una petición de temporada casa con la serie y lleva su estado en la temporada: si solo se va la temporada, ni su
    cruce ni sus candidatos están en lo borrado, y se quedaba sin volver a cruzar."""
    from emuwarez_uploadrr.database import borrar_biblioteca
    peticion = conn.execute("INSERT INTO request_items (emu_id, title) VALUES ('7', 'Serie 20')").lastrowid
    serie = conn.execute("INSERT INTO library_items (item_type, title, instance_id, external_id, local_status)"
                         " VALUES ('series', 'Serie 20', ?, '20', 'Disponible')", (SONARR,)).lastrowid
    temporada = conn.execute(
        "INSERT INTO library_items (item_type, title, instance_id, external_id, local_status, parent_id, request_id,"
        " request_status) VALUES ('season', 'Serie 20', ?, 'season:20:1', 'Disponible', ?, ?, 'Compatible')",
        (SONARR, serie, peticion)).lastrowid
    conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status) VALUES (?, ?, 'Compatible')",
                 (serie, peticion))

    assert borrar_biblioteca(conn, "id = ?", (temporada,)) == (1, [peticion])


def test_lo_que_no_vino_de_la_sincronizacion_tambien_se_borra(conn, arr):
    """Una fila sin last_seen_at (de antes de existir la columna) que un recorrido completo no ve ya no está."""
    conn.execute("INSERT INTO library_items (item_type, title, instance_id, external_id, local_status)"
                 " VALUES ('movie', 'Borrada hace meses', ?, '9', 'Disponible')", (RADARR,))
    conn.commit()

    arr[RADARR] = [_peli(1, "Matrix", 603)]
    _sincroniza(conn, RADARR)

    assert _externos(conn, RADARR) == {"1"}


def test_borrar_una_instancia_borra_lo_que_se_sincronizo_de_ella(conn, arr):
    arr[RADARR] = [_peli(1, "Matrix", 603)]
    arr[SONARR] = {20: [1, 2]}
    library.sync_all(conn, include_episodes=True)
    subida = conn.execute("INSERT INTO upload_jobs (library_item_id, title, path, status)"
                          " VALUES (?, 'Serie 20', '/tv/Serie 20', 'completed')", (_id(conn, SONARR, "episode:2001"),)).lastrowid
    conn.commit()

    assert remove_instance(conn, SONARR)

    assert _externos(conn, SONARR) == set()
    assert _externos(conn, RADARR) == {"1"}
    assert conn.execute("SELECT library_item_id FROM upload_jobs WHERE id = ?", (subida,)).fetchone()[0] is None


def test_no_se_borra_una_instancia_mientras_hay_una_sincronizacion(conn, arr, client, auth_headers, monkeypatch):
    """La sincronización en marcha (la programada ya tiene su lista de instancias) volvería a escribir lo suyo, y ya
    nada lo borraría."""
    arr[RADARR] = [_peli(1, "Matrix", 603)]
    _sincroniza(conn, RADARR)
    monkeypatch.setitem(library._LIB_SYNC_PROGRESS, "active", True)

    assert client.delete(f"/api/instances/{RADARR}", headers=auth_headers).status_code == 429
    assert get_instance(conn, RADARR) is not None and _externos(conn, RADARR) == {"1"}


def test_la_instancia_que_se_borra_mientras_su_sincronizacion_espera_no_se_sincroniza(
        conn, arr, client, auth_headers, monkeypatch, isolated_db):
    """Se buscaba antes de esperar el candado: si se borraba entretanto, la sincronización volvía a escribir lo suyo."""
    from contextlib import contextmanager
    candado = library.sync._lib_sync_guard

    @contextmanager
    def se_borra_mientras_espera():
        otra = connect(isolated_db / "emuwarez_uploadrr.db")  # en el hilo del servidor, no en el del test
        otra.execute("DELETE FROM instances WHERE id = ?", (RADARR,))
        otra.commit()
        otra.close()
        with candado():
            yield

    monkeypatch.setattr(library.sync, "_LIB_SYNC_PROGRESS", dict(library.sync._LIB_SYNC_PROGRESS))
    monkeypatch.setattr(library.sync, "_lib_sync_guard", se_borra_mientras_espera)
    arr[RADARR] = [_peli(1, "Matrix", 603)]

    assert client.post(f"/api/instances/{RADARR}/sync", headers=auth_headers).status_code == 404
    assert _externos(conn, RADARR) == set()


def _migra(conn):
    conn.execute("DELETE FROM app_state WHERE key = 'schema_version'")
    conn.commit()
    init_db(conn)


def test_una_base_de_datos_anterior_recibe_la_marca_y_el_indice(conn):
    conn.execute("DROP INDEX idx_upload_jobs_library")
    conn.execute("ALTER TABLE library_items DROP COLUMN last_seen_at")

    _migra(conn)

    assert "last_seen_at" in {fila[1] for fila in conn.execute("PRAGMA table_info(library_items)")}
    assert "idx_upload_jobs_library" in {fila[1] for fila in conn.execute("PRAGMA index_list(upload_jobs)")}


def test_dos_init_db_a_la_vez_no_fallan_por_la_columna_repetida(conn, isolated_db):
    """La primera carga tras actualizar pasa por init_db varias veces a la vez: si otra conexión añade la columna justo
    antes, el ALTER de esta da «duplicate column name»."""
    from emuwarez_uploadrr.database import _migrate_library_items_last_seen
    conn.execute("ALTER TABLE library_items DROP COLUMN last_seen_at")
    conn.commit()
    otra = connect(isolated_db / "emuwarez_uploadrr.db")

    class OtraLaAnadeAntes:
        primera = True

        def execute(self, sql, *args):
            if self.primera and sql.startswith("ALTER TABLE"):
                self.primera = False
                otra.execute(sql)
                otra.commit()
            return conn.execute(sql, *args)

    _migrate_library_items_last_seen(OtraLaAnadeAntes())
    otra.close()
    assert "last_seen_at" in {fila[1] for fila in conn.execute("PRAGMA table_info(library_items)")}


def test_la_migracion_no_se_traga_una_base_de_datos_bloqueada(conn, isolated_db):
    """Tragándose el «database is locked», el esquema quedaría en 43 sin la columna y toda sincronización fallaría."""
    from emuwarez_uploadrr.database import _migrate_library_items_last_seen
    conn.execute("ALTER TABLE library_items DROP COLUMN last_seen_at")
    conn.commit()
    otra = connect(isolated_db / "emuwarez_uploadrr.db")
    otra.execute("BEGIN IMMEDIATE")
    conn.execute("PRAGMA busy_timeout = 0")
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        _migrate_library_items_last_seen(conn)
    otra.rollback()
    otra.close()


def test_al_migrar_se_borra_lo_de_las_instancias_que_ya_no_existen(conn):
    """Antes, borrar una instancia dejaba lo suyo en la biblioteca para siempre."""
    ids = {}
    for instancia, externo in ((99, "huérfana"), (None, "sin instancia"), (RADARR, "1")):
        ids[externo] = conn.execute("INSERT INTO library_items (item_type, title, instance_id, external_id, local_status)"
                                    " VALUES ('movie', ?, ?, ?, 'Disponible')", (externo, instancia, externo)).lastrowid
    peticion = conn.execute("INSERT INTO request_items (emu_id, title, readiness_best_library_item_id)"
                            " VALUES ('7', 'Huérfana', ?)", (ids["huérfana"],)).lastrowid
    conn.execute("INSERT INTO request_readiness (request_item_id, best_library_item_id, status) VALUES (?, ?, 'ready')",
                 (peticion, ids["huérfana"]))
    _migra(conn)
    assert {r[0] for r in conn.execute("SELECT external_id FROM library_items")} == {"sin instancia", "1"}
    # La migración no recalcula la preparación, pero tampoco la deja apuntando a lo borrado.
    assert conn.execute("SELECT readiness_best_library_item_id FROM request_items").fetchone()[0] is None
    assert conn.execute("SELECT best_library_item_id FROM request_readiness").fetchone()[0] is None

    # Sin ninguna instancia, lo que no tiene instancia sigue ahí.
    conn.execute("DELETE FROM instances")
    _migra(conn)
    assert {r[0] for r in conn.execute("SELECT external_id FROM library_items")} == {"sin instancia"}
