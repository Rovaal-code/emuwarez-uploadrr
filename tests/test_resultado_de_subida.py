"""La ficha del torrent de cada subida, el motivo real de un fallo y lo que dicen los avisos."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.upload_execution import (
    _notify_upload_completed,
    _notify_upload_failed,
    _run_uploadrr_subprocess,
    get_upload_job,
)


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _job(conn, status="completed", *, title="Peli", request_title=None, request_url=None):
    cur = conn.execute(
        "INSERT INTO upload_jobs (title, path, status, stage, request_title, request_url, created_at, updated_at)"
        " VALUES (?, '', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (title, status, status, request_title, request_url),
    )
    conn.commit()
    return cur.lastrowid


def _notificaciones(conn, job_id):
    return conn.execute(
        "SELECT * FROM notifications WHERE entity_type = 'upload_job' AND entity_id = ? ORDER BY id", (job_id,)
    ).fetchall()


def _ejecutar(db_conn, tmp_path, jid, *, returncode, stdout, stderr=""):
    """Corre _run_uploadrr_subprocess con un proceso de mentira que imprime esa salida."""
    proc = MagicMock()
    proc.pid = 4242
    proc.returncode = returncode
    proc.wait.return_value = returncode
    proc.stdout = iter(stdout.splitlines(keepends=True))
    proc.stderr = iter(stderr.splitlines(keepends=True))
    with patch("subprocess.Popen", return_value=proc):
        _run_uploadrr_subprocess(jid, {
            "executable": "/usr/bin/python3",
            "args": ["/fake/upload.py", "x"],
            "cwd": str(tmp_path),
            "command_preview": "python3 upload.py x",
        }, [])
    return get_upload_job(jid, conn=db_conn)


# ---------------------------------------------------------------------------
# F2 / EJEC-8: la ficha del torrent es la línea `Torrent URL:`
# ---------------------------------------------------------------------------

SALIDA_CON_OTRAS_URLS = (
    "[pixhost] https://t.pixhost.to/thumbs/1/captura.jpg\n"
    "TMDb: https://www.themoviedb.org/movie/550\n"
    "Torrent URL: https://emu-warez.com/torrents/123456\n"
    "Torrent uploaded successfully!\n"
)


def test_una_subida_completada_guarda_la_ficha_y_el_id_del_torrent(db_conn, tmp_path):
    jid = _job(db_conn, "ready")
    job = _ejecutar(db_conn, tmp_path, jid, returncode=0, stdout=SALIDA_CON_OTRAS_URLS)

    assert job["status"] == "completed"
    assert job["result_url"] == "https://emu-warez.com/torrents/123456"
    assert job["result_torrent_id"] == "123456"
    artefactos = {a["artifact_type"]: a for a in db_conn.execute("SELECT * FROM upload_artifacts WHERE upload_job_id = ?", (jid,))}
    assert artefactos["uploaded_url"]["url"] == "https://emu-warez.com/torrents/123456"
    assert artefactos["torrent_id"]["value"] == "123456"


def test_sin_la_linea_fija_no_se_inventa_ninguna_ficha(db_conn, tmp_path):
    jid = _job(db_conn, "ready")
    job = _ejecutar(db_conn, tmp_path, jid, returncode=0, stdout="TMDb: https://www.themoviedb.org/movie/550\nid: 54321\n")

    assert job["status"] == "completed"
    assert job["result_url"] is None
    assert job["result_torrent_id"] is None


def test_el_aviso_de_subida_completada_enlaza_a_la_ficha_y_nombra_la_peticion(db_conn):
    jid = _job(db_conn, request_title="Dune: Parte Dos", request_url="https://emu-warez.com/requests/9")

    _notify_upload_completed(jid, "https://emu-warez.com/torrents/123456")

    (aviso,) = _notificaciones(db_conn, jid)
    assert aviso["link"] == "https://emu-warez.com/torrents/123456"
    assert "Dune: Parte Dos" in aviso["body"]


# ---------------------------------------------------------------------------
# EJEC-2 / N15: el motivo real del fallo, no el cierre de Uploadrr
# ---------------------------------------------------------------------------

SALIDA_DE_DUPLICADO = (
    "Searching for existing torrents on EMU...\n"
    "Exact size match. Aborting..\n"
    "╭──────────────────── Potential duplicate on EMU ────────────────────╮\n"
    "│ Path: /data/uploads/                                               │\n"
    "│ • Peli.2020.1080p.mkv                                              │\n"
    "╰────────────────────────────────────────────────────────────────────╯\n"
    "╭───────────────────────── Upload Summary ───────────────────────────╮\n"
    "│ Failed Uploads: 1                                                  │\n"
    "╰────────────────────────────────────────────────────────────────────╯\n"
    "                         see you soon ^.<\n"
)


def test_un_fallo_guarda_y_avisa_del_motivo_real(db_conn, tmp_path):
    jid = _job(db_conn, "ready", request_title="Dune: Parte Dos")
    job = _ejecutar(db_conn, tmp_path, jid, returncode=1, stdout=SALIDA_DE_DUPLICADO)

    assert job["status"] == "failed"
    assert job["error_message"] == "Potential duplicate on EMU\nExit code: 1"
    (aviso,) = _notificaciones(db_conn, jid)
    assert "Potential duplicate on EMU" in aviso["body"]
    assert "see you soon" not in aviso["body"]
    assert "Dune: Parte Dos" in aviso["body"]
    assert aviso["link"] is None


def test_un_fallo_tras_subir_el_torrent_conserva_su_ficha_y_la_enlaza(db_conn, tmp_path):
    jid = _job(db_conn, "ready")
    salida = SALIDA_CON_OTRAS_URLS + "Torrent client add failed: boom\n"
    job = _ejecutar(db_conn, tmp_path, jid, returncode=1, stdout=salida)

    assert job["status"] == "failed"
    assert job["result_url"] == "https://emu-warez.com/torrents/123456"
    assert job["result_torrent_id"] == "123456"
    (aviso,) = _notificaciones(db_conn, jid)
    assert aviso["link"] == "https://emu-warez.com/torrents/123456"
    assert "llegó a subirse" in aviso["body"]


def test_un_corte_por_tiempo_tras_subir_el_torrent_conserva_su_ficha_y_la_enlaza(db_conn, tmp_path):
    """El tiempo agotado es una forma normal de fallar tras subir: el tracker ya tiene el torrent."""
    jid = _job(db_conn, "ready")
    codigo = "import time; print('Torrent URL: https://emu-warez.com/torrents/321', flush=True); time.sleep(60)"
    _run_uploadrr_subprocess(jid, {
        "executable": sys.executable,
        "args": ["-c", codigo],
        "cwd": str(tmp_path),
        "command_preview": "python -c ...",
        "timeout": 1,
    }, [])

    job = get_upload_job(jid, conn=db_conn)
    assert job["status"] == "failed" and job["stage"] == "timeout"
    assert job["result_url"] == "https://emu-warez.com/torrents/321"
    assert job["result_torrent_id"] == "321"
    assert job["torrent_subido"] == 1
    (aviso,) = _notificaciones(db_conn, jid)
    assert aviso["link"] == "https://emu-warez.com/torrents/321"
    assert "llegó a subirse" in aviso["body"]


def test_un_corte_por_tiempo_sin_haber_subido_no_inventa_ficha(db_conn, tmp_path):
    jid = _job(db_conn, "ready")
    _run_uploadrr_subprocess(jid, {
        "executable": sys.executable,
        "args": ["-c", "import time; print('Hashing 10%', flush=True); time.sleep(60)"],
        "cwd": str(tmp_path),
        "command_preview": "python -c ...",
        "timeout": 1,
    }, [])

    job = get_upload_job(jid, conn=db_conn)
    assert job["stage"] == "timeout"
    assert job["result_url"] is None and job["torrent_subido"] == 0
    (aviso,) = _notificaciones(db_conn, jid)
    assert aviso["link"] is None


def test_el_aviso_de_fallo_sin_ficha_no_lleva_enlace(db_conn):
    jid = _job(db_conn, "failed")

    _notify_upload_failed(jid, "TMDb ID not found\nExit code: 1")

    (aviso,) = _notificaciones(db_conn, jid)
    assert aviso["link"] is None
    assert "TMDb ID not found" in aviso["body"]
