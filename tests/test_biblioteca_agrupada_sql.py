"""Filtrar Biblioteca en plano sube lo que cumple hasta su serie, y eso se hace en SQL.

Antes se leían todas las filas que cumplían (de todos los niveles), se subían a
su serie en Python y se leía otra vez el nivel raíz entero para ordenarlo: en
una biblioteca de 55.000 filas, 2-3 s por cada filtro. Ahora la subida, el
orden, el recorte y el total salen de una sola consulta que solo trae la página.

El oráculo de estas pruebas es el algoritmo de antes, escrito aquí tal cual: lo
nuevo tiene que devolver las mismas filas, en el mismo orden y con el mismo total.
"""
from __future__ import annotations

import itertools

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import library as lib
from emuwarez_uploadrr.services.library import (
    TOP_LEVEL_PARENT_FILTER, list_library, list_library_agrupada, subir_a_su_serie,
)


@pytest.fixture
def conn(isolated_db):
    c = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(c)
    return c


def _poner(conn, title, item_type="movie", *, parent_id=None, status="Disponible", request="Sin petición",
           nomenclature="N/A", season=None, episode=None, origin="radarr", instance_id=1, size=None, year=None,
           audio=None, subs=None) -> int:
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status, instance_type, instance_id,
            parent_id, season_number, episode_number, size_bytes, year, has_spanish_audio, has_spanish_subs,
            updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (item_type, title, status, request, nomenclature, origin, instance_id, parent_id, season, episode, size,
         year, audio, subs),
    )
    return cur.lastrowid


@pytest.fixture
def biblioteca(conn):
    """Tres series (una con especiales), cuatro películas, estados mezclados."""
    _poner(conn, "Árbol", status="Faltante", size=None, year=2001, request="Compatible")
    _poner(conn, "Zeta Movie", status="Disponible", size=900, year=1999, audio=1, subs=1)
    _poner(conn, "Beta Movie", status="Faltante", size=None, year=2020, nomenclature="Correcta")
    _poner(conn, "Alfa Movie", status="Descargando", size=None, year=2010, instance_id=2, audio=0, subs=0)

    def serie(titulo, temporadas, instance_id=3, request="Sin petición"):
        sid = _poner(conn, titulo, "series", status="Parcial", origin="sonarr", instance_id=instance_id,
                     request=request, year=2015)
        for sn, estados in temporadas.items():
            seid = _poner(conn, f"{titulo} - Temporada {sn}", "season", parent_id=sid, season=sn, origin="sonarr",
                          instance_id=instance_id, status="Parcial")
            for e, (estado, tam, aud) in enumerate(estados, 1):
                _poner(conn, f"{titulo} - T{sn}E{e}", "episode", parent_id=seid, season=sn, episode=e,
                       origin="sonarr", instance_id=instance_id, status=estado, size=tam, audio=aud, subs=aud,
                       nomenclature="Correcta" if estado == "Disponible" else "N/A")
        return sid

    serie("Mundo Uno", {1: [("Disponible", 100, 1), ("Faltante", None, None)], 2: [("Faltante", None, None)]})
    # Todo lo que cumple "Faltante" está en los especiales: con «ignorar especiales» no la trae.
    serie("Mundo Dos", {0: [("Faltante", None, None)], 1: [("Disponible", 500, 0), ("Disponible", 400, 0)]},
          request="Llena")
    serie("Otro Titulo", {1: [("Faltante", None, None), ("Descargando", None, None)]}, instance_id=4)
    conn.commit()
    return conn


def _oraculo(conn, *, sort=None, ignore_specials=True, **filtros) -> list[int]:
    """El algoritmo de antes, tal cual."""
    filas = list_library(conn, limit=-1, ignore_specials=ignore_specials, **filtros)
    serie_de = dict(conn.execute("SELECT id, parent_id FROM library_items WHERE item_type = 'season'"))
    raices = {it["id"] if it["parent_id"] is None else serie_de.get(it["parent_id"], it["parent_id"])
              for it in filas if not (ignore_specials and it["season_number"] == 0)}
    arriba = list_library(conn, parent_id=TOP_LEVEL_PARENT_FILTER, sort=sort, limit=-1,
                          ignore_specials=ignore_specials)
    return [it["id"] for it in arriba if it["id"] in raices]


