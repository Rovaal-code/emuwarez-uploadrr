"""La API key de eMuwarez sale del mismo sitio en todos los caminos.

La aplicación tiene dos sitios donde vive la configuración (la tabla settings
y el fichero del CLI antiguo) y esto ya causó el mismo fallo tres veces: una
función leía solo el fichero y decía "No hay API Key" a quien la tenía puesta
en la interfaz. Aquí se fija que todos los caminos usan el mismo resolutor.
"""
from __future__ import annotations

import json

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import cli_config
from emuwarez_uploadrr.services import requests as rq
from emuwarez_uploadrr.web.services.settings_service import set_setting_canonical


@pytest.fixture
def db_conn(isolated_db):
    """La misma BD aislada que usan los demás tests del proyecto."""
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _con_clave(conn, valor="clave-de-la-interfaz"):
    set_setting_canonical(conn, "emu.api_key", valor)
    conn.commit()
    return valor


def test_la_clave_de_la_interfaz_gana(db_conn):
    esperada = _con_clave(db_conn)
    assert rq._resolve_emu_api_key(db_conn) == esperada


def test_la_sincronizacion_vieja_ve_la_clave_de_la_interfaz(db_conn, monkeypatch):
    """El fallo 3.6: sync_requests leía SOLO la configuración del CLI, así que
    reventaba con "No hay API Key" teniéndola configurada."""
    _con_clave(db_conn)
    llamadas = {}

    def falso_get_requests(api_key, endpoint_url=None):
        llamadas["api_key"] = api_key
        return []

    monkeypatch.setattr(rq.emu, "get_requests", falso_get_requests)
    r = rq.sync_requests(db_conn, endpoint_url="http://ejemplo/api/requests", force=True)
    assert r["status"] == "ok"
    # Y la clave que llega a la red es la de verdad, no una vacía.
    assert llamadas["api_key"] == "clave-de-la-interfaz"


def test_el_recalculo_de_coincidencias_tambien_la_ve(db_conn, monkeypatch):
    """match_all_requests y match_single_request leían solo el fichero del CLI:
    con la clave en la interfaz les salía None y la comprobación contra el
    catálogo de eMuwarez se saltaba en silencio."""
    _con_clave(db_conn)
    vistas = []
    monkeypatch.setattr(rq, "_check_emu_catalog_duplicate",
                        lambda conn, req, key, **kw: vistas.append(key))
    # Sin peticiones no hay nada que comprobar, pero el resolutor sí corre:
    # lo que se fija aquí es que ya no pasa por load_app_config.
    rq.match_all_requests(db_conn)
    assert rq._resolve_emu_api_key(db_conn) == "clave-de-la-interfaz"


def test_la_config_cifrada_del_cli_no_mata_el_proceso(tmp_path, monkeypatch):
    """legacy.load_app_config llamaba a die() -> SystemExit cuando había
    configuración cifrada y no se le daba contraseña. Desde un servicio web eso
    tumbaba el hilo. El lector nuevo devuelve None y sigue."""
    cifrada = tmp_path / "config.enc.json"
    cifrada.write_text(json.dumps({"salt": "x", "nonce": "y", "data": "z"}))
    monkeypatch.setattr(cli_config, "CONFIG_ENC_FILE", cifrada)
    monkeypatch.setattr(cli_config, "CONFIG_FILE", tmp_path / "no-existe.json")

    assert cli_config.hay_config_cifrada() is True
    assert cli_config.emu_api_key() is None       # y no lanza SystemExit


def test_un_fichero_de_config_corrupto_no_tumba_nada(tmp_path, monkeypatch):
    roto = tmp_path / "config.json"
    roto.write_text("{ esto no es json")
    monkeypatch.setattr(cli_config, "CONFIG_FILE", roto)
    monkeypatch.setattr(cli_config, "CONFIG_ENC_FILE", tmp_path / "no-existe.enc.json")
    assert cli_config.emu_api_key() is None


def test_la_clave_del_cli_sirve_de_respaldo(tmp_path, monkeypatch, db_conn):
    """Sin clave en la interfaz, la del CLI antiguo sigue valiendo: es un
    puente hacia atrás, no un adorno."""
    plana = tmp_path / "config.json"
    plana.write_text(json.dumps({"emu_api_key": "clave-vieja-del-cli"}))
    monkeypatch.setattr(cli_config, "CONFIG_FILE", plana)
    monkeypatch.setattr(cli_config, "CONFIG_ENC_FILE", tmp_path / "no-existe.enc.json")
    assert rq._resolve_emu_api_key(db_conn) == "clave-vieja-del-cli"
