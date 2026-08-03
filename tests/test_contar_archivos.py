"""Cuántos archivos de vídeo tienes de verdad (el subtítulo de Biblioteca).

Antes enseñaba el número de FILAS del nivel raíz, así que una serie con 90
capítulos contaba 1 y una temporada suelta también contaba. La pregunta que
hace ese texto es "cuánto tengo", no "cuántas filas hay en la tabla".
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.library import contar_archivos


@pytest.fixture
def conn(isolated_db):
    c = connect(db_path()); init_db(c)
    yield c
    c.close()


def _meter(conn, tipo, estado, parent=None):
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, parent_id)
           VALUES (?, ?, ?, ?)""", (tipo, f"{tipo} {estado}", estado, parent))
    conn.commit()
    return cur.lastrowid


def test_una_biblioteca_vacia_cuenta_cero(conn):
    assert contar_archivos(conn) == 0


def test_cuenta_peliculas_y_capitulos(conn):
    _meter(conn, "movie", "Disponible")
    serie = _meter(conn, "series", "Disponible")
    temp = _meter(conn, "season", "Disponible", serie)
    for _ in range(3):
        _meter(conn, "episode", "Disponible", temp)
    # 1 película + 3 capítulos. La serie y la temporada NO son archivos.
    assert contar_archivos(conn) == 4


def test_una_serie_entera_no_cuenta_como_uno(conn):
    """El fallo que se arregla: la serie con 90 capítulos contaba 1."""
    serie = _meter(conn, "series", "Disponible")
    temp = _meter(conn, "season", "Disponible", serie)
    for _ in range(90):
        _meter(conn, "episode", "Disponible", temp)
    assert contar_archivos(conn) == 90


def test_lo_que_no_tienes_no_cuenta(conn):
    """Un Faltante es algo que Radarr o Sonarr conocen, no un archivo tuyo."""
    _meter(conn, "movie", "Disponible")
    _meter(conn, "movie", "Faltante")
    _meter(conn, "episode", "Faltante")
    assert contar_archivos(conn) == 1


@pytest.mark.parametrize("estado", ["Disponible", "Subiendo", "Subido"])
def test_subirlo_no_deja_de_ser_tuyo(conn, estado):
    """Mismo criterio que nomenclature_check y emu_catalog: subir un archivo
    no lo borra del disco."""
    _meter(conn, "movie", estado)
    assert contar_archivos(conn) == 1


@pytest.mark.parametrize("estado", ["Faltante", "En cola", "Descargando", "Error"])
def test_los_estados_sin_archivo_no_cuentan(conn, estado):
    _meter(conn, "movie", estado)
    assert contar_archivos(conn) == 0


def test_una_temporada_suelta_no_cuenta(conn):
    """Una temporada huérfana (su serie no está) sí era raíz, así que el número
    viejo la contaba. Pero sigue sin ser un archivo."""
    temp = _meter(conn, "season", "Disponible")
    _meter(conn, "episode", "Disponible", temp)
    assert contar_archivos(conn) == 1
