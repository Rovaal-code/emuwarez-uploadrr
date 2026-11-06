"""Un 422 de validación no devuelve ni registra lo que se envió.

Pydantic repite el valor recibido (`input`) en cada error; en los ajustes ese valor
puede ser una URL con la clave en la query (`qbit_qui_proxy_url`), una API key, un
token o una contraseña. El manejador global de `RequestValidationError` (web/app.py)
quita `input` y `ctx` y deja `loc`, `msg` y `type`, que es lo que lee el frontend.
"""
from __future__ import annotations

import logging

import pytest

SECRETO = "SECRETO-no-debe-salir"
URL_CON_CLAVE = f"ftp://x?apikey={SECRETO}"


def _comprobar_422(resp, caplog, esperado_msg: str | None = None):
    assert resp.status_code == 422, resp.text
    assert SECRETO not in resp.text
    assert SECRETO not in caplog.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and detail
    for error in detail:
        assert "input" not in error
        assert "ctx" not in error
        assert error["loc"] and error["msg"] and error["type"]
    if esperado_msg:
        assert any(esperado_msg in e["msg"] for e in detail)


@pytest.mark.parametrize("campo", ["qbit_url", "qbit_qui_proxy_url"])
def test_put_settings_url_mal_formada_no_se_repite(client, auth_headers, caplog, campo):
    caplog.set_level(logging.DEBUG)
    resp = client.put("/api/settings", json={campo: URL_CON_CLAVE}, headers=auth_headers)
    _comprobar_422(resp, caplog, "debe empezar por http")


def test_put_settings_tipo_incorrecto_no_se_repite(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    cuerpo = {"notify_telegram_bot_token": {"x": SECRETO}, "qbit_password": [SECRETO]}
    resp = client.put("/api/settings", json=cuerpo, headers=auth_headers)
    _comprobar_422(resp, caplog)


@pytest.mark.parametrize("ruta, cuerpo", [
    ("/api/setup/qbit", {"url": URL_CON_CLAVE, "password": SECRETO}),
    ("/api/setup/tmdb", {"api_key": {"k": SECRETO}}),
    ("/api/setup/emu", {"api_key": [SECRETO]}),
    ("/api/setup/instances", {"type": "lidarr", "name": "x", "url": URL_CON_CLAVE, "api_key": SECRETO}),
    ("/api/instances", {"type": "radarr", "name": "x", "url": URL_CON_CLAVE, "api_key": SECRETO}),
    ("/api/notifications/test/telegram", {"bot_token": {"t": SECRETO}, "chat_id": "1"}),
    ("/api/notifications/test/discord", {"webhook_url": {"u": SECRETO}}),
])
def test_otros_endpoints_no_repiten_lo_enviado(client, auth_headers, caplog, ruta, cuerpo):
    caplog.set_level(logging.DEBUG)
    resp = client.post(ruta, json=cuerpo, headers=auth_headers)
    _comprobar_422(resp, caplog)


def test_login_con_contrasena_de_tipo_incorrecto_no_se_repite(client, caplog):
    caplog.set_level(logging.DEBUG)
    resp = client.post("/api/auth/login", json={"username": "a", "password": [SECRETO]})
    _comprobar_422(resp, caplog)


def test_json_invalido_no_se_repite(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    resp = client.put(
        "/api/settings", content=f'{{"qbit_url": "{SECRETO}"'.encode(),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    _comprobar_422(resp, caplog)


def test_el_formato_que_lee_el_frontend_se_conserva(client, auth_headers):
    resp = client.put("/api/settings", json={"qbit_url": "ftp://x"}, headers=auth_headers)
    assert resp.status_code == 422
    (error,) = resp.json()["detail"]
    assert error["loc"] == ["body", "qbit_url"]
    assert error["msg"].startswith("Value error, La URL de qBittorrent")
    assert error["type"] == "value_error"
