"""integrations/http_cliente.py: la única puerta de las peticiones salientes, y lo que hereda de urllib."""
from __future__ import annotations

import ssl

import httpx
import pytest

from emuwarez_uploadrr.integrations import http_cliente
from tests.http_falso import falla_conexion, respuesta, tiempo_agotado

_URL = "https://emuwarez.invalid/api/torrents/filter?api_token=CLAVESECRETA123&perPage=1"


@pytest.fixture
def clientes_reales():
    http_cliente.cerrar_clientes()
    yield
    http_cliente.cerrar_clientes()


def _contexto(cliente: httpx.Client) -> ssl.SSLContext:
    return cliente._transport._pool._ssl_context


def test_verify_true_usa_los_certificados_del_sistema(clientes_reales):
    contexto = _contexto(http_cliente.cliente(True))
    assert contexto.verify_mode == ssl.CERT_REQUIRED and contexto.check_hostname is True
    # Los del sistema, como urllib (ssl.create_default_context), no solo los de certifi.
    assert contexto.cert_store_stats() == ssl.create_default_context().cert_store_stats()


def test_verify_false_no_comprueba_nada(clientes_reales):
    contexto = _contexto(http_cliente.cliente(False))
    assert contexto.verify_mode == ssl.CERT_NONE and contexto.check_hostname is False


def test_un_cliente_compartido_por_cada_verify(clientes_reales):
    assert http_cliente.cliente(True) is http_cliente.cliente(True)
    assert http_cliente.cliente(False) is http_cliente.cliente(False)
    assert http_cliente.cliente(True) is not http_cliente.cliente(False)
    viejo = http_cliente.cliente(True)
    http_cliente.cerrar_clientes()
    assert viejo.is_closed and http_cliente.cliente(True) is not viejo


def test_el_cliente_compartido_sigue_redirecciones_como_urllib(clientes_reales):
    cliente = http_cliente.cliente(True)
    assert cliente.follow_redirects is True and cliente.max_redirects == 10


def test_pedir_devuelve_la_respuesta_leida(http_falso):
    http_falso.responde(respuesta(200, cuerpo=b"hola"))
    r = http_cliente.pedir("get", "http://radarr:7878/x", timeout=5)
    assert r.status_code == 200 and r.content == b"hola"
    assert http_falso.ultima.method == "GET"


def test_un_cuerpo_sin_content_type_va_como_formulario_como_en_urllib(http_falso):
    http_cliente.pedir("POST", "https://api.imgbb.com/1/upload", contenido=b"", timeout=5)
    assert http_falso.ultima.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert http_falso.ultima.headers["Content-Length"] == "0"
    http_cliente.pedir("POST", "https://x.invalid/", contenido=b"{}", cabeceras={"content-type": "application/json"},
                       timeout=5)
    assert http_falso.ultima.headers.get_list("Content-Type") == ["application/json"]
    http_cliente.pedir("GET", "https://x.invalid/", timeout=5)
    assert "Content-Type" not in http_falso.ultima.headers


class _CuerpoEnTrozos(httpx.SyncByteStream):
    """Un cuerpo que reparte en trozos y apunta cuántos se han pedido: prueba que la lectura se corta a tiempo."""

    def __init__(self, trozos: int, tamano: int, relleno: bytes = b"a") -> None:
        self.trozos, self.tamano, self.relleno, self.pedidos = trozos, tamano, relleno, 0

    def __iter__(self):
        for _ in range(self.trozos):
            self.pedidos += 1
            yield self.relleno * self.tamano


def test_con_limite_no_se_leen_mas_trozos_que_los_necesarios(http_falso):
    cuerpo = _CuerpoEnTrozos(trozos=1000, tamano=1024)
    http_falso.responde(lambda req: httpx.Response(200, headers={"X-Uno": "1"}, stream=cuerpo, request=req))
    r = http_cliente.pedir("POST", "https://x.invalid/", contenido=b"", timeout=5, limite=4096)
    assert r.status_code == 200 and r.headers["X-Uno"] == "1"
    assert r.content == b"a" * 4096
    assert cuerpo.pedidos == 4  # 4 trozos de 1 KiB llenan el límite; los otros 996 no se piden


def test_con_limite_se_pide_sin_comprimir_y_no_se_descomprime(http_falso):
    import gzip

    comprimido = gzip.compress(b"A" * (16 * 1024 * 1024))
    http_falso.responde(lambda req: httpx.Response(
        200, headers={"Content-Encoding": "gzip"}, stream=httpx.ByteStream(comprimido), request=req))
    r = http_cliente.pedir("POST", "https://x.invalid/", contenido=b"", timeout=5, limite=4096)
    assert http_falso.ultima.headers["Accept-Encoding"] == "identity"
    assert len(r.content) == 4096 and r.content != b"A" * 4096  # tal cual llegó: sin descomprimir
    assert "content-encoding" not in r.headers


