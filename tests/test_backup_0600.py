"""Los backups y la copia de antes de migrar se guardan solo legibles por su dueño (0600).

INFRA-9 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import datetime
import os
import sqlite3
import stat
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import backup_service as bs

solo_posix = pytest.mark.skipif(os.name == "nt", reason="los permisos 0600 son de POSIX")


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    (d / "emuwarez_uploadrr.db").write_text("fake db")
    (d / "settings.json").write_text("{}")
    monkeypatch.setenv("CONFIG_DIR", str(d))
    return d


@solo_posix
@pytest.mark.parametrize("con_claves", [False, True])
def test_el_backup_nace_solo_legible_por_su_dueno(config_dir, con_claves):
    old = os.umask(0)  # sin umask que lo recorte: el modo es cosa del código
    try:
        r = bs.create_config_backup(include_secrets=con_claves, confirmation=bs.RESTORE_CONFIRMATION if con_claves else None)
    finally:
        os.umask(old)
    assert r["ok"]
    assert stat.S_IMODE(os.stat(r["archive_path"]).st_mode) == 0o600


@solo_posix
def test_un_backup_que_ya_existia_con_otro_modo_tambien_acaba_en_0600(config_dir, monkeypatch):
    class Reloj:
        @staticmethod
        def now():
            return datetime.datetime(2026, 1, 2, 3, 4, 5)
    monkeypatch.setattr(bs, "datetime", SimpleNamespace(datetime=Reloj))
    destino = bs._get_backup_dir() / "emuwarez_config_20260102_030405.tar.gz"
    destino.write_bytes(b"viejo")
    destino.chmod(0o644)

    r = bs.create_config_backup()

    assert Path(r["archive_path"]) == destino
    assert stat.S_IMODE(os.stat(destino).st_mode) == 0o600
    assert tarfile.is_tarfile(str(destino))


@solo_posix
def test_la_copia_antes_de_migrar_tambien_va_en_0600(isolated_db):
    from emuwarez_uploadrr.database import SCHEMA_VERSION, olvidar_esquema, preparar_base, set_state
    olvidar_esquema()
    c = connect(db_path())
    init_db(c)
    set_state(c, "schema_version", str(SCHEMA_VERSION - 1))
    c.commit()
    c.close()
    olvidar_esquema()

    preparar_base()

    copias = list((db_path().parent / "backups").glob("pre-migracion-*.db"))
    assert len(copias) == 1
    assert stat.S_IMODE(os.stat(copias[0]).st_mode) == 0o600


class _ConexionEspia:
    """Una conexión que avisa justo antes del VACUUM INTO y deja que corra (o falle) a voluntad."""

    def __init__(self, real, antes_del_vacuum):
        self.real, self.antes_del_vacuum = real, antes_del_vacuum

    def execute(self, sql, *args):
        if sql.startswith("VACUUM INTO"):
            self.antes_del_vacuum(args[0][0])
        return self.real.execute(sql, *args)

    def commit(self):
        self.real.commit()


@solo_posix
def test_la_copia_previa_ya_es_0600_mientras_se_escribe(isolated_db):
    """VACUUM INTO crea el fichero con el umask: sin crearlo antes, queda legible hasta el chmod."""
    from emuwarez_uploadrr.database import _copia_antes_de_migrar
    c = connect(db_path())
    init_db(c)
    modos = []
    old = os.umask(0)
    try:
        _copia_antes_de_migrar(
            _ConexionEspia(c, lambda ruta: modos.append(stat.S_IMODE(os.stat(ruta).st_mode))), 44)
    finally:
        os.umask(old)
        c.close()
    copia = next((db_path().parent / "backups").glob("pre-migracion-*.db"))
    assert modos == [0o600]
    assert stat.S_IMODE(os.stat(copia).st_mode) == 0o600
    assert sqlite3.connect(copia).execute("SELECT COUNT(*) FROM app_state").fetchone()[0] > 0


def test_si_el_vacuum_falla_no_queda_una_copia_vacia(isolated_db):
    """Un fichero vacío entre las últimas copias echaría a una buena."""
    from emuwarez_uploadrr.database import _copia_antes_de_migrar

    def falla(_ruta):
        raise sqlite3.OperationalError("database or disk is full")

    c = connect(db_path())
    init_db(c)
    try:
        _copia_antes_de_migrar(_ConexionEspia(c, falla), 44)
    finally:
        c.close()
    assert not list((db_path().parent / "backups").glob("pre-migracion-*.db"))
