"""Una subida empieza al momento si no hay otra en marcha.

Antes cada subida se quedaba 60 s «En cola» aunque no hubiera nada delante.
Ahora «En cola» solo existe mientras espera plaza de verdad en "Subidas en
paralelo", con su puesto, y Cancelar funciona en cada paso: en la cola,
preparando los ficheros y con Uploadrr-EMU en marcha.
"""
from __future__ import annotations

import pathlib
import threading
import time

import pytest

from emuwarez_uploadrr.services import upload_execution as ue
from emuwarez_uploadrr.services import upload_queue as uq
from emuwarez_uploadrr.services.upload_execution import cancel_upload_job, get_upload_job


@pytest.fixture(autouse=True)
def _biblioteca_en_tmp(tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import uploadrr_contract
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path)])


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def puerta(monkeypatch):
    """Una puerta de "Subidas en paralelo" propia del test, con límite 1."""
    g = ue._UploadConcurrencyGate()
    monkeypatch.setattr(ue, "_upload_concurrency_gate", g)
    monkeypatch.setattr(ue, "get_upload_max_concurrent", lambda conn=None: 1)
    return g


def _esperar(condicion, timeout=5.0) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return condicion()


def _peli(conn, tmp_path, nombre="peli.mkv") -> int:
    f = tmp_path / nombre
    f.write_bytes(b"x" * 100)
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status,
                                      path, size_bytes, updated_at)
           VALUES ('movie', 'Peli', 'Disponible', 'Sin petición', 'N/A', ?, 100, CURRENT_TIMESTAMP)""",
        (str(f),))
    conn.commit()
    return cur.lastrowid


def _fila_en_cola(conn, item_id=None) -> int:
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, title, path, source_path, created_at, updated_at)
           VALUES (?, 'queued', 'queued', 'X', '', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (item_id,))
    conn.commit()
    return cur.lastrowid


def _estado(conn, job_id) -> dict:
    return get_upload_job(job_id, conn=conn)


def _hilo_terminado(job_id) -> bool:
    with uq._LOCK:
        return job_id not in uq._EN_CURSO


# ---------------------------------------------------------------------------
# Sin espera fija
# ---------------------------------------------------------------------------

def test_sin_nada_en_marcha_la_subida_sale_de_la_cola_al_momento(
        db_conn, tmp_path, puerta, subidas_reales, ficheros_de_mentira, monkeypatch):
    """Antes se quedaba 60 s en «En cola» aunque no hubiera nada delante."""
    llego = threading.Event()

    def comprobar(job_id, item_id, is_season, conn):
        llego.set()
        return False  # se para aquí: lo que importa es que llegó sin esperar

    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", comprobar)
    jid = uq.queue_upload_for_item(_peli(db_conn, tmp_path), conn=db_conn)["job"]["id"]

    assert llego.wait(timeout=3), "la subida no empezó al momento"
    assert _estado(db_conn, jid)["status"] == "preparing"
    assert _esperar(lambda: _hilo_terminado(jid))
    assert puerta._active == 0


def test_sin_nada_en_marcha_no_hay_puesto_ni_aviso_de_espera(db_conn, puerta, monkeypatch):
    avisos = []
    monkeypatch.setattr(ue, "publicar", lambda tipo, datos=None: avisos.append(datos) or 0)
    jid = _fila_en_cola(db_conn)

    inicio = time.monotonic()
    assert puerta.acquire(jid) is True
    assert time.monotonic() - inicio < 1
    assert puerta.posiciones() == {}
    assert avisos == []
    puerta.release()


# ---------------------------------------------------------------------------
# El puesto en la cola
# ---------------------------------------------------------------------------

def test_el_puesto_en_la_cola_sigue_el_orden_de_entrada(db_conn, puerta, monkeypatch):
    avisos = []
    monkeypatch.setattr(ue, "publicar", lambda tipo, datos=None: avisos.append((tipo, datos)) or 0)
    ocupa, a, b = _fila_en_cola(db_conn), _fila_en_cola(db_conn), _fila_en_cola(db_conn)
    assert puerta.acquire(ocupa)

    dentro = []

    def esperar_turno(jid):
        assert puerta.acquire(jid)
        dentro.append(jid)

    # Llegan al revés: el puesto lo decide el orden de creación, no quién llega antes.
    hilos = [threading.Thread(target=esperar_turno, args=(j,)) for j in (b, a)]
    for h in hilos:
        h.start()
    assert _esperar(lambda: len(puerta.posiciones()) == 2)
    assert puerta.posiciones() == {a: (1, 2), b: (2, 2)}
    assert uq.get_queue_positions() == {a: (1, 2), b: (2, 2)}
    # Cada una avisa al empezar a esperar: la interfaz enseña el puesto sin preguntar.
    assert {d["job_id"] for t, d in avisos if t == "subida-estado"} >= {a, b}

    avisos.clear()
    puerta.release()  # sale la que ocupaba: entra a, b pasa a ser la primera
    assert _esperar(lambda: dentro == [a])
    assert _esperar(lambda: puerta.posiciones() == {b: (1, 1)})
    assert any((d or {}).get("job_id") == a for _t, d in avisos), "nadie avisó de que la cola avanzó"

    puerta.release()
    assert _esperar(lambda: dentro == [a, b])
    puerta.release()
    for h in hilos:
        h.join(timeout=5)
    assert puerta.posiciones() == {}


def test_la_api_devuelve_el_puesto_y_ya_no_el_plazo(client, auth_headers, puerta, monkeypatch):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path())
    init_db(conn)
    try:
        jid = _fila_en_cola(conn)
    finally:
        conn.close()
    monkeypatch.setattr(puerta, "posiciones", lambda: {jid: (2, 3)})

    detalle = client.get(f"/api/uploads/{jid}", headers=auth_headers).json()
    assert (detalle["queue_position"], detalle["queue_total"]) == (2, 3)
    assert "queued_until" not in detalle

    lista = client.get("/api/uploads", headers=auth_headers).json()
    fila = next(j for j in lista if j["id"] == jid)
    assert (fila["queue_position"], fila["queue_total"]) == (2, 3)


# ---------------------------------------------------------------------------
# Cancelar en cada paso
# ---------------------------------------------------------------------------

def test_cancelar_en_la_cola_la_saca_al_momento(db_conn, tmp_path, puerta, subidas_reales):
    ocupa = _fila_en_cola(db_conn)
    assert puerta.acquire(ocupa)
    try:
        a = uq.queue_upload_for_item(_peli(db_conn, tmp_path, "a.mkv"), conn=db_conn)["job"]["id"]
        b = uq.queue_upload_for_item(_peli(db_conn, tmp_path, "b.mkv"), conn=db_conn)["job"]["id"]
        assert _esperar(lambda: puerta.posiciones() == {a: (1, 2), b: (2, 2)})

        assert cancel_upload_job(a, conn=db_conn)["ok"] is True
        # Sin esperar a que se libere plaza: deja la cola ya, y la de detrás sube.
        assert _esperar(lambda: _hilo_terminado(a), timeout=2)
        assert puerta.posiciones() == {b: (1, 1)}
        job = _estado(db_conn, a)
        assert (job["status"], job["stage"]) == ("cancelled", "cancelled")
        assert job["started_at"] is None and job["prepared_path"] is None
        assert puerta._active == 1  # solo la que ocupaba: la cancelada no tomó plaza
        assert uq.trabajo_activo(db_conn, job["library_item_id"]) is None

        assert cancel_upload_job(b, conn=db_conn)["ok"] is True
        assert _esperar(lambda: _hilo_terminado(b), timeout=2)
        assert puerta.posiciones() == {}
    finally:
        puerta.release()
    assert puerta._active == 0
    assert puerta._retirados == set()


def test_cancelada_antes_de_llegar_a_la_puerta_no_espera(puerta):
    puerta.retirar(7)
    assert puerta.acquire(7) is False
    assert puerta._active == 0
    # La retirada se consume: un trabajo nuevo con otro id no hereda nada.
    assert puerta.acquire(7) is True
    puerta.release()


def test_cancelar_una_fila_en_cola_sin_hilo_no_deja_rastro_en_la_puerta(db_conn, puerta):
    """Sin hilo nadie recogería la retirada, y un id reutilizado más tarde
    nacería ya cancelado en la puerta."""
    jid = _fila_en_cola(db_conn)
    assert cancel_upload_job(jid, conn=db_conn)["ok"] is True
    assert puerta._retirados == set()
    assert puerta.acquire(jid) is True
    puerta.release()


def test_cancelada_justo_al_tocarle_plaza_suelta_la_plaza(db_conn, puerta):
    jid = _fila_en_cola(db_conn)
    db_conn.execute("UPDATE upload_jobs SET status = 'cancelled', stage = 'cancelled' WHERE id = ?", (jid,))
    db_conn.commit()

    uq._run_queued_job(jid)

    assert _estado(db_conn, jid)["status"] == "cancelled"
    assert _estado(db_conn, jid)["started_at"] is None
    assert puerta._active == 0


def test_cancelar_mientras_prepara_para_en_el_siguiente_paso_y_suelta_la_plaza(
        db_conn, tmp_path, puerta, ficheros_de_mentira, monkeypatch):
    iid = _peli(db_conn, tmp_path)
    jid = _fila_en_cola(db_conn, iid)
    lanzado = []
    monkeypatch.setattr(ue, "start_upload_job", lambda *a, **k: lanzado.append(a) or {"error": None})

    def cancelar_aqui(job_id, item_id, is_season, conn):
        assert _estado(db_conn, job_id)["status"] == "preparing"
        assert cancel_upload_job(job_id, conn=db_conn)["ok"] is True
        return True

    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", cancelar_aqui)
    uq._run_queued_job(jid)

    job = _estado(db_conn, jid)
    assert job["status"] == "cancelled"
    assert job["prepared_path"] is None  # no llegó a enlazar nada en la carpeta de subidas
    assert lanzado == []
    assert puerta._active == 0


def test_el_frontend_ya_no_cuenta_60_segundos():
    """La cuenta atrás vivía en el frontend leyendo queued_until."""
    front = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"
    con_plazo = [str(f.relative_to(front)) for f in front.rglob("*.ts*")
                 if "__tests__" not in f.parts and "queued_until" in f.read_text(encoding="utf-8")]
    assert con_plazo == []
