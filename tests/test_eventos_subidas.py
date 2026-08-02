"""Los avisos de una subida (fase 2).

Aquí lo que importa no es que el aviso salga, sino DESDE DÓNDE sale. El estado
de una subida se escribe desde cinco sitios distintos del pipeline, y el
progreso desde el hilo que lee la salida del proceso: si el aviso se pone en
uno de esos sitios y no en la puerta común, hay caminos que no avisan y la
tabla se queda parada sin que nadie sepa por qué.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import eventos, upload_states


@pytest.fixture(autouse=True)
def _limpio():
    eventos.olvidar_todos()
    yield
    eventos.olvidar_todos()


@pytest.fixture
def trabajo(isolated_db):
    """Una subida en la base de datos. Mismo molde que test_transiciones_de_estado."""
    conn = connect(db_path()); init_db(conn)
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, title, path, status, stage, created_at, updated_at)
           VALUES (NULL, 'Prueba', '/x.mkv', 'queued', 'queued', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""")
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    return job_id


def _espiar(monkeypatch, modulo=upload_states) -> list:
    avisos: list = []
    monkeypatch.setattr(modulo, "publicar",
                        lambda tipo, datos=None: avisos.append((tipo, datos)) or 0)
    return avisos


def test_cambiar_de_estado_avisa(trabajo, monkeypatch):
    """`escribir_estado` es la ÚNICA puerta que escribe upload_jobs.status
    (services/upload_states.py). Por eso el aviso va ahí y no en cada uno de
    los cinco sitios que la llaman."""
    avisos = _espiar(monkeypatch)
    assert upload_states.escribir_estado(trabajo, salvo=("cancelled",), status="running") is True
    assert avisos == [("subida-estado", {"job_id": trabajo, "status": "running", "stage": None})]


def test_avanzar_de_fase_avisa(trabajo, monkeypatch):
    avisos = _espiar(monkeypatch)
    upload_states.escribir_estado(trabajo, salvo=(), status="staging", stage="preparando")
    assert avisos[0][1]["stage"] == "preparando"


def test_si_la_guardia_lo_rechaza_no_se_avisa(trabajo, monkeypatch):
    """El caso real: cancelas una subida y el proceso intenta marcarla como
    fallida justo después. La guardia lo rechaza — no ha pasado nada — así que
    avisar solo haría recargar a la interfaz para enseñar lo mismo."""
    upload_states.escribir_estado(trabajo, salvo=(), status="cancelled")
    avisos = _espiar(monkeypatch)
    assert upload_states.escribir_estado(trabajo, salvo=("cancelled",), status="failed") is False
    assert avisos == []


def test_un_trabajo_que_no_existe_no_avisa(trabajo, monkeypatch):
    avisos = _espiar(monkeypatch)
    assert upload_states.escribir_estado(999999, salvo=(), status="running") is False
    assert avisos == []


def test_avisar_no_puede_romper_una_escritura_de_estado(trabajo, monkeypatch):
    """La misma garantía que en la fase 1, y aquí importa más: si esto lanzara,
    una subida podría quedarse sin marcar como completada con el trabajo hecho.
    `publicar` traga con todo (ver services/eventos.py)."""
    def _revienta(*a, **k):
        raise RuntimeError("el bus está roto")

    monkeypatch.setattr(upload_states, "publicar", _revienta)
    with pytest.raises(RuntimeError):
        upload_states.escribir_estado(trabajo, salvo=(), status="completed")

    # Y aun así el estado quedó escrito: el aviso va DESPUÉS del commit.
    conn = connect(db_path()); init_db(conn)
    fila = conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (trabajo,)).fetchone()
    conn.close()
    assert fila["status"] == "completed"


def test_el_registro_avisa_agrupado(trabajo, monkeypatch):
    """Cientos de líneas por segundo, un aviso por segundo. Y el aviso NO lleva
    las líneas: solo dice que las hay."""
    from emuwarez_uploadrr.services import upload_execution

    avisos: list = []
    monkeypatch.setattr(upload_execution, "publicar_agrupado",
                        lambda clave, tipo, datos=None, cada=1.0: avisos.append((clave, tipo, datos)))

    for i in range(20):
        upload_execution.append_upload_log(trabajo, "info", f"línea {i}")

    assert len(avisos) == 20                       # el agrupador está mockeado aquí
    clave, tipo, datos = avisos[0]
    assert clave == f"log-{trabajo}"               # agrupa POR TRABAJO
    assert tipo == "subida-log"
    assert datos == {"job_id": trabajo}            # sin las líneas dentro


def test_el_registro_de_verdad_se_agrupa(trabajo):
    """Sin mockear el agrupador: 20 líneas seguidas, un solo aviso."""
    import asyncio

    async def escenario():
        from emuwarez_uploadrr.services import upload_execution
        sus = eventos.suscribir()
        try:
            for i in range(20):
                upload_execution.append_upload_log(trabajo, "info", f"línea {i}")
            await asyncio.sleep(0)
            assert sus.cola.qsize() == 1
        finally:
            eventos.desuscribir(sus)

    asyncio.run(escenario())