def test_con_limite_una_cabecera_no_ascii_no_rompe_la_respuesta(http_falso):
    http_falso.responde(lambda req: httpx.Response(
        200, headers=[(b"Server", "Caf\xe9".encode("latin-1")), (b"X-Otra", b"ok")],
        stream=httpx.ByteStream(b"hola"), request=req))
    r = http_cliente.pedir("POST", "https://x.invalid/", contenido=b"", timeout=5, limite=4096)
    assert r.content == b"hola" and r.headers["X-Otra"] == "ok"
    assert dict(r.headers.raw)[b"Server"] == "Caf\xe9".encode("latin-1")


def test_con_limite_un_error_http_lleva_el_cuerpo_cortado(http_falso):
    http_falso.responde(respuesta(400, cuerpo=b"b" * 1_000_000))
    with pytest.raises(http_cliente.ErrorHTTP) as e:
        http_cliente.pedir("POST", "https://x.invalid/", contenido=b"", timeout=5, limite=4096)
    assert e.value.status == 400 and len(e.value.contenido) == 4096


def test_con_limite_un_cuerpo_corto_llega_entero(http_falso):
    http_falso.responde(respuesta(200, cuerpo=b"corto"))
    assert http_cliente.pedir("GET", "https://x.invalid/", timeout=5, limite=4096).content == b"corto"


def test_un_4xx_o_5xx_es_error_http_con_codigo_cabeceras_y_cuerpo(http_falso):
    http_falso.responde(respuesta(429, cuerpo="más despacio".encode(), headers={"Retry-After": "30"}))
    with pytest.raises(http_cliente.ErrorHTTP) as info:
        http_cliente.pedir("GET", _URL, timeout=5)
    exc = info.value
    assert exc.status == 429
    assert exc.headers["Retry-After"] == "30"
    assert exc.contenido == "más despacio".encode()
    assert exc.texto() == "más despacio" and exc.texto(2) == "m\ufffd"
    assert "CLAVESECRETA123" not in str(exc) and "CLAVESECRETA123" not in repr(exc)


@pytest.mark.parametrize("fallo,agotado", [
    (falla_conexion("[Errno 111] Connection refused"), False),
    (httpx.ReadError("Connection reset by peer"), False),
    (httpx.RemoteProtocolError("Server disconnected without sending a response."), False),
    (tiempo_agotado(), True),
    (httpx.ReadTimeout("The read operation timed out"), True),
])
def test_sin_respuesta_es_error_de_conexion(http_falso, fallo, agotado):
    http_falso.responde(fallo)
    with pytest.raises(http_cliente.ErrorConexion) as info:
        http_cliente.pedir("GET", _URL, timeout=5)
    assert info.value.tiempo_agotado is agotado
    assert info.value.motivo == str(fallo)
    assert info.value.__cause__ is None and info.value.__suppress_context__ is True
    assert "CLAVESECRETA123" not in str(info.value) and "CLAVESECRETA123" not in repr(info.value)


def test_sigue_las_redirecciones_de_un_get(http_falso):
    http_falso.responde(
        respuesta(301, headers={"Location": "https://radarr.example/api/v3/movie"}),
        respuesta(200, json=[]),
    )
    r = http_cliente.pedir("GET", "http://radarr.example/api/v3/movie", cabeceras={"X-Api-Key": "K"}, timeout=5)
    assert r.status_code == 200
    assert http_falso.urls == ["http://radarr.example/api/v3/movie", "https://radarr.example/api/v3/movie"]
    assert http_falso.ultima.headers["X-Api-Key"] == "K"  # urllib también la reenviaba


def test_un_post_redirigido_con_303_sigue_como_get_sin_cuerpo(http_falso):
    http_falso.responde(respuesta(303, headers={"Location": "/hecho"}), respuesta(200))
    http_cliente.pedir("POST", "https://x.invalid/form", contenido=b"a=1", timeout=5)
    assert [p.method for p in http_falso.peticiones] == ["POST", "GET"]
    assert http_falso.ultima.content == b""


def test_un_bucle_de_redirecciones_es_error_de_conexion(http_falso):
    http_falso.responde(respuesta(302, headers={"Location": "https://x.invalid/otra"}))
    with pytest.raises(http_cliente.ErrorConexion):
        http_cliente.pedir("GET", "https://x.invalid/", timeout=5)
    assert len(http_falso.peticiones) == 11  # la primera y 10 redirecciones, como urllib


