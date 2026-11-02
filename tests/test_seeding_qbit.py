"""La salud del seeding de las subidas, leída de qBittorrent: casamiento, estados, caché y fallos."""
from __future__ import annotations

import logging
import types

import pytest

from emuwarez_uploadrr.database import db
from emuwarez_uploadrr.services import seeding_qbit as sq
from emuwarez_uploadrr.services.settings import set_setting
from tests.http_falso import falla_conexion, respuesta

RAIZ = "/data/uploads"
URL = "http://qbit.lan:8080"
CLAVE_QUI = "http://qui.lan:7476/proxy/CLAVE-SECRETA-DE-QUI"
LOGIN_OK = respuesta(200, cuerpo="Ok.", headers={"Set-Cookie": "SID=abc; path=/"})


def torrent(nombre="Peli 2020 1080p", *, ruta=RAIZ, hash="a" * 40, estado="uploading", progreso=1.0, ratio=1.5,
            subido=3_000_000_000, tags="", contenido=None, seeds=12, peers=3):
    return {
        "hash": hash, "name": nombre, "save_path": ruta + "/", "content_path": contenido or f"{ruta}/{nombre}",
        "state": estado, "progress": progreso, "ratio": ratio, "uploaded": subido, "tags": tags,
        "num_complete": seeds, "num_incomplete": peers,
    }


def _indices(*torrents):
    return sq._indices([sq._resumir(t) for t in torrents])


# --- casamiento ---------------------------------------------------------------------------------------------

def test_una_url_con_el_puerto_mal_escrito_es_un_error_de_qbit_y_no_un_500():
    from emuwarez_uploadrr.integrations.qbittorrent import ErrorQbit, qbit_listar_torrents
    with pytest.raises(ErrorQbit, match="no es válida"):
        qbit_listar_torrents("http://qbit:bad", None, "usuario", "clave")


def test_una_metrica_no_finita_no_rompe_el_resumen():
    t = sq._resumir(torrent(ratio=float("inf"), progreso=float("nan"), subido=float("inf")))
    assert (t["ratio"], t["progress"], t["uploaded"]) == (0.0, 0.0, 0)


def test_casa_por_la_ruta_de_contenido():
    t, como = sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(torrent(), torrent("Otra", hash="b" * 40)), "", RAIZ)
    assert t["hash"] == "a" * 40 and como == "ruta"


def test_casa_por_ruta_de_guardado_y_nombre_si_no_hay_content_path():
    sin_contenido = torrent()
    sin_contenido["content_path"] = ""
    t, como = sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(sin_contenido), "", RAIZ)
    assert t is not None and como == "ruta"


def test_la_ruta_se_normaliza_barras_y_final():
    t, _ = sq.casar(f"{RAIZ}\\Peli 2020 1080p/", _indices(torrent()), "", RAIZ)
    assert t is not None


def test_dos_torrents_en_la_misma_ruta_es_ambiguo_y_no_se_adivina():
    a, b = torrent(hash="a" * 40), torrent(hash="b" * 40)
    assert sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(a, b), "", RAIZ) == (None, "")


def test_la_etiqueta_desempata_dos_torrents_en_la_misma_ruta():
    a, b = torrent(hash="a" * 40), torrent(hash="b" * 40, tags="emuwarez, uploadrr")
    t, como = sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(a, b), "uploadrr", RAIZ)
    assert t["hash"] == "b" * 40 and como == "ruta"


def test_lo_ambiguo_por_ruta_no_baja_al_nombre():
    a, b = torrent(hash="a" * 40, tags="uploadrr"), torrent(hash="b" * 40, tags="uploadrr")
    assert sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(a, b), "uploadrr", RAIZ) == (None, "")


def test_casa_por_nombre_si_es_de_las_subidas_aunque_la_ruta_difiera():
    """qBittorrent ve la carpeta de subidas en otra ruta (proxy de qui): vale el nombre si lleva la etiqueta."""
    t, como = sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(torrent(ruta="/downloads/up", tags="uploadrr")),
                       "uploadrr", RAIZ)
    assert t is not None and como == "nombre"


