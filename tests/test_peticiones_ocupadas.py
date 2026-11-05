"""La sincronización de peticiones no corre a la vez que otra de eMuwarez ni con una subida en marcha.

Todas gastan las mismas 30 llamadas por minuto de la clave, y a la subida un 429 le para el trabajo."""
from __future__ import annotations

import argparse
import threading

import pytest

from emuwarez_uploadrr import cli
from emuwarez_uploadrr.database import connect, db_path, get_state, init_db
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import emu_catalog
from emuwarez_uploadrr.services import requests as reqs
from emuwarez_uploadrr.services.settings import set_setting

CATALOGO = "Se está sincronizando el catálogo de eMuwarez; vuelve a probar cuando termine."
SUBIDA = "Hay una subida en marcha; vuelve a probar cuando termine."


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    set_setting(conn, "emu.api_key", "clave")
    conn.commit()  # el hilo de una de las pruebas abre su propia conexión
    yield conn
    conn.close()


@pytest.fixture
def fetch(monkeypatch):
    """Cuenta las veces que la sincronización llega a pedir páginas a eMuwarez."""
    llamadas = []
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: llamadas.append(1) or ([], 0))
    return llamadas


@pytest.fixture
def catalogo_activo():
    emu_catalog._set_progress(active=True)
    yield
    emu_catalog._set_progress(active=False)


def _subida(conn, estado):
    conn.execute("INSERT INTO upload_jobs (title, path, status) VALUES ('X', '/x', ?)", (estado,))
    conn.commit()


def test_con_el_catalogo_sincronizando_responde_ocupado_y_no_toca_nada(db_conn, fetch, catalogo_activo):
    assert reqs.sync_emu_requests(db_conn, force=True) == {"status": "busy", "message": CATALOGO}
    assert fetch == []
    assert db_conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 0
    assert get_state(db_conn, reqs.SYNC_STATE_KEY) is None  # y el turno de una hora sigue libre

    emu_catalog._set_progress(active=False)
    assert reqs.sync_emu_requests(db_conn, force=True)["status"] == "ok"
    assert fetch == [1]


@pytest.mark.parametrize("estado", ["staging", "preparing", "running"])
def test_con_una_subida_en_curso_responde_ocupado(db_conn, fetch, estado):
    _subida(db_conn, estado)
    assert reqs.sync_emu_requests(db_conn, force=True) == {"status": "busy", "message": SUBIDA}
    assert fetch == []


def test_una_subida_en_cola_no_para_la_sincronizacion(db_conn, fetch):
    """Mientras espera turno no llama a eMuwarez: un lote de 40 en cola no deja horas sin peticiones nuevas."""
    _subida(db_conn, "queued")
    assert reqs.sync_emu_requests(db_conn, force=True)["status"] == "ok"
    assert fetch == [1]
    # En cuanto una arranca, vuelve a contar.
    _subida(db_conn, "preparing")
    assert reqs.sync_emu_requests(db_conn, force=True) == {"status": "busy", "message": SUBIDA}
    assert fetch == [1]


def test_los_estados_en_marcha_son_los_activos_menos_la_cola():
    from emuwarez_uploadrr.services.upload_states import ACTIVE_JOB_STATUSES
    assert reqs.ESTADOS_EN_MARCHA == ACTIVE_JOB_STATUSES - {"queued"}


@pytest.mark.parametrize("estado", ["completed", "failed", "cancelled", "ready"])
def test_una_subida_terminada_no_estorba(db_conn, fetch, estado):
    _subida(db_conn, estado)
    assert reqs.sync_emu_requests(db_conn, force=True)["status"] == "ok"
    assert fetch == [1]


def test_dos_sincronizaciones_a_la_vez_la_segunda_se_queda_fuera(db_conn, monkeypatch):
    dentro, seguir = threading.Event(), threading.Event()

    def lenta(*a, **kw):
        dentro.set()
        assert seguir.wait(10)
        return [], 0

    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lenta)
    primera = {}

    def corre():
        conn = connect(db_path())
        try:
            primera["resultado"] = reqs.sync_emu_requests(conn, force=True)
        finally:
            conn.close()

    hilo = threading.Thread(target=corre)
    hilo.start()
    try:
        assert dentro.wait(10)
        segunda = reqs.sync_emu_requests(db_conn, force=True)
    finally:
        seguir.set()
        hilo.join(10)

    assert segunda == {"status": "busy", "message": "Ya hay una sincronización de peticiones en marcha."}
    assert primera["resultado"]["status"] == "ok"
    # Cuando la primera termina, la siguiente ya puede.
    assert reqs.sync_emu_requests(db_conn, force=True)["status"] == "ok"


def test_una_sincronizacion_que_falla_no_deja_el_candado_puesto(db_conn, monkeypatch):
    def rota(*a, **kw):
        raise IntegrationError("eMuwarez ha limitado las peticiones; prueba en unos minutos", status=429)

    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", rota)
    with pytest.raises(IntegrationError):
        reqs.sync_emu_requests(db_conn, force=True)

    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: ([], 0))
    assert reqs.sync_emu_requests(db_conn, force=True)["status"] == "ok"


def test_el_endpoint_responde_ocupado_sin_error(client, auth_headers, catalogo_activo):
    resp = client.post("/api/requests/sync", json={"force": True}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False, "status": "busy", "imported": 0, "matched": 0, "wait_seconds": 0, "message": CATALOGO,
    }


def test_el_cli_cuenta_que_esta_ocupado(isolated_db, monkeypatch, capsys):
    monkeypatch.setattr(
        reqs, "sync_emu_requests", lambda conn, force=False: {"status": "busy", "message": SUBIDA})
    args = argparse.Namespace(db=str(isolated_db / "emuwarez_uploadrr.db"), requests_command="sync", force=True)

    assert cli.cmd_requests(args) == 0
    assert SUBIDA in capsys.readouterr().out
