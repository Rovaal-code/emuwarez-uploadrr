"""La tarea «Copia de seguridad»: crea la copia automática, aplica la retención y registra lo que pasó.

N18 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import tarfile
from pathlib import Path

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.scheduler import TASK_BACKUP, get_scheduled_task, run_scheduled_task


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
        assert "emuwarez_config_auto_" in run["summary"] and "3 automática(s) antigua(s) retirada(s)" in run["summary"]
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