def test_sin_etiqueta_el_nombre_solo_vale_dentro_de_la_carpeta_de_subidas():
    de_subidas = torrent(ruta=f"{RAIZ}/sub", contenido=f"{RAIZ}/sub/otra/ruta")
    assert sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(de_subidas), "", RAIZ)[1] == "nombre"
    de_fuera = torrent(ruta="/data/descargas", contenido="/data/descargas/x")
    assert sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(de_fuera), "", RAIZ) == (None, "")


def test_con_etiqueta_un_torrent_del_mismo_nombre_sin_ella_no_cuenta():
    """Un release bajado con el mismo nombre desde otro sitio no es la subida."""
    ajeno = torrent(ruta="/data/descargas", contenido="/data/descargas/x")
    assert sq.casar(f"{RAIZ}/Peli 2020 1080p", _indices(ajeno), "uploadrr", RAIZ) == (None, "")


def test_no_encontrado_y_sin_ruta():
    assert sq.casar(f"{RAIZ}/Nada", _indices(torrent()), "", RAIZ) == (None, "")
    assert sq.casar(None, _indices(torrent()), "", RAIZ) == (None, "")
    assert sq.casar("", _indices(torrent()), "", RAIZ) == (None, "")


# --- estados -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("estado,progreso,esperado", [
    ("uploading", 1.0, "sembrando"), ("stalledUP", 1.0, "sembrando"), ("forcedUP", 1.0, "sembrando"),
    ("queuedUP", 1.0, "en_cola"),
    ("pausedUP", 1.0, "pausado"), ("stoppedUP", 1.0, "pausado"),
    ("checkingUP", 1.0, "comprobando"), ("checkingResumeData", 0.0, "comprobando"),
    ("moving", 1.0, "moviendo"),
    ("missingFiles", 1.0, "faltan_ficheros"), ("missingFiles", 0.4, "faltan_ficheros"),
    ("error", 0.4, "faltan_ficheros"), ("error", 1.0, "error"),
    ("downloading", 0.7, "incompleto"), ("stalledDL", 0.2, "incompleto"),
    ("stoppedDL", 0.5, "incompleto"), ("pausedUP", 0.9, "incompleto"),
    ("algoNuevoDeQbit", 1.0, "desconocido"),
])
def test_traduccion_de_estados(estado, progreso, esperado):
    clave, etiqueta = sq.estado_de(sq._resumir(torrent(estado=estado, progreso=progreso)))
    assert clave == esperado
    assert etiqueta and etiqueta[0].isupper()


def test_etiquetas_en_castellano():
    nombres = {sq.estado_de(sq._resumir(torrent(estado=e)))[1] for e in ("uploading", "pausedUP", "error", "missingFiles")}
    assert nombres == {"Sembrando", "Pausado", "Error", "Faltan ficheros"}


# --- consulta, caché y fallos --------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _cache_limpia():
    sq.olvidar_cache()
    yield
    sq.olvidar_cache()


@pytest.fixture
def reloj(monkeypatch):
    ahora = [1_000_000.0]
    monkeypatch.setattr(sq, "time", types.SimpleNamespace(time=lambda: ahora[0]))
    return ahora


def _servidor(http_falso, torrents, *, login=LOGIN_OK):
    """qBittorrent de mentira: el login y /torrents/info con esa lista."""
    def atiende(request):
        if request.url.path.endswith("/auth/login"):
            return login
        if request.url.path.endswith("/torrents/info"):
            return respuesta(200, json=torrents)
        return respuesta(404)
    http_falso.responde(atiende)


def _config(url=URL, qui=None, tag=""):
    with db() as conn:
        if url:
            set_setting(conn, "qbit.url", url)
            set_setting(conn, "qbit.username", "admin")
            set_setting(conn, "qbit.password", "CLAVE-DE-QBIT")
        if qui:
            set_setting(conn, "qbit.qui_proxy_url", qui)
        if tag:
            set_setting(conn, "qbit.tag", tag)


