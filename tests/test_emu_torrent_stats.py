"""Las estadísticas de eMuwarez de una subida: id de la ficha, caché, fallos y que la clave no salga."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import emu_torrent_stats as ets
from emuwarez_uploadrr.services.emu_torrent_stats import estadisticas_de_la_subida, id_de_la_ficha
from emuwarez_uploadrr.services.settings import set_setting

# Lo que devuelve UNIT3D (TorrentResource): los contadores van en `attributes`.
TORRENTE = {"type": "torrent", "id": "321", "attributes": {
    "seeders": 7, "leechers": 2, "times_completed": 15, "freeleech": "50%", "double_upload": True}}


@pytest.fixture
def conn():
    ets.olvidar_cache()
    c = connect(db_path())
    init_db(c)
    set_setting(c, "emu.api_key", "clave-secreta")
    c.commit()
    yield c
    c.close()
    ets.olvidar_cache()


def _subida(conn, *, estado="completed", ficha="https://emu-warez.com/torrents/321"):
    cur = conn.execute("INSERT INTO upload_jobs (title, path, status, result_tracker) VALUES ('Peli', '/x', ?, ?)", (estado, ficha))
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def llamadas(monkeypatch):
    hechas: list[tuple] = []

    def falso(api_key, torrent_id, base_url=None):
        hechas.append((api_key, torrent_id))
        return dict(TORRENTE["attributes"])

    monkeypatch.setattr(ets, "emu_get_torrent", falso)
    return hechas


@pytest.mark.parametrize("url,esperado", [
    ("https://emu-warez.com/torrents/321", 321),
    ("https://emu-warez.com/torrents/321?hash=abc", 321),
    ("https://emu-warez.com/torrents/321/", 321),
    ("https://emu-warez.com/torrents/similar/1.5", None),
    ("https://emu-warez.com/torrents", None),
    ("", None), (None, None),
])
def test_id_de_la_ficha(url, esperado):
    assert id_de_la_ficha(url) == esperado


def test_emu_get_torrent_pide_api_torrents_id_y_devuelve_los_atributos(monkeypatch):
    urls = []
    monkeypatch.setattr(emu, "request_json", lambda method, url: urls.append(url) or dict(TORRENTE))
    assert emu.emu_get_torrent("k", 321)["seeders"] == 7
    assert urls == ["https://emu-warez.com/api/torrents/321?api_token=k"]


def test_las_estadisticas_se_resumen_y_se_guardan_cinco_minutos(conn, llamadas):
    job = _subida(conn)
    primera = estadisticas_de_la_subida(conn, job)
    assert primera["aplica"] and primera["disponible"]
    assert (primera["seeders"], primera["leechers"], primera["completadas"]) == (7, 2, 15)
    assert primera["freeleech"] == "50%" and primera["doble_subida"] is True
    estadisticas_de_la_subida(conn, job)
    assert llamadas == [("clave-secreta", 321)]
    estadisticas_de_la_subida(conn, job, refrescar=True)
    assert len(llamadas) == 2


def test_sin_ficha_o_sin_completar_no_aplica_y_no_llama(conn, llamadas):
    assert estadisticas_de_la_subida(conn, _subida(conn, estado="failed"))["aplica"] is False
    assert estadisticas_de_la_subida(conn, _subida(conn, ficha=None))["aplica"] is False
    assert estadisticas_de_la_subida(conn, 9999)["aplica"] is False
    assert llamadas == []


def test_sin_clave_dice_que_falta_y_no_llama(conn, llamadas):
    set_setting(conn, "emu.api_key", "")
    conn.commit()
    datos = estadisticas_de_la_subida(conn, _subida(conn))
    assert datos["aplica"] and not datos["configurado"] and not datos["disponible"]
    assert "API key" in datos["mensaje"] and llamadas == []


def test_un_fallo_del_tracker_no_es_un_error_y_se_recuerda_poco(conn, monkeypatch):
    intentos = []

    def falla(api_key, torrent_id, base_url=None):
        intentos.append(1)
        raise IntegrationError("eMuwarez no responde")

    monkeypatch.setattr(ets, "emu_get_torrent", falla)
    job = _subida(conn)
    datos = estadisticas_de_la_subida(conn, job)
    assert datos["aplica"] and datos["configurado"] and not datos["disponible"]
    assert datos["mensaje"] == "eMuwarez no responde"
    estadisticas_de_la_subida(conn, job)
    assert len(intentos) == 1


def test_la_respuesta_no_lleva_la_clave(conn, llamadas):
    assert "clave-secreta" not in str(estadisticas_de_la_subida(conn, _subida(conn)))


def test_el_endpoint_da_404_sin_ficha_y_200_con_ella(client, auth_headers, conn, llamadas):
    assert client.get("/api/uploads/12345/tracker-stats").status_code in (401, 403)
    assert client.get("/api/uploads/12345/tracker-stats", headers=auth_headers).status_code == 404
    job = _subida(conn)
    r = client.get(f"/api/uploads/{job}/tracker-stats", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["completadas"] == 15 and "clave-secreta" not in r.text
