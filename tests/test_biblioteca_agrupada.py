"""Con un filtro puesto, Biblioteca se pide en plano y lo que cumple sale
agrupado bajo su película o serie.

Filtrando por Origen = Sonarr o Español = Ambos cumplen la serie, sus
temporadas y sus capítulos a la vez, y la tabla y los pósters sacaban cada
capítulo como una fila suelta al lado de su serie. Quedarse con el nivel más
alto que cumple tampoco bastaba: con Estado = Disponible una serie Parcial no
cumple y sus capítulos seguían saliendo sueltos. Lo de dentro se ve
desplegando la serie.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def biblioteca(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db

    conn = connect(db_path()); init_db(conn)
    conn.execute("""INSERT INTO library_items (id, item_type, title, local_status, instance_type, resolution)
                    VALUES (1, 'movie', 'Peli', 'Disponible', 'radarr', '1080p')""")
    conn.execute("""INSERT INTO library_items (id, item_type, title, local_status, instance_type)
                    VALUES (2, 'series', 'Serie', 'Disponible', 'sonarr')""")
    for t in (1, 2):
        conn.execute(
            """INSERT INTO library_items (id, item_type, title, local_status, instance_type,
                                          parent_id, season_number)
               VALUES (?, 'season', ?, 'Disponible', 'sonarr', 2, ?)""", (10 + t, f"Serie T{t}", t))
        for e in (1, 2):
            conn.execute(
                """INSERT INTO library_items (id, item_type, title, local_status, instance_type,
                                              parent_id, season_number, episode_number, resolution)
                   VALUES (?, 'episode', ?, 'Disponible', 'sonarr', ?, ?, ?, '1080p')""",
                (100 + 10 * t + e, f"Serie S{t:02d}E{e:02d}", 10 + t, t, e))
    conn.commit(); conn.close()
    return client, auth_headers


def _ids(cliente, cab, **filtros):
    r = cliente.get("/api/library", params={"limit": 20000, **filtros}, headers=cab)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["total"] == len(datos["items"])
    return [i["id"] for i in datos["items"]]


def test_la_serie_sale_sola_y_no_sus_capitulos(biblioteca):
    assert _ids(*biblioteca, origin="sonarr") == [2]
    assert _ids(*biblioteca, origin=["sonarr", "radarr"]) == [1, 2]


def test_un_capitulo_que_cumple_trae_su_serie_aunque_ella_no_cumpla(biblioteca):
    """El caso real: la serie está Parcial y sus capítulos, Disponibles."""
    from emuwarez_uploadrr.database import connect, db_path

    conn = connect(db_path())
    conn.execute("UPDATE library_items SET local_status = 'Parcial' WHERE id IN (2, 11, 12)")
    conn.execute("UPDATE library_items SET local_status = 'Faltante' WHERE id IN (112, 121, 122)")
    conn.commit(); conn.close()
    assert _ids(*biblioteca, status="Disponible") == [1, 2]
    assert _ids(*biblioteca, status="Faltante") == [2]


def test_con_un_tipo_elegido_sale_ese_tipo_tal_cual(biblioteca):
    assert _ids(*biblioteca, type="episode") == [111, 112, 121, 122]
    assert _ids(*biblioteca, type=["season", "episode"]) == [11, 111, 112, 12, 121, 122]


def test_un_especial_no_trae_la_serie_si_se_ignoran(biblioteca):
    from emuwarez_uploadrr.database import connect, db_path

    conn = connect(db_path())
    conn.execute("""INSERT INTO library_items (id, item_type, title, local_status, instance_type)
                    VALUES (30, 'series', 'Otra', 'Parcial', 'sonarr')""")
    conn.execute("""INSERT INTO library_items (id, item_type, title, local_status, instance_type,
                                                parent_id, season_number)
                    VALUES (31, 'season', 'Otra T0', 'Parcial', 'sonarr', 30, 0)""")
    conn.execute("""INSERT INTO library_items (id, item_type, title, local_status, instance_type,
                                                parent_id, season_number, episode_number)
                    VALUES (32, 'episode', 'Otra S00E01', 'Faltante', 'sonarr', 31, 0, 1)""")
    conn.commit(); conn.close()
    assert _ids(*biblioteca, status="Faltante") == []


def test_la_temporada_que_no_cumple_no_descuelga_sus_capitulos(biblioteca):
    """La serie cumple, la T1 no y sus capítulos sí: sale la serie sola."""
    from emuwarez_uploadrr.database import connect, db_path

    conn = connect(db_path())
    conn.execute("UPDATE library_items SET local_status = 'Parcial' WHERE id = 11")
    conn.commit(); conn.close()
    assert _ids(*biblioteca, status="Disponible") == [1, 2]


def test_tambien_con_los_filtros_por_lo_que_se_ve(biblioteca):
    from emuwarez_uploadrr.database import connect, db_path

    conn = connect(db_path())
    conn.execute("UPDATE library_items SET local_status = 'Parcial' WHERE id = 11")
    conn.commit(); conn.close()
    assert _ids(*biblioteca, status="Disponible", resolution="1080p") == [1, 2]


def test_el_tope_y_el_desplazamiento_van_despues_de_agrupar(biblioteca):
    """Paginando antes de agrupar, la segunda página traería la T1 de Serie."""
    from emuwarez_uploadrr.database import connect, db_path

    conn = connect(db_path())
    conn.execute("""INSERT INTO library_items (id, item_type, title, local_status, instance_type)
                    VALUES (20, 'series', 'Serie Z', 'Disponible', 'sonarr')""")
    conn.commit(); conn.close()
    cliente, cab = biblioteca
    r = cliente.get("/api/library", params={"origin": "sonarr", "limit": 2, "offset": 1}, headers=cab).json()
    assert r["total"] == 2 and [i["id"] for i in r["items"]] == [20]


def test_un_filtro_vacio_no_cuenta(biblioteca):
    cliente, cab = biblioteca
    r = cliente.get("/api/library", params={"origin": "", "limit": 20000}, headers=cab).json()
    assert r["total"] == 8  # todos los niveles, como sin filtro


def test_un_nivel_concreto_no_se_toca(biblioteca):
    cliente, cab = biblioteca
    r = cliente.get("/api/library", params={"parent_id": 2, "origin": "sonarr"}, headers=cab).json()
    assert [i["id"] for i in r["items"]] == [11, 12]
