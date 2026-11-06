"""El texto de una excepción de integración no lleva claves hasta la respuesta, el log ni la base.

eMuwarez y TMDb llevan la clave en la URL (`?api_token=…`, `?api_key=…`), y el mensaje de una excepción de red o de
HTTP puede repetir esa URL. Cada sitio que mete `str(exc)` en un `detail`, en un log o en una columna pasa por
`integrations.base.texto_de_error`, y el log tapa lo que se escape (`web/logging_setup.py`). El 422 de validación
tiene su propio test (`test_422_sin_claves.py`).
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.integrations.base import IntegrationError, tapar_claves, texto_de_error
from tests.http_falso import falla_conexion

SECRETO = "SECRETO-no-debe-salir"
URL_CON_CLAVE = f"https://host/x?apikey={SECRETO}"


def _limpio(resp, caplog):
    assert SECRETO not in resp.text
    assert SECRETO not in caplog.text


# ---------------------------------------------------------------------------
# El punto único
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    (f"GET {URL_CON_CLAVE}&b=1 falló", "GET https://host/x?apikey=***&b=1 falló"),
    (f"https://host/x?api_token={SECRETO}", "https://host/x?api_token=***"),
    (f"https://host/x?API_KEY={SECRETO}&language=es", "https://host/x?API_KEY=***&language=es"),
    (f"({'token'}={SECRETO})", "(token=***)"),
    (f"https://usuario:{SECRETO}@host/x", "https://***@host/x"),
    (f"X-Api-Key: {SECRETO}", "X-Api-Key: ***"),
    (f"Authorization: Bearer {SECRETO}", "Authorization: Bearer ***"),
    (f"https://api.telegram.org/bot123456:{SECRETO}/sendMessage", "https://api.telegram.org/bot***/sendMessage"),
    (f"https://discord.com/api/webhooks/123/{SECRETO}", "https://discord.com/api/webhooks/123/***"),
    (f'{{"api_key": "{SECRETO}", "message": "hola"}}', '{"api_key": "***", "message": "hola"}'),
])
def test_tapar_claves_por_forma(texto, esperado):
    assert tapar_claves(texto) == esperado


def test_tapar_claves_sin_nada_que_tapar_no_toca_el_texto():
    texto = "No se pudo conectar con http://radarr:7878/api/v3/movie: [Errno 111] Connection refused"
    assert tapar_claves(texto) == texto
    assert tapar_claves("") == ""


def test_tapar_claves_conocidas_en_cualquier_formato():
    assert tapar_claves(f"rechazó {SECRETO} y {SECRETO.upper()}", SECRETO) == f"rechazó *** y {SECRETO.upper()}"
    assert tapar_claves("clave a%2Bb%2Fc", "a+b/c") == "clave ***"
    assert tapar_claves("sin tocar abc", "abc") == "sin tocar abc"  # una «clave» de menos de 4 caracteres no se busca
    assert tapar_claves("nada", None, "") == "nada"


def test_texto_de_error_taparia_la_url_de_una_excepcion():
    exc = RuntimeError(f"fallo en {URL_CON_CLAVE}")
    assert texto_de_error(exc) == "fallo en https://host/x?apikey=***"
    assert texto_de_error(ValueError("Ya existe una instancia")) == "Ya existe una instancia"


# ---------------------------------------------------------------------------
# El log
# ---------------------------------------------------------------------------

def test_el_log_tapa_el_mensaje_y_el_traceback(client, caplog):
    # `client` ya creó la app, que instala el tapado de claves en los registros.
    caplog.set_level(logging.DEBUG)
    log = logging.getLogger("emuwarez.prueba")
    log.warning("fallo en %s", URL_CON_CLAVE)
    try:
        raise RuntimeError(f"conexión rota con {URL_CON_CLAVE}")
    except RuntimeError:
        log.exception("no se pudo")
    assert SECRETO not in caplog.text
    assert "apikey=***" in caplog.text
    assert "conexión rota con" in caplog.text  # el traceback sigue ahí, solo sin la clave


def test_el_anillo_de_logs_de_la_interfaz_no_lleva_claves(client, auth_headers):
    logging.getLogger("emuwarez.prueba").error("fallo en %s", URL_CON_CLAVE)
    resp = client.get("/api/logs", headers=auth_headers)
    assert resp.status_code == 200
    assert SECRETO not in resp.text


# ---------------------------------------------------------------------------
# El 500 genérico
# ---------------------------------------------------------------------------

def test_el_500_generico_no_devuelve_ni_registra_la_url(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    cliente = TestClient(client.app, raise_server_exceptions=False)
    with patch("emuwarez_uploadrr.services.instances.list_instance_rows",
               side_effect=RuntimeError(f"fallo en {URL_CON_CLAVE}")):
        resp = cliente.get("/api/instances", headers=auth_headers)
    assert resp.status_code == 500
    cuerpo = resp.json()
    assert cuerpo["error"] == "Internal server error"
    assert cuerpo["detail"] == "fallo en https://host/x?apikey=***"
    _limpio(resp, caplog)
    assert "EXCEPCIÓN" in caplog.text  # el fallo sí queda en el log, solo que sin la clave


# ---------------------------------------------------------------------------
# Instancias
# ---------------------------------------------------------------------------

def _crear_instancia(client, auth_headers, *, tipo="radarr", nombre="R1", clave="clave-de-radarr"):
    resp = client.post("/api/instances", headers=auth_headers,
                       json={"type": tipo, "name": nombre, "url": "http://x:7878", "api_key": clave})
    assert resp.status_code == 201, resp.text
    return next(i for i in client.get("/api/instances", headers=auth_headers).json() if i["name"] == nombre)


def test_sync_de_una_instancia_que_falla_no_devuelve_la_clave(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    inst = _crear_instancia(client, auth_headers)
    with patch("emuwarez_uploadrr.services.library.sync_instance_con_candado",
               side_effect=RuntimeError(f"fallo en {URL_CON_CLAVE}")):
        resp = client.post(f"/api/instances/{inst['id']}/sync", headers=auth_headers)
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Error en sync: fallo en https://host/x?apikey=***"
    _limpio(resp, caplog)


def test_sync_parcial_de_una_instancia_no_devuelve_la_clave(client, auth_headers, caplog):
    from emuwarez_uploadrr.services.library import SincronizacionParcial
    caplog.set_level(logging.DEBUG)
    inst = _crear_instancia(client, auth_headers)
    parcial = SincronizacionParcial(f"1 serie falló: {URL_CON_CLAVE}", 3, 1)
    with patch("emuwarez_uploadrr.services.library.sync_instance_con_candado", side_effect=parcial):
        resp = client.post(f"/api/instances/{inst['id']}/sync", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 3
    _limpio(resp, caplog)


def test_sync_real_de_una_instancia_caida_no_deja_la_clave_en_ningun_sitio(client, auth_headers, http_falso, caplog):
    """De punta a punta: Radarr responde con un error de red que repite la URL con la clave."""
    caplog.set_level(logging.DEBUG)
    inst = _crear_instancia(client, auth_headers, clave=SECRETO)
    http_falso.responde(falla_conexion(f"proxy roto en http://usuario:{SECRETO}@x:7878/api/v3/movie?apikey={SECRETO}"))
    resp = client.post(f"/api/instances/{inst['id']}/sync", headers=auth_headers)
    assert resp.status_code in (200, 500), resp.text
    _limpio(resp, caplog)
    conn = connect(db_path())
    try:
        init_db(conn)
        for fila in conn.execute("SELECT name, status, summary, details FROM task_runs").fetchall():
            assert SECRETO not in " ".join(str(c) for c in tuple(fila))
    finally:
        conn.close()


def test_probar_una_instancia_caida_no_deja_la_clave_en_la_respuesta_ni_en_la_base(
        client, auth_headers, http_falso, caplog):
    caplog.set_level(logging.DEBUG)
    inst = _crear_instancia(client, auth_headers, clave=SECRETO)
    http_falso.responde(falla_conexion(f"proxy roto en http://usuario:{SECRETO}@x:7878/api/v3/system/status?apikey={SECRETO}"))
    resp = client.post(f"/api/instances/{inst['id']}/test", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    _limpio(resp, caplog)
    conn = connect(db_path())
    try:
        estado = conn.execute("SELECT last_test_status FROM instances WHERE id = ?", (inst["id"],)).fetchone()[0]
    finally:
        conn.close()
    assert SECRETO not in estado


def test_crear_una_instancia_que_no_conecta_no_devuelve_la_clave(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    with patch("emuwarez_uploadrr.services.instances.test_connection_params",
               return_value={"ok": False, "error": f"No se pudo conectar: {URL_CON_CLAVE}"}):
        resp = client.post("/api/instances", headers=auth_headers,
                           json={"type": "radarr", "name": "R2", "url": "http://x:7878", "api_key": SECRETO})
    assert resp.status_code == 400
    assert "No se pudo conectar con la instancia radarr" in resp.json()["detail"]
    _limpio(resp, caplog)


def test_editar_una_instancia_con_un_error_no_devuelve_la_clave(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    inst = _crear_instancia(client, auth_headers)
    with patch("emuwarez_uploadrr.services.instances.update_instance",
               side_effect=ValueError(f"no se pudo guardar {SECRETO}")):
        resp = client.put(f"/api/instances/{inst['id']}", headers=auth_headers,
                          json={"name": "R1", "api_key": SECRETO})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "no se pudo guardar ***"
    _limpio(resp, caplog)


def test_los_mensajes_seguros_de_las_instancias_no_cambian(client, auth_headers):
    _crear_instancia(client, auth_headers, nombre="R3")
    resp = client.post("/api/instances", headers=auth_headers,
                       json={"type": "radarr", "name": "R3", "url": "http://x:7878", "api_key": "k"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Ya existe una instancia con el nombre 'R3'."


# ---------------------------------------------------------------------------
# Asistente de configuración
# ---------------------------------------------------------------------------

def test_setup_tmdb_con_la_red_caida_no_devuelve_la_clave(client, auth_headers, http_falso, caplog):
    caplog.set_level(logging.DEBUG)
    http_falso.responde(falla_conexion(f"fallo en https://api.themoviedb.org/3/configuration?api_key={SECRETO}"))
    resp = client.post("/api/setup/tmdb", headers=auth_headers, json={"api_key": SECRETO})
    assert resp.status_code == 400
    assert "No se pudo conectar con TMDb" in resp.json()["detail"]
    _limpio(resp, caplog)


def test_setup_tmdb_tapa_la_clave_aunque_no_vaya_como_parametro(client, auth_headers, http_falso, caplog):
    caplog.set_level(logging.DEBUG)
    http_falso.responde(falla_conexion(f"el servidor rechazó la clave {SECRETO}"))
    resp = client.post("/api/setup/tmdb", headers=auth_headers, json={"api_key": SECRETO})
    assert resp.status_code == 400
    _limpio(resp, caplog)


def test_setup_emu_con_la_red_caida_no_devuelve_la_clave(client, auth_headers, http_falso, caplog):
    caplog.set_level(logging.DEBUG)
    http_falso.responde(falla_conexion(f"fallo en https://emu-warez.com/api/torrents/filter?api_token={SECRETO}"))
    resp = client.post("/api/setup/emu", headers=auth_headers, json={"api_key": SECRETO})
    assert resp.status_code == 400
    assert "No se pudo conectar con eMuwarez" in resp.json()["detail"]
    _limpio(resp, caplog)


def test_setup_emu_con_una_url_con_clave_no_la_repite(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    resp = client.post("/api/setup/emu", headers=auth_headers,
                       json={"api_key": "una-clave-de-prueba", "endpoint_url": f"ftp://host/x?api_token={SECRETO}"})
    assert resp.status_code == 400
    _limpio(resp, caplog)


def test_setup_instancia_con_un_fallo_inesperado_no_devuelve_la_clave(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    with patch("emuwarez_uploadrr.web.services.setup_service.setup_add_instance",
               side_effect=RuntimeError(f"fallo en {URL_CON_CLAVE} con la clave {SECRETO}")):
        resp = client.post("/api/setup/instances", headers=auth_headers,
                           json={"type": "radarr", "name": "R9", "url": "http://x:7878", "api_key": SECRETO})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "fallo en https://host/x?apikey=*** con la clave ***"
    _limpio(resp, caplog)


# ---------------------------------------------------------------------------
# Pruebas de conexión
# ---------------------------------------------------------------------------

def test_probar_tmdb_con_la_red_caida_no_devuelve_la_clave(client, auth_headers, http_falso, caplog):
    caplog.set_level(logging.DEBUG)
    http_falso.responde(falla_conexion(f"fallo en https://api.themoviedb.org/3/configuration?api_key={SECRETO}"))
    resp = client.post("/api/integrations/test/tmdb", headers=auth_headers, json={"api_key": SECRETO})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    _limpio(resp, caplog)


def test_probar_emuwarez_con_la_red_caida_no_devuelve_la_clave(client, auth_headers, http_falso, caplog):
    caplog.set_level(logging.DEBUG)
    http_falso.responde(falla_conexion(f"fallo en https://emu-warez.com/api/torrents/filter?api_token={SECRETO}"))
    resp = client.post("/api/integrations/test/emuwarez", headers=auth_headers, json={"api_key": SECRETO})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    _limpio(resp, caplog)


def test_probar_emuwarez_con_una_url_con_clave_no_la_devuelve(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    resp = client.post("/api/integrations/test/emuwarez", headers=auth_headers,
                       json={"api_key": "una-clave-de-prueba", "base_url": f"emu-warez.com?api_token={SECRETO}"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    _limpio(resp, caplog)


def test_probar_radarr_con_la_red_caida_no_devuelve_la_clave(client, auth_headers, http_falso, caplog):
    caplog.set_level(logging.DEBUG)
    http_falso.responde(falla_conexion(f"proxy roto en http://usuario:{SECRETO}@x:7878/api/v3/system/status?apikey={SECRETO}"))
    resp = client.post("/api/integrations/test/arr", headers=auth_headers,
                       json={"kind": "radarr", "base_url": f"http://usuario:{SECRETO}@x:7878", "api_key": SECRETO})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    _limpio(resp, caplog)


# ---------------------------------------------------------------------------
# Sincronizaciones
# ---------------------------------------------------------------------------

def test_sync_de_peticiones_con_un_error_de_integracion_no_devuelve_la_clave(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    with patch("emuwarez_uploadrr.services.requests.start_requests_sync_background",
               side_effect=IntegrationError(f"HTTP 500 en {URL_CON_CLAVE}")):
        resp = client.post("/api/requests/sync", headers=auth_headers, json={})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "HTTP 500 en https://host/x?apikey=***"
    _limpio(resp, caplog)


def test_sync_de_biblioteca_con_un_error_no_devuelve_la_clave(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    with patch("emuwarez_uploadrr.services.library.sync_all", side_effect=RuntimeError(f"fallo en {URL_CON_CLAVE}")):
        resp = client.post("/api/sync", headers=auth_headers, json={})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Error en sync: fallo en https://host/x?apikey=***"
    _limpio(resp, caplog)


def test_sync_de_peticiones_apunta_el_error_sin_la_clave(isolated_db, caplog):
    """El error que se enseña en la barra de progreso y se guarda en task_runs."""
    from emuwarez_uploadrr.services import requests as servicio

    caplog.set_level(logging.DEBUG)
    conn = connect(db_path())
    init_db(conn)
    try:
        with patch.object(servicio, "_importar_peticiones", side_effect=RuntimeError(f"fallo en {URL_CON_CLAVE}")):
            with pytest.raises(RuntimeError):
                servicio._sincronizar_peticiones(conn)
        assert SECRETO not in str(servicio.get_request_sync_progress())
    finally:
        conn.close()
    assert SECRETO not in caplog.text
