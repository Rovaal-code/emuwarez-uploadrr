"""La única puerta de las peticiones HTTP salientes: Radarr, Sonarr, eMuwarez, TMDb, qBittorrent, los proveedores de
imágenes, Discord, Telegram y el manifiesto de versiones salen todos por `pedir`.

Hereda lo que hacía urllib, para que pasar a httpx no cambie nada visto desde fuera:

- Certificados: los del sistema (`ssl.create_default_context()`, que también lee SSL_CERT_FILE/SSL_CERT_DIR), no
  los de certifi que httpx usaría por su cuenta: una CA propia añadida al sistema sigue valiendo. `verify=False` usa
  el mismo contexto sin verificar que usaba urllib.
- Redirecciones: se siguen (urllib también), hasta 10 como urllib.
- Sin cookies: urllib no guardaba ninguna. El cliente compartido las rechaza todas, para que una cookie de un
  servicio no viaje en la petición siguiente; quien necesita sesión (el inicio de sesión de qBittorrent) abre la
  suya con `sesion()`.
- Proxies del entorno (HTTP_PROXY, HTTPS_PROXY, NO_PROXY), como urllib.
- `timeout` vale para cada fase (conectar, leer, escribir, esperar conexión libre), como el `timeout` de urlopen.
- Un cuerpo sin Content-Type va como `application/x-www-form-urlencoded`, que es lo que ponía urllib.
- Un 4xx/5xx es una excepción (`ErrorHTTP`, con el código, las cabeceras y el cuerpo), como el HTTPError de urllib;
  los fallos de red y los tiempos agotados son `ErrorConexion`.

Ni el texto de estas excepciones ni su `repr` llevan la URL: eMuwarez y TMDb llevan la clave en ella.

Hay dos clientes compartidos (con y sin verificar el certificado), que reaprovechan conexiones y son seguros entre
hilos. `con_plazo` pone un límite de reloj a una llamada entera: el `timeout` de httpx, como el de urllib, no cubre
la resolución DNS (getaddrinfo), y un resolutor atascado colgaría la llamada para siempre.
"""
from __future__ import annotations

import http.cookiejar
import logging
import ssl
import threading
import urllib.parse
from typing import Any, Callable, Optional, TypeVar

import httpx

_MAX_REDIRECCIONES = 10  # el max_redirections de urllib
# Únicos hosts a los que se permite http:// cuando se exige una conexión segura (una instancia local de pruebas).
HOSTS_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})

# httpx apunta cada petición en INFO con la URL entera, y la de eMuwarez y TMDb lleva la clave: que no llegue a
# app.log ni a la consola, aunque nadie haya llamado a setup_app_logging (la CLI). Sus avisos sí pasan.
for _nombre in ("httpx", "httpcore"):
    logging.getLogger(_nombre).setLevel(logging.WARNING)

# Solo para los tests (tests/http_falso.py): un transporte falso en vez de la red.
_transporte_de_prueba: Optional[httpx.BaseTransport] = None

_clientes: dict[bool, httpx.Client] = {}
_candado = threading.Lock()

T = TypeVar("T")


class ErrorHTTP(Exception):
    """La respuesta llegó con un código 4xx/5xx."""

    def __init__(self, respuesta: httpx.Response):
        super().__init__(f"HTTP {respuesta.status_code}")
        self.respuesta = respuesta
        self.status = respuesta.status_code
        self.headers = respuesta.headers
        self.contenido = respuesta.content

    def texto(self, limite: Optional[int] = None) -> str:
        return texto(self.contenido, limite)


class ErrorConexion(Exception):
    """No hubo respuesta: DNS, conexión rechazada, TLS, corte a medias o tiempo agotado."""

    def __init__(self, motivo: str, *, tiempo_agotado: bool = False):
        super().__init__(motivo)
        self.motivo = motivo
        self.tiempo_agotado = tiempo_agotado


class PlazoAgotado(Exception):
    """La llamada entera pasó del límite de `con_plazo` y se dejó atrás (sigue en un hilo daemon)."""


def texto(contenido: bytes, limite: Optional[int] = None) -> str:
    """El cuerpo como texto UTF-8, con lo que no lo sea cambiado por �."""
    return (contenido if limite is None else contenido[:limite]).decode("utf-8", errors="replace")


