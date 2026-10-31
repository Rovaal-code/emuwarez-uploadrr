"""Renombrar y repuntar una instancia de Radarr/Sonarr."""
from __future__ import annotations

from emuwarez_uploadrr.services.instances import (
    AVISO_SIN_RESPUESTA, aviso_si_cambia_el_destino, get_instance, update_instance,
)

from tests import arr_falso
from tests.arr_falso import RADARR, _peli, _sincroniza

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
arr, conn, _progreso_aparte = arr_falso.arr, arr_falso.conn, arr_falso._progreso_aparte


# --- BIB-12: renombrar y repuntar una instancia -----------------------------------------------------------------

def test_renombrar_una_instancia_renombra_sus_fichas(conn, arr):
    arr["peliculas"] = [_peli(1, "Matrix")]
    _sincroniza(conn, RADARR)

    update_instance(conn, RADARR, name="Radarr 4K")

    assert conn.execute("SELECT DISTINCT instance_name FROM library_items").fetchall()[0][0] == "Radarr 4K"


def _prueba_de_conexion(monkeypatch, resultado):
    """Sustituye la prueba de conexión; devuelve las veces que se llamó."""
    from emuwarez_uploadrr.services import instances
    llamadas = []
    monkeypatch.setattr(instances, "test_connection_params", lambda *a, **kw: llamadas.append(a) or resultado)
    return llamadas


def test_cambiar_la_url_de_una_instancia_que_no_responde_se_guarda_con_aviso(conn, client, auth_headers, monkeypatch):
    """Hay instancias apagadas días: no se puede comprobar, así que se guarda y se avisa."""
    _prueba_de_conexion(monkeypatch, {"ok": False, "error": "timeout"})

    resp = client.put(f"/api/instances/{RADARR}", json={"url": "http://otra:7878"}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["warning"] == AVISO_SIN_RESPUESTA and "no responde" in resp.json()["warning"]
    assert get_instance(conn, RADARR).url == "http://otra:7878"


def test_cambiar_la_clave_de_una_instancia_que_responde_se_guarda_sin_aviso(conn, client, auth_headers, monkeypatch):
    llamadas = _prueba_de_conexion(monkeypatch, {"ok": True})

    resp = client.put(f"/api/instances/{RADARR}", json={"api_key": "nueva"}, headers=auth_headers)

    assert resp.status_code == 200 and resp.json()["warning"] is None
    assert len(llamadas) == 1 and get_instance(conn, RADARR).api_key == "nueva"


def test_lo_que_no_cambia_el_destino_no_se_prueba_ni_avisa(conn, client, auth_headers, monkeypatch):
    llamadas = _prueba_de_conexion(monkeypatch, {"ok": False, "error": "timeout"})

    resp = client.put(f"/api/instances/{RADARR}", json={"url": "http://radarr", "name": "Radarr 2", "enabled": False},
                      headers=auth_headers)

    assert resp.status_code == 200 and resp.json()["warning"] is None
    assert llamadas == []


def test_el_aviso_al_cambiar_el_destino_solo_sale_si_no_responde(conn, monkeypatch):
    instancia = get_instance(conn, RADARR)

    _prueba_de_conexion(monkeypatch, {"ok": True})
    assert aviso_si_cambia_el_destino(instancia, url="http://otra:7878", api_key=None) is None

    _prueba_de_conexion(monkeypatch, {"ok": False, "error": "Connection refused"})
    assert aviso_si_cambia_el_destino(instancia, url="http://otra:7878", api_key=None) == AVISO_SIN_RESPUESTA
    assert aviso_si_cambia_el_destino(instancia, url=None, api_key="otra") == AVISO_SIN_RESPUESTA
    assert aviso_si_cambia_el_destino(instancia, url="http://radarr/", api_key="clave") is None
