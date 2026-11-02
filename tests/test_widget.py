"""El widget de Homepage: GET /api/widget con su propia clave de solo lectura.

La clave abre ese endpoint y nada más, ninguna sesión hace falta para él, y de
la clave solo queda su hash: ni la base, ni las respuestas, ni el registro la
llevan.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import widget as svc
from emuwarez_uploadrr.services.settings import all_settings, es_secreto

CAMPOS = {"peticiones_listas", "subidas_hoy", "subidas_fallidas", "en_cola", "subiendo"}


@pytest.fixture
def clave(client, auth_headers):
    resp = client.post("/api/widget/clave", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["clave"]


def _conn():
    conn = connect(db_path())
    init_db(conn)
    return conn


def _subida(conn, estado, finished_at=None):
    ahora = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO upload_jobs (title, path, status, finished_at, created_at, updated_at)"
        " VALUES ('t', '/p', ?, ?, ?, ?)", (estado, finished_at, ahora, ahora))


# ---------- autenticación ----------

def test_sin_clave_configurada_el_widget_no_existe(client):
    assert client.get("/api/widget").status_code == 404
    assert client.get("/api/widget", headers={"X-Api-Key": "emuw_lo-que-sea"}).status_code == 404


def test_clave_ausente_o_incorrecta_es_401(client, clave):
    for cabeceras in ({}, {"X-Api-Key": "emuw_incorrecta"}, {"Authorization": "Bearer emuw_incorrecta"},
                      {"Authorization": clave}, {"X-Api-Key": ""}):
        resp = client.get("/api/widget", headers=cabeceras)
        assert resp.status_code == 401, cabeceras
        assert clave not in resp.text


def test_la_clave_vale_en_x_api_key_y_en_bearer(client, clave):
    assert client.get("/api/widget", headers={"X-Api-Key": clave}).status_code == 200
    assert client.get("/api/widget", headers={"Authorization": f"Bearer {clave}"}).status_code == 200


def test_el_widget_no_necesita_sesion_y_una_sesion_no_lo_abre(client, clave, admin_token):
    # Sin ninguna sesión (el cliente de Homepage no tiene) basta la clave...
    assert client.get("/api/widget", headers={"X-Api-Key": clave}).status_code == 200
    # ...y el token de una sesión no es la clave del widget.
    assert client.get("/api/widget", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 401
    assert client.get("/api/widget", headers={"X-Api-Key": admin_token}).status_code == 401


@pytest.mark.parametrize("ruta", [
    "/api/auth/me", "/api/settings", "/api/dashboard/summary", "/api/library", "/api/uploads",
    "/api/widget/clave", "/api/maintenance/status",
])
def test_la_clave_del_widget_no_abre_ninguna_otra_ruta(client, clave, ruta):
    for cabeceras in ({"X-Api-Key": clave}, {"Authorization": f"Bearer {clave}"}):
        resp = client.get(ruta, headers=cabeceras)
        assert resp.status_code == 401, (ruta, cabeceras, resp.status_code)


def test_la_clave_no_hace_nada_con_los_endpoints_que_la_gestionan(client, clave):
    cabeceras = {"X-Api-Key": clave}
    assert client.post("/api/widget/clave", headers=cabeceras).status_code == 401
    assert client.delete("/api/widget/clave", headers=cabeceras).status_code == 401
    assert client.get("/api/widget", headers=cabeceras).status_code == 200  # sigue siendo la misma


def test_gestionar_la_clave_exige_sesion(client):
    assert client.get("/api/widget/clave").status_code == 401
    assert client.post("/api/widget/clave").status_code == 401
    assert client.delete("/api/widget/clave").status_code == 401


def test_un_fallo_de_la_base_es_503_y_no_401(client, clave, monkeypatch):
    def falla(conn):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(svc, "clave_configurada", falla)
    resp = client.get("/api/widget", headers={"X-Api-Key": clave})
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"


def test_la_comparacion_es_en_tiempo_constante(client, clave, monkeypatch):
    llamadas = []
    original = svc.hmac.compare_digest
    monkeypatch.setattr(svc.hmac, "compare_digest", lambda a, b: llamadas.append(1) or original(a, b))
    assert client.get("/api/widget", headers={"X-Api-Key": clave}).status_code == 200
    assert client.get("/api/widget", headers={"X-Api-Key": "emuw_mala"}).status_code == 401
    assert len(llamadas) == 2


# ---------- generar, regenerar, quitar ----------

def test_estado_de_la_clave(client, auth_headers):
    assert client.get("/api/widget/clave", headers=auth_headers).json() == {"configurada": False}
    clave = client.post("/api/widget/clave", headers=auth_headers).json()["clave"]
    assert clave.startswith("emuw_") and len(clave) > 40
    # Después de generarla solo se sabe que existe: la clave no vuelve a salir.
    resp = client.get("/api/widget/clave", headers=auth_headers)
    assert resp.json() == {"configurada": True}
    assert clave not in resp.text


def test_regenerar_invalida_la_anterior(client, auth_headers, clave):
    nueva = client.post("/api/widget/clave", headers=auth_headers).json()["clave"]
    assert nueva != clave
    assert client.get("/api/widget", headers={"X-Api-Key": clave}).status_code == 401
    assert client.get("/api/widget", headers={"X-Api-Key": nueva}).status_code == 200


def test_quitar_la_clave_desactiva_el_widget(client, auth_headers, clave):
    assert client.delete("/api/widget/clave", headers=auth_headers).json() == {"configurada": False}
    assert client.get("/api/widget", headers={"X-Api-Key": clave}).status_code == 404
    assert client.get("/api/widget/clave", headers=auth_headers).json() == {"configurada": False}


def test_la_respuesta_de_generar_no_se_guarda_en_cache(client, auth_headers):
    resp = client.post("/api/widget/clave", headers=auth_headers)
    assert resp.headers["cache-control"] == "no-store"


# ---------- la clave no se filtra ----------

def test_la_clave_no_se_guarda_ni_se_devuelve_ni_se_registra(client, auth_headers, caplog):
    with caplog.at_level(logging.DEBUG):
        clave = client.post("/api/widget/clave", headers=auth_headers).json()["clave"]
        client.get("/api/widget", headers={"X-Api-Key": clave})
        client.get("/api/widget", headers={"X-Api-Key": clave + "x"})
        client.get("/api/widget", headers={"Authorization": f"Bearer {clave}"})
        ajustes = client.get("/api/settings", headers=auth_headers)
        resumen = client.get("/api/dashboard/summary", headers=auth_headers)

    conn = _conn()
    try:
        guardado = all_settings(conn)
    finally:
        conn.close()
    assert not any(clave in (v or "") for v in guardado.values())
    assert guardado["widget.api_key_hash"] == svc._hash(clave) != clave
    assert clave not in ajustes.text and clave not in resumen.text
    assert "widget.api_key_hash" not in ajustes.text and guardado["widget.api_key_hash"] not in ajustes.text
    assert clave not in caplog.text


def test_el_hash_cuenta_como_secreto_para_las_copias():
    assert es_secreto(svc.CLAVE_HASH_SETTING)


# ---------- los datos ----------

def test_las_claves_de_la_respuesta(client, clave):
    datos = client.get("/api/widget", headers={"X-Api-Key": clave}).json()
    assert set(datos) == CAMPOS
    assert all(type(v) is int and v == 0 for v in datos.values())


def test_los_contadores(client, clave):
    ahora = datetime.now(timezone.utc)
    conn = _conn()
    for i, estado in enumerate(("ready_to_upload", "ready_to_upload", "needs_nomenclature")):
        peticion = conn.execute("INSERT INTO request_items (emu_id, title) VALUES (?, 'p')", (str(i),)).lastrowid
        conn.execute("INSERT INTO request_readiness (request_item_id, status) VALUES (?, ?)", (peticion, estado))
    for estado in ("queued", "staging", "preparing"):
        _subida(conn, estado)
    _subida(conn, "running")
    _subida(conn, "failed", ahora.isoformat())
    _subida(conn, "failed", (ahora - timedelta(days=3)).isoformat())
    _subida(conn, "cancelled", ahora.isoformat())
    _subida(conn, "completed", ahora.isoformat())
    _subida(conn, "completed", ahora.strftime("%Y-%m-%d %H:%M:%S"))  # la otra forma de escribir la fecha
    _subida(conn, "completed", (ahora - timedelta(days=3)).isoformat())
    conn.commit()
    conn.close()

    assert client.get("/api/widget", headers={"X-Api-Key": clave}).json() == {
        "peticiones_listas": 2, "subidas_hoy": 2, "subidas_fallidas": 2, "en_cola": 3, "subiendo": 1,
    }


def test_los_contadores_son_los_del_panel(client, clave, auth_headers):
    conn = _conn()
    _subida(conn, "running")
    _subida(conn, "failed")
    peticion = conn.execute("INSERT INTO request_items (emu_id, title) VALUES ('1', 'p')").lastrowid
    conn.execute("INSERT INTO request_readiness (request_item_id, status) VALUES (?, 'ready_to_upload')", (peticion,))
    conn.commit()
    conn.close()

    panel = client.get("/api/dashboard/summary", headers=auth_headers).json()
    widget = client.get("/api/widget", headers={"X-Api-Key": clave}).json()
    assert widget["subiendo"] == panel["uploads_running"] == 1
    assert widget["subidas_fallidas"] == panel["uploads_failed"] == 1
    assert widget["peticiones_listas"] == panel["requests_ready_to_upload"] == 1


def test_subidas_hoy_cuenta_desde_la_medianoche_de_la_zona_del_servidor(isolated_db, monkeypatch):
    from zoneinfo import ZoneInfo
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")  # UTC+14: su «hoy» y el de UTC casi nunca coinciden
    ahora_local = datetime.now(ZoneInfo("Pacific/Kiritimati"))
    medianoche = ahora_local.replace(hour=0, minute=0, second=0, microsecond=0)
    conn = _conn()
    _subida(conn, "completed", (medianoche + timedelta(minutes=1)).astimezone(timezone.utc).isoformat())
    _subida(conn, "completed", (medianoche - timedelta(minutes=1)).astimezone(timezone.utc).isoformat())
    # Sin finished_at: vale updated_at (ahora).
    _subida(conn, "completed", None)
    conn.commit()
    assert svc.contadores(conn)["subidas_hoy"] == 2
    conn.close()
