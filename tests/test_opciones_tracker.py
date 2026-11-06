"""Anónimo y Personal release (services/opciones_tracker.py): por grupo en Configuración, cambiables por subida en el
Resumen, y hasta Uploadrr-EMU como -a / -pr."""
from __future__ import annotations

import json

import pytest

from emuwarez_uploadrr.services import opciones_tracker as ot
from emuwarez_uploadrr.services import upload_queue as uq
from emuwarez_uploadrr.services.uploadrr_contract import build_uploadrr_emu_command


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _movie(conn, path: str) -> int:
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path,
                                      size_bytes, updated_at)
           VALUES ('movie', 'X', 'Disponible', 'Sin petición', 'N/A', ?, 100, CURRENT_TIMESTAMP)""",
        (path,),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _cmd(**kw):
    return build_uploadrr_emu_command(
        python_path="/usr/bin/python3", uploadrr_script_path="/opt/Uploadrr/upload.py",
        prepared_path="/data/x.mkv", torrent_name="X", category="movie", **kw,
    )


# --- La regla por grupo -------------------------------------------------------------------------------------------

def test_sin_grupos_marcados_nada_va_marcado(db_conn):
    assert ot.opciones_de_subida(db_conn, "EMUWAREZ") == {"anon": False, "personal_release": False}


def test_el_grupo_marcado_decide_sin_distinguir_mayusculas(db_conn):
    ot.guardar_grupos(db_conn, personal_release=["MiGrupo"], anonimos=["Oculto"])
    assert ot.opciones_de_subida(db_conn, "migrupo") == {"anon": False, "personal_release": True}
    assert ot.opciones_de_subida(db_conn, "OCULTO") == {"anon": True, "personal_release": False}
    assert ot.opciones_de_subida(db_conn, None) == {"anon": False, "personal_release": False}


def test_lo_elegido_a_mano_gana_al_grupo(db_conn):
    ot.guardar_grupos(db_conn, personal_release=["MiGrupo"], anonimos=["MiGrupo"])
    assert ot.opciones_de_subida(db_conn, "MiGrupo", anonimo=False, personal_release=False) == {
        "anon": False, "personal_release": False}
    assert ot.opciones_de_subida(db_conn, "Otro", anonimo=True) == {"anon": True, "personal_release": False}


def test_guardar_limpia_vacios_y_repetidos(db_conn):
    ot.guardar_grupos(db_conn, personal_release=[" A ", "", "a", "B"])
    assert ot.grupos_personal_release(db_conn) == ["A", "B"]
    ot.guardar_grupos(db_conn, anonimos=["C"])          # la otra lista no se toca
    assert ot.grupos_personal_release(db_conn) == ["A", "B"]
    assert ot.grupos_anonimos(db_conn) == ["C"]


# --- El comando de Uploadrr-EMU -----------------------------------------------------------------------------------

def test_el_comando_lleva_a_y_pr_solo_si_toca():
    assert "-a" not in _cmd() and "-pr" not in _cmd()
    assert "-a" in _cmd(anonimo=True) and "-pr" not in _cmd(anonimo=True)
    assert "-pr" in _cmd(personal_release=True) and "-a" not in _cmd(personal_release=True)


def test_la_ejecucion_lee_las_marcas_del_trabajo(db_conn, tmp_path):
    from emuwarez_uploadrr.services.upload_execution.consultas import build_uploadrr_execution_command
    job = {"prepared_path": str(tmp_path / "x.mkv"),
           "uploadrr_command_json": json.dumps({"category": "movie", "anon": True, "personal_release": True})}
    args = build_uploadrr_execution_command(job, conn=db_conn)["args"]
    assert "-a" in args and "-pr" in args


# --- La cola: lo elegido se guarda en el trabajo y _marcar_lista lo resuelve ------------------------------------

def test_encolar_guarda_lo_elegido_y_none_se_queda_en_null(db_conn, tmp_path):
    f = tmp_path / "m.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie(db_conn, str(f))
    job_id = uq.queue_upload_for_item(iid, anonimo=True, conn=db_conn)["job"]["id"]
    fila = db_conn.execute("SELECT anonimo, personal_release FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
    assert fila["anonimo"] == 1 and fila["personal_release"] is None


def test_marcar_lista_aplica_la_regla_y_lo_elegido(db_conn, tmp_path):
    ot.guardar_grupos(db_conn, personal_release=["MiGrupo"])
    iid = _movie(db_conn, str(tmp_path / "m.mkv"))
    cur = db_conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, title, path, anonimo, created_at, updated_at)
           VALUES (?, 'queued', 'queued', 'X', '', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""", (iid,))
    db_conn.commit()
    job_id = cur.lastrowid
    preview = {"runtime_type": "uploadrr_emu", "command_args": ["python", "upload.py", "/data/x.mkv"]}
    assert uq._marcar_lista(job_id, preview, db_conn, grupo="MiGrupo")
    guardado = json.loads(db_conn.execute(
        "SELECT uploadrr_command_json FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()[0])
    assert guardado["anon"] is True and guardado["personal_release"] is True
    assert guardado["command_args"][-2:] == ["-a", "-pr"]


def test_el_reintento_conserva_lo_elegido(db_conn, tmp_path):
    f = tmp_path / "m.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie(db_conn, str(f))
    cur = db_conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, title, path, source_path, personal_release,
                                    created_at, updated_at)
           VALUES (?, 'failed', 'failed', 'X', '', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""", (iid,))
    db_conn.commit()
    nuevo = uq.queue_retry_for_job(cur.lastrowid, conn=db_conn)["job"]
    assert nuevo["personal_release"] == 0 and nuevo["anonimo"] is None


# --- Configuración ------------------------------------------------------------------------------------------------

def test_ajustes_ida_y_vuelta(client, auth_headers):
    r = client.put("/api/settings", json={
        "upload_tags": ["EMUWAREZ", "MiGrupo"],
        "upload_tags_personal_release": ["MiGrupo"],
        "upload_tags_anonimos": ["EMUWAREZ", "MiGrupo"],
    }, headers=auth_headers)
    assert r.status_code == 200, r.text
    s = client.get("/api/settings", headers=auth_headers).json()
    assert s["upload_tags_personal_release"] == ["MiGrupo"]
    assert s["upload_tags_anonimos"] == ["EMUWAREZ", "MiGrupo"]


def test_la_cola_acepta_las_casillas(client, auth_headers, isolated_db, tmp_path):
    from emuwarez_uploadrr.database import connect, init_db
    f = tmp_path / "m.mkv"
    f.write_bytes(b"x" * 100)
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    iid = _movie(conn, str(f))
    conn.close()
    r = client.post(f"/api/library/{iid}/upload/queue", json={"personal_release": True}, headers=auth_headers)
    assert r.status_code == 200, r.text
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    fila = conn.execute("SELECT anonimo, personal_release FROM upload_jobs").fetchone()
    conn.close()
    assert fila["anonimo"] is None and fila["personal_release"] == 1
