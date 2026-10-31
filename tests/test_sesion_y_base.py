"""Un fallo de la base no es una sesión caducada ni una app sin configurar: es un 503.

F4, FEA-7 y F10 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import sqlite3

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from emuwarez_uploadrr.database import get_state, set_state


def _bloqueada(*_a, **_k):
    raise sqlite3.OperationalError("database is locked")


# ---------------------------------------------------------------------------
# F4: require_auth
# ---------------------------------------------------------------------------

def test_un_fallo_de_la_base_al_comprobar_el_token_es_503_no_401(client, auth_headers, monkeypatch):
    """Con 401 el cliente borraba la sesión por un bloqueo pasajero."""
    monkeypatch.setattr("emuwarez_uploadrr.web.services.auth_service.get_user_by_token", _bloqueada)
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 503
    assert resp.headers["retry-after"]


def test_un_token_que_no_existe_sigue_siendo_401(client, auth_headers):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer no-existe"})
    assert resp.status_code == 401


def test_sin_token_es_401_sin_tocar_la_base(client, monkeypatch):
    monkeypatch.setattr("emuwarez_uploadrr.database.init_db", _bloqueada)
    assert client.get("/api/auth/me").status_code == 401


def test_con_la_base_caida_require_auth_tampoco_dice_401(client, auth_headers, monkeypatch):
    monkeypatch.setattr("emuwarez_uploadrr.database.init_db", _bloqueada)
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 503


# ---------------------------------------------------------------------------
# FEA-7: /api/setup/status
# ---------------------------------------------------------------------------

def test_setup_status_con_un_error_de_la_base_es_503_no_el_asistente(client, monkeypatch):
    """Antes contestaba 200 con admin_configured=false, y la interfaz enseñaba
    el asistente de primer arranque a una app ya configurada."""
    monkeypatch.setattr("emuwarez_uploadrr.web.services.setup_service.get_setup_state", _bloqueada)
    assert client.get("/api/setup/status").status_code == 503


def test_setup_status_con_la_base_sin_abrir_es_503(client, monkeypatch):
    monkeypatch.setattr("emuwarez_uploadrr.database.init_db", _bloqueada)
    assert client.get("/api/setup/status").status_code == 503


def test_setup_status_normal_sigue_dando_el_estado(client, auth_headers):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json()["admin_configured"] is True


# ---------------------------------------------------------------------------
# F10: /api/health
# ---------------------------------------------------------------------------

def test_health_es_503_cuando_la_base_no_responde(client, monkeypatch):
    """El HEALTHCHECK de Docker solo mira el código de estado."""
    monkeypatch.setattr("emuwarez_uploadrr.database.init_db", _bloqueada)
    resp = client.get("/api/health")
    assert resp.status_code == 503
    cuerpo = resp.json()
    assert cuerpo["database"] == "error"
    assert cuerpo["status"] == "error"


def test_health_es_200_con_la_base_bien(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["database"] == "ok"


def _app_con_get_db() -> FastAPI:
    from emuwarez_uploadrr.web.dependencies import get_db

    app = FastAPI()

    @app.post("/escribe/{valor}")
    def escribe(valor: str, conn: sqlite3.Connection = Depends(get_db)):
        set_state(conn, "prueba", valor)
        if valor == "falla":
            raise RuntimeError("a medias")
        return {"ok": True}

    @app.get("/lee")
    def lee(conn: sqlite3.Connection = Depends(get_db)):
        return {"valor": get_state(conn, "prueba")}

    return app


def test_get_db_confirma_y_deshace_por_peticion():
    c = TestClient(_app_con_get_db(), raise_server_exceptions=False)
    assert c.post("/escribe/uno").status_code == 200
    assert c.get("/lee").json() == {"valor": "uno"}
    assert c.post("/escribe/falla").status_code == 500
    assert c.get("/lee").json() == {"valor": "uno"}


def test_get_db_sirve_peticiones_seguidas_aunque_el_hilo_cambie():
    c = TestClient(_app_con_get_db())
    for i in range(20):
        assert c.post(f"/escribe/{i}").status_code == 200
        assert c.get("/lee").json() == {"valor": str(i)}
