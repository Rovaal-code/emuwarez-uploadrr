"""Los pasos que Uploadrr-EMU da por terminados (`Step done:`) y el reintento que lo reanuda con `--resume`.

Cubre el contrato con Uploadrr-EMU (líneas fijas y flag), que se apunten en el trabajo, lo que el detalle de la subida
enseña y que solo un reintento con los ficheros de la anterior lance `--resume`.
"""
from __future__ import annotations

import json
import time

import pytest

from emuwarez_uploadrr.services import subida_pasos as sp
from emuwarez_uploadrr.services.uploadrr_contract import build_uploadrr_emu_command


def _argv(**kw):
    return build_uploadrr_emu_command(python_path="py", uploadrr_script_path="upload.py", prepared_path="/data/x.mkv",
                                      torrent_name="X", tmdb_id=1, category="movie", **kw)


# ---------------------------------------------------------------------------
# El contrato: flag y líneas
# ---------------------------------------------------------------------------

def test_sin_reanudar_no_hay_resume():
    assert "--resume" not in _argv()
    assert "--resume" not in _argv(reanudar=False)


def test_reanudar_añade_resume():
    assert _argv(reanudar=True)[-1] == "--resume"


@pytest.mark.parametrize("linea, esperado", [
    ("Step done: screenshots", "screenshots"),
    ("Step done: torrent", "torrent"),
    ("  Step done: torrent  ", "torrent"),
    ("Torrent URL: https://emu-warez.com/torrents/123", "tracker"),
    ("Step done: tracker", None),            # el tracker lo dice la ficha, no esta línea
    ("Step done: screenshots y más", None),
    ("Generating screenshots (2/3)", None),
    ("INFO Step done: torrent", None),       # una línea del registro que lo cite no cuenta
    ("Torrent URL: ", None),
    ("", None),
])
def test_que_linea_da_un_paso_por_hecho(linea, esperado):
    assert sp.subpaso_de_linea(linea) == esperado


# ---------------------------------------------------------------------------
# Lo guardado y lo que enseña el detalle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo, esperado", [
    (None, []), ("", []), ("no es json", []), ('{"a": 1}', []), ('"torrent"', []),
    ('["torrent", "screenshots"]', ["screenshots", "torrent"]),     # siempre en el orden de la subida
    ('["torrent", "raro"]', ["torrent"]),
])
def test_leer_subpasos_aguanta_cualquier_cosa(crudo, esperado):
    assert sp.leer_subpasos(crudo) == esperado


def test_los_subpasos_solo_cuelgan_del_paso_de_subir():
    pasos = {p["clave"]: p for p in sp.pasos_de_subida("failed", "running", "running", '["screenshots"]')}
    assert [(s["clave"], s["hecho"]) for s in pasos["subida"]["subpasos"]] == [
        ("screenshots", True), ("torrent", False), ("tracker", False)]
    assert all("subpasos" not in pasos[c] for c in ("nomenclatura", "preparacion", "verificacion"))


def test_sin_nada_apuntado_no_se_enseña_ningun_subpaso():
    assert sp.subpasos_de_subida("failed", None) == []
    assert sp.subpasos_de_subida("running", "[]") == []


def test_una_subida_completada_tiene_todos_los_subpasos_hechos_aunque_no_se_apuntaran():
    assert [s["hecho"] for s in sp.subpasos_de_subida("completed", None)] == [True, True, True]


@pytest.mark.parametrize("status, parada, crudo, esperado", [
    ("failed", "running", '["screenshots", "torrent"]', ["Capturas", "Torrent"]),
    ("failed", "running", '["screenshots"]', ["Capturas"]),
    ("cancelled", "finalizing", '["torrent"]', ["Torrent"]),
    ("failed", "running", "[]", []),
    ("failed", "running", None, []),
    # Ya en eMuwarez: reintentar no reanuda nada, chocaría con el duplicado.
    ("failed", "running", '["screenshots", "torrent", "tracker"]', []),
    # Paradas antes de preparar los ficheros no reanudan.
    ("failed", "remux", '["screenshots"]', []),
    ("running", "running", '["screenshots"]', []),
])
def test_lo_que_un_reintento_no_repetiria(status, parada, crudo, esperado):
    assert sp.subpasos_que_reutilizaria(status, parada, crudo) == esperado


# ---------------------------------------------------------------------------
# La migración (esquema 51)
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    yield conn
    conn.close()


