"""Renombrar y repuntar una instancia de Radarr/Sonarr."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.instances import get_instance, update_instance

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


def test_cambiar_la_url_exige_que_la_instancia_responda(conn, monkeypatch):
    from emuwarez_uploadrr.services import instances
    pruebas = []

    def prueba(*a, **kw):
        pruebas.append(a)
        return {"ok": False, "error": "Connection refused"}

    monkeypatch.setattr(instances, "test_connection_params", prueba)

    with pytest.raises(ValueError, match="Connection refused"):
        update_instance(conn, RADARR, url="http://otra:7878", test_connection=True)
    assert get_instance(conn, RADARR).url == "http://radarr"

    # Lo que no cambia el destino no se prueba: poder apagarla, renombrarla o repetir la misma URL.
    pruebas.clear()
    assert update_instance(conn, RADARR, url="http://radarr", enabled=False, name="Radarr 2", test_connection=True)
    assert pruebas == []


def test_cambiar_la_url_con_la_instancia_respondiendo_la_cambia(conn, monkeypatch):
    from emuwarez_uploadrr.services import instances
    monkeypatch.setattr(instances, "test_connection_params", lambda *a, **kw: {"ok": True})

    update_instance(conn, RADARR, url="http://otra:7878", api_key="nueva", test_connection=True)

    assert get_instance(conn, RADARR).url == "http://otra:7878"
    assert get_instance(conn, RADARR).api_key == "nueva"


def test_la_edicion_web_rechaza_una_url_que_no_responde(conn, client, auth_headers, monkeypatch):
    from emuwarez_uploadrr.services import instances
    monkeypatch.setattr(instances, "test_connection_params", lambda *a, **kw: {"ok": False, "error": "timeout"})

    resp = client.put(f"/api/instances/{RADARR}", json={"url": "http://otra:7878"}, headers=auth_headers)

    assert resp.status_code == 400 and "timeout" in resp.json()["detail"]
    assert get_instance(conn, RADARR).url == "http://radarr"
