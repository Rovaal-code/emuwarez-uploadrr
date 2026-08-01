"""Los títulos se resuelven al SINCRONIZAR, no al generar la nomenclatura.

La idea: cuando la sincronización termina, la biblioteca ya tiene el título
español y el inglés de cada cosa, así que el asistente de subida no sale a la
red. Antes no era así y cada plan de temporada pagaba una consulta a TMDb para
el desplegable de Título.

De dónde sale cada uno:
  - Sonarr no manda ningún campo de título original, pero el `title` que manda
    ya es el bueno para la opción "Inglés": se guarda antes de traducirlo.
  - Radarr sí manda `originalTitle`, pero el original de un anime japonés es
    japonés y la opción pide el INGLÉS, así que ese se consulta aparte.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.integrations import radarr, sonarr
from emuwarez_uploadrr.services import tmdb_titles
from emuwarez_uploadrr.services.settings import set_setting_canonical


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def tmdb_falso(monkeypatch, db_conn):
    """TMDb simulado que además CUENTA las consultas."""
    set_setting_canonical(db_conn, "tmdb.api_key", "clave")
    db_conn.commit()
    llamadas: list[tuple[str, str]] = []
    titulos = {("tv", "es-ES"): "Arcane", ("tv", "en-US"): "Arcane",
               ("movie", "es-ES"): "Tiburón", ("movie", "en-US"): "Jaws"}

    def tv(tid, language=None, conn=None):
        llamadas.append(("tv", language)); return titulos[("tv", language)]

    def peli(tid, language=None, conn=None):
        llamadas.append(("movie", language)); return titulos[("movie", language)]

    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title", tv)
    monkeypatch.setattr(tmdb_titles.tmdb, "get_movie_title", peli)
    return llamadas


def test_sonarr_no_pierde_el_titulo_que_manda(db_conn, tmdb_falso):
    """El inglés viene gratis en el payload de Sonarr: se guarda antes de que
    la traducción lo pise."""
    from emuwarez_uploadrr.services.library import _sync_one_series

    class _Inst:
        id, name, type, url, api_key = 1, "Sonarr", "sonarr", "http://x", "k"

    serie = {"id": 7, "title": "Arcane: League of Legends", "tmdbId": 99,
             "path": "/data/Arcane", "seasons": [], "statistics": {}}
    monkey_titulo = "Arcane"
    tmdb_titles.tmdb.get_tv_title = lambda tid, language=None, conn=None: monkey_titulo

    _sync_one_series(db_conn, _Inst(), serie, localize_titles=True, include_episodes=False)
    fila = db_conn.execute(
        "SELECT title, english_title FROM library_items WHERE item_type='series'").fetchone()
    assert fila["title"] == "Arcane"
    assert fila["english_title"] == "Arcane: League of Legends"


def test_un_titulo_que_no_cambia_no_ofrece_dos_opciones_iguales(db_conn):
    """One Piece se llama igual en los dos idiomas: guardar el inglés haría que
    el desplegable enseñara la misma cadena dos veces."""
    from emuwarez_uploadrr.services.library import _sync_one_series

    class _Inst:
        id, name, type, url, api_key = 1, "Sonarr", "sonarr", "http://x", "k"

    tmdb_titles.tmdb.get_tv_title = lambda tid, language=None, conn=None: "One Piece"
    serie = {"id": 8, "title": "One Piece", "tmdbId": 100, "path": "/d", "seasons": [], "statistics": {}}
    _sync_one_series(db_conn, _Inst(), serie, localize_titles=True, include_episodes=False)
    fila = db_conn.execute(
        "SELECT english_title FROM library_items WHERE item_type='series'").fetchone()
    assert not fila["english_title"]


def test_el_ingles_de_una_pelicula_no_es_su_titulo_original(db_conn, tmdb_falso):
    """Radarr manda originalTitle, pero el de un anime japonés es japonés. La
    opción del desplegable pide el INGLÉS, así que se consulta aparte."""
    item = radarr.movie_to_library_item(
        {"id": 1, "title": "Tiburón", "originalTitle": "Jaws", "tmdbId": 578,
         "path": "/data/Tiburon", "hasFile": False, "monitored": True},
        instance_id=1, instance_name="Radarr",
    )
    assert item.original_title == "Jaws"
    # Lo pone la sincronización, no el mapeador: sin ella viene vacío.
    assert item.english_title is None


def test_tras_sincronizar_la_nomenclatura_no_sale_a_la_red(db_conn, tmdb_falso, tmp_path):
    """La prueba del objetivo: con los títulos ya guardados, construir las
    opciones del desplegable no hace ni una consulta."""
    from emuwarez_uploadrr.services.source_assistant import build_title_options

    db_conn.execute(
        """INSERT INTO library_items (item_type, title, english_title, tmdb_id, local_status,
                                      instance_id, external_id)
           VALUES ('series', 'Arcane', 'Arcane: League of Legends', '99', 'Disponible', 1, '7')""")
    db_conn.commit()
    fila = dict(db_conn.execute("SELECT * FROM library_items").fetchone())

    antes = len(tmdb_falso)
    opciones = build_title_options(fila["title"], fila["english_title"])
    assert len(tmdb_falso) == antes, "ha consultado a TMDb teniendo el título guardado"
    assert [o["value"] for o in opciones] == ["Arcane", "Arcane: League of Legends"]


def test_generar_la_nomenclatura_no_consulta_a_tmdb(db_conn, tmdb_falso, monkeypatch):
    """El objetivo entero, de punta a punta: se sincroniza una serie (una
    consulta, la del español) y a partir de ahí el plan de temporada no sale a
    la red ni una vez."""
    import os
    import pathlib

    from emuwarez_uploadrr.services.library import _sync_one_series
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan

    base = pathlib.Path(os.environ["CLAUDE_JOB_DIR"]) / "tmp/pack/Season1"
    if not base.exists():
        pytest.skip("hacen falta los MKV de prueba")

    class _Inst:
        id, name, type, url, api_key = 1, "Sonarr", "sonarr", "http://x", "k"

    _sync_one_series(db_conn, _Inst(),
                     {"id": 7, "title": "Arcane: League of Legends", "tmdbId": 99,
                      "path": "/d", "seasons": [], "statistics": {}},
                     localize_titles=True, include_episodes=False)
    assert len(tmdb_falso) == 1, "la sincronización debería resolver el español y ya"

    sid = db_conn.execute("SELECT id FROM library_items WHERE item_type='series'").fetchone()["id"]
    cur = db_conn.execute(
        "INSERT INTO library_items(item_type,title,local_status,parent_id,season_number,tmdb_id)"
        " VALUES ('season','T1','Disponible',?,1,'99')", (sid,))
    season = cur.lastrowid
    for n in (1, 2):
        db_conn.execute(
            """INSERT INTO library_items(item_type,title,local_status,parent_id,season_number,
                 episode_number,path,quality,resolution,source,video_codec,audio_codec,
                 audio_languages,subtitle_languages,has_spanish_ok,tmdb_id)
               VALUES ('episode',?,'Disponible',?,1,?,?,'Bluray-1080p','1080p','BluRay','x264',
                       'AC3','eng/spa','spa',1,'99')""",
            (f"E0{n}", season, n, str(base / f"S01E0{n}.mkv")))
    db_conn.commit()

    antes = len(tmdb_falso)
    plan = build_season_pack_plan(season, conn=db_conn)
    assert len(tmdb_falso) == antes, f"ha consultado a TMDb: {tmdb_falso[antes:]}"
    assert [o["value"] for o in plan["title_options"]] == ["Arcane", "Arcane: League of Legends"]
