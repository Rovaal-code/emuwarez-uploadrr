"""Cancelar, el timeout y el arranque de Uploadrr.

Procesos reales contra tests/fixtures/fake_uploadrr_emu.py (nunca un Uploadrr
de verdad), salvo donde se simula con Popen falso una carrera de milisegundos.
"""
from __future__ import annotations

import json
import os
import signal
import threading
import time
from unittest.mock import MagicMock, patch

import psutil
import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import upload_execution as ue
from emuwarez_uploadrr.services.upload_execution import concurrencia, config as cfg, ejecucion, estado
from emuwarez_uploadrr.services.upload_execution import (
    CONFIRMATION_TOKEN,
    cancel_upload_job,
    get_upload_job,
    start_upload_job,
)


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _settings(conn, uploadrr_dir, python_path, *, timeout=None):
    ajustes = {
        "uploadrr.path": str(uploadrr_dir),
        "uploadrr.python_path": python_path,
        "tmdb.api_key": "tmdb_secret_abc123",
        "emu.api_key": "emu_secret_xyz789",
    }
    if timeout is not None:
        ajustes["uploadrr.timeout"] = str(timeout)
    for k, v in ajustes.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?, ?, 0)", (k, v))
    conn.commit()


def _job(conn, prepared_path="/fake/movie.mkv", status="ready"):
    cmd_json = json.dumps({"category": "movie", "tmdb_id": "1", "resolution": "1080p", "title": "Peli 2024"})
    cur = conn.execute(
        """INSERT INTO upload_jobs
           (library_item_id, title, path, status, stage, source_path, prepared_path,
            uploadrr_command_json, created_at, updated_at)
           VALUES (NULL, 'Peli 2024', ?, ?, 'preflight', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (prepared_path, status, prepared_path, prepared_path, cmd_json),
    )
    conn.commit()
    return cur.lastrowid


def _estado(conn, jid):
    return conn.execute("SELECT status, stage, exit_code FROM upload_jobs WHERE id = ?", (jid,)).fetchone()


def _esperar(condicion, plazo=10.0):
    limite = time.monotonic() + plazo
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.05)
    return False


def _vivo(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _terminal(conn, jid, plazo=15.0):
    assert _esperar(lambda: _estado(conn, jid)["status"] in ("completed", "failed", "cancelled"), plazo)
    time.sleep(0.3)  # el finally del hilo (restaurar config, logs) va justo detrás
    return _estado(conn, jid)


@pytest.fixture
def hijo_de_uploadrr(tmp_path, monkeypatch):
    """El fake arranca un hijo que sigue vivo y con las tuberías abiertas, como mkbrr o ffmpeg."""
    pidfile = tmp_path / "hijo.pid"
    monkeypatch.setenv("FAKE_UPLOADRR_GRANDCHILD", str(pidfile))

    def pid() -> int:
        assert _esperar(pidfile.exists, 5), "el fake no llegó a arrancar su hijo"
        assert _esperar(lambda: pidfile.read_text().strip() != "", 5)
        return int(pidfile.read_text())

    yield pid
    if pidfile.exists() and pidfile.read_text().strip():
        try:
            os.kill(int(pidfile.read_text()), signal.SIGKILL)
        except ProcessLookupError:
            pass


def _lanzar(db_conn, tmp_path, fake_dir, python_path, **kw):
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00" * 16)
    _settings(db_conn, fake_dir, python_path, **kw)
    jid = _job(db_conn, str(prepared))
    assert start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn)["action"] == "started"
    return jid


# --- F5: Cancelar y el timeout paran a Uploadrr Y a lo que lanzó -----------------------------

def test_cancelar_mata_tambien_a_los_hijos_de_uploadrr(
        db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch, hijo_de_uploadrr):
    monkeypatch.setenv("FAKE_UPLOADRR_SLEEP", "30")
    jid = _lanzar(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    hijo = hijo_de_uploadrr()
    assert _esperar(lambda: get_upload_job(jid, conn=db_conn).get("process_id"), 5)
    assert _vivo(hijo)

    assert cancel_upload_job(jid, conn=db_conn)["ok"] is True

    assert _terminal(db_conn, jid)["status"] == "cancelled"
    assert _esperar(lambda: not _vivo(hijo), 5), "el hijo de Uploadrr siguió vivo tras Cancelar"


def test_el_timeout_mata_el_grupo_y_deja_la_subida_en_timeout(
        db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch, hijo_de_uploadrr):
    monkeypatch.setenv("FAKE_UPLOADRR_SLEEP", "30")
    jid = _lanzar(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, timeout=2)
    hijo = hijo_de_uploadrr()

    fila = _terminal(db_conn, jid)

    assert (fila["status"], fila["stage"]) == ("failed", "timeout")
    assert _esperar(lambda: not _vivo(hijo), 5), "el hijo de Uploadrr siguió vivo tras el timeout"


# --- EJEC-10: el resultado lo decide el código de salida, no el fin de las tuberías ----------

def test_una_subida_buena_no_espera_a_las_tuberias_de_un_hijo(
        db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, monkeypatch, hijo_de_uploadrr):
    """Uploadrr sale con 0 pero su hijo hereda stdout: esperar a que cierre daba
    la subida por fallida («timeout») cuando el torrent ya estaba en el tracker."""
    monkeypatch.setattr(ejecucion, "_GRACIA_LECTORES", 1)
    jid = _lanzar(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path, timeout=30)
    hijo = hijo_de_uploadrr()

    fila = _terminal(db_conn, jid, plazo=20)

    assert (fila["status"], fila["exit_code"]) == ("completed", 0)
    assert _esperar(lambda: not _vivo(hijo), 5), "el hijo que retenía la tubería no se cortó"


def test_ctrl_c_en_el_cli_detiene_a_uploadrr(db_conn, tmp_path, fake_uploadrr_emu_dir, fake_uploadrr_python_path):
    """Uploadrr va en su propia sesión y ya no recibe el Ctrl-C del terminal: el
    CLI (`start --wait`) tiene que pararlo él al salir."""
    prepared = tmp_path / "prepared.mkv"
    prepared.write_bytes(b"\x00" * 16)
    _settings(db_conn, fake_uploadrr_emu_dir, fake_uploadrr_python_path)
    jid = _job(db_conn, str(prepared))
    proc = MagicMock(pid=4242)
    ue._PROCESOS[jid] = proc

    class HiloInterrumpido:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def join(self):
            raise KeyboardInterrupt

    try:
        with patch.object(threading, "Thread", HiloInterrumpido), patch.object(ejecucion, "_detener_proceso") as detener:
            with pytest.raises(KeyboardInterrupt):
                start_upload_job(jid, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=db_conn, wait=True)
    finally:
        ue._PROCESOS.pop(jid, None)

    detener.assert_called_once_with(proc)


# --- EJEC-3: Cancelar no se puede pisar ni lanzar la subida después ----------------------------

def _cmd(tmp_path, **extra):
    return {
        "executable": "/usr/bin/python3", "args": [], "cwd": str(tmp_path),
        "command_preview": "python3 upload.py", **extra,
    }


def _cancelar_en_la_base(jid):
    conn = connect(db_path())
    try:
        conn.execute("UPDATE upload_jobs SET status = 'cancelled', stage = 'cancelled' WHERE id = ?", (jid,))
        conn.commit()
    finally:
        conn.close()


def test_un_job_cancelado_antes_de_arrancar_no_lanza_uploadrr(db_conn, tmp_path):
    jid = _job(db_conn, status="cancelled")

    with patch("subprocess.Popen") as popen:
        ue._run_uploadrr_subprocess(jid, _cmd(tmp_path), [])

    popen.assert_not_called()
    assert _estado(db_conn, jid)["status"] == "cancelled"


def test_cancelar_mientras_se_stagea_el_config_no_lanza_uploadrr(db_conn, tmp_path, fake_uploadrr_emu_dir):
    """Entre marcarlo «en marcha» y el Popen el job no tiene PID: un Cancelar ahí
    solo escribía «cancelled», y el siguiente paso lo volvía a poner «running»."""
    jid = _job(db_conn)
    original = ue._acquire_staged_config

    def cancelar_y_stagear(job_id, cwd):
        _cancelar_en_la_base(job_id)
        return original(job_id, cwd)

    with patch.object(ejecucion, "_acquire_staged_config", cancelar_y_stagear), patch("subprocess.Popen") as popen:
        ue._run_uploadrr_subprocess(jid, _cmd(fake_uploadrr_emu_dir, runtime_type="uploadrr_emu"), [])

    popen.assert_not_called()
    assert _estado(db_conn, jid)["status"] == "cancelled"
    assert ue._config_stage_refcount == {}
    config = fake_uploadrr_emu_dir / "data" / "config.yaml"
    assert config.read_bytes() == (fake_uploadrr_emu_dir / "data" / "config.yaml.bak").read_bytes()


def test_cancelar_justo_despues_del_popen_detiene_el_proceso(db_conn, tmp_path):
    jid = _job(db_conn)
    proc = MagicMock(pid=4242, returncode=-15)
    proc.wait.return_value = -15
    proc.stdout = iter([])
    proc.stderr = iter([])

    def lanzar(*a, **k):
        _cancelar_en_la_base(jid)  # Cancelar no ve ningún PID todavía
        return proc

    with patch("subprocess.Popen", side_effect=lanzar), patch.object(ejecucion, "_detener_proceso") as detener:
        ue._run_uploadrr_subprocess(jid, _cmd(tmp_path), [])

    detener.assert_called_once_with(proc)
    assert _estado(db_conn, jid)["status"] == "cancelled"


def test_uploadrr_arranca_en_su_propio_grupo_de_procesos(db_conn, tmp_path):
    jid = _job(db_conn)
    proc = MagicMock(pid=4242, returncode=0)
    proc.wait.return_value = 0
    proc.stdout = iter([])
    proc.stderr = iter([])

    with patch("subprocess.Popen", return_value=proc) as popen:
        ue._run_uploadrr_subprocess(jid, _cmd(tmp_path), [])

    assert popen.call_args.kwargs["start_new_session"] is True


# --- EJEC-6: un fallo en un paso previo no deja el job «en marcha» ni el config sin restaurar ---

def test_un_fallo_al_escribir_el_primer_estado_deja_el_job_fallido(db_conn, tmp_path):
    jid = _job(db_conn)

    with patch.object(ejecucion, "_avanzar_job", side_effect=RuntimeError("database is locked")), \
            patch("subprocess.Popen") as popen:
        ue._run_uploadrr_subprocess(jid, _cmd(tmp_path), [])

    popen.assert_not_called()
    assert _estado(db_conn, jid)["status"] == "failed"


def test_si_falla_tras_stagear_el_config_se_restaura(db_conn, tmp_path, fake_uploadrr_emu_dir):
    """El contador subía en _acquire_staged_config y la escritura de estado de
    después iba fuera del try: si fallaba, nadie lo soltaba y el config.yaml con
    las claves reales no se restauraba hasta reiniciar."""
    jid = _job(db_conn)
    real = estado._avanzar_job
    llamadas = []

    def falla_la_tercera(*a, **k):
        llamadas.append(1)
        if len(llamadas) == 3:
            raise RuntimeError("database is locked")
        return real(*a, **k)

    original = (fake_uploadrr_emu_dir / "data" / "config.yaml").read_bytes()
    with patch.object(ejecucion, "_avanzar_job", falla_la_tercera), patch("subprocess.Popen") as popen:
        ue._run_uploadrr_subprocess(jid, _cmd(fake_uploadrr_emu_dir, runtime_type="uploadrr_emu"), [])

    popen.assert_not_called()
    assert _estado(db_conn, jid)["status"] == "failed"
    assert ue._config_stage_refcount == {}
    assert (fake_uploadrr_emu_dir / "data" / "config.yaml").read_bytes() == original


def test_el_turno_no_revienta_si_falla_la_base(db_conn):
    """acquire corre antes del try de _run_queued_job: si lanzaba, el hilo moría
    en silencio y el job se quedaba en cola."""
    puerta = ue._UploadConcurrencyGate()

    with patch.object(concurrencia, "get_upload_max_concurrent", side_effect=RuntimeError("database is locked")):
        puerta.acquire(1)

    assert puerta._active == 1
    puerta.release()


def test_esperar_turno_no_muere_si_falla_el_log(db_conn):
    puerta = ue._UploadConcurrencyGate()
    admitido = threading.Event()

    def espera():
        puerta.acquire(2)
        admitido.set()
        puerta.release()

    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=1), \
            patch.object(concurrencia, "append_upload_log", side_effect=RuntimeError("database is locked")):
        puerta.acquire(1)
        hilo = threading.Thread(target=espera, daemon=True)
        hilo.start()
        time.sleep(0.3)
        assert not admitido.is_set()
        puerta.release()
        hilo.join(timeout=5)

    assert admitido.is_set()


# --- Cancelar desde otro proceso: el PID guardado puede ser de cualquier otro ------------------

def _proceso_ajeno(*extra):
    """Un proceso en su propia sesión (como Uploadrr) con esos argumentos de más."""
    import subprocess
    import sys
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", *extra], start_new_session=True)


def _job_con_pid(conn, pid, source_path):
    jid = _job(conn, source_path, status="running")
    conn.execute("UPDATE upload_jobs SET process_id = ?, safe_command_json = ? WHERE id = ?",
                 (pid, json.dumps({"source_path": source_path}), jid))
    conn.commit()
    return jid


def test_cancelar_no_senala_un_pid_que_ya_no_es_de_uploadrr(db_conn):
    """Con el job lanzado por otro proceso solo se conoce el PID, y los PID se
    reutilizan: si ya no es el Uploadrr de este job no se le manda nada."""
    ajeno = _proceso_ajeno()
    try:
        jid = _job_con_pid(db_conn, ajeno.pid, "/data/uploads/Pack")

        assert cancel_upload_job(jid, conn=db_conn)["ok"] is True

        time.sleep(0.5)
        assert ajeno.poll() is None, "se señaló un proceso que no era de este job"
        assert _estado(db_conn, jid)["status"] == "cancelled"
    finally:
        ajeno.kill()
        ajeno.wait()


def test_cancelar_senala_al_uploadrr_de_otro_proceso(db_conn):
    ruta = "/data/uploads/Pack"
    uploadrr = _proceso_ajeno("/opt/Uploadrr/upload.py", ruta, "-tk", "EMU")
    try:
        jid = _job_con_pid(db_conn, uploadrr.pid, ruta)

        assert cancel_upload_job(jid, conn=db_conn)["ok"] is True

        assert _esperar(lambda: uploadrr.poll() is not None, 5)
    finally:
        if uploadrr.poll() is None:
            uploadrr.kill()
        uploadrr.wait()


# --- Apagar el servidor: Uploadrr y mkvmerge ya no caen con el terminal ------------------------

def test_apagar_el_servidor_detiene_a_uploadrr_y_al_remux():
    from emuwarez_uploadrr.services import mkv_remux

    uploadrr, remux = _proceso_ajeno(), _proceso_ajeno()
    ue._PROCESOS[987654] = uploadrr
    mkv_remux._REMUXES.add(remux)
    try:
        ue.detener_procesos_en_marcha()
        mkv_remux.detener_remuxes()

        assert _esperar(lambda: uploadrr.poll() is not None and remux.poll() is not None, 5)
    finally:
        ue._PROCESOS.pop(987654, None)
        mkv_remux._REMUXES.discard(remux)
        for p in (uploadrr, remux):
            if p.poll() is None:
                p.kill()
            p.wait()


def test_el_apagado_de_la_aplicacion_detiene_los_procesos():
    from fastapi.testclient import TestClient

    from emuwarez_uploadrr.web.app import create_app

    with patch.object(ue, "detener_procesos_en_marcha") as uploadrr, \
            patch("emuwarez_uploadrr.services.mkv_remux.detener_remuxes") as remux:
        with TestClient(create_app()):
            uploadrr.assert_not_called()
        uploadrr.assert_called_once()
        remux.assert_called_once()


# --- Apagar el servidor: nada se lanza durante el apagado ni se escapa de la lista -------------

class _MkvmergeFalso:
    """Lo que devuelve el Popen de mkvmerge en estos tests, con un proceso real detrás."""
    def __init__(self, real):
        self._real = real
        self.pid = real.pid
        self.stdout = iter([])

    def wait(self, timeout=None):
        return self._real.wait(timeout)

    def kill(self):
        self._real.kill()


def _remux_de_prueba(conn, tmp_path):
    from tests.test_mkv_remux import _SAMPLE_MKV_JSON, _enable_reorder, _insert_library_item

    mkv = tmp_path / "Film.2024.mkv"
    mkv.write_bytes(b"fake mkv original")
    item_id = _insert_library_item(conn, prepared_path=str(mkv))
    _enable_reorder(conn)
    patches = (
        patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available",
              return_value={"available": True, "path": "/usr/bin/mkvmerge"}),
        patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json",
              return_value={"ok": True, "data": _SAMPLE_MKV_JSON}),
    )
    return item_id, patches


def _aplicar_remux(item_id):
    # Sin conexión: apply_remux abre la suya, en el hilo desde el que se llama.
    from emuwarez_uploadrr.services.mkv_remux import REMUX_CONFIRMATION_TOKEN, apply_remux
    return apply_remux(item_id, dry_run=False, apply=True, confirmation=REMUX_CONFIRMATION_TOKEN)


def test_un_remux_que_se_lanza_mientras_se_apaga_no_se_escapa(db_conn, tmp_path):
    """El apagado hacía una foto de los mkvmerge en marcha, y uno lanzado justo
    antes de apuntarse quedaba fuera y seguía escribiendo tras apagar."""
    from emuwarez_uploadrr.services import mkv_remux

    item_id, (p_mkvmerge, p_pistas) = _remux_de_prueba(db_conn, tmp_path)
    real = _proceso_ajeno()
    lanzando, seguir = threading.Event(), threading.Event()

    def lanzar(*args, **kwargs):
        lanzando.set()
        assert seguir.wait(10)
        return _MkvmergeFalso(real)

    resultado = []
    try:
        with p_mkvmerge, p_pistas, patch("emuwarez_uploadrr.services.mkv_remux.subprocess.Popen", side_effect=lanzar):
            remux = threading.Thread(target=lambda: resultado.append(_aplicar_remux(item_id)), daemon=True)
            remux.start()
            assert lanzando.wait(5)
            apagado = threading.Thread(target=mkv_remux.detener_remuxes, daemon=True)
            apagado.start()
            apagado.join(timeout=0.5)
            assert apagado.is_alive(), "el apagado no esperó a que el proceso en lanzamiento se apuntara"

            seguir.set()
            apagado.join(timeout=5)
            remux.join(timeout=10)

        assert _esperar(lambda: real.poll() is not None, 5), "el mkvmerge lanzado durante el apagado no se detuvo"
        assert resultado and resultado[0]["status"] == "error"
    finally:
        if real.poll() is None:
            real.kill()
        real.wait()


def test_no_se_lanza_un_remux_una_vez_empezado_el_apagado(db_conn, tmp_path):
    from emuwarez_uploadrr.services import mkv_remux

    item_id, (p_mkvmerge, p_pistas) = _remux_de_prueba(db_conn, tmp_path)
    mkv_remux.detener_remuxes()

    with p_mkvmerge, p_pistas, patch("emuwarez_uploadrr.services.mkv_remux.subprocess.Popen") as popen:
        resultado = _aplicar_remux(item_id)

    popen.assert_not_called()
    assert resultado["status"] == "error" and "apagando" in resultado["errors"][0]


def test_no_se_lanza_uploadrr_una_vez_empezado_el_apagado(db_conn, tmp_path):
    jid = _job(db_conn)
    ue.detener_procesos_en_marcha()

    with patch("subprocess.Popen") as popen:
        ue._run_uploadrr_subprocess(jid, _cmd(tmp_path), [])

    popen.assert_not_called()
    assert _estado(db_conn, jid)["status"] == "failed"


# --- Sin config.yaml preparado no se lanza Uploadrr --------------------------------------------

def test_si_no_se_puede_preparar_el_config_el_job_falla_sin_lanzar_uploadrr(db_conn, fake_uploadrr_emu_dir):
    """Preparar el config falló (en la imagen: EPERM al sustituir el enlace) y la
    subida se lanzaba igual, con el config sin las claves: TMDb 401, dupes mal."""
    jid = _job(db_conn)

    with patch.object(cfg, "write_staged_config", side_effect=PermissionError(1, "Operation not permitted")), \
            patch("subprocess.Popen") as popen:
        ue._run_uploadrr_subprocess(jid, _cmd(fake_uploadrr_emu_dir, runtime_type="uploadrr_emu"), [])

    popen.assert_not_called()
    fila = db_conn.execute("SELECT status, error_message FROM upload_jobs WHERE id = ?", (jid,)).fetchone()
    assert fila["status"] == "failed"
    assert "No se pudo preparar el config.yaml de Uploadrr" in fila["error_message"]
    assert "No se lanza la subida" in fila["error_message"]
    assert ue._config_stage_refcount == {}
