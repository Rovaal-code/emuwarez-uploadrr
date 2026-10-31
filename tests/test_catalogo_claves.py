"""El catálogo de eMuwarez: de qué temporadas es un torrent, con qué clave se indexa y cuándo se da por completo."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import get_state, set_state
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import emu_catalog
from emuwarez_uploadrr.services.emu_catalog import (
    _compute_and_store_item_status,
    _parse_seasons,
    catalogo_cubre,
    filas_del_catalogo,
)
from emuwarez_uploadrr.services.settings import set_setting


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


# --- Temporadas del nombre --------------------------------------------------

@pytest.mark.parametrize("nombre, esperado", [
    ("Show (2020) S01-S03 1080p WEB-DL", [1, 2, 3]),
    ("Show (2020) S01-03 1080p WEB-DL", [1, 2, 3]),
    ("Show (2020) S1-S2 1080p", [1, 2]),
    ("Show (2020) Temporada 2 1080p", [2]),
    ("Show (2020) Season 2 1080p", [2]),
    ("Show (2020) Temporadas 1-3 1080p", [1, 2, 3]),
    ("The S1 Files S02 1080p", [2]),
    ("The S1 Files (2008) S02E05 1080p", [2]),
    ("Show (2020) S02E05 1080p", [2]),
    ("Show (2020) S01 - 1080p WEB-DL", [1]),
    ("Show S01 (2020) 1080p", [1]),
    ("Dune (2021) 2160p Remux", []),
    ("", []),
])
def test_temporadas_del_nombre(nombre, esperado):
    assert _parse_seasons(nombre) == esperado


def test_un_pack_de_varias_temporadas_guarda_la_primera_y_se_lee_entero_del_nombre():
    filas = emu_catalog._index_catalog([{"id": 1, "attributes": {
        "name": "Show (2020) S01-S03 1080p", "category": "Series", "tvdb_id": 5}}])
    assert filas[0]["season_number"] == 1
    assert emu_catalog._row_seasons(filas[0]) == [1, 2, 3]


# --- Claves ------------------------------------------------------------------

def _catalogo(conn, torrent_id, category, name, tmdb=None, tvdb=None, resolution="1080p", source="WEB-DL"):
    conn.execute(
        "INSERT INTO emu_catalog (torrent_id, category, tmdb_id, tvdb_id, season_number, resolution, source, codec, "
        "has_spanish, size, name) VALUES (?, ?, ?, ?, NULL, ?, ?, NULL, NULL, 1, ?)",
        (torrent_id, category, tmdb, tvdb, resolution, source, name))
    conn.commit()


def _fila(conn, item_type, title, parent_id=None, season_number=None, **cols):
    campos = {"local_status": "Disponible", **cols}
    return conn.execute(
        f"INSERT INTO library_items(item_type, title, parent_id, season_number, {','.join(campos)}) "
        f"VALUES (?, ?, ?, ?, {','.join('?' * len(campos))})",
        (item_type, title, parent_id, season_number, *campos.values())).lastrowid


def _en_catalogo(conn, item_id):
    return conn.execute("SELECT emu_in_catalog FROM library_items WHERE id = ?", (item_id,)).fetchone()[0]


def test_una_serie_con_el_mismo_tmdb_que_una_pelicula_no_la_marca_como_subida(db_conn):
    """PET-7: los ids de TMDb de películas y series se pisan; la serie 1399 no es la película 1399."""
    pelicula = _fila(db_conn, "movie", "Otra", tmdb_id="1399", resolution="1080p", source="WEB-DL")
    _catalogo(db_conn, "t1", "Series", "Show (2011) S01 1080p WEB-DL", tmdb="1399", tvdb="121361")
    _compute_and_store_item_status(db_conn)
    assert _en_catalogo(db_conn, pelicula) == 0


def test_un_torrent_de_serie_sin_tvdb_se_encuentra_por_tmdb(db_conn):
    serie = _fila(db_conn, "series", "Show", tmdb_id="1399", tvdb_id="121361")
    temporada = _fila(db_conn, "season", "T1", parent_id=serie, season_number=1)
    _catalogo(db_conn, "t1", "Series", "Show (2011) S01 1080p WEB-DL", tmdb="1399")
    _compute_and_store_item_status(db_conn)
    assert (_en_catalogo(db_conn, temporada), _en_catalogo(db_conn, serie)) == (1, 1)


def test_un_documental_con_temporada_es_una_serie_y_sin_temporada_una_pelicula(db_conn):
    pelicula = _fila(db_conn, "movie", "Doc", tmdb_id="50")
    serie = _fila(db_conn, "series", "Doc serie", tmdb_id="60")
    temporada = _fila(db_conn, "season", "T1", parent_id=serie, season_number=1)
    _catalogo(db_conn, "d1", "Documentales", "Doc (2020) 1080p", tmdb="50")
    _catalogo(db_conn, "d2", "Documentales", "Doc serie (2020) S01 1080p", tmdb="60")
    _compute_and_store_item_status(db_conn)
    assert (_en_catalogo(db_conn, pelicula), _en_catalogo(db_conn, temporada)) == (1, 1)


def test_un_pack_de_varias_temporadas_cubre_cada_una(db_conn):
    """PET-6: «S01-S03» solo contaba para la 1 y las temporadas 2 y 3 se recomendaban como duplicado."""
    serie = _fila(db_conn, "series", "Show", tvdb_id="9")
    temporadas = [_fila(db_conn, "season", f"T{n}", parent_id=serie, season_number=n, tvdb_id="9") for n in (1, 2, 3, 4)]
    _catalogo(db_conn, "p1", "Series", "Show (2020) S01-S03 1080p WEB-DL", tvdb="9")
    _compute_and_store_item_status(db_conn)
    assert [_en_catalogo(db_conn, t) for t in temporadas] == [1, 1, 1, 0]


def test_filas_del_catalogo_y_lo_que_cubre(db_conn):
    serie = _fila(db_conn, "series", "Show", tvdb_id="9", tmdb_id="7")
    temporada = _fila(db_conn, "season", "T2", parent_id=serie, season_number=2)
    capitulo = _fila(db_conn, "episode", "E3", parent_id=temporada, season_number=2, episode_number=3)
    _catalogo(db_conn, "a", "Series", "Show (2020) S02 1080p BluRay", tvdb="9", resolution="1080p", source="Encode")
    _catalogo(db_conn, "b", "Series", "Show (2020) S02E03 2160p", tmdb="7", resolution="2160p", source="Remux")
    item = lambda i: dict(db_conn.execute("SELECT * FROM library_items WHERE id = ?", (i,)).fetchone())
    assert sorted(r["torrent_id"] for r in filas_del_catalogo(db_conn, item(temporada))) == ["a", "b"]
    assert [r["torrent_id"] for r in filas_del_catalogo(db_conn, item(capitulo))] == ["b"]
    assert catalogo_cubre(db_conn, temporada, "1080p", "Encode") is True
    assert catalogo_cubre(db_conn, temporada, "1080p", "Remux") is False  # 1080p y Remux no están juntos
    assert catalogo_cubre(db_conn, temporada, "2160p", None) is True
    assert catalogo_cubre(db_conn, temporada, "720p", None) is False


# --- Descarga completa --------------------------------------------------------

@pytest.fixture
def con_clave(db_conn, monkeypatch):
    set_setting(db_conn, "emu.api_key", "KEY")
    db_conn.commit()
    monkeypatch.setattr(emu_catalog.emu, "emu_test_connection", lambda *a, **kw: {"data": []})
    return db_conn


def _torrents(n):
    return [{"id": i, "attributes": {"name": f"Peli {i} (2020) 1080p", "category": "Películas", "tmdb_id": i}}
            for i in range(1, n + 1)]


def _descarga(monkeypatch, torrents, total=None):
    def falso(api_key, progress=None, stop_after_id=None, **kw):
        if progress:
            progress(1, None, len(torrents), total)
        return torrents
    monkeypatch.setattr(emu_catalog.emu, "emu_fetch_all_torrents", falso)


def _sembrar(conn, n):
    for i in range(1, n + 1):
        _catalogo(conn, f"v{i}", "Películas", f"Vieja {i}", tmdb=str(i))
    set_state(conn, emu_catalog.COUNT_STATE_KEY, str(n))
    conn.commit()


def test_una_descarga_que_se_corta_no_sustituye_el_catalogo(con_clave, monkeypatch):
    """PET-5: una página corta a mitad del recorrido dejaba el catálogo con una fracción de sus torrents."""
    _sembrar(con_clave, 100)
    _descarga(monkeypatch, _torrents(40))
    with pytest.raises(IntegrationError, match="incompleta"):
        emu_catalog.sync_emu_catalog(con_clave, force=True, mode="full")
    assert con_clave.execute("SELECT COUNT(*) FROM emu_catalog WHERE torrent_id LIKE 'v%'").fetchone()[0] == 100
    assert not get_state(con_clave, emu_catalog.SYNC_COMPLETED_STATE_KEY)


def test_con_el_total_de_emuwarez_se_compara_con_el_total(con_clave, monkeypatch):
    _sembrar(con_clave, 100)
    _descarga(monkeypatch, _torrents(90), total=100)
    with pytest.raises(IntegrationError, match="incompleta"):
        emu_catalog.sync_emu_catalog(con_clave, force=True, mode="full")


def test_una_descarga_completa_sustituye_el_catalogo(con_clave, monkeypatch):
    _sembrar(con_clave, 100)
    _descarga(monkeypatch, _torrents(95))
    assert emu_catalog.sync_emu_catalog(con_clave, force=True, mode="full")["status"] == "ok"
    assert con_clave.execute("SELECT COUNT(*) FROM emu_catalog").fetchone()[0] == 95


def test_la_primera_descarga_no_tiene_con_que_compararse(con_clave, monkeypatch):
    _descarga(monkeypatch, _torrents(3))
    assert emu_catalog.sync_emu_catalog(con_clave, force=True, mode="full")["torrents"] == 3
