"""La lista y la ficha agregan una serie o temporada igual.

La lista calcula los agregados de todas sus filas de golpe (_batch_rollups) y
la ficha, de una en una con sus propios ayudantes. Son dos copias de la misma
regla, así que aquí se cruzan: lo que enseña la fila tiene que ser lo que
enseña la ficha.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.library import (
    _ROLLUP_EMPTY,
    _batch_rollups,
    _child_quality_rollup,
    _local_status_rollup,
    _nomenclature_rollup,
    _rollup_path,
    _size_rollup,
)


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "db.sqlite"); init_db(c)

    def fila(**k):
        return c.execute(f"INSERT INTO library_items ({','.join(k)}) VALUES ({','.join('?' * len(k))})",
                         list(k.values())).lastrowid

    for s, temporadas in enumerate(([0, 1, 2], [1], [0])):
        serie = fila(item_type="series", title=f"S{s}", local_status="Disponible", external_id=f"s{s}")
        for t in temporadas:
            temp = fila(item_type="season", title=f"S{s} T{t}", local_status="Disponible", parent_id=serie,
                        season_number=t, external_id=f"s{s}t{t}")
            for e in (1, 2):
                tiene = (s + t + e) % 3 != 0
                fila(item_type="episode", title=f"S{s}T{t}E{e}", parent_id=temp, season_number=t, episode_number=e,
                     external_id=f"s{s}t{t}e{e}", local_status="Disponible" if tiene else "Faltante",
                     nomenclature_status="Correcta" if e == 1 else "No adaptada",
                     path=f"/tv/S{s}/Season {t}/S{s}T{t}E{e}.{'1080p' if t else '720p'}.AMZN.WEB-DL.mkv" if tiene else None,
                     resolution="1080p" if t else "720p", source="WEB-DL", release_group=f"G{t}",
                     size_bytes=(t + 1) * 10**9 if tiene else None)
    c.commit()
    yield c
    c.close()


@pytest.mark.parametrize("ignorar_especiales", [True, False])
def test_la_lista_agrega_igual_que_la_ficha(conn, ignorar_especiales):
    filas = conn.execute("SELECT id, item_type FROM library_items WHERE item_type IN ('series', 'season')").fetchall()
    series = [f["id"] for f in filas if f["item_type"] == "series"]
    temporadas = [f["id"] for f in filas if f["item_type"] == "season"]
    lista = _batch_rollups(conn, series, temporadas, ignorar_especiales)
    for f in filas:
        i, tipo = f["id"], f["item_type"]
        ficha = {
            "nomenclature": _nomenclature_rollup(conn, i, tipo, ignorar_especiales),
            "size": _size_rollup(conn, i, tipo, ignorar_especiales),
            "local_status": _local_status_rollup(conn, i, tipo, ignorar_especiales),
            "quality": _child_quality_rollup(conn, i, tipo, ignorar_especiales),
            "path": _rollup_path(conn, i, tipo, ignorar_especiales),
        }
        fila = dict(lista.get(i, {k: None for k in ficha}))
        # Sin capítulos la lista no trae calidad; la fila la pinta vacía igual.
        fila["quality"] = fila["quality"] or dict(_ROLLUP_EMPTY)
        assert fila == ficha, (tipo, i)


def test_muchos_ids_no_topan_con_el_tope_de_parametros(conn):
    """En plano llegan todas las series y temporadas: no pueden ir de una en una como parámetro."""
    assert _batch_rollups(conn, list(range(10**6, 10**6 + 40000)), list(range(2 * 10**6, 2 * 10**6 + 40000)), True) == {}
    assert _batch_rollups(conn, [], [], True) == {}
