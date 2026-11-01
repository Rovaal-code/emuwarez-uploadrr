"""Cabeceras de seguridad en todas las respuestas, sin romper lo que ya mandaba la interfaz.

F9 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from emuwarez_uploadrr.web import app as app_modulo
from emuwarez_uploadrr.web.cabeceras import CSP, CabecerasDeSeguridad


def _seguras(resp):
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "same-origin"
    assert resp.headers["content-security-policy"] == CSP


def test_la_csp_cierra_lo_que_la_aplicacion_no_usa():
    assert "default-src 'self'" in CSP
    assert "img-src 'self' https: data:" in CSP
    assert "frame-ancestors 'none'" in CSP
    assert "object-src 'none'" in CSP
    assert "unsafe-eval" not in CSP and "script-src" not in CSP  # los scripts caen en default-src 'self'


def test_toda_respuesta_de_la_api_lleva_las_cabeceras(client, auth_headers):
    _seguras(client.get("/api/health"))
    _seguras(client.get("/api/auth/me", headers=auth_headers))
    _seguras(client.get("/api/auth/me"))        # un 401
    _seguras(client.get("/api/no-existe"))      # un 404


def test_swagger_y_redoc_no_llevan_csp_pero_si_el_resto(client):
    for ruta in ("/api/docs", "/api/redoc"):
        resp = client.get(ruta)
        assert resp.status_code == 200
        assert "content-security-policy" not in resp.headers
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["referrer-policy"] == "same-origin"
    assert "content-security-policy" in client.get("/api/openapi.json").headers


def test_la_interfaz_y_sus_iconos_las_llevan_y_el_cors_del_icono_sigue(isolated_db, monkeypatch):
    dist = isolated_db / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>x</title>")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(app_modulo, "_FRONTEND_DIST", dist)
    cliente = TestClient(app_modulo.create_app())

    pagina = cliente.get("/")
    _seguras(pagina)
    assert "no-store" in pagina.headers["cache-control"]

    icono = cliente.get("/favicon.svg")
    _seguras(icono)
    assert icono.headers["access-control-allow-origin"] == "*"

    _seguras(cliente.get("/assets/app.js"))


def _correr(app, scope):
    mensajes = []

    async def recibir():
        return {"type": "http.request"}

    async def enviar(m):
        mensajes.append(m)

    asyncio.run(app(scope, recibir, enviar))
    return mensajes


def test_lo_que_una_ruta_ya_puso_no_se_pisa_y_el_cuerpo_pasa_entero():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"Referrer-Policy", b"no-referrer"), (b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": b"data: 1\n\n", "more_body": True})
        await send({"type": "http.response.body", "body": b"data: 2\n\n"})

    mensajes = _correr(CabecerasDeSeguridad(app), {"type": "http", "path": "/api/eventos"})

    cabeceras = dict(mensajes[0]["headers"])
    assert cabeceras[b"Referrer-Policy"] == b"no-referrer"
    assert b"referrer-policy" not in cabeceras
    assert cabeceras[b"x-content-type-options"] == b"nosniff"
    assert [m.get("body") for m in mensajes[1:]] == [b"data: 1\n\n", b"data: 2\n\n"]


def test_lo_que_no_es_http_pasa_sin_tocar():
    visto = []

    async def app(scope, receive, send):
        visto.append(scope["type"])

    _correr(CabecerasDeSeguridad(app), {"type": "lifespan"})
    assert visto == ["lifespan"]