def _contexto_ssl(verify: bool) -> ssl.SSLContext:
    # Los mismos contextos que urllib: el de por defecto (certificados del sistema) o el que no verifica nada.
    return ssl.create_default_context() if verify else ssl._create_unverified_context()


def _sin_cookies() -> http.cookiejar.CookieJar:
    # allowed_domains vacío: la política rechaza toda cookie que llegue, así que nunca se reenvía ninguna.
    return http.cookiejar.CookieJar(policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))


def _nuevo_cliente(verify: bool, *, con_cookies: bool) -> httpx.Client:
    # Límite conocido: el pool de conexiones (100 por defecto) es de todos los servidores a los que llama la
    # aplicación. Una llamada que `con_plazo` abandona porque el DNS no contesta sigue ocupando su plaza hasta que
    # el resolutor devuelva algo; con más de 100 a la vez, las siguientes llamadas (a cualquier servidor) fallarían
    # con ErrorConexion por el timeout del pool. Con urllib cada llamada abría su propia conexión y no pasaba.
    return httpx.Client(
        verify=_contexto_ssl(verify),
        follow_redirects=True,
        max_redirects=_MAX_REDIRECCIONES,
        cookies=None if con_cookies else _sin_cookies(),
        transport=_transporte_de_prueba,  # con uno puesto, httpx ignora los proxies del entorno
    )


def cliente(verify: bool = True) -> httpx.Client:
    """El cliente compartido (sin cookies) para verificar o no el certificado. Se crea la primera vez."""
    verify = bool(verify)
    with _candado:
        actual = _clientes.get(verify)
        if actual is None:
            actual = _clientes[verify] = _nuevo_cliente(verify, con_cookies=False)
        return actual


def sesion(verify: bool = True) -> httpx.Client:
    """Un cliente propio que sí guarda cookies, para una conversación con sesión (`with sesion() as s:`)."""
    return _nuevo_cliente(verify, con_cookies=True)


def cerrar_clientes() -> None:
    """Cierra los clientes compartidos; el siguiente `cliente()` crea uno nuevo (tests, o cambiar de transporte)."""
    with _candado:
        viejos = list(_clientes.values())
        _clientes.clear()
    for viejo in viejos:
        viejo.close()