def test_la_migracion_añade_las_columnas_y_se_puede_repetir(db_conn):
    from emuwarez_uploadrr.database import _migrate_upload_jobs_pasos_uploadrr
    columnas = lambda: {f[1] for f in db_conn.execute("PRAGMA table_info(upload_jobs)")}  # noqa: E731
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN pasos_uploadrr_json")
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN reanuda_uploadrr")
    assert not {"pasos_uploadrr_json", "reanuda_uploadrr"} & columnas()

    _migrate_upload_jobs_pasos_uploadrr(db_conn)
    _migrate_upload_jobs_pasos_uploadrr(db_conn)

    assert {"pasos_uploadrr_json", "reanuda_uploadrr"} <= columnas()
    db_conn.execute("INSERT INTO upload_jobs (title, path, status, created_at, updated_at) "
                    "VALUES ('x', '/x', 'failed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
    fila = db_conn.execute("SELECT pasos_uploadrr_json, reanuda_uploadrr FROM upload_jobs").fetchone()
    assert tuple(fila) == (None, 0)


# ---------------------------------------------------------------------------
# La ejecución real contra el Uploadrr-EMU falso
# ---------------------------------------------------------------------------

def _preparar_subida(db_conn, tmp_path, uploadrr_dir, python_path, *, reanuda):
    from emuwarez_uploadrr.services.upload_execution import get_upload_job  # noqa: F401
    for k, v in {"uploadrr.path": str(uploadrr_dir), "uploadrr.python_path": python_path,
                 "tmdb.api_key": "tmdb_secret_abc123", "emu.api_key": "emu_secret_xyz789",
                 "uploadrr.timeout": "30"}.items():
        db_conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (k, v))
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00" * 16)
    cur = db_conn.execute(
        "INSERT INTO upload_jobs (title, path, status, stage, source_path, prepared_path, uploadrr_command_json, "
        "reanuda_uploadrr, created_at, updated_at) "
        "VALUES ('T', ?, 'ready', 'preflight', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (str(prepared), str(prepared), str(prepared),
         json.dumps({"category": "movie", "tmdb_id": "1", "resolution": "1080p", "title": "T"}), reanuda))
    db_conn.commit()
    return cur.lastrowid


def _correr(db_conn, jid):
    from emuwarez_uploadrr.services.upload_execution import CONFIRMATION_TOKEN, get_upload_job, start_upload_job
    start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)
    limite = time.monotonic() + 15
    while time.monotonic() < limite:
        job = get_upload_job(jid, conn=db_conn)
        if job["status"] in ("completed", "failed", "cancelled"):
            time.sleep(0.3)
            return get_upload_job(jid, conn=db_conn)
        time.sleep(0.1)
    raise AssertionError("la subida no terminó")


def _logs(db_conn, jid):
    return [f["message"] for f in db_conn.execute("SELECT message FROM upload_job_logs WHERE upload_job_id = ?", (jid,))]


def test_se_apuntan_los_pasos_que_uploadrr_va_terminando(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    jid = _preparar_subida(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, reanuda=0)

    job = _correr(db_conn, jid)

    assert job["status"] == "completed"
    assert sp.leer_subpasos(job["pasos_uploadrr_json"]) == ["screenshots", "torrent", "tracker"]
    assert not any("Reanudando" in m for m in _logs(db_conn, jid))


def test_una_subida_fallida_conserva_los_pasos_que_termino(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch):
    monkeypatch.setenv("FAKE_UPLOADRR_FAIL", "1")
    jid = _preparar_subida(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, reanuda=0)

    job = _correr(db_conn, jid)

    assert job["status"] == "failed"
    # Fallo simulado tras capturas y torrent y antes de subir al tracker.
    assert sp.leer_subpasos(job["pasos_uploadrr_json"]) == ["screenshots", "torrent"]
    assert sp.subpasos_que_reutilizaria(job["status"], job["etapa_parada"], job["pasos_uploadrr_json"]) == ["Capturas", "Torrent"]


def test_solo_un_trabajo_que_reanuda_lanza_resume(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    jid = _preparar_subida(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, reanuda=1)

    job = _correr(db_conn, jid)

    assert job["status"] == "completed"
    assert any("--resume" in m for m in _logs(db_conn, jid))
    assert any("Reanudando" in m for m in _logs(db_conn, jid))
