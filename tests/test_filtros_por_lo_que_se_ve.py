"""Proveedor, Resolución, Source, Grupo, eMuwarez y Aportes miran la biblioteca
entera.

Se filtraban en el navegador sobre lo que había cargado, y con un filtro puesto
eso eran las primeras LOAD_LIMIT (20.000) filas en plano. La biblioteca de
verdad tiene unas 52.400, así que un valor que el desplegable ofrecía podía no
devolver nada. Ahora filtra el servidor, sobre lo que enseña cada columna (en
una serie o temporada, lo que comparten sus capítulos).
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.library import filtrar_por_lo_que_se_ve

LIMITE = 20000  # el tope del endpoint, y LOAD_LIMIT en LibraryPage


@pytest.fixture
def biblioteca_grande(client, auth_headers):
    """Más películas de relleno que el tope, y detrás lo que se busca: en plano
    las temporadas y capítulos van después de todo lo de arriba, y por título
    las Z al final."""
    from emuwarez_uploadrr.database import connect, db_path, init_db

    conn = connect(db_path()); init_db(conn)
    conn.executemany(
        "INSERT INTO library_items (item_type, title, local_status, resolution) "
        "VALUES ('movie', ?, 'Disponible', '1080p')",
        [(f"a{n:05d}",) for n in range(LIMITE + 1)])
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, resolution, source, path)
           VALUES ('movie', 'Zulu', 'Disponible', '2160p', 'WEB-DL',
                   '/data/Zulu.2020.2160p.AMZN.WEB-DL.DDP5.1.H.265-GRP.mkv')""")

    def serie(titulo, resoluciones):
        sid = conn.execute(
            "INSERT INTO library_items (item_type, title, local_status) VALUES ('series', ?, 'Disponible')",
            (titulo,)).lastrowid
        temporadas = {}
        for t, res in enumerate(resoluciones, start=1):
            tid = conn.execute(
                """INSERT INTO library_items (item_type, title, local_status, parent_id, season_number)
                   VALUES ('season', ?, 'Disponible', ?, ?)""", (f"{titulo} T{t}", sid, t)).lastrowid
            temporadas[t] = tid
            for e in (1, 2):
                conn.execute(
                    """INSERT INTO library_items (item_type, title, local_status, parent_id,
                                                  season_number, episode_number, resolution,
                                                  source, release_group)
                       VALUES ('episode', ?, 'Disponible', ?, ?, ?, ?, 'BluRay', 'GRP')""",
                    (f"{titulo} S{t:02d}E{e:02d}", tid, t, e, res))
        return sid, temporadas

    uniforme, _ = serie("Zyx", ["2160p", "2160p"])
    mezclada, temporadas = serie("Zzz", ["2160p", "1080p"])
    conn.commit(); conn.close()
    return client, auth_headers, {"uniforme": uniforme, "mezclada": mezclada, "t1": temporadas[1]}


