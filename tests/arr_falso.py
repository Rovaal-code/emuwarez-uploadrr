"""Lo que comparten las pruebas de la sincronización de biblioteca: instancias de Radarr/Sonarr de mentira.

Nada aquí habla con Radarr ni con Sonarr: sus llamadas se sustituyen por lo que devolverían."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.integrations import radarr, sonarr
from emuwarez_uploadrr.services import library
from emuwarez_uploadrr.services.instances import get_instance

RADARR, SONARR = 1, 2


@pytest.fixture(autouse=True)
def _progreso_aparte(monkeypatch):
    """sync_all deja su error en el progreso compartido: que no pase a otros tests."""
    monkeypatch.setattr(library.sync, "_LIB_SYNC_PROGRESS", dict(library.sync._LIB_SYNC_PROGRESS))


@pytest.fixture
def conn(isolated_db):
    c = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(c)
    for id_, tipo, nombre in ((RADARR, "radarr", "Radarr"), (SONARR, "sonarr", "Sonarr")):
        c.execute("INSERT INTO instances (id, type, name, url, api_key) VALUES (?, ?, ?, ?, 'clave')",
                  (id_, tipo, nombre, f"http://{tipo}"))
    c.commit()
    yield c
    c.close()


def _peli(id_, titulo, tmdb_id=None, con_archivo=True):
    peli = {"id": id_, "title": titulo, "year": 1999, "tmdbId": tmdb_id}
    if con_archivo:
        peli["movieFile"] = {"id": id_, "path": f"/movies/{titulo}.mkv", "size": 1000,
                             "quality": {"quality": {"name": "WEB-DL-1080p"}}}
    return peli


def _serie(id_, **extra):
    return {"id": id_, "title": f"Serie {id_}", "year": 2010, "tvdbId": id_ + 1000, "path": f"/tv/Serie {id_}",
            "seasons": [{"seasonNumber": 1}], **extra}


def _capitulo(serie, numero, con_archivo=True):
    id_ = serie * 100 + numero
    return {"id": id_, "seriesId": serie, "seasonNumber": 1, "episodeNumber": numero, "title": f"Capítulo {numero}",
            "episodeFileId": id_ * 10 if con_archivo else 0}


def _archivo(capitulo, **media):
    return {"id": capitulo["episodeFileId"], "path": f"/tv/Serie/S01E{capitulo['episodeNumber']:02d}.mkv",
            "size": 500, "quality": {"quality": {"name": "WEBRip-720p"}},
            "mediaInfo": {"videoCodec": "x265", "audioCodec": "AC3", "audioLanguages": "spa", "subtitles": "spa", **media}}


def _o_falla(valor):
    if isinstance(valor, Exception):
        raise valor
    return valor


@pytest.fixture
def arr(monkeypatch):
    """Lo que contesta cada instancia. Una excepción en cualquier valor hace fallar esa llamada."""
    e = {"peliculas": [], "cola": [], "series": [], "capitulos": {}, "archivos": {}}
    monkeypatch.setattr(radarr, "get_queue", lambda *a: _o_falla(e["cola"]))
    monkeypatch.setattr(radarr, "get_movies", lambda *a: _o_falla(e["peliculas"]))
    monkeypatch.setattr(sonarr, "get_queue", lambda *a: _o_falla(e["cola"]))
    monkeypatch.setattr(sonarr, "get_series", lambda *a: _o_falla(e["series"]))
    monkeypatch.setattr(sonarr, "get_episodes", lambda _u, _k, s: _o_falla(e["capitulos"].get(s, [])))
    monkeypatch.setattr(sonarr, "get_episode_files", lambda _u, _k, s: _o_falla(e["archivos"].get(s, [])))
    return e


def _con_serie(arr, id_, capitulos, **extra):
    """Sonarr con esta serie (y las que ya hubiera) y sus capítulos, todos con archivo."""
    caps = [_capitulo(id_, n) for n in capitulos]
    arr["series"] = [s for s in arr["series"] if s["id"] != id_] + [_serie(id_, **extra)]
    arr["capitulos"][id_] = caps
    arr["archivos"][id_] = [_archivo(c) for c in caps]


def _sincroniza(conn, instancia, **kw):
    return library.sync_instance(conn, get_instance(conn, instancia), **kw)


def _externos(conn, instancia):
    return {r[0] for r in conn.execute("SELECT external_id FROM library_items WHERE instance_id = ?", (instancia,))}


def _estado(conn, externo):
    return conn.execute("SELECT local_status FROM library_items WHERE external_id = ?", (externo,)).fetchone()[0]
