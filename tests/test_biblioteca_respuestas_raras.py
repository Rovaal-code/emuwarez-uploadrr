"""Radarr/Sonarr apagados, a medio arrancar o que contestan algo raro no pueden borrar, dar por faltante ni avisar de
nada en la biblioteca, ni perder los cruces con peticiones y las subidas."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from emuwarez_uploadrr.integrations import radarr, sonarr, tmdb
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import library
from emuwarez_uploadrr.services.notification_center import list_notifications
from emuwarez_uploadrr.services.settings import set_setting

from tests import arr_falso
from tests.arr_falso import (
    RADARR, SONARR, _archivo, _capitulo, _con_serie, _estado, _externos, _peli, _serie, _sincroniza,
)

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
arr, conn, _progreso_aparte = arr_falso.arr, arr_falso.conn, arr_falso._progreso_aparte


# --- BIB-1: un listado vacío no es una biblioteca vacía ---------------------------------------------------------

def test_radarr_que_contesta_vacio_no_borra_la_instancia_ni_sus_cruces(conn, arr):
    arr["peliculas"] = [_peli(1, "Matrix", 603), _peli(2, "Dune", 438631)]
    _sincroniza(conn, RADARR)
    matrix = conn.execute("SELECT id FROM library_items WHERE external_id = '1'").fetchone()[0]
    peticion = conn.execute("INSERT INTO request_items (emu_id, title, tmdb_id) VALUES ('7', 'Matrix', '603')").lastrowid
    conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status) VALUES (?, ?, 'Compatible')",
                 (matrix, peticion))
    conn.commit()

    arr["peliculas"] = []
    with pytest.raises(IntegrationError, match="no se borra nada"):
        _sincroniza(conn, RADARR)

    assert _externos(conn, RADARR) == {"1", "2"}
    assert conn.execute("SELECT COUNT(*) FROM request_matches").fetchone()[0] == 1


def test_una_instancia_nueva_si_puede_estar_vacia(conn, arr):
    assert _sincroniza(conn, RADARR) == (0, 0)
    assert _sincroniza(conn, SONARR, include_episodes=True) == (0, 0)


def test_sonarr_que_contesta_vacio_no_borra_la_instancia(conn, arr):
    _con_serie(arr, 20, [1, 2])
    _sincroniza(conn, SONARR, include_episodes=True)
    antes = _externos(conn, SONARR)

    arr["series"] = []
    with pytest.raises(IntegrationError, match="no se borra nada"):
        _sincroniza(conn, SONARR, include_episodes=True)

    assert _externos(conn, SONARR) == antes and len(antes) == 4


def test_una_serie_sin_capitulos_que_antes_los_tenia_no_pierde_los_suyos(conn, arr):
    """Sonarr a medio refrescar contesta 200 con []: sus capítulos no se borran ni pasan a faltante."""
    _con_serie(arr, 20, [1, 2])
    _con_serie(arr, 30, [1])
    _sincroniza(conn, SONARR, include_episodes=True)
    antes = _externos(conn, SONARR)

    arr["capitulos"][20] = []
    with pytest.raises(library.SincronizacionParcial, match="Serie 20"):
        _sincroniza(conn, SONARR, include_episodes=True)

    assert _externos(conn, SONARR) == antes
    assert {_estado(conn, "episode:2001"), _estado(conn, "episode:2002")} == {"Disponible"}
    assert list_notifications(conn) == []


def test_una_serie_sin_capitulos_que_Sonarr_dice_que_tiene_falla(conn, arr):
    arr["series"] = [_serie(20, statistics={"totalEpisodeCount": 8, "episodeCount": 8})]
    with pytest.raises(library.SincronizacionParcial):
        _sincroniza(conn, SONARR, include_episodes=True)


def test_sin_los_archivos_de_la_serie_sus_capitulos_no_pasan_a_faltante(conn, arr):
    _con_serie(arr, 20, [1, 2])
    _sincroniza(conn, SONARR, include_episodes=True)
    antes = conn.execute("SELECT path, size_bytes, audio_languages FROM library_items WHERE external_id = 'episode:2001'"
                         ).fetchone()

    arr["archivos"][20] = []
    with pytest.raises(library.SincronizacionParcial, match="archivos"):
        _sincroniza(conn, SONARR, include_episodes=True)

    despues = conn.execute("SELECT path, size_bytes, audio_languages, local_status, missing_since FROM library_items "
                           "WHERE external_id = 'episode:2001'").fetchone()
    assert tuple(despues)[:3] == tuple(antes)
    assert despues["local_status"] == "Disponible" and despues["missing_since"] is None
    assert list_notifications(conn) == []


_FICHAS = [
    lambda: radarr.get_movie("http://r", "k", 1),
    lambda: sonarr.get_series_by_id("http://s", "k", 1),
    lambda: sonarr.get_episode_files("http://s", "k", 1),
]
_COLAS = [lambda: radarr.get_queue("http://r", "k"), lambda: sonarr.get_queue("http://s", "k")]


@pytest.mark.parametrize("llamada", _FICHAS + _COLAS, ids=["película", "serie", "archivos", "cola Radarr", "cola Sonarr"])
@pytest.mark.parametrize("respuesta", [{}, {"message": "Unauthorized"}, None, "<html>", 5])
def test_una_respuesta_rara_es_un_error_y_no_un_listado_vacio(monkeypatch, llamada, respuesta):
    monkeypatch.setattr(radarr, "request_json", lambda *a, **kw: respuesta)
    monkeypatch.setattr(sonarr, "request_json", lambda *a, **kw: respuesta)
    with pytest.raises(IntegrationError):
        llamada()


@pytest.mark.parametrize("llamada", _FICHAS, ids=["película", "serie", "archivos"])
@pytest.mark.parametrize("respuesta", [[{"title": "sin id"}], [{"id": 0}], [{"id": True}]])
def test_unas_fichas_sin_id_de_verdad_no_valen(monkeypatch, llamada, respuesta):
    monkeypatch.setattr(radarr, "request_json", lambda *a, **kw: respuesta)
    monkeypatch.setattr(sonarr, "request_json", lambda *a, **kw: respuesta)
    with pytest.raises(IntegrationError):
        llamada()


@pytest.mark.parametrize("llamada", _FICHAS + _COLAS, ids=["película", "serie", "archivos", "cola Radarr", "cola Sonarr"])
def test_una_llamada_que_falla_no_se_traga_como_una_lista_vacia(monkeypatch, llamada):
    def caida(*a, **kw):
        raise IntegrationError("No se pudo conectar con http://radarr")

    monkeypatch.setattr(radarr, "request_json", caida)
    monkeypatch.setattr(sonarr, "request_json", caida)
    with pytest.raises(IntegrationError):
        llamada()


def test_una_cola_o_unos_archivos_vacios_si_son_validos(monkeypatch):
    monkeypatch.setattr(radarr, "request_json", lambda *a, **kw: {"page": 1, "totalRecords": 0, "records": []})
    monkeypatch.setattr(sonarr, "request_json", lambda *a, **kw: [])
    assert radarr.get_queue("http://r", "k") == []
    assert sonarr.get_episode_files("http://s", "k", 1) == []


# --- BIB-2: resincronizar una ficha ---------------------------------------------------------------------------

@pytest.fixture
def con_tmdb(conn, monkeypatch):
    set_setting(conn, "tmdb.api_key", "clave")
    monkeypatch.setattr(tmdb, "get_movie_title", lambda _id, *, language, **kw: "EN" if language == "en-US" else "ES-M1")


def _ficha(conn, externo):
    return conn.execute("SELECT id, title, english_title, local_status, path FROM library_items WHERE external_id = ?",
                        (externo,)).fetchone()


def test_resincronizar_una_pelicula_conserva_sus_titulos_en_castellano_e_ingles(conn, arr, con_tmdb, monkeypatch):
    arr["peliculas"] = [_peli(1, "M1", 77)]
    _sincroniza(conn, RADARR)
    antes = _ficha(conn, "1")
    assert (antes["title"], antes["english_title"]) == ("ES-M1", "EN")

    monkeypatch.setattr(radarr, "get_movie", lambda *a: _peli(1, "M1", 77))
    assert library.resync_single_item(conn, antes["id"]) == {"ok": True}

    assert _ficha(conn, "1")["title"] == "ES-M1" and _ficha(conn, "1")["english_title"] == "EN"


def test_resincronizar_con_radarr_aun_sin_el_archivo_no_pasa_la_pelicula_a_faltante(conn, arr, con_tmdb, monkeypatch):
    arr["peliculas"] = [_peli(1, "M1", 77)]
    _sincroniza(conn, RADARR)
    antes = _ficha(conn, "1")

    monkeypatch.setattr(radarr, "get_movie", lambda *a: _peli(1, "M1", 77, con_archivo=False))
    assert library.resync_single_item(conn, antes["id"]) == {"ok": True}

    despues = _ficha(conn, "1")
    assert despues["local_status"] == "Disponible" and despues["path"] == antes["path"]
    assert list_notifications(conn) == []


def test_resincronizar_sin_cola_no_pasa_a_faltante_lo_que_se_descarga(conn, arr, monkeypatch):
    arr["peliculas"] = [_peli(1, "M1", con_archivo=False)]
    arr["cola"] = [{"movieId": 1, "status": "downloading", "statusMessages": []}]
    _sincroniza(conn, RADARR)
    monkeypatch.setattr(radarr, "get_movie", lambda *a: _peli(1, "M1", con_archivo=False))

    assert library.resync_single_item(conn, _ficha(conn, "1")["id"]) == {"ok": True}

    assert _estado(conn, "1") == "Descargando"


def test_resincronizar_con_una_respuesta_vacia_no_crea_una_ficha_sin_id(conn, arr, monkeypatch):
    arr["peliculas"] = [_peli(1, "M1")]
    _sincroniza(conn, RADARR)
    monkeypatch.setattr(radarr, "request_json", lambda *a, **kw: {})

    assert library.resync_single_item(conn, _ficha(conn, "1")["id"])["ok"] is False

    assert _externos(conn, RADARR) == {"1"}


def test_resincronizar_una_serie_sin_sus_archivos_no_pasa_nada_a_faltante(conn, arr, monkeypatch):
    _con_serie(arr, 20, [1, 2])
    _sincroniza(conn, SONARR, include_episodes=True)
    monkeypatch.setattr(sonarr, "get_series_by_id", lambda *a: _serie(20))
    arr["archivos"][20] = []
    arr["capitulos"][20] = [_capitulo(20, 1, con_archivo=False), _capitulo(20, 2, con_archivo=False)]

    library.resync_single_item(conn, _ficha(conn, "20")["id"])

    assert {_estado(conn, "episode:2001"), _estado(conn, "episode:2002")} == {"Disponible"}
    assert list_notifications(conn) == []


# --- BIB-6: una cola que falla no es una cola vacía -----------------------------------------------------------

def test_si_la_cola_falla_la_sincronizacion_sigue_y_lo_que_se_descarga_conserva_su_estado(conn, arr):
    """La cola no es un listado de lo que tienes: sin ella no se borra ni se da por faltante nada, pero tampoco se para."""
    arr["peliculas"] = [_peli(1, "Matrix", con_archivo=False), _peli(2, "Dune")]
    arr["cola"] = [{"movieId": 1, "status": "downloading", "statusMessages": []}]
    _sincroniza(conn, RADARR)
    assert _estado(conn, "1") == "Descargando"

    arr["cola"] = IntegrationError("Tiempo de espera agotado")
    arr["peliculas"] = [_peli(1, "Matrix", con_archivo=False), _peli(2, "Dune 2"), _peli(3, "Nueva", con_archivo=False)]
    for _ in range(2):  # y un segundo recorrido sin cola tampoco cambia nada
        assert _sincroniza(conn, RADARR) == (3, 2)

    assert _estado(conn, "1") == "Descargando"
    assert _estado(conn, "3") == "Desconocido"  # nueva: no se sabe si se descarga
    assert conn.execute("SELECT title FROM library_items WHERE external_id = '2'").fetchone()[0] == "Dune 2"
    assert list_notifications(conn) == []

    # Vuelve la cola: la ficha nueva pasa a lo que sea y se avisa de lo que de verdad falta, una vez.
    arr["cola"] = [{"movieId": 1, "status": "downloading", "statusMessages": []}]
    _sincroniza(conn, RADARR)
    assert (_estado(conn, "1"), _estado(conn, "3")) == ("Descargando", "Faltante")
    assert [n["content_title"] for n in list_notifications(conn)] == ["Nueva (1999)"]


def test_si_la_cola_de_sonarr_falla_los_capitulos_sin_archivo_conservan_su_estado(conn, arr):
    caps = [_capitulo(20, 1), _capitulo(20, 2, con_archivo=False)]
    arr["series"] = [_serie(20)]
    arr["capitulos"][20] = caps
    arr["archivos"][20] = [_archivo(caps[0])]
    arr["cola"] = [{"seriesId": 20, "episodeIds": [2002], "status": "downloading"}]
    _sincroniza(conn, SONARR, include_episodes=True)
    assert _estado(conn, "episode:2002") == "Descargando"

    arr["cola"] = IntegrationError("HTTP 500")
    arr["capitulos"][20] = caps + [_capitulo(20, 3, con_archivo=False)]
    _sincroniza(conn, SONARR, include_episodes=True)

    assert _estado(conn, "episode:2001") == "Disponible"
    assert _estado(conn, "episode:2002") == "Descargando"
    assert _estado(conn, "episode:2003") == "Desconocido"
    assert list_notifications(conn) == []


def test_un_primer_recorrido_sin_cola_sigue_siendo_el_primero(conn, arr):
    """Lo que quedó en Desconocido pasa a Faltante al volver la cola: no son «nuevos faltantes»."""
    arr["peliculas"] = [_peli(1, "Matrix", con_archivo=False), _peli(2, "Dune", con_archivo=False)]
    arr["cola"] = IntegrationError("Tiempo de espera agotado")
    _sincroniza(conn, RADARR)
    assert (_estado(conn, "1"), _estado(conn, "2")) == ("Desconocido", "Desconocido")

    arr["cola"] = [{"movieId": 1, "status": "downloading", "statusMessages": []}]
    _sincroniza(conn, RADARR)
    assert (_estado(conn, "1"), _estado(conn, "2")) == ("Descargando", "Faltante")
    assert list_notifications(conn) == []

    arr["peliculas"].append(_peli(3, "P3", con_archivo=False))
    _sincroniza(conn, RADARR)
    assert len(list_notifications(conn)) == 1


def test_la_cola_se_lee_entera_aunque_pase_de_una_pagina(monkeypatch):
    paginas = {1: {"totalRecords": 3, "records": [{"movieId": 1}, {"movieId": 2}]},
               2: {"totalRecords": 3, "records": [{"movieId": 3}]}}
    pedidas = []

    def pagina(_metodo, url, **kw):
        n = int(parse_qs(urlsplit(url).query)["page"][0])
        pedidas.append(n)
        return paginas[n]

    monkeypatch.setattr(radarr, "request_json", pagina)
    assert [r["movieId"] for r in radarr.get_queue("http://r", "k")] == [1, 2, 3]
    assert pedidas == [1, 2]


def test_una_cola_que_llega_cortada_es_un_error(monkeypatch):
    monkeypatch.setattr(sonarr, "request_json",
                        lambda *a, **kw: {"totalRecords": 5, "records": [{"seriesId": 1}] if "page=1" in a[1] else []})
    with pytest.raises(IntegrationError, match="1 de 5"):
        sonarr.get_queue("http://s", "k")


# --- BIB-7: una serie que falla no frena a las demás; un primer recorrido cortado sigue siendo el primero ----------

def test_una_serie_que_falla_no_frena_las_demas_ni_pierde_lo_suyo(conn, arr):
    for s in (20, 30, 40):
        _con_serie(arr, s, [1, 2])
    _sincroniza(conn, SONARR, include_episodes=True)

    _con_serie(arr, 20, [1, 2, 3])  # un capítulo nuevo en una serie que sí responde
    arr["capitulos"][30] = IntegrationError("HTTP 500")
    arr["series"] = [s for s in arr["series"] if s["id"] != 40]  # y otra que ya no está en Sonarr
    with pytest.raises(library.SincronizacionParcial, match="Serie 30") as fallo:
        _sincroniza(conn, SONARR, include_episodes=True)

    externos = _externos(conn, SONARR)
    assert "episode:2003" in externos
    assert {"30", "season:30:1", "episode:3001", "episode:3002"} <= externos
    assert not any(e.endswith(("40", "4001", "4002", "40:1")) for e in externos)
    assert fallo.value.imported > 0


def test_un_primer_recorrido_cortado_no_hace_que_el_siguiente_avise_de_lo_que_faltaba(conn, arr, monkeypatch):
    arr["peliculas"] = [_peli(i, f"P{i}", con_archivo=False) for i in (1, 2, 3)]
    a_la_ficha = radarr.movie_to_library_item

    def se_corta_en_la_tercera(movie, **kw):
        if movie["id"] == 3:
            raise RuntimeError("el contenedor se para")
        return a_la_ficha(movie, **kw)

    monkeypatch.setattr(radarr, "movie_to_library_item", se_corta_en_la_tercera)
    with pytest.raises(RuntimeError):
        _sincroniza(conn, RADARR)
    monkeypatch.setattr(radarr, "movie_to_library_item", a_la_ficha)

    _sincroniza(conn, RADARR)
    assert list_notifications(conn) == []  # sigue siendo el primero: 1, 2 y 3 no son «nuevos faltantes»

    arr["peliculas"].append(_peli(4, "P4", con_archivo=False))
    _sincroniza(conn, RADARR)
    assert [n["content_title"] for n in list_notifications(conn)] == ["P4 (1999)"]


def test_un_primer_recorrido_con_una_serie_rota_sigue_siendo_el_primero(conn, arr):
    """Los capítulos de la serie rota no están aún: al llegar en el siguiente recorrido no son «nuevos faltantes»."""
    for s in (20, 30):
        arr["series"].append(_serie(s))
        arr["capitulos"][s] = [_capitulo(s, 1, con_archivo=False), _capitulo(s, 2, con_archivo=False)]
    arr["capitulos"][30] = IntegrationError("HTTP 500")
    with pytest.raises(library.SincronizacionParcial):
        _sincroniza(conn, SONARR, include_episodes=True)

    arr["capitulos"][30] = [_capitulo(30, 1, con_archivo=False), _capitulo(30, 2, con_archivo=False)]
    _sincroniza(conn, SONARR, include_episodes=True)
    assert list_notifications(conn) == []

    arr["series"].append(_serie(40))
    arr["capitulos"][40] = [_capitulo(40, 1, con_archivo=False), _capitulo(40, 2, con_archivo=False)]
    _sincroniza(conn, SONARR, include_episodes=True)
    assert len(list_notifications(conn)) == 1


def test_la_sincronizacion_web_de_una_instancia_con_una_serie_rota_cuenta_lo_demas(conn, arr, client, auth_headers):
    _con_serie(arr, 20, [1])
    _con_serie(arr, 30, [1])
    arr["capitulos"][30] = IntegrationError("HTTP 500")

    resp = client.post(f"/api/instances/{SONARR}/sync", headers=auth_headers)

    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["imported"] > 0 and "Serie 30" in cuerpo["errors"][0]