def _pedir(cliente, cab, **filtros):
    r = cliente.get("/api/library", params={"limit": LIMITE, **filtros}, headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_lo_que_cumple_queda_mas_alla_del_tope(biblioteca_grande):
    """El punto de partida: lo que se busca no estaba en lo que se cargaba."""
    cliente, cab, _ = biblioteca_grande
    titulos = {i["title"] for i in _pedir(cliente, cab)["items"]}
    assert "Zulu" not in titulos and "Zzz T1" not in titulos


def test_resolucion_mira_la_biblioteca_entera_y_sube_al_nivel_mas_alto(biblioteca_grande):
    cliente, cab, ids = biblioteca_grande
    datos = _pedir(cliente, cab, resolution="2160p")
    # Zyx cumple entera y de Zzz solo T1: las dos salen como serie.
    assert {i["title"] for i in datos["items"]} == {"Zulu", "Zyx", "Zzz"}
    assert datos["total"] == 3
    assert ids["mezclada"] in {i["id"] for i in datos["items"]}


def test_proveedor_source_y_grupo_tambien(biblioteca_grande):
    cliente, cab, _ = biblioteca_grande
    proveedores = cliente.get("/api/library/filter-options", headers=cab).json()["providers"]
    assert proveedores == ["Amazon (AMZN)"]
    assert [i["title"] for i in _pedir(cliente, cab, provider="Amazon (AMZN)")["items"]] == ["Zulu"]
    assert {i["title"] for i in _pedir(cliente, cab, source="BluRay")["items"]} == {"Zyx", "Zzz"}
    assert {i["title"] for i in _pedir(cliente, cab, release_group="GRP")["items"]} == {"Zyx", "Zzz"}
    # Entre columnas se cruzan.
    assert {i["title"] for i in _pedir(cliente, cab, source="BluRay", resolution="2160p")["items"]} == {"Zyx", "Zzz"}


def test_el_tope_y_el_desplazamiento_van_despues_de_filtrar(biblioteca_grande):
    cliente, cab, _ = biblioteca_grande
    r = cliente.get("/api/library?resolution=2160p&limit=1&offset=1", headers=cab).json()
    assert r["total"] == 3 and [i["title"] for i in r["items"]] == ["Zyx"]


def test_el_recorte_en_sql_da_lo_mismo_que_mirarlo_todo(biblioteca_grande, monkeypatch):
    """list_library descarta en SQL las películas y capítulos que no cumplen.
    Sin ese recorte tiene que salir exactamente lo mismo."""
    cliente, cab, ids = biblioteca_grande
    from emuwarez_uploadrr.database import connect, db_path
    from emuwarez_uploadrr.services import library

    conn = connect(db_path())
    conn.execute("UPDATE library_items SET emu_in_catalog = 1 WHERE item_type = 'episode'")
    conn.execute("UPDATE library_items SET emu_in_catalog = 0 WHERE id = ? OR parent_id = ?",
                 (ids["t1"], ids["t1"]))
    conn.execute("UPDATE library_items SET emu_in_catalog = 2 WHERE id = ?", (ids["mezclada"],))
    conn.commit(); conn.close()
    casos = [{"resolution": "2160p"}, {"provider": "Amazon (AMZN)"}, {"source": "BluRay"},
             {"release_group": "GRP"}, {"source": "BluRay", "resolution": "2160p"},
             {"emu": "candidate"}, {"emu": "present"}, {"provider": "Netflix (NF)"}]
    con_recorte = [_pedir(cliente, cab, **c) for c in casos]

    original = library.list_library
    monkeypatch.setattr(library, "list_library", lambda conn, *, provider=None, resolution=None, source=None,
                        release_group=None, emu=None, **resto: original(conn, **resto))
    assert con_recorte == [_pedir(cliente, cab, **c) for c in casos]
    assert {i["title"] for i in con_recorte[5]["items"]} == {"Zzz"}


def _fila(id_, parent_id=None, *, emu=None, aportes=None, estado="Disponible"):
    return {"id": id_, "parent_id": parent_id, "provider_label": None, "resolution": None,
            "source": None, "release_group": None, "local_status": estado,
            "emu_in_catalog": emu, "emu_aportes": aportes}


def test_emuwarez_una_serie_a_medias_deja_paso_a_sus_temporadas():
    filas = [_fila(1, emu=2), _fila(2, 1, emu=0), _fila(3, 1, emu=1)]
    assert [f["id"] for f in filtrar_por_lo_que_se_ve(filas, emu=["candidate"])] == [2]
    assert [f["id"] for f in filtrar_por_lo_que_se_ve(filas, emu=["candidate", "present"])] == [2, 3]


def test_aportes_solo_cuenta_lo_que_se_tiene():
    filas = [
        _fila(1, emu=0),                          # nuevo: se aporta entero
        _fila(2, emu=1, aportes=[{"x": 1}]),      # está, pero se mejora
        _fila(3, emu=1),                          # está y no hay nada que aportar
        _fila(4, emu=0, estado="Faltante"),       # no lo tienes
    ]
    assert [f["id"] for f in filtrar_por_lo_que_se_ve(filas, aporte="yes")] == [1, 2]
    assert [f["id"] for f in filtrar_por_lo_que_se_ve(filas, aporte="no")] == [3]


def test_sin_filtros_no_toca_nada():
    filas = [_fila(1), _fila(2, 1)]
    assert filtrar_por_lo_que_se_ve(filas, provider=[], emu=None) is filas


# Un valor con «!» delante oculta en vez de elegir.
FILAS = [
    {"id": 1, "release_group": "A", "resolution": "1080p", "source": None, "provider_label": "Netflix"},
    {"id": 2, "release_group": "B", "resolution": "1080p", "source": None, "provider_label": None},
    {"id": 3, "release_group": None, "resolution": "720p", "source": None, "provider_label": None},
]


def _ids(**filtros):
    return [f["id"] for f in filtrar_por_lo_que_se_ve(FILAS, **filtros)]


def test_un_grupo_oculto_no_sale_y_los_que_no_tienen_grupo_si():
    assert _ids(release_group=["!B"]) == [1, 3]


def test_ocultar_se_combina_con_elegir_y_con_otras_columnas():
    assert _ids(release_group=["!B"], resolution=["1080p"]) == [1]
    assert _ids(release_group=["A", "!B"]) == [1]


def test_ocultar_un_proveedor():
    assert _ids(provider=["!Netflix"]) == [2, 3]


def test_list_library_oculta_en_sql(isolated_db):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services.library import list_library

    conn = connect(db_path()); init_db(conn)
    for titulo, grupo in (("uno", "A"), ("dos", "B"), ("tres", None)):
        conn.execute(
            "INSERT INTO library_items (item_type, title, local_status, release_group) "
            "VALUES ('movie', ?, 'Disponible', ?)", (titulo, grupo))
    conn.commit()
    assert sorted(r["title"] for r in list_library(conn, release_group=["!B"])) == ["tres", "uno"]