FILTROS = [
    dict(status=["Faltante"]),
    dict(status=["Faltante", "Descargando"]),
    dict(status=[lib.NOT_AVAILABLE_STATUS_FILTER]),
    dict(status=["Disponible"], request=["Sin petición"]),
    dict(request=["Compatible", "Llena"]),
    dict(nomenclature=["Correcta"]),
    dict(origin=["sonarr"]),
    dict(instance_id=[1, 3]),
    dict(search="Mundo"),
    dict(search="T1E1"),
    dict(search="Movie", status=["Faltante"]),
    dict(spanish=["ambos"]),
    dict(spanish=["no", "desconocido"]),
    dict(status=["Nada"]),
]
ORDENES = [None, "title_desc", "updated_desc", "year_desc", "year_asc", "size_desc", "size_asc"]


@pytest.mark.parametrize("ignore_specials", [True, False])
@pytest.mark.parametrize("sort", ORDENES)
@pytest.mark.parametrize("filtros", FILTROS, ids=lambda f: ",".join(f))
def test_agrupada_devuelve_lo_mismo_que_el_algoritmo_de_antes(biblioteca, filtros, sort, ignore_specials):
    esperado = _oraculo(biblioteca, sort=sort, ignore_specials=ignore_specials, **filtros)
    filas, total = list_library_agrupada(biblioteca, sort=sort, ignore_specials=ignore_specials, limit=-1, **filtros)
    assert [f["id"] for f in filas] == esperado
    assert total == len(esperado)


@pytest.mark.parametrize("filtros", FILTROS, ids=lambda f: ",".join(f))
def test_las_paginas_son_trozos_del_listado_y_el_total_no_cambia(biblioteca, filtros):
    esperado = _oraculo(biblioteca, **filtros)
    paginas = [list_library_agrupada(biblioteca, limit=2, offset=o, **filtros) for o in range(0, max(len(esperado), 1), 2)]
    assert list(itertools.chain(*[[f["id"] for f in filas] for filas, _ in paginas])) == esperado
    assert {total for _, total in paginas} == {len(esperado)}


def test_una_serie_con_varios_aciertos_sale_una_sola_vez(biblioteca):
    # Mundo Uno cumple por su temporada 2, por su capítulo 2 y por su temporada 1.
    filas, total = list_library_agrupada(biblioteca, status=["Faltante"], limit=-1)
    titulos = [f["title"] for f in filas]
    assert titulos.count("Mundo Uno") == 1 and total == len(titulos)


def test_con_ignorar_especiales_una_serie_que_solo_cumple_en_la_temporada_cero_no_sale(biblioteca):
    con = [f["title"] for f in list_library_agrupada(biblioteca, status=["Faltante"], ignore_specials=False, limit=-1)[0]]
    sin = [f["title"] for f in list_library_agrupada(biblioteca, status=["Faltante"], ignore_specials=True, limit=-1)[0]]
    assert "Mundo Dos" in con and "Mundo Dos" not in sin


def test_lo_que_sale_es_siempre_nivel_raiz(biblioteca):
    filas, _ = list_library_agrupada(biblioteca, status=["Faltante", "Disponible", "Parcial"], limit=-1)
    assert filas and all(f["parent_id"] is None and f["item_type"] in ("movie", "series") for f in filas)


def test_las_filas_no_traen_raw_json(biblioteca):
    filas, _ = list_library_agrupada(biblioteca, status=["Faltante"], limit=-1)
    assert "raw_json" not in filas[0]