def _motivo(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def _leer_hasta(usar: httpx.Client, metodo: str, url: str, cabeceras: dict[str, str], contenido: Optional[bytes],
                timeout: float, limite: int) -> httpx.Response:
    """La respuesta con el cuerpo cortado a `limite` bytes: se lee por trozos y se cierra la conexión al llegar.

    Se pide sin comprimir (`Accept-Encoding: identity`, como hacía urllib) y se lee el cuerpo tal cual llega, sin
    descomprimir: un servidor que comprima aun así no puede inflar la memoria con un gzip pequeño. Por eso la
    respuesta devuelta no lleva `Content-Encoding` ni `Content-Length`: su cuerpo ya es lo leído."""
    if not any(k.lower() == "accept-encoding" for k in cabeceras):
        cabeceras = {**cabeceras, "Accept-Encoding": "identity"}
    with usar.stream(metodo, url, headers=cabeceras, content=contenido, timeout=httpx.Timeout(timeout)) as recibida:
        cuerpo = bytearray()
        for trozo in recibida.iter_raw():
            cuerpo.extend(trozo[: limite - len(cuerpo)])
            if len(cuerpo) >= limite:
                break
        # En bytes, tal como llegaron: pasar por texto rompería con una cabecera no ASCII (UnicodeEncodeError).
        propias = [(k, v) for k, v in recibida.headers.raw if k.lower() not in (b"content-encoding", b"content-length")]
        return httpx.Response(recibida.status_code, headers=propias, content=bytes(cuerpo), request=recibida.request)


def _es_segura(url: str) -> bool:
    partes = urllib.parse.urlsplit(url)
    return partes.scheme == "https" or (partes.scheme == "http" and (partes.hostname or "") in HOSTS_LOOPBACK)


def _pedir_solo_seguras(usar: httpx.Client, metodo: str, url: str, cabeceras: dict[str, str],
                        contenido: Optional[bytes], timeout: float) -> httpx.Response:
    """Sigue las redirecciones a mano para mirar el destino de cada salto antes de pedirlo."""
    respuesta = usar.request(metodo, url, headers=cabeceras, content=contenido,
                             timeout=httpx.Timeout(timeout), follow_redirects=False)
    for _ in range(_MAX_REDIRECCIONES):
        siguiente = respuesta.next_request
        if siguiente is None:
            return respuesta
        if not _es_segura(str(siguiente.url)):
            raise ErrorConexion("redirección a una dirección sin https")
        respuesta = usar.send(siguiente, follow_redirects=False)
    if respuesta.next_request is not None:
        raise ErrorConexion("demasiadas redirecciones")
    return respuesta


def pedir(
    metodo: str,
    url: str,
    *,
    cabeceras: Optional[dict[str, str]] = None,
    contenido: Optional[bytes] = None,
    timeout: float,
    verify: bool = True,
    en_sesion: Optional[httpx.Client] = None,
    limite: Optional[int] = None,
    solo_seguras: bool = False,
) -> httpx.Response:
    """Hace la petición y devuelve la respuesta ya leída entera (2xx/3xx tras seguir las redirecciones).

    Con `limite` (bytes) solo se leen los primeros `limite` bytes del cuerpo y se corta ahí, para no traerse
    en memoria el cuerpo enorme de un servidor ajeno cuando solo interesa el principio.

    Lanza `ErrorHTTP` con un 4xx/5xx y `ErrorConexion` si no hay respuesta. Cualquier otra excepción (una URL mal
    formada, por ejemplo) sale tal cual. `en_sesion` es un cliente de `sesion()`, para que viajen sus cookies.

    Con `solo_seguras` cada redirección se comprueba antes de seguirla y una que baje a `http://` (salvo en
    loopback) corta con `ErrorConexion`: la URL de la petición puede llevar una clave y no debe viajar en claro."""
    cabeceras = dict(cabeceras or {})
    if contenido is not None and not any(k.lower() == "content-type" for k in cabeceras):
        cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
    usar = en_sesion if en_sesion is not None else cliente(verify)
    try:
        if solo_seguras and limite is None:
            respuesta = _pedir_solo_seguras(usar, metodo.upper(), url, cabeceras, contenido, timeout)
        elif limite is None:
            respuesta = usar.request(
                metodo.upper(), url, headers=cabeceras, content=contenido, timeout=httpx.Timeout(timeout),
            )
        else:
            respuesta = _leer_hasta(usar, metodo.upper(), url, cabeceras, contenido, timeout, limite)
    except httpx.TimeoutException as exc:
        raise ErrorConexion(_motivo(exc), tiempo_agotado=True) from None
    except httpx.RequestError as exc:  # red, TLS, protocolo, demasiadas redirecciones
        raise ErrorConexion(_motivo(exc)) from None
    if respuesta.status_code >= 400:
        raise ErrorHTTP(respuesta)
    return respuesta


def con_plazo(funcion: Callable[[], T], segundos: float) -> T:
    """Llama a `funcion` con un límite de reloj para la llamada entera, DNS incluido.

    Corre en un hilo *daemon* y se espera como mucho `segundos`: si no ha vuelto, lanza `PlazoAgotado` y el hilo
    se queda atrás sin impedir que el proceso termine (un ejecutor no daemon se quedaría esperándolo al cerrar).
    Lo que lance `funcion` se relanza aquí."""
    resultado: dict[str, Any] = {}

    def _trabajo() -> None:
        try:
            resultado["valor"] = funcion()
        except BaseException as exc:  # noqa: BLE001 — se relanza en el hilo que llama
            resultado["error"] = exc

    hilo = threading.Thread(target=_trabajo, daemon=True, name="http-con-plazo")
    hilo.start()
    hilo.join(timeout=segundos)
    if hilo.is_alive():
        raise PlazoAgotado()
    if "error" in resultado:
        raise resultado["error"]
    return resultado["valor"]


__all__ = [
    "ErrorConexion", "ErrorHTTP", "PlazoAgotado",
    "cerrar_clientes", "cliente", "con_plazo", "pedir", "sesion", "texto",
]