def test_el_cliente_compartido_no_guarda_cookies(http_falso):
    """urllib no guardaba ninguna: la cookie de un servicio no viaja en la petición siguiente."""
    http_falso.responde(respuesta(200, headers={"Set-Cookie": "laravel_session=abc; path=/"}), respuesta(200))
    http_cliente.pedir("GET", "https://emuwarez.invalid/api/a", timeout=5)
    http_cliente.pedir("GET", "https://emuwarez.invalid/api/b", timeout=5)
    assert "Cookie" not in http_falso.ultima.headers
    assert not http_cliente.cliente(True).cookies


def test_una_sesion_si_guarda_las_cookies(http_falso):
    http_falso.responde(respuesta(200, headers={"Set-Cookie": "SID=abc; path=/"}), respuesta(200))
    with http_cliente.sesion() as s:
        http_cliente.pedir("POST", "http://qbit:8080/api/v2/auth/login", contenido=b"x", timeout=5, en_sesion=s)
        http_cliente.pedir("GET", "http://qbit:8080/api/v2/app/version", timeout=5, en_sesion=s)
    assert http_falso.ultima.headers["Cookie"] == "SID=abc"
    # Y no se queda en el compartido.
    http_cliente.pedir("GET", "http://qbit:8080/api/v2/app/version", timeout=5)
    assert "Cookie" not in http_falso.ultima.headers


def test_una_url_mal_formada_sale_tal_cual(http_falso):
    with pytest.raises(httpx.InvalidURL):
        http_cliente.pedir("GET", "http://radarr:abc/api", timeout=5)


def test_texto_cambia_lo_que_no_es_utf8():
    assert http_cliente.texto(b"caf\xe9") == "caf\ufffd"
    assert http_cliente.texto(b"abcdef", 3) == "abc"


def test_ninguna_peticion_sale_por_otro_lado():
    """Una sola puerta: nadie más importa urllib.request, http.client ni httpx en el código de la aplicación."""
    from pathlib import Path
    import re

    raiz = Path(__file__).resolve().parent.parent / "emuwarez_uploadrr"
    prohibido = re.compile(r"^\s*(?:import|from)\s+(?:urllib\.request|urllib\.error|http\.client|httpx|requests)\b",
                           re.M)
    culpables = [
        str(f.relative_to(raiz)) for f in raiz.rglob("*.py")
        if f.name != "http_cliente.py" and prohibido.search(f.read_text(encoding="utf-8"))
    ]
    assert culpables == []


# arr_request: los mismos errores de siempre, ahora desde http_cliente.

def test_arr_request_devuelve_el_json_con_sus_cabeceras(http_falso):
    from emuwarez_uploadrr.integrations.arr_base import arr_request
    http_falso.responde(respuesta(200, json=[{"id": 1}]), respuesta(200))
    assert arr_request("GET", "http://radarr:7878/api/v3/movie", "K") == [{"id": 1}]
    p = http_falso.ultima
    assert p.headers["X-Api-Key"] == "K" and p.headers["User-Agent"] == "emuwarez-uploadrr/3"
    assert p.extensions["timeout"]["read"] == 15
    assert arr_request("PUT", "http://radarr:7878/api/v3/movie/1", "K", data={"a": 1}) == {}
    assert http_falso.ultima.content == b'{"a": 1}'


@pytest.mark.parametrize("fallo,tipo,texto", [
    (respuesta(401), "ArrAuthError", "Autenticación fallida en http://radarr:7878/api/v3/movie (HTTP 401)"),
    (respuesta(403), "ArrAuthError", "(HTTP 403)"),
    (respuesta(500, cuerpo=b"boom"), "ArrApiError", "HTTP 500 desde http://radarr:7878/api/v3/movie: boom"),
    (respuesta(200, cuerpo=b"<html>"), "ArrApiError", "Respuesta no-JSON"),
    (falla_conexion("[Errno 111] Connection refused"), "ArrConnectionError",
     "No se pudo conectar con http://radarr:7878/api/v3/movie: [Errno 111] Connection refused"),
    (tiempo_agotado(), "ArrConnectionError", "Timeout conectando con http://radarr:7878/api/v3/movie"),
])
def test_arr_request_traduce_los_errores(http_falso, fallo, tipo, texto):
    from emuwarez_uploadrr.integrations import arr_base
    http_falso.responde(fallo)
    with pytest.raises(arr_base.ArrClientError) as info:
        arr_base.arr_request("GET", "http://radarr:7878/api/v3/movie", "K")
    assert type(info.value).__name__ == tipo
    assert texto in str(info.value)
    if tipo == "ArrApiError" and info.value.status_code:
        assert info.value.status_code == 500 and info.value.body == "boom"
