"""El filtro de la columna Español, contra lo que enseña la celda.

Este test existe porque la regla vive en DOS sitios: el SQL que filtra y la
función del frontend que pinta la celda. Si se separan, filtras por "Audio" y
te salen filas que dicen otra cosa — y nada falla, solo miente.

El caso que ya se coló una vez, escribiendo este filtro: en SQL `NOT (NULL = 1)`
es NULL, no TRUE, así que la primera versión de "desconocido" no devolvía
ninguna de las tres filas que tenía que devolver.
"""
from __future__ import annotations

import itertools

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.library import list_library, library_filter_values

# Los 9 estados posibles: cada lado puede ser sí, no, o sin leer.
COMBINACIONES = list(itertools.product([1, 0, None], repeat=2))


def estado_esperado(audio, subs) -> str:
    """La MISMA regla que utils/castellano.ts::estadoCastellano."""
    if audio == 1 and subs == 1:
        return "ambos"
    if audio == 1:
        return "audio"
    if subs == 1:
        return "subs"
    if audio == 0 and subs == 0:
        return "no"
    return "desconocido"


@pytest.fixture
def conn(isolated_db):
    c = connect(db_path()); init_db(c)
    for i, (audio, subs) in enumerate(COMBINACIONES):
        c.execute(
            """INSERT INTO library_items (id, item_type, title, local_status,
                                          has_spanish_audio, has_spanish_subs)
               VALUES (?, 'movie', ?, 'Disponible', ?, ?)""",
            (i + 1, f"a={audio} s={subs}", audio, subs))
    c.commit()
    yield c
    c.close()


@pytest.mark.parametrize("estado", ["ambos", "audio", "subs", "no", "desconocido"])
def test_el_filtro_devuelve_justo_lo_que_la_celda_enseña(conn, estado):
    ids = {r["id"] for r in list_library(conn, spanish=estado, limit=100)}
    esperados = {i + 1 for i, (a, s) in enumerate(COMBINACIONES)
                 if estado_esperado(a, s) == estado}
    assert ids == esperados, (
        f"\nEl filtro '{estado}' y la celda no dicen lo mismo."
        f"\n  el filtro devuelve: {sorted(ids)}"
        f"\n  la celda enseñaría: {sorted(esperados)}")


def test_los_cinco_filtros_reparten_todas_las_filas(conn):
    """Sin solapes ni huecos: cada fila cae en uno y solo uno."""
    visto: dict[int, list[str]] = {}
    for estado in ("ambos", "audio", "subs", "no", "desconocido"):
        for r in list_library(conn, spanish=estado, limit=100):
            visto.setdefault(r["id"], []).append(estado)

    repetidas = {i: e for i, e in visto.items() if len(e) > 1}
    assert not repetidas, f"filas en más de un filtro: {repetidas}"
    assert len(visto) == len(COMBINACIONES), (
        f"filas que no caen en ningún filtro: "
        f"{sorted(set(range(1, len(COMBINACIONES) + 1)) - set(visto))}")


def test_desconocido_incluye_el_lado_a_medio_leer(conn):
    """Con un lado confirmado que NO y el otro sin leer, todavía puede aparecer
    castellano por ese lado: no se puede decir "No" sin mirar los dos."""
    ids = {r["id"] for r in list_library(conn, spanish="desconocido", limit=100)}
    a_medias = {i + 1 for i, (a, s) in enumerate(COMBINACIONES)
                if (a, s) in [(0, None), (None, 0)]}
    assert a_medias <= ids


def test_el_desplegable_solo_ofrece_lo_que_existe(conn):
    """Estilo Excel, igual que el resto de columnas."""
    ofrecidos = library_filter_values(conn)["spanish_states"]
    presentes = {estado_esperado(a, s) for a, s in COMBINACIONES}
    assert set(ofrecidos) == presentes
    # Y en el orden de la columna, no alfabético.
    assert ofrecidos == [v for v in ("ambos", "audio", "subs", "no", "desconocido")
                         if v in presentes]


# ---------------------------------------------------------------------------
# El endpoint tiene su propia lista de valores válidos
# ---------------------------------------------------------------------------

def test_el_endpoint_acepta_los_cinco_estados(client, auth_headers):
    """El parámetro `spanish` se valida con un patrón en la ruta, y ese patrón
    es UNA TERCERA COPIA de la lista de estados.

    Se quedó con los tres viejos (yes/no/unknown) al ampliar la columna, así
    que descartaba en silencio "ambos", "audio" y "subs": FastAPI devolvía 422
    y el filtro no traía nada. Ni los tests del SQL ni los de la celda lo
    pillaron, porque los dos se saltaban la capa web.
    """
    for estado in ("ambos", "audio", "subs", "no", "desconocido"):
        r = client.get(f"/api/library?spanish={estado}", headers=auth_headers)
        assert r.status_code == 200, (
            f"\nEl endpoint rechaza '{estado}' ({r.status_code})."
            f"\nRevisa el patrón de `spanish` en web/api/library.py.")


def test_el_endpoint_rechaza_los_estados_viejos(client, auth_headers):
    """Y al revés: si alguien deja un enlace guardado con el valor antiguo,
    mejor un error claro que devolver la biblioteca entera como si nada."""
    for viejo in ("yes", "unknown"):
        r = client.get(f"/api/library?spanish={viejo}", headers=auth_headers)
        assert r.status_code == 422, f"'{viejo}' debería rechazarse, dio {r.status_code}"