def test_sin_ningun_filtro_salen_todos_los_de_la_raiz(biblioteca):
    filas, total = list_library_agrupada(biblioteca, ignore_specials=False, limit=-1)
    assert total == 7 and len(filas) == 7


@pytest.mark.parametrize("filtros", [dict(status=["Faltante"]), dict(search="Mundo"), dict(origin=["sonarr"])],
                         ids=lambda f: ",".join(f))
@pytest.mark.parametrize("sort", ORDENES)
def test_subir_a_su_serie_pagina_en_sql_igual_que_antes(biblioteca, filtros, sort):
    filas = list_library(biblioteca, limit=-1, **filtros)
    esperado = _oraculo(biblioteca, sort=sort, **filtros)
    todas, total = subir_a_su_serie(biblioteca, filas, sort=sort)
    assert [f["id"] for f in todas] == esperado and total == len(esperado)
    segunda, total2 = subir_a_su_serie(biblioteca, filas, sort=sort, limit=1, offset=1)
    assert [f["id"] for f in segunda] == esperado[1:2] and total2 == len(esperado)


def test_subir_a_su_serie_sin_filas_no_devuelve_nada(biblioteca):
    assert subir_a_su_serie(biblioteca, []) == ([], 0)


def test_subir_a_su_serie_ignora_los_especiales_de_las_filas_que_le_llegan(biblioteca):
    especial = list_library(biblioteca, limit=-1, search="Mundo Dos - T0E1")
    assert subir_a_su_serie(biblioteca, especial, ignore_specials=True) == ([], 0)
    filas, total = subir_a_su_serie(biblioteca, especial, ignore_specials=False)
    assert [f["title"] for f in filas] == ["Mundo Dos"] and total == 1


# --- Por el endpoint ---------------------------------------------------------------------------

@pytest.fixture
def api_con_biblioteca(client):
    c = connect(db_path())
    init_db(c)
    _poner(c, "Película A", status="Faltante")
    _poner(c, "Película B", status="Faltante")
    _poner(c, "Película C", status="Disponible")
    sid = _poner(c, "Serie D", "series", status="Parcial", origin="sonarr", instance_id=2)
    seid = _poner(c, "Serie D - Temporada 1", "season", parent_id=sid, season=1, origin="sonarr", instance_id=2)
    _poner(c, "Serie D - T1E1", "episode", parent_id=seid, season=1, episode=1, origin="sonarr", instance_id=2,
           status="Faltante")
    c.commit()
    c.close()
    return client


