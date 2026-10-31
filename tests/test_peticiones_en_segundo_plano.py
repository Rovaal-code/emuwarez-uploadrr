"""PET-11: la sincronización de peticiones corre en un hilo y se sigue por su progreso, no dentro de una petición HTTP."""
from __future__ import annotations

import datetime as dt
import threading
import time

import pytest

from emuwarez_uploadrr.database import connect, db_path, get_state, init_db, set_state
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import emu_catalog
from emuwarez_uploadrr.services import requests as reqs
from emuwarez_uploadrr.services.settings import set_setting

FILA = {"id": 1, "name": "Dune", "category_id": 1, "tmdb": 438631, "status": "unfilled"}


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    set_setting(conn, "emu.api_key", "clave")
    conn.commit()  # el hilo abre su propia conexión
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def progreso_limpio():
    reqs._set_progress(active=False, done=False, phase="", page=0, total_pages=None, imported=0, message="", error=None)
    yield
    reqs._set_progress(active=False, done=False)


@pytest.fixture
def avisos(monkeypatch):
    publicados = []
    monkeypatch.setattr(reqs, "publicar", lambda tipo, datos=None: publicados.append((tipo, datos)))
    return publicados


def _esperar(condicion, segundos=10):
    limite = time.time() + segundos
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def _fetch_lento(monkeypatch, filas=(FILA,)):
    """Un recorrido que se queda esperando en `seguir` y que cuenta cuántas veces se pide."""
    estado = {"dentro": threading.Event(), "seguir": threading.Event(), "veces": 0}

    def fetch(api_key, *a, progress=None, **kw):
        estado["veces"] += 1
        estado["dentro"].set()
        if progress:
            progress(1, 3, len(filas))
        assert estado["seguir"].wait(10)
        return list(filas), len(filas)

    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", fetch)
    return estado


def test_arranca_en_segundo_plano_y_vuelve_al_instante(db_conn, monkeypatch, avisos):
    estado = _fetch_lento(monkeypatch)
    assert reqs.start_requests_sync_background(force=True) == {"status": "started"}
    try:
        assert estado["dentro"].wait(10)
        progreso = reqs.get_request_sync_progress()
        # El recorrido sigue a medias y ya se sabe en qué página va.
        assert (progreso["active"], progreso["done"], progreso["page"], progreso["total_pages"]) == (True, False, 1, 3)
        assert progreso["phase"] == "Descargando peticiones…"
    finally:
        estado["seguir"].set()

    assert _esperar(lambda: reqs.get_request_sync_progress()["done"])
    progreso = reqs.get_request_sync_progress()
    assert (progreso["active"], progreso["error"]) == (False, None)
    assert progreso["message"] == "1 peticiones importadas, 0 cruces actualizados."
    assert db_conn.execute("SELECT title FROM request_items").fetchone()[0] == "Dune"


def test_una_segunda_pulsacion_sigue_la_que_hay_sin_lanzar_otra(db_conn, monkeypatch, avisos):
    estado = _fetch_lento(monkeypatch)
    reqs.start_requests_sync_background(force=True)
    try:
        assert estado["dentro"].wait(10)
        assert reqs.start_requests_sync_background(force=True) == {"status": "started"}
    finally:
        estado["seguir"].set()
    assert _esperar(lambda: reqs.get_request_sync_progress()["done"])
    assert estado["veces"] == 1


def test_avisa_a_la_interfaz_al_empezar_y_al_terminar(db_conn, monkeypatch, avisos):
    estado = _fetch_lento(monkeypatch)
    estado["seguir"].set()
    reqs.start_requests_sync_background(force=True)
    assert _esperar(lambda: reqs.get_request_sync_progress()["done"])
    assert avisos == [("sync-empezada", {"que": "peticiones"}), ("sync-terminada", {"que": "peticiones"})]


def test_un_fallo_se_ve_en_el_progreso_y_devuelve_el_turno(db_conn, monkeypatch, avisos):
    antes = get_state(db_conn, reqs.SYNC_STATE_KEY)

    def roto(*a, **kw):
        raise IntegrationError("eMuwarez ha limitado las peticiones; prueba en unos minutos", status=429)

    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", roto)
    reqs.start_requests_sync_background(force=True)
    assert _esperar(lambda: reqs.get_request_sync_progress()["done"])
    progreso = reqs.get_request_sync_progress()
    assert progreso["active"] is False
    assert progreso["error"] == "eMuwarez ha limitado las peticiones; prueba en unos minutos"
    assert get_state(db_conn, reqs.SYNC_STATE_KEY) == (antes or "")


def test_dentro_de_la_hora_responde_que_espere_sin_arrancar_nada(db_conn, monkeypatch, avisos):
    set_state(db_conn, reqs.SYNC_STATE_KEY, dt.datetime.now(dt.timezone.utc).isoformat())
    db_conn.commit()
    estado = _fetch_lento(monkeypatch)
    resultado = reqs.start_requests_sync_background(force=False)
    assert resultado["status"] == "throttled" and resultado["wait_seconds"] > 0
    assert estado["veces"] == 0 and not reqs.get_request_sync_progress()["active"]


