"""Los filtros de columna de Biblioteca admiten varios valores: dentro de una
columna se suman (OR) y entre columnas se cruzan (AND)."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.library import NOT_AVAILABLE_STATUS_FILTER, count_library, list_library

FILAS = [
    # id, tipo, instancia, estado, audio, subs
    (1, "movie", 1, "Disponible", 1, 1),
    (2, "movie", 2, "Disponible", 1, 0),
    (3, "series", 2, "Disponible", 0, 0),
    (4, "series", 3, "Faltante", None, None),
]


@pytest.fixture
def conn(isolated_db):
    c = connect(db_path()); init_db(c)
    for id_, tipo, inst, estado, audio, subs in FILAS:
        c.execute(
            """INSERT INTO library_items (id, item_type, instance_id, title, local_status,
                                          has_spanish_audio, has_spanish_subs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id_, tipo, inst, f"t{id_}", estado, audio, subs))
    c.commit()
    yield c
    c.close()


def _ids(conn, **filtros):
    ids = {r["id"] for r in list_library(conn, limit=100, **filtros)}
    assert count_library(conn, **filtros) == len(ids)
    return ids


def test_varios_valores_de_una_columna_se_suman(conn):
    assert _ids(conn, instance_id=[1, 3]) == {1, 4}
    assert _ids(conn, spanish=["ambos", "audio"]) == {1, 2}


def test_columnas_distintas_se_cruzan(conn):
    assert _ids(conn, item_type=["movie", "series"], instance_id=[2]) == {2, 3}
    assert _ids(conn, item_type=["series"], spanish=["no", "desconocido"]) == {3, 4}


def test_un_valor_suelto_sigue_funcionando(conn):
    assert _ids(conn, item_type="movie") == {1, 2}
    assert _ids(conn, item_type=[]) == {1, 2, 3, 4}


def test_no_disponible_se_combina_con_otros_estados(conn):
    assert _ids(conn, status=[NOT_AVAILABLE_STATUS_FILTER]) == {4}
    assert _ids(conn, status=[NOT_AVAILABLE_STATUS_FILTER, "Disponible"]) == {1, 2, 3, 4}


def test_el_endpoint_acepta_el_parametro_repetido(client, auth_headers):
    r = client.get("/api/library?type=movie&type=series&spanish=ambos&spanish=no", headers=auth_headers)
    assert r.status_code == 200
    assert client.get("/api/library?spanish=ambos&spanish=yes", headers=auth_headers).status_code == 422
