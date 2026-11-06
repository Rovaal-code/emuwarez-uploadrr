"""La tarea «Copia de seguridad»: crea la copia automática, aplica la retención y registra lo que pasó.

N18 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import os
import re
import stat
import tarfile
from pathlib import Path

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import backup_service as bs
from emuwarez_uploadrr.services.maintenance_service import guardar_opciones
from emuwarez_uploadrr.services.scheduler import TASK_BACKUP, get_scheduled_task, run_scheduled_task
from emuwarez_uploadrr.services.settings import set_setting

CLAVE = "clave-secreta-de-tmdb"
solo_posix = pytest.mark.skipif(os.name == "nt", reason="los permisos 0600 son de POSIX")


def _copia(nombre: str, dir_: Path, contenido: bytes = b"x") -> Path:
    ruta = dir_ / nombre
    ruta.write_bytes(contenido)
    return ruta


def test_la_tarea_programada_crea_la_copia_y_aplica_la_retencion(isolated_db):
    carpeta = isolated_db / "backups"
    carpeta.mkdir()
    for dia in range(1, 10):
        _copia(f"emuwarez_config_auto_2026010{dia}_030000.tar.gz", carpeta)
    conn = connect(db_path())
    init_db(conn)
    try:
        run = run_scheduled_task(conn, TASK_BACKUP, manual=True)

        assert run["status"] == "completed"
        assert "emuwarez_config_auto_" in run["summary"] and "3 automáticas antiguas retiradas" in run["summary"]
        # El tamaño como en Backup: coma decimal y unidad adaptada, no «0.0 MB» para una copia de unos KB.
        assert re.search(r"\(\d+,\d\u00a0(B|KB|MB)\)", run["summary"]), run["summary"]
        assert len(list(carpeta.glob("emuwarez_config_auto_*"))) == 7
        assert get_scheduled_task(conn, TASK_BACKUP)["run_at"] == "03:30"
        assert conn.execute("SELECT status FROM task_runs WHERE name = ?", (TASK_BACKUP,)).fetchone()[0] == "completed"
    finally:
        conn.close()


def test_la_tarea_programada_respeta_cuantas_copias_se_guardan(isolated_db):
    from emuwarez_uploadrr.services.maintenance_service import guardar_opciones
    carpeta = isolated_db / "backups"
    carpeta.mkdir()
    for dia in range(1, 5):
        _copia(f"emuwarez_config_auto_2026010{dia}_030000.tar.gz", carpeta)
    conn = connect(db_path())
    init_db(conn)
    try:
        guardar_opciones(conn, {"copias.conservar": 2})
        run_scheduled_task(conn, TASK_BACKUP, manual=True)
        assert len(list(carpeta.glob("emuwarez_config_auto_*"))) == 2
    finally:
        conn.close()


def test_la_copia_de_la_tarea_programada_lleva_la_base_sin_claves(isolated_db):
    from emuwarez_uploadrr.services.settings import set_setting
    conn = connect(db_path())
    init_db(conn)
    try:
        set_setting(conn, "tmdb.api_key", "clave-secreta-de-tmdb")
        conn.commit()
        run_scheduled_task(conn, TASK_BACKUP, manual=True)
    finally:
        conn.close()
    copia = next((isolated_db / "backups").glob("emuwarez_config_auto_*"))
    with tarfile.open(copia) as tar:
        assert b"clave-secreta-de-tmdb" not in tar.extractfile("emuwarez_uploadrr.db").read()


def test_la_tarea_programada_registra_el_fallo_si_no_hay_directorio(isolated_db, monkeypatch):
    conn = connect(db_path())
    init_db(conn)
    try:
        monkeypatch.setenv("CONFIG_DIR", str(isolated_db / "no-existe"))
        run = run_scheduled_task(conn, TASK_BACKUP, manual=True)
        assert run["status"] == "failed" and "CONFIG_DIR no existe" in run["summary"]
    finally:
        conn.close()


def _base_de_la_copia(copia: Path) -> bytes:
    with tarfile.open(copia) as tar:
        return tar.extractfile("emuwarez_uploadrr.db").read()


def _copia_con_clave(isolated_db, *, incluir: bool | None):
    """Pone una clave, activa (o no) la opción y ejecuta la tarea; devuelve su resultado."""
    conn = connect(db_path())
    init_db(conn)
    try:
        set_setting(conn, "tmdb.api_key", CLAVE)
        conn.commit()
        if incluir is not None:
            guardar_opciones(conn, {"copias.incluir_claves": int(incluir)})
        return run_scheduled_task(conn, TASK_BACKUP, manual=True)
    finally:
        conn.close()


@solo_posix
@pytest.mark.parametrize("incluir", [None, False, True])
def test_las_copias_automaticas_van_en_0600_lleven_o_no_claves(isolated_db, incluir):
    old = os.umask(0)
    try:
        run = _copia_con_clave(isolated_db, incluir=incluir)
    finally:
        os.umask(old)
    copia = next((isolated_db / "backups").glob("emuwarez_config_auto_*"))
    assert run["status"] == "completed"
    assert stat.S_IMODE(os.stat(copia).st_mode) == 0o600


def test_por_defecto_las_copias_automaticas_no_llevan_claves(isolated_db):
    _copia_con_clave(isolated_db, incluir=None)
    copia = next((isolated_db / "backups").glob("emuwarez_config_auto_*"))
    assert not copia.name.endswith("_with_secrets.tar.gz")
    assert CLAVE.encode() not in _base_de_la_copia(copia)


def test_con_la_opcion_activada_las_copias_automaticas_llevan_las_claves(isolated_db):
    run = _copia_con_clave(isolated_db, incluir=True)

    copia = next((isolated_db / "backups").glob("emuwarez_config_auto_*"))
    assert copia.name.endswith("_with_secrets.tar.gz")
    assert CLAVE.encode() in _base_de_la_copia(copia)
    assert run["summary"].startswith("Copia emuwarez_config_auto_") and " con claves" in run["summary"]
    marcada = next(b for b in bs.list_config_backups() if b["name"] == copia.name)
    assert (marcada["tipo"], marcada["con_claves"]) == ("automatica", True)


def test_apagar_la_opcion_vuelve_a_las_copias_sin_claves(isolated_db):
    _copia_con_clave(isolated_db, incluir=True)
    conn = connect(db_path())
    init_db(conn)
    try:
        guardar_opciones(conn, {"copias.incluir_claves": 0})
        run_scheduled_task(conn, TASK_BACKUP, manual=True)
    finally:
        conn.close()
    con, sin = sorted((isolated_db / "backups").glob("emuwarez_config_auto_*"), key=lambda p: p.name.endswith("_with_secrets.tar.gz"), reverse=True)
    assert CLAVE.encode() in _base_de_la_copia(con) and CLAVE.encode() not in _base_de_la_copia(sin)


def test_la_retencion_cuenta_igual_las_copias_con_y_sin_claves(isolated_db):
    carpeta = isolated_db / "backups"
    carpeta.mkdir()
    _copia("emuwarez_config_auto_20260101_033000_with_secrets.tar.gz", carpeta)
    _copia("emuwarez_config_auto_20260102_033000.tar.gz", carpeta)
    _copia("emuwarez_config_20260101_000000_with_secrets.tar.gz", carpeta)  # manual con claves: intocable

    assert bs.retirar_copias_automaticas(1) == [
        "emuwarez_config_auto_20260101_033000_with_secrets.tar.gz"]
    assert (carpeta / "emuwarez_config_20260101_000000_with_secrets.tar.gz").exists()


@pytest.mark.parametrize("valor", [2, -1])
def test_la_opcion_solo_admite_0_o_1(isolated_db, valor):
    conn = connect(db_path())
    init_db(conn)
    try:
        with pytest.raises(ValueError, match="entre 0 y 1"):
            guardar_opciones(conn, {"copias.incluir_claves": valor})
    finally:
        conn.close()


def test_la_opcion_se_activa_por_la_api_con_su_aviso(client, auth_headers):
    r = client.put("/api/tasks/scheduled/backup-config/opciones",
                   json={"valores": {"copias.incluir_claves": 1}}, headers=auth_headers)
    assert r.status_code == 200
    opcion = next(o for o in r.json()["opciones"] if o["clave"] == "copias.incluir_claves")
    assert opcion["valor"] == 1 and opcion["nota"]
    assert client.put("/api/tasks/scheduled/backup-config/opciones",
                      json={"valores": {"copias.incluir_claves": 5}}, headers=auth_headers).status_code == 422