def _pedir(client, headers, query):
    r = client.get(f"/api/library?{query}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_el_endpoint_pagina_el_filtro_en_plano(api_con_biblioteca, auth_headers):
    todo = _pedir(api_con_biblioteca, auth_headers, "status=Faltante&sort=title_asc&limit=50")
    assert todo["total"] == 3 and [i["title"] for i in todo["items"]] == ["Película A", "Película B", "Serie D"]
    primera = _pedir(api_con_biblioteca, auth_headers, "status=Faltante&sort=title_asc&limit=2&offset=0")
    segunda = _pedir(api_con_biblioteca, auth_headers, "status=Faltante&sort=title_asc&limit=2&offset=2")
    assert [i["title"] for i in primera["items"]] == ["Película A", "Película B"]
    assert [i["title"] for i in segunda["items"]] == ["Serie D"]
    assert primera["total"] == segunda["total"] == 3
    assert (primera["offset"], primera["limit"]) == (0, 2)


def test_el_endpoint_con_un_filtro_de_columna_tambien_pagina_en_sql(api_con_biblioteca, auth_headers):
    # Proveedor y compañía pasan por el camino de «lo que se ve»: también tiene que paginar bien.
    c = connect(db_path())
    c.execute("UPDATE library_items SET resolution = '1080p' WHERE item_type != 'season'")
    c.commit()
    c.close()
    todo = _pedir(api_con_biblioteca, auth_headers, "resolution=1080p&sort=title_asc&limit=50")
    pagina = _pedir(api_con_biblioteca, auth_headers, "resolution=1080p&sort=title_asc&limit=2&offset=1")
    assert todo["total"] == pagina["total"] == 4
    assert [i["title"] for i in pagina["items"]] == [i["title"] for i in todo["items"]][1:3]
    # Las series que salen traen su resumen calculado, no el de la fila cruda.
    serie = next(i for i in todo["items"] if i["item_type"] == "series")
    assert serie["local_status"] == "Faltante"


# --- Filtros que ocultan («!valor»), con la paginación en SQL ------------------------------------

@pytest.fixture
def api_con_grupos(client):
    c = connect(db_path())
    init_db(c)

    def poner(titulo, item_type="movie", parent=None, grupo=None, estado="Disponible", season=None, ep=None):
        return c.execute(
            "INSERT INTO library_items (item_type, title, local_status, release_group, parent_id, season_number, "
            "episode_number, updated_at) VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            (item_type, titulo, estado, grupo, parent, season, ep)).lastrowid

    poner("A", grupo="G1")
    poner("B", grupo="G2")
    poner("C", grupo=None)
    poner("D", grupo="G1", estado="Faltante")
    # Todos sus capítulos son de G2: la serie enseña G2 y se oculta con ella.
    sx = poner("Serie X", "series", estado="Parcial")
    tx = poner("Serie X - T1", "season", sx, season=1)
    poner("Serie X - T1E1", "episode", tx, grupo="G2", season=1, ep=1)
    poner("Serie X - T1E2", "episode", tx, grupo="G2", season=1, ep=2)
    # Mezcla de grupos: no enseña ninguno, así que no hay nada que ocultar y sale por sus capítulos.
    sy = poner("Serie Y", "series", estado="Parcial")
    ty = poner("Serie Y - T1", "season", sy, season=1)
    poner("Serie Y - T1E1", "episode", ty, grupo="G1", season=1, ep=1)
    poner("Serie Y - T1E2", "episode", ty, grupo="G2", season=1, ep=2)
    c.commit()
    c.close()
    return client


def _titulos(client, headers, query):
    r = _pedir(client, headers, query)
    return [i["title"] for i in r["items"]], r["total"]


def test_ocultar_un_grupo_pagina_en_sql_y_el_total_cuenta_lo_que_queda(api_con_grupos, auth_headers):
    todos, total = _titulos(api_con_grupos, auth_headers, "release_group=!G2&sort=title_asc&limit=50")
    assert todos == ["A", "C", "D", "Serie Y"] and total == 4
    primera, total1 = _titulos(api_con_grupos, auth_headers, "release_group=!G2&sort=title_asc&limit=3&offset=0")
    segunda, total2 = _titulos(api_con_grupos, auth_headers, "release_group=!G2&sort=title_asc&limit=3&offset=3")
    assert primera == ["A", "C", "D"] and segunda == ["Serie Y"]
    # «Mostrando 3 de 4»: el total es el de todo lo que cumple, no el de la página.
    assert total1 == total2 == 4


def test_ocultar_se_combina_con_un_filtro_que_va_por_sql(api_con_grupos, auth_headers):
    titulos, total = _titulos(api_con_grupos, auth_headers, "release_group=!G2&status=Faltante&sort=title_asc&limit=50")
    assert titulos == ["D"] and total == 1


def test_ocultar_se_combina_con_elegir_otro_valor_de_la_misma_columna(api_con_grupos, auth_headers):
    titulos, total = _titulos(api_con_grupos, auth_headers, "release_group=G1&release_group=!G2&sort=title_asc&limit=50")
    assert titulos == ["A", "D", "Serie Y"] and total == 3


def test_ocultar_y_ordenar_por_tamano_no_cambia_el_total(api_con_grupos, auth_headers):
    _, total = _titulos(api_con_grupos, auth_headers, "release_group=!G2&sort=size_desc&limit=1&offset=3")
    assert total == 4
