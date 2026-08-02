"""Ordenar Biblioteca por Tamaño tiene que coincidir con la columna Tamaño.

Una serie o una temporada no guardan tamaño propio: el que enseña la tabla es
la suma de lo que cuelga de ellas. Ordenando por la columna cruda, una serie
que enseña 11 GB caía por detrás de una película de 4 GB en "Tamaño (Más)" —
el orden contradecía a la vista, y no había forma de notarlo salvo mirándolo
(auditoría de tablas).
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.library import list_library


@pytest.fixture
def biblioteca(isolated_db):
    """Una serie de 11 GB repartidos en capítulos, y dos películas sueltas."""
    conn = connect(db_path()); init_db(conn)
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status)
           VALUES ('series', 'Serie grande', 'Disponible')""")
    serie = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, parent_id, season_number)
           VALUES ('season', 'T1', 'Disponible', ?, 1)""", (serie,))
    temporada = cur.lastrowid
    for n, tam in ((1, 6_000_000_000), (2, 5_000_000_000)):
        conn.execute(
            """INSERT INTO library_items (item_type, title, local_status, parent_id,
                                          season_number, episode_number, size_bytes)
               VALUES ('episode', ?, 'Disponible', ?, 1, ?, ?)""",
            (f"T1E{n}", temporada, n, tam))
    for titulo, tam in (("Peli mediana", 8_000_000_000), ("Peli pequeña", 4_000_000_000)):
        conn.execute(
            """INSERT INTO library_items (item_type, title, local_status, size_bytes)
               VALUES ('movie', ?, 'Disponible', ?)""", (titulo, tam))
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status)
           VALUES ('movie', 'Peli sin descargar', 'Faltante')""")
    conn.commit()
    yield conn
    conn.close()


def _raices(conn, orden):
    return [r["title"] for r in list_library(conn, parent_id=0, sort=orden, limit=100)]


def test_mas_grande_primero_cuenta_lo_que_cuelga(biblioteca):
    """La serie enseña 11 GB (6 + 5), así que va por delante de la de 8."""
    assert _raices(biblioteca, "size_desc")[:3] == [
        "Serie grande", "Peli mediana", "Peli pequeña"]


def test_mas_pequeno_primero_tambien(biblioteca):
    assert _raices(biblioteca, "size_asc")[:3] == [
        "Peli pequeña", "Peli mediana", "Serie grande"]


@pytest.mark.parametrize("orden", ["size_desc", "size_asc"])
def test_lo_que_no_tiene_tamano_va_al_final(biblioteca, orden):
    """En los DOS sentidos: amontonarlo arriba en el ascendente nunca es lo que
    estás buscando."""
    assert _raices(biblioteca, orden)[-1] == "Peli sin descargar"


def test_ordenar_por_tamano_no_pierde_ni_duplica_filas(biblioteca):
    """La subconsulta del tamaño efectivo va en el ORDER BY, no en el WHERE:
    si se colara en el filtro, dejaría fuera lo que no tiene tamaño."""
    por_defecto = _raices(biblioteca, "title_asc")
    for orden in ("size_desc", "size_asc"):
        assert sorted(_raices(biblioteca, orden)) == sorted(por_defecto)
