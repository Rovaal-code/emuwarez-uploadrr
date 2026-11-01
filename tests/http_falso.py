"""Un servidor HTTP de mentira para los tests: un `httpx.MockTransport` puesto en `integrations.http_cliente`.

Toda petición saliente de la aplicación pasa por `http_cliente.pedir`, así que con el fixture `http_falso`
(conftest.py) ninguna llega a la red y cada una queda apuntada en `.peticiones`::

    def test_algo(http_falso):
        http_falso.responde(respuesta(200, json={"ok": True}))
        ...
        assert http_falso.ultima.headers["X-Api-Key"] == "k"

Dentro de una función sin el fixture vale igual `with servidor_falso(respuesta(204)) as servidor:`.

`responde` acepta una o varias respuestas en orden (la última se repite). Cada una puede ser una `respuesta(...)`,
una excepción de httpx que se lanza (`httpx.ConnectError("…")`, `httpx.ConnectTimeout("timed out")`) o una función
que recibe la `httpx.Request` y devuelve una de las anteriores.
"""
from __future__ import annotations

import contextlib
import json as _json
from typing import Any, Callable, Iterator, Optional, Union

import httpx

from emuwarez_uploadrr.integrations import http_cliente

Fabrica = Callable[[httpx.Request], httpx.Response]
Respuesta = Union[Fabrica, BaseException, Callable[[httpx.Request], Any]]


def respuesta(status: int = 200, *, json: Any = None, cuerpo: Union[bytes, str] = b"",
              headers: Optional[Any] = None) -> Fabrica:
    """Una respuesta para `responde`. Con `json`, el cuerpo es ese JSON."""
    if json is not None:
        cuerpo = _json.dumps(json)
    datos = cuerpo.encode("utf-8") if isinstance(cuerpo, str) else cuerpo

    def _fabrica(request: httpx.Request) -> httpx.Response:
        # Con stream (y no con content=) la respuesta llega sin leer, como una de verdad: se puede leer por trozos.
        return httpx.Response(status, stream=httpx.ByteStream(datos), headers=headers, request=request)

    _fabrica.es_respuesta = True  # type: ignore[attr-defined]
    return _fabrica


def falla_conexion(motivo: str = "[Errno 111] Connection refused") -> httpx.ConnectError:
    return httpx.ConnectError(motivo)


def tiempo_agotado(motivo: str = "timed out") -> httpx.ConnectTimeout:
    return httpx.ConnectTimeout(motivo)


class ServidorFalso:
    def __init__(self) -> None:
        self.peticiones: list[httpx.Request] = []
        self._cola: list[Respuesta] = [respuesta(200)]

    def responde(self, *respuestas: Respuesta) -> "ServidorFalso":
        self._cola = list(respuestas) or [respuesta(200)]
        return self

    @property
    def ultima(self) -> httpx.Request:
        assert self.peticiones, "no se ha hecho ninguna petición"
        return self.peticiones[-1]

    @property
    def urls(self) -> list[str]:
        return [str(p.url) for p in self.peticiones]

    def json_enviado(self, indice: int = -1) -> Any:
        return _json.loads(self.peticiones[indice].content)

    def _atiende(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.peticiones.append(request)
        siguiente = self._cola.pop(0) if len(self._cola) > 1 else self._cola[0]
        return self._resolver(siguiente, request)

    def _resolver(self, que: Any, request: httpx.Request) -> httpx.Response:
        if isinstance(que, BaseException):
            raise que
        if isinstance(que, httpx.Response):
            return que
        if callable(que):
            resultado = que(request)
            if getattr(que, "es_respuesta", False):
                return resultado
            return self._resolver(resultado, request)
        raise TypeError(f"respuesta falsa no válida: {que!r}")


@contextlib.contextmanager
def servidor_falso(*respuestas: Respuesta) -> Iterator[ServidorFalso]:
    """El servidor falso puesto en http_cliente mientras dure el `with` (el fixture `http_falso` lo usa)."""
    servidor = ServidorFalso()
    if respuestas:
        servidor.responde(*respuestas)
    anterior = http_cliente._transporte_de_prueba
    http_cliente.cerrar_clientes()
    http_cliente._transporte_de_prueba = httpx.MockTransport(servidor._atiende)
    try:
        yield servidor
    finally:
        http_cliente._transporte_de_prueba = anterior
        http_cliente.cerrar_clientes()  # los clientes con el transporte falso no se quedan para después
