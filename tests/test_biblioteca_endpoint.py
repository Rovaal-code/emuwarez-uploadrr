"""La lista de Biblioteca se pide de verdad, con datos dentro.

Existía cobertura de casi todo menos de esto: pedir GET /api/library con una
serie que tiene temporadas y capítulos, que es el camino que recorre los
agregadores (tamaño, ruta, calidad, estado, nomenclatura). Al sacarlos de la
capa web se quedó atrás un ayudante y la pantalla entera reventó con
"Error al cargar la biblioteca" — 1952 tests en verde y ninguno la pedía.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def con_datos(client, auth_headers):
    """Una serie con temporada y dos capítulos, más una película."""
    from emuwarez_uploadrr.database import connect, db_path, init_db

    conn = connect(db_path()); init_db(conn)
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, tmdb_id,
                                      instance_id, instance_type, instance_name, external_id)
           VALUES ('series','Arcane',2021,'Disponible','99',1,'sonarr','Sonarr','7')""")
    serie = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, parent_id, season_number,
                                      instance_id, instance_type, instance_name, external_id)
           VALUES ('season','T1','Disponible',?,1,1,'sonarr','Sonarr','7-1')""", (serie,))
    temporada = cur.lastrowid
    for n in (1, 2):
        conn.execute(
            """INSERT INTO library_items (item_type, title, local_status, parent_id, season_number,
                                          episode_number, path, quality, resolution, source,
                                          video_codec, audio_codec, audio_languages,
                                          subtitle_languages, size_bytes, instance_id,
                                          instance_type, instance_name, external_id)
               VALUES ('episode',?,'Disponible',?,1,?,?,'Bluray-1080p','1080p','BluRay','x264',
                       'AC3','spa/eng','spa',1000000,1,'sonarr','Sonarr',?)""",
            (f"Arcane S01E0{n}", temporada, n, f"/data/Arcane/S01E0{n}.mkv", f"7-1-{n}"))
    conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, path, quality,
                                      resolution, source, size_bytes, instance_id,
                                      instance_type, instance_name, external_id)
           VALUES ('movie','Dune',2021,'Disponible','/data/Dune.mkv','Bluray-2160p','2160p',
                   'BluRay',9000000,2,'radarr','Radarr','1')""")
    conn.commit(); conn.close()
    return client, auth_headers


def test_la_lista_de_biblioteca_responde(con_datos):
    cliente, cab = con_datos
    r = cliente.get("/api/library?limit=50", headers=cab)
    assert r.status_code == 200, r.text
    datos = r.json()
    titulos = {i["title"] for i in datos["items"]}
    assert "Arcane" in titulos and "Dune" in titulos


def test_una_serie_agrega_los_datos_de_sus_capitulos(con_datos):
    """El camino que reventó: los agregadores de una serie con hijos."""
    cliente, cab = con_datos
    r = cliente.get("/api/library?limit=50", headers=cab)
    assert r.status_code == 200, r.text
    serie = next(i for i in r.json()["items"] if i["title"] == "Arcane")
    # La serie no tiene tamaño ni resolución propios: salen de sumar sus capítulos.
    assert serie.get("size_bytes"), "no ha agregado el tamaño de los capítulos"
    assert serie.get("resolution") == "1080p"


def test_los_filtros_ofrecen_lo_que_existe(con_datos):
    """library_filter_values, que también salió de la capa web."""
    cliente, cab = con_datos
    r = cliente.get("/api/library/filter-options", headers=cab)
    assert r.status_code == 200, r.text
    opciones = r.json()
    assert "1080p" in str(opciones.get("qualities", "")) or "1080p" in str(opciones)
    assert opciones.get("types")


def test_la_ficha_de_una_temporada_responde(con_datos):
    cliente, cab = con_datos
    r = cliente.get("/api/library?limit=50", headers=cab)
    temporada = next(i for i in r.json()["items"] if i["item_type"] == "season")
    detalle = cliente.get(f"/api/library/{temporada['id']}", headers=cab)
    assert detalle.status_code == 200, detalle.text
