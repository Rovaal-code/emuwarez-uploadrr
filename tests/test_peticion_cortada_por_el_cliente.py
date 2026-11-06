"""Una conexión que corta el navegador no es un error de la app.

Al cambiar de página con iconos a medio bajar, Starlette acaba la petición sin respuesta y lanza
``RuntimeError("No response returned.")``. El registro de peticiones lo apuntaba como ERROR con la traza entera
(y uvicorn otra vez, como «Exception in ASGI application»): líneas rojas en Logs que no eran fallos. Ahora es
una línea DEBUG, sin traza, y nada sale de la app. Un fallo de verdad se sigue registrando como siempre.
"""
from __future__ import annotations

import asyncio
import logging

from starlette.routing import Mount


def _app_con_ruta(client, ruta, asgi):
    app = client.app
    app.router.routes.insert(0, Mount(ruta, app=asgi))
    return app


async def _espera_al_corte(scope, receive, send):
    # Lo que hace un fichero estático cuando el navegador se va: espera, ve el corte y no responde.
    while (await receive())["type"] != "http.disconnect":
        pass


async def _llamar(app, path):
    mensajes = [{"type": "http.request", "body": b"", "more_body": False}, {"type": "http.disconnect"}]
    enviados = []

    async def receive():
        return mensajes.pop(0) if mensajes else {"type": "http.disconnect"}

    async def send(m):
        enviados.append(m)

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "",
        "query_string": b"", "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 1), "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return enviados


def test_un_corte_del_navegador_se_registra_bajo_y_sin_traza(client, caplog):
    app = _app_con_ruta(client, "/__corte", _espera_al_corte)
    with caplog.at_level(logging.DEBUG, logger="emuwarez.request"):
        asyncio.run(_llamar(app, "/__corte/icono.ico"))
    registros = [r for r in caplog.records if r.name == "emuwarez.request"]
    assert [r.levelno for r in registros] == [logging.DEBUG]
    assert "cerró la conexión" in registros[0].getMessage()
    assert registros[0].exc_info is None
    assert "EXCEPCIÓN" not in caplog.text


def test_una_app_que_falla_de_verdad_sigue_siendo_error(client, caplog):
    async def rota(scope, receive, send):
        raise RuntimeError("fallo de verdad")

    app = _app_con_ruta(client, "/__rota", rota)
    with caplog.at_level(logging.DEBUG, logger="emuwarez.request"):
        try:
            asyncio.run(_llamar(app, "/__rota/x"))
        except RuntimeError:
            pass
    errores = [r for r in caplog.records if r.name == "emuwarez.request" and r.levelno == logging.ERROR]
    assert errores and "EXCEPCIÓN" in errores[0].getMessage()
