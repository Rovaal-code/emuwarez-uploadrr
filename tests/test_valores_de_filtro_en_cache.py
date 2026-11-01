"""Los valores de los desplegables de Biblioteca se guardan en vez de recorrer la biblioteca en cada apertura.

El desplegable los pide al abrir la sección y tras cada sincronización; calcularlos
lee las rutas de todos los archivos. Se guardan hasta que termine una
sincronización (`recompute_after_sync`) y un minuto como mucho, porque un estado
nuevo (una subida acabada) también cambia la lista.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services import library as lib


@pytest.fixture
def conn(isolated_db):
    c = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(c)
    return c


def _poner(conn, title, status="Disponible") -> None:
    conn.execute(
        "INSERT INTO library_items (item_type, title, local_status, updated_at) "
        "VALUES ('movie', ?, ?, CURRENT_TIMESTAMP)", (title, status))
    conn.commit()


def test_los_valores_de_filtro_se_guardan_hasta_que_se_olvidan(conn):
    _poner(conn, "Uno")
    lib.olvidar_valores_de_filtro()
    assert lib.valores_de_filtro(conn)["statuses"] == ["Disponible"]
    _poner(conn, "Dos", "Faltante")
    assert lib.valores_de_filtro(conn)["statuses"] == ["Disponible"]  # sigue la copia
    lib.olvidar_valores_de_filtro()
    assert lib.valores_de_filtro(conn)["statuses"] == ["Disponible", "Faltante"]


def test_los_valores_de_filtro_caducan(conn, monkeypatch):
    _poner(conn, "Uno")
    lib.olvidar_valores_de_filtro()
    lib.valores_de_filtro(conn)
    _poner(conn, "Dos", "Faltante")
    monkeypatch.setattr(lib, "_VALORES_DE_FILTRO_SEGUNDOS", 0)
    assert "Faltante" in lib.valores_de_filtro(conn)["statuses"]


def test_terminar_una_sincronizacion_olvida_los_valores_de_filtro(conn):
    lib.olvidar_valores_de_filtro()
    lib.valores_de_filtro(conn)
    _poner(conn, "Nueva", "Faltante")
    lib.recompute_after_sync(conn)
    assert lib.valores_de_filtro(conn)["statuses"] == ["Faltante"]


def test_una_conexion_sin_ruta_no_guarda_nada(conn, isolated_db):
    import sqlite3
    cruda = sqlite3.connect(isolated_db / "emuwarez_uploadrr.db")
    cruda.row_factory = sqlite3.Row
    lib.olvidar_valores_de_filtro()
    lib.valores_de_filtro(cruda)
    assert lib._valores_de_filtro == {}


def test_los_valores_de_filtro_de_eMuwarez_salen_de_valores_distintos(conn):
    # Presente con aportes, presente sin ellos (vacío, nulo y roto) y candidato: se ofrece todo.
    for emu, aportes in [(1, '[{"torrent": 1}]'), (1, "[]"), (1, None), (1, "no es json"), (0, None), (None, None)]:
        conn.execute(
            "INSERT INTO library_items (item_type, title, local_status, emu_in_catalog, emu_aportes) "
            "VALUES ('movie', 'x', 'Disponible', ?, ?)", (emu, aportes))
    conn.commit()
    valores = lib.library_filter_values(conn)
    assert valores["emu_states"] == ["candidate", "present"]
    assert valores["aporte_states"] == ["yes", "no"]


def test_solo_presentes_sin_aportes_ofrece_solo_no_aporta(conn):
    conn.execute("INSERT INTO library_items (item_type, title, local_status, emu_in_catalog, emu_aportes) "
                 "VALUES ('movie', 'x', 'Disponible', 1, '[]')")
    conn.commit()
    valores = lib.library_filter_values(conn)
    assert valores["emu_states"] == ["present"] and valores["aporte_states"] == ["no"]