def _subida(estado="completed", ruta=None, subido=0):
    with db() as conn:
        return conn.execute(
            "INSERT INTO upload_jobs (title, path, status, stage, prepared_path, torrent_subido, created_at, updated_at)"
            " VALUES ('X', '', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (estado, estado, ruta, subido),
        ).lastrowid


def _salud(**kw):
    with db() as conn:
        return sq.salud_del_seeding(conn, **kw)


def test_una_sola_consulta_en_bloque_para_todas_las_subidas(http_falso):
    _config()
    a = _subida(ruta=f"{RAIZ}/A")
    b = _subida(ruta=f"{RAIZ}/B")
    c = _subida(ruta=f"{RAIZ}/C")
    _servidor(http_falso, [torrent("A", hash="a" * 40, ratio=2.5, subido=5_000),
                           torrent("B", hash="b" * 40, estado="missingFiles")])
    r = _salud()
    assert r["configurado"] and r["disponible"] and r["mensaje"] is None
    por_id = {i["job_id"]: i for i in r["items"]}
    assert por_id[a]["estado"] == "sembrando" and por_id[a]["ratio"] == 2.5 and por_id[a]["subido"] == 5_000
    assert por_id[a]["seeds"] == 12 and por_id[a]["peers"] == 3 and por_id[a]["hash"] == "a" * 40
    assert por_id[b]["estado"] == "faltan_ficheros" and por_id[b]["etiqueta"] == "Faltan ficheros"
    assert por_id[c]["estado"] == "no_encontrado"
    # login + una lista, no una consulta por subida
    assert [(p.method, p.url.path) for p in http_falso.peticiones] == [
        ("POST", "/api/v2/auth/login"), ("GET", "/api/v2/torrents/info")]


def test_solo_las_subidas_con_torrent_subido(http_falso):
    _config()
    _subida("running", f"{RAIZ}/A")
    _subida("queued", f"{RAIZ}/B")
    cancelada_con_torrent = _subida("cancelled", f"{RAIZ}/C", subido=1)
    completada = _subida("completed", None)
    _servidor(http_falso, [torrent("C")])
    items = {i["job_id"]: i for i in _salud()["items"]}
    assert set(items) == {cancelada_con_torrent, completada}
    assert items[cancelada_con_torrent]["estado"] == "sembrando"
    assert items[completada]["estado"] == "no_encontrado"


def test_cache_de_60_segundos_y_refrescar_se_la_salta(http_falso, reloj):
    _config()
    _subida(ruta=f"{RAIZ}/A")
    _servidor(http_falso, [torrent("A")])
    _salud()
    reloj[0] += sq.TTL_CACHE - 1
    _salud()
    assert len(http_falso.peticiones) == 2, "la segunda lectura sale de la caché"
    reloj[0] += 2
    _salud()
    assert len(http_falso.peticiones) == 4, "caducada la caché se vuelve a preguntar"
    _salud(refrescar=True)
    assert len(http_falso.peticiones) == 6


def test_cambiar_la_configuracion_no_sirve_la_cache_de_otra(http_falso):
    _config()
    _servidor(http_falso, [])
    _salud()
    _config(url="http://otro.lan:8080")
    _salud()
    assert len(http_falso.peticiones) == 4


def test_sin_qbittorrent_configurado_no_se_sale_a_la_red(http_falso):
    r = _salud()
    assert r == {"configurado": False, "disponible": False, "mensaje": sq.MENSAJE_SIN_CONFIGURAR,
                 "actualizado": None, "items": []}
    assert http_falso.peticiones == []


def test_qbittorrent_caido_no_rompe_y_el_fallo_se_recuerda_unos_segundos(http_falso, reloj):
    _config()
    _subida(ruta=f"{RAIZ}/A")
    http_falso.responde(falla_conexion())
    r = _salud()
    assert r["configurado"] and not r["disponible"] and r["items"] == []
    assert r["mensaje"] == sq.MENSAJE_SIN_RESPUESTA
    intentos = len(http_falso.peticiones)
    assert intentos == sq._INTENTOS, "reintenta una vez si no hay conexión"
    _salud()
    assert len(http_falso.peticiones) == intentos, "un fallo reciente no vuelve a esperar al timeout"
    reloj[0] += sq.TTL_FALLO + 1
    _salud()
    assert len(http_falso.peticiones) == 2 * intentos


