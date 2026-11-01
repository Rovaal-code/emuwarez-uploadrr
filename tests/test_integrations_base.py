"""Tests for integrations/base.py::request_json: the hard wall-clock deadline, the errors and what they never carry.

httpx's own `timeout`, like urlopen's, only bounds each phase once a socket
exists — DNS resolution (getaddrinfo, which runs first) is NOT covered by it,
so a stuck/misconfigured resolver can hang past `timeout` forever with no
exception ever raised. request_json runs the call on a daemon thread with a
hard deadline (http_cliente.con_plazo), which bounds the WHOLE call regardless
of what's actually stuck.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time

import pytest

from emuwarez_uploadrr.integrations import http_cliente
from emuwarez_uploadrr.integrations.base import IntegrationError, build_url, request_json, url_sin_claves
from tests.http_falso import falla_conexion, respuesta, tiempo_agotado

_PROXIES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


@pytest.fixture
def dns_atascado(monkeypatch):
    """getaddrinfo no vuelve nunca (hasta que acaba el test): un resolutor colgado de verdad, con el cliente real."""
    for nombre in _PROXIES:
        monkeypatch.delenv(nombre, raising=False)
    soltar = threading.Event()
    llamadas = []

    def _cuelga(host, *args, **kwargs):
        llamadas.append(host)
        soltar.wait(60)
        raise socket.gaierror(-3, "Temporary failure in name resolution")

    http_cliente.cerrar_clientes()  # que el cliente se cree sin los proxies del entorno
    monkeypatch.setattr(socket, "getaddrinfo", _cuelga)
    yield llamadas
    soltar.set()
    http_cliente.cerrar_clientes()


def test_hanging_dns_raises_within_the_deadline_not_forever(dns_atascado):
    """A real DNS-level hang (getaddrinfo never returns) under the real httpx
    client: request_json must still come back with a clear error by
    timeout + 5, well before the caller would consider it "frozen"."""
    start = time.monotonic()
    with pytest.raises(IntegrationError, match="Tiempo de espera agotado") as info:
        request_json("GET", "https://example.invalid/api?api_key=CLAVETMDB456", timeout=1)
    elapsed = time.monotonic() - start
    assert dns_atascado == ["example.invalid"], "la llamada no llegó a resolver el nombre"
    assert 5.5 < elapsed < 10
    assert "CLAVETMDB456" not in str(info.value)
    assert info.value.status is None


def test_con_plazo_deja_atras_la_llamada_colgada_y_relanza_los_errores():
    soltar = threading.Event()
    try:
        start = time.monotonic()
        with pytest.raises(http_cliente.PlazoAgotado):
            http_cliente.con_plazo(lambda: soltar.wait(60), 0.2)
        assert time.monotonic() - start < 2
    finally:
        soltar.set()
    assert http_cliente.con_plazo(lambda: 7, 1) == 7
    with pytest.raises(KeyError):
        http_cliente.con_plazo(lambda: {}["x"], 1)


def test_normal_call_still_returns_the_response(http_falso):
    http_falso.responde(respuesta(200, cuerpo=b'{"ok": true}'))
    assert request_json("GET", "https://example.invalid/api") == {"ok": True}


def test_un_cuerpo_vacio_es_un_dict_vacio(http_falso):
    http_falso.responde(respuesta(204))
    assert request_json("DELETE", "https://example.invalid/api/v3/x/1") == {}


def test_lo_que_no_es_utf8_se_cambia_en_vez_de_reventar(http_falso):
    http_falso.responde(respuesta(200, cuerpo='{"title": "café"}'.encode("latin-1")))
    assert request_json("GET", "https://example.invalid/api") == {"title": "caf\ufffd"}


def test_las_cabeceras_y_el_cuerpo_json_van_como_antes(http_falso):
    http_falso.responde(respuesta(201, json={"id": 3}))
    datos = {"title": "Película", "tags": [1, 2]}
    assert request_json("POST", "http://radarr:7878/api/v3/movie", api_key="K", data=datos,
                        headers={"X-Extra": "1"}) == {"id": 3}
    p = http_falso.ultima
    assert p.method == "POST"
    assert p.content == json.dumps(datos).encode("utf-8")  # el mismo json.dumps de siempre, byte a byte
    assert p.headers["Content-Type"] == "application/json"
    assert p.headers["Accept"] == "application/json"
    assert p.headers["User-Agent"] == "emuwarez-uploadrr-cli/2"
    assert p.headers["X-Api-Key"] == "K"
    assert p.headers["X-Extra"] == "1"


def test_el_timeout_vale_para_cada_fase(http_falso):
    request_json("GET", "https://example.invalid/api", timeout=7)
    assert http_falso.ultima.extensions["timeout"] == {"connect": 7, "read": 7, "write": 7, "pool": 7}


@pytest.mark.parametrize("verify", [True, False])
def test_verify_ssl_elige_el_cliente(http_falso, monkeypatch, verify):
    pedidos = []
    original = http_cliente.cliente
    monkeypatch.setattr(http_cliente, "cliente", lambda v=True: pedidos.append(v) or original(v))
    request_json("GET", "https://radarr.local/api", verify_ssl=verify)
    assert pedidos == [verify]


_URL_CON_CLAVE = "https://emuwarez.invalid/api/requests?api_token=CLAVESECRETA123&page=1"


@pytest.mark.parametrize("fallo,status", [
    (respuesta(401, cuerpo=b"no autorizado"), 401),
    (respuesta(429, cuerpo=b"slow down", headers={"Retry-After": "30"}), 429),
    (respuesta(503, cuerpo=b"mantenimiento"), 503),
    (falla_conexion("[Errno -2] Name or service not known"), None),
    (tiempo_agotado(), None),
])
def test_el_error_no_lleva_la_clave(http_falso, fallo, status):
    """Estos mensajes acaban en app.log, task_runs y la respuesta HTTP."""
    http_falso.responde(fallo)
    with pytest.raises(IntegrationError) as info:
        request_json("GET", _URL_CON_CLAVE)
    assert info.value.status == status
    assert "CLAVESECRETA123" not in str(info.value)
    assert "CLAVESECRETA123" not in repr(info.value)
    assert "api_token=***" in str(info.value)
    assert info.value.__cause__ is None


def test_los_mensajes_de_error_siguen_igual(http_falso):
    http_falso.responde(respuesta(404, cuerpo=b"Not Found"))
    with pytest.raises(IntegrationError, match=r"^HTTP 404 en http://radarr:7878/api/v3/movie/9: Not Found$"):
        request_json("GET", "http://radarr:7878/api/v3/movie/9")
    http_falso.responde(falla_conexion("[Errno 111] Connection refused"))
    with pytest.raises(IntegrationError,
                       match=r"^No se pudo conectar con http://radarr:7878/api: \[Errno 111\] Connection refused$"):
        request_json("GET", "http://radarr:7878/api")


def test_ni_el_log_ni_la_traza_llevan_la_clave(http_falso, caplog):
    """Ni httpx (que apunta cada petición con la URL) ni quien registre el error con su traza."""
    caplog.set_level(logging.DEBUG)
    http_falso.responde(
        respuesta(200, json={"data": []}),
        respuesta(500, cuerpo=b"error en /api?api_token=CLAVESECRETA123"),
    )
    request_json("GET", _URL_CON_CLAVE)
    try:
        request_json("GET", _URL_CON_CLAVE)
    except IntegrationError:
        logging.getLogger("emuwarez_uploadrr.prueba").exception("falló la petición")
    assert "falló la petición" in caplog.text
    assert "CLAVESECRETA123" not in caplog.text


def test_una_respuesta_no_json_no_lleva_la_clave(http_falso):
    http_falso.responde(respuesta(200, cuerpo=b"<html>mantenimiento</html>"))
    with pytest.raises(IntegrationError, match="Respuesta no JSON") as info:
        request_json("GET", _URL_CON_CLAVE)
    assert "CLAVESECRETA123" not in str(info.value)


def test_un_error_raro_solo_dice_su_tipo(http_falso):
    def _revienta(request):
        raise ValueError(f"algo raro con {request.url}")
    http_falso.responde(_revienta)
    with pytest.raises(IntegrationError, match=r"Error con .*: ValueError$") as info:
        request_json("GET", _URL_CON_CLAVE)
    assert "CLAVESECRETA123" not in str(info.value)


def test_el_cuerpo_del_error_no_repite_la_clave_codificada(http_falso):
    # La clave viaja con %2B y %2F; el servidor puede repetir la URL pedida tal cual, o la clave ya decodificada.
    url = "https://emuwarez.invalid/api/requests?api_token=ab%2Bcd%2Fef&page=1"
    for eco in (b"Bad request for /api?api_token=ab%2Bcd%2Fef", b"clave recibida: ab+cd/ef"):
        http_falso.responde(respuesta(400, cuerpo=eco))
        with pytest.raises(IntegrationError) as info:
            request_json("GET", url)
        texto = str(info.value)
        assert "ab%2Bcd%2Fef" not in texto and "ab+cd/ef" not in texto and "cd%2Fef" not in texto


def test_url_sin_claves_deja_el_resto_igual():
    assert url_sin_claves(_URL_CON_CLAVE) == "https://emuwarez.invalid/api/requests?api_token=***&page=1"
    assert url_sin_claves("http://radarr:7878/api/v3/movie") == "http://radarr:7878/api/v3/movie"


def test_url_sin_claves_quita_usuario_y_contrasena():
    assert url_sin_claves("http://usu:pass@radarr:7878/api?apikey=K") == "http://radarr:7878/api?apikey=***"


def test_el_cuerpo_del_error_no_repite_la_clave(http_falso):
    http_falso.responde(respuesta(400, cuerpo=b"Bad request for /api?api_token=CLAVESECRETA123"))
    with pytest.raises(IntegrationError) as info:
        request_json("GET", _URL_CON_CLAVE)
    assert "CLAVESECRETA123" not in str(info.value)
    assert "api_token=***" in str(info.value)


def test_el_motivo_de_conexion_no_repite_la_clave(http_falso):
    http_falso.responde(falla_conexion("proxy rechazó /api/requests?api_token=CLAVESECRETA123"))
    with pytest.raises(IntegrationError) as info:
        request_json("GET", _URL_CON_CLAVE)
    assert "CLAVESECRETA123" not in str(info.value)


def test_build_url_repite_la_clave_de_un_valor_lista_y_se_salta_los_none():
    url = build_url("https://t.x", "/api/requests/filter", {"filled": 0, "category_id[]": [1, 2], "name": None})
    assert url == "https://t.x/api/requests/filter?filled=0&category_id%5B%5D=1&category_id%5B%5D=2"
