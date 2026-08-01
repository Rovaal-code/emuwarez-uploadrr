"""Foto de quién puede pisar el estado de una subida, y cuándo.

Cinco funciones escriben `upload_jobs.status`/`stage`, cada una con su propia
política de guardia (auditoría, hallazgo 4.1). Esta tabla NO juzga si las
políticas son buenas: las FOTOGRAFÍA, para poder unificarlas sabiendo que el
resultado no cambia.

Si al refactorizar una celda cambia, o el refactor está mal o había un fallo
escondido, y las dos cosas hay que verlas antes de seguir.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db

ESTADOS = ["queued", "staging", "preparing", "running", "completed", "failed", "cancelled"]


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _job(conn, status: str) -> int:
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, title, path, status, stage, created_at, updated_at)
           VALUES (NULL, 'Test', '/x.mkv', ?, 'preflight', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (status,))
    conn.commit()
    return cur.lastrowid


def _estado(conn, jid: int) -> tuple[str, str]:
    r = conn.execute("SELECT status, stage FROM upload_jobs WHERE id = ?", (jid,)).fetchone()
    return r["status"], r["stage"]


# --- _mark: avanza de fase durante la preparación --------------------------

@pytest.mark.parametrize("inicial", ESTADOS)
def test_mark_solo_avanza_lo_que_no_ha_terminado(db_conn, inicial):
    from emuwarez_uploadrr.services.upload_queue import _mark

    jid = _job(db_conn, inicial)
    avanzo = _mark(jid, stage="remux")
    estado, fase = _estado(db_conn, jid)

    # Los terminales no se tocan; el resto pasa a 'preparing'.
    if inicial in ("cancelled", "failed"):
        assert avanzo is False and (estado, fase) == (inicial, "preflight")
    else:
        assert avanzo is True and (estado, fase) == ("preparing", "remux")


# --- _fail: marca el fallo, salvo sobre una cancelación --------------------

@pytest.mark.parametrize("inicial", ESTADOS)
def test_fail_respeta_la_cancelacion_del_usuario(db_conn, inicial):
    from emuwarez_uploadrr.services.upload_queue import _fail

    jid = _job(db_conn, inicial)
    _fail(jid, "algo se rompió")
    estado, _fase = _estado(db_conn, jid)

    assert estado == ("cancelled" if inicial == "cancelled" else "failed")


# --- _update_staging_stage: solo mientras siga en 'staging' ----------------

@pytest.mark.parametrize("inicial", ESTADOS)
def test_la_subfase_de_staging_solo_avanza_en_staging(db_conn, inicial):
    from emuwarez_uploadrr.services.upload_queue import _update_staging_stage

    jid = _job(db_conn, inicial)
    _update_staging_stage(jid, "remux", db_conn)
    _estado_, fase = _estado(db_conn, jid)

    assert fase == ("remux" if inicial == "staging" else "preflight")


# --- _finalize_job_status: el estado final, salvo sobre una cancelación ----

@pytest.mark.parametrize("inicial", ESTADOS)
@pytest.mark.parametrize("destino", ["completed", "failed"])
def test_el_estado_final_no_pisa_una_cancelacion(db_conn, inicial, destino):
    from emuwarez_uploadrr.services.upload_execution import _finalize_job_status

    jid = _job(db_conn, inicial)
    _finalize_job_status(jid, destino, exit_code=0)
    estado, _fase = _estado(db_conn, jid)

    assert estado == ("cancelled" if inicial == "cancelled" else destino)


@pytest.mark.parametrize("inicial", ESTADOS)
def test_update_job_status_escribe_siempre(db_conn, inicial):
    """La única sin guardia. Se fotografía tal cual, incluido que pisa una
    cancelación: es lo que hace hoy."""
    from emuwarez_uploadrr.services.upload_execution import _update_job_status

    jid = _job(db_conn, inicial)
    _update_job_status(jid, "running")
    estado, _fase = _estado(db_conn, jid)
    assert estado == "running"