def test_credenciales_malas_no_se_reintentan_y_se_dice(http_falso):
    _config()
    _servidor(http_falso, [], login=respuesta(401))
    r = _salud()
    assert not r["disponible"] and "incorrectos" in r["mensaje"]
    assert len(http_falso.peticiones) == 1


@pytest.mark.parametrize("respuesta_info", [respuesta(500), respuesta(200, cuerpo="<html>no soy json</html>"),
                                            respuesta(200, json={"no": "una lista"})])
def test_una_lista_que_no_lo_es_cuenta_como_sin_datos(http_falso, respuesta_info):
    _config()
    http_falso.responde(lambda r: respuesta_info if r.url.path.endswith("/info") else LOGIN_OK)
    r = _salud()
    assert not r["disponible"] and r["items"] == []


def test_con_el_proxy_de_qui_se_consulta_ese_y_no_qbit_url(http_falso):
    _config(qui=CLAVE_QUI)
    _subida(ruta=f"{RAIZ}/A")
    _servidor(http_falso, [torrent("A")])
    r = _salud()
    assert r["items"][0]["estado"] == "sembrando"
    assert all(p.url.host == "qui.lan" for p in http_falso.peticiones)
    assert http_falso.peticiones[0].url.path == "/proxy/CLAVE-SECRETA-DE-QUI/api/v2/auth/login"


def test_solo_lectura_nunca_se_toca_un_torrent(http_falso):
    _config()
    _subida(ruta=f"{RAIZ}/A")
    _servidor(http_falso, [torrent("A", estado="missingFiles")])
    _salud()
    assert {(p.method, p.url.path) for p in http_falso.peticiones} <= {
        ("POST", "/api/v2/auth/login"), ("GET", "/api/v2/torrents/info")}


def test_valores_raros_de_qbittorrent_no_rompen(http_falso):
    _config()
    _subida(ruta=f"{RAIZ}/A")
    _servidor(http_falso, [torrent("A", seeds=-1, peers=None, ratio="x", progreso=None, subido=None), "basura", 3])
    item = _salud()["items"][0]
    assert item["seeds"] is None and item["peers"] is None and item["ratio"] == 0.0 and item["subido"] == 0


# --- endpoint ------------------------------------------------------------------------------------------------

def test_endpoint_exige_sesion_y_no_se_confunde_con_un_id(client):
    assert client.get("/api/uploads/seeding").status_code == 401


def test_endpoint_sin_configurar_es_200(client, auth_headers):
    r = client.get("/api/uploads/seeding", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["disponible"] is False and r.json()["configurado"] is False


def test_endpoint_con_qbittorrent_caido_es_200_y_no_filtra_url_ni_claves(client, auth_headers, http_falso, caplog):
    _config(qui=CLAVE_QUI)
    http_falso.responde(falla_conexion(f"fallo conectando a {CLAVE_QUI}"))
    with caplog.at_level(logging.DEBUG):
        r = client.get("/api/uploads/seeding?refresh=true", headers=auth_headers)
    assert r.status_code == 200
    cuerpo = r.text + caplog.text
    for secreto in ("CLAVE-SECRETA-DE-QUI", "qui.lan", "CLAVE-DE-QBIT", "qbit.lan"):
        assert secreto not in cuerpo
    assert r.json()["disponible"] is False


def test_endpoint_devuelve_el_estado_de_cada_subida(client, auth_headers, http_falso):
    _config(tag="uploadrr")
    sid = _subida(ruta=f"{RAIZ}/A")
    _servidor(http_falso, [torrent("A", tags="uploadrr")])
    r = client.get("/api/uploads/seeding", headers=auth_headers)
    assert r.status_code == 200
    datos = r.json()
    assert datos["disponible"] and datos["actualizado"]
    assert datos["items"][0]["job_id"] == sid and datos["items"][0]["etiqueta"] == "Sembrando"
    assert "password" not in r.text
