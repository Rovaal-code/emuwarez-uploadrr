"""Con la red caída, la lista de anime y TMDb no se reintentan ficha a ficha."""
from __future__ import annotations

import time

from emuwarez_uploadrr.database import get_state, set_state
from emuwarez_uploadrr.integrations import tmdb
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import anime_lists, tmdb_titles
from emuwarez_uploadrr.services.settings import set_setting

from tests import arr_falso
from tests.arr_falso import RADARR, _o_falla, _peli, _sincroniza

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
arr, conn, _progreso_aparte = arr_falso.arr, arr_falso.conn, arr_falso._progreso_aparte


# --- BIB-5: sin reintentos por ficha cuando la red falla ------------------------------------------------------

def test_la_lista_de_anime_se_intenta_una_vez_por_recorrido_y_no_en_cada_ficha(conn, arr, monkeypatch):
    intentos = []

    def sin_red(*a, **kw):
        intentos.append(1)
        raise RuntimeError("sin red")

    monkeypatch.setattr(anime_lists, "request_json", sin_red)
    arr["peliculas"] = [_peli(i, f"P{i}", 1000 + i) for i in range(1, 6)]

    _sincroniza(conn, RADARR)
    _sincroniza(conn, RADARR)
    assert len(intentos) == 1  # ni cinco fichas ni dos recorridos, dentro de la hora

    set_state(conn, "last_anime_id_map_failure_utc", str(int(time.time()) - 7200))
    _sincroniza(conn, RADARR)
    assert len(intentos) == 2


def test_si_el_reemplazo_de_la_lista_de_anime_falla_se_conserva_la_anterior(conn, monkeypatch):
    conn.execute("INSERT INTO anime_id_map (tvdb_id, season_number, tmdb_movie_id, mal_id) VALUES ('1', 1, NULL, '10')")
    conn.commit()
    # Un número que SQLite no puede guardar hace fallar el INSERT con la tabla ya vaciada.
    malo = [{"tvdb_id": 2, "mal_id": 20, "season": {"tvdb": 10 ** 30}}]
    monkeypatch.setattr(anime_lists, "request_json", lambda *a, **kw: malo)

    anime_lists.ensure_anime_id_map(conn, force=True)

    assert [tuple(r) for r in conn.execute("SELECT tvdb_id, mal_id FROM anime_id_map")] == [("1", "10")]
    assert get_state(conn, "last_anime_id_map_failure_utc") is not None


def test_un_404_de_tmdb_se_recuerda_y_no_se_vuelve_a_preguntar(conn, monkeypatch):
    llamadas = []

    def no_existe(*a, **kw):
        llamadas.append(1)
        raise IntegrationError("HTTP 404", status=404)

    monkeypatch.setattr(tmdb, "get_movie_title", no_existe)
    for _ in range(3):
        assert tmdb_titles.resolve_movie_title(conn, 123, "Radarr dice") == "Radarr dice"

    assert len(llamadas) == 1
    assert conn.execute("SELECT title FROM tmdb_title_cache WHERE tmdb_id = '123'").fetchone()[0] is None


def test_tmdb_caido_se_deja_de_preguntar_tras_unos_fallos_seguidos(conn, monkeypatch):
    set_setting(conn, "tmdb.api_key", "clave")
    llamadas = []

    def caido(*a, **kw):
        llamadas.append(1)
        raise IntegrationError("No se pudo conectar con api.themoviedb.org")

    monkeypatch.setattr(tmdb, "get_movie_title", caido)
    for i in range(10):
        assert tmdb_titles.resolve_movie_title(conn, i + 1, "Radarr dice") == "Radarr dice"
    assert len(llamadas) == 3

    # Pasada la pausa vuelve a probar, y un acierto cuenta de nuevo desde cero.
    set_state(conn, "tmdb_titulos_pausa_hasta", "0")
    tmdb_titles.resolve_movie_title(conn, 50, "Radarr dice")
    assert len(llamadas) == 4


def test_un_acierto_corta_la_racha_de_fallos_de_tmdb(conn, monkeypatch):
    set_setting(conn, "tmdb.api_key", "clave")
    respuestas = iter([IntegrationError("caído"), IntegrationError("caído"), "Titulo", IntegrationError("caído"),
                       IntegrationError("caído")])

    def tmdb_a_ratos(*a, **kw):
        return _o_falla(next(respuestas))

    monkeypatch.setattr(tmdb, "get_movie_title", tmdb_a_ratos)
    for i in range(5):
        tmdb_titles.resolve_movie_title(conn, i + 1, "x")

    assert get_state(conn, "tmdb_titulos_pausa_hasta") is None


def test_un_404_tambien_corta_la_racha_de_fallos_de_tmdb(conn, monkeypatch):
    set_setting(conn, "tmdb.api_key", "clave")
    respuestas = iter([IntegrationError("caído"), IntegrationError("caído"), IntegrationError("HTTP 404", status=404),
                       IntegrationError("caído"), IntegrationError("caído")])

    def tmdb_a_ratos(*a, **kw):
        return _o_falla(next(respuestas))

    monkeypatch.setattr(tmdb, "get_movie_title", tmdb_a_ratos)
    for i in range(5):
        tmdb_titles.resolve_movie_title(conn, i + 1, "x")

    assert get_state(conn, "tmdb_titulos_pausa_hasta") is None
