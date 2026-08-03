"""Buscar en Biblioteca devuelve la SERIE, no la serie más todo lo que cuelga.

Los títulos de temporadas y capítulos llevan dentro el de su serie ("One Piece
- Temporada 1", "One Piece - T1E1"), así que un `title LIKE '%One Piece%'`
acierta en los tres niveles a la vez. Pidiendo la biblioteca en plano —que es
lo que se hacía con cualquier filtro puesto— eso son la serie, sus temporadas y
todos sus capítulos como filas hermanas: cientos de filas para un contenido.

Lo que se busca es el contenido, y el contenido es la serie. Un acierto por
debajo SUBE hasta ella, y lo de dentro se ve expandiéndola, igual que sin
buscar. De paso, buscar el título de un capítulo suelto ya no devuelve una fila
descolgada sin decirte de qué serie es: devuelve la serie.

La otra mitad de la regla está en el frontend (utils/filtrosBiblioteca.ts:
buscar es el único filtro que NO aplana el árbol). Si alguien vuelve a
aplanarlo, estos tests siguen pasando y la pantalla vuelve a la locura de
antes — por eso el de allí nombra a este.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.library import (
    TOP_LEVEL_PARENT_FILTER, count_library, list_library,
)


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert(conn, title, *, item_type="movie", parent_id=None) -> int:
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            instance_type, parent_id, updated_at)
           VALUES (?,?,'Disponible','Sin petición','N/A','sonarr',?,CURRENT_TIMESTAMP)""",
        (item_type, title, parent_id),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def biblioteca(db_conn):
    """Una serie con dos temporadas y dos capítulos cada una, más una película
    y otra serie que no pintan nada, para que buscar tenga de dónde no acertar."""
    serie = _insert(db_conn, "One Piece", item_type="series")
    for t in (1, 2):
        temp = _insert(db_conn, f"One Piece - Temporada {t}",
                       item_type="season", parent_id=serie)
        for e in (1, 2):
            _insert(db_conn, f"One Piece - T{t}E{e}",
                    item_type="episode", parent_id=temp)
    _insert(db_conn, "Dune")
    otra = _insert(db_conn, "Sherlock Hound", item_type="series")
    _insert(db_conn, "Sherlock Hound - Temporada 1", item_type="season", parent_id=otra)
    return db_conn


def _buscar(conn, texto):
    return list_library(conn, search=texto, parent_id=TOP_LEVEL_PARENT_FILTER)


def test_buscar_una_serie_devuelve_solo_la_serie(biblioteca):
    # Lo que veía el usuario: 1 serie + 2 temporadas + 4 capítulos = 7 filas.
    filas = _buscar(biblioteca, "One Piece")
    assert [f["title"] for f in filas] == ["One Piece"]


def test_buscar_el_titulo_de_un_capitulo_devuelve_su_serie(biblioteca):
    # Dos niveles por debajo: el acierto sube del capítulo a la serie, saltando
    # la temporada. Antes salía el capítulo suelto, sin decir de qué serie era.
    filas = _buscar(biblioteca, "T2E1")
    assert [f["title"] for f in filas] == ["One Piece"]


def test_buscar_una_temporada_devuelve_su_serie(biblioteca):
    filas = _buscar(biblioteca, "Temporada 2")
    assert [f["title"] for f in filas] == ["One Piece"]


def test_una_temporada_que_existe_en_dos_series_devuelve_las_dos(biblioteca):
    # "Temporada 1" cuelga de las dos series: tienen que salir las dos, y cada
    # una UNA vez (el EXISTS no puede multiplicar filas por cada acierto).
    filas = _buscar(biblioteca, "Temporada 1")
    assert sorted(f["title"] for f in filas) == ["One Piece", "Sherlock Hound"]


def test_una_pelicula_sigue_saliendo_por_su_propio_titulo(biblioteca):
    # Sin hijos que mirar: la búsqueda de siempre tiene que seguir funcionando.
    assert [f["title"] for f in _buscar(biblioteca, "Dune")] == ["Dune"]


def test_lo_que_no_esta_no_sale(biblioteca):
    assert _buscar(biblioteca, "Naruto") == []


def test_el_total_cuadra_con_las_filas(biblioteca):
    # count_library comparte el constructor de WHERE, pero el EXISTS es nuevo:
    # si se le escapara, el paginador diría 7 y la tabla enseñaría 1.
    for texto in ("One Piece", "T2E1", "Temporada 1", "Dune", "Naruto"):
        filas = _buscar(biblioteca, texto)
        total = count_library(biblioteca, search=texto,
                              parent_id=TOP_LEVEL_PARENT_FILTER)
        assert total == len(filas), texto


def test_expandiendo_una_serie_la_busqueda_no_se_arrastra(biblioteca):
    """Pidiendo los hijos de algo concreto, buscar vuelve a ser un LIKE normal.

    Es lo que hace falta para que la serie que ha salido se pueda abrir: si el
    acierto también subiera aquí, pedir los hijos de One Piece devolvería sus
    dos temporadas por tener capítulos que aciertan, y expandir dependería de
    lo que hubiera escrito en el cajón.
    """
    serie = next(f for f in _buscar(biblioteca, "One Piece"))
    hijos = list_library(biblioteca, parent_id=serie["id"])
    assert sorted(h["title"] for h in hijos) == [
        "One Piece - Temporada 1", "One Piece - Temporada 2",
    ]