def test_con_el_catalogo_sincronizando_responde_ocupado_sin_arrancar_nada(db_conn, monkeypatch, avisos):
    estado = _fetch_lento(monkeypatch)
    emu_catalog._set_progress(active=True)
    try:
        resultado = reqs.start_requests_sync_background(force=True)
    finally:
        emu_catalog._set_progress(active=False)
    assert resultado["status"] == "busy" and "catálogo" in resultado["message"]
    assert estado["veces"] == 0 and not reqs.get_request_sync_progress()["active"]


def test_sin_api_key_falla_al_momento_y_no_deja_nada_activo(isolated_db, monkeypatch, avisos):
    conn = connect(db_path())
    init_db(conn)
    conn.close()
    with pytest.raises(IntegrationError, match="API Key"):
        reqs.start_requests_sync_background(force=True)
    assert not reqs.get_request_sync_progress()["active"]


def test_el_endpoint_arranca_y_el_progreso_se_consulta(client, auth_headers, db_conn, monkeypatch, avisos):
    set_setting(db_conn, "emu.api_key", "clave")
    db_conn.commit()
    estado = _fetch_lento(monkeypatch)
    estado["seguir"].set()

    resp = client.post("/api/requests/sync", json={"force": True}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "started" and resp.json()["ok"] is True

    assert _esperar(lambda: client.get("/api/requests/sync-progress", headers=auth_headers).json()["done"])
    progreso = client.get("/api/requests/sync-progress", headers=auth_headers).json()
    assert progreso["error"] is None and progreso["active"] is False
    assert client.get("/api/requests/sync-progress").status_code == 401


def test_si_el_hilo_falla_antes_de_sincronizar_la_barra_no_se_queda_encendida(db_conn, monkeypatch, avisos):
    def rota(*a, **kw):
        raise RuntimeError("base de datos bloqueada")

    monkeypatch.setattr(reqs, "_sincronizar_peticiones", rota)
    reqs.start_requests_sync_background(force=True)
    assert _esperar(lambda: reqs.get_request_sync_progress()["done"])
    progreso = reqs.get_request_sync_progress()
    assert (progreso["active"], progreso["error"]) == (False, "base de datos bloqueada")


def _candado_libre():
    libre = reqs._SYNC_EN_CURSO.acquire(blocking=False)
    if libre:
        reqs._SYNC_EN_CURSO.release()
    return libre


def test_si_no_arranca_nada_el_candado_queda_libre(db_conn, monkeypatch, avisos):
    set_state(db_conn, reqs.SYNC_STATE_KEY, dt.datetime.now(dt.timezone.utc).isoformat())
    db_conn.commit()
    assert reqs.start_requests_sync_background(force=False)["status"] == "throttled"
    assert _candado_libre()
    emu_catalog._set_progress(active=True)
    try:
        assert reqs.start_requests_sync_background(force=True)["status"] == "busy"
    finally:
        emu_catalog._set_progress(active=False)
    assert _candado_libre()
    db_conn.execute("DELETE FROM settings WHERE key = 'emu.api_key'")
    db_conn.commit()
    with pytest.raises(IntegrationError):
        reqs.start_requests_sync_background(force=True)
    assert _candado_libre()


def test_dos_arranques_a_la_vez_lanzan_un_solo_hilo_y_no_se_pisan_el_progreso(db_conn, monkeypatch, avisos):
    """Dos pestañas a la vez: las dos veían «no hay ninguna» y la que perdía apagaba la barra de la que corría."""
    estado = _fetch_lento(monkeypatch)
    salida = []
    salida_lock = threading.Lock()
    salida_barrera = threading.Barrier(2)

    def pulsa():
        salida_barrera.wait(10)
        r = reqs.start_requests_sync_background(force=True)
        with salida_lock:
            salida.append(r["status"])

    hilos = [threading.Thread(target=pulsa) for _ in range(2)]
    for h in hilos:
        h.start()
    try:
        assert estado["dentro"].wait(10)
        for h in hilos:
            h.join(10)
        # Con la sincronización a medias sigue encendida y sin error, la haya pedido quien la haya pedido.
        progreso = reqs.get_request_sync_progress()
        assert (progreso["active"], progreso["done"], progreso["error"]) == (True, False, None)
    finally:
        estado["seguir"].set()
    assert _esperar(lambda: reqs.get_request_sync_progress()["done"])
    assert estado["veces"] == 1
    assert salida.count("started") >= 1 and set(salida) <= {"started", "busy"}
    assert reqs.get_request_sync_progress()["error"] is None
    assert _candado_libre()


def test_con_otra_sincronizacion_en_marcha_no_se_toca_su_progreso(db_conn, monkeypatch, avisos):
    """La tarea programada ya tiene el candado: su progreso es suyo y el arranque del botón no lo reinicia."""
    estado = _fetch_lento(monkeypatch)
    reqs._SYNC_EN_CURSO.acquire()
    try:
        reqs._set_progress(active=True, phase="Descargando peticiones…", page=4, total_pages=9)
        assert reqs.start_requests_sync_background(force=True) == {"status": "started"}
        progreso = reqs.get_request_sync_progress()
        assert (progreso["active"], progreso["page"], progreso["phase"]) == (True, 4, "Descargando peticiones…")
        # Y si todavía no ha escrito su progreso, se dice que hay una en marcha en vez de fingir que arranca.
        reqs._set_progress(active=False)
        resultado = reqs.start_requests_sync_background(force=True)
        assert resultado["status"] == "busy" and "en marcha" in resultado["message"]
    finally:
        reqs._SYNC_EN_CURSO.release()
    assert estado["veces"] == 0
