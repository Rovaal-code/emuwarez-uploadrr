"""El diagnóstico de secretos mira donde la interfaz escribe.

Hallazgo 3.2 de la auditoría, reproducido: `check_required_secrets` preguntaba
por 'tmdb_api_key' y 'emu_api_key', la grafía ANTIGUA con guion bajo. El
asistente de configuración y la interfaz escriben solo la canónica con punto
('tmdb.api_key'), y `set_setting_canonical` lo dice en su docstring: nunca
escribe el alias viejo.

O sea que toda instalación configurada por la interfaz veía "Secretos sin
configurar" en la pestaña Diagnóstico teniendo las dos claves puestas.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.runtime_diagnostics import check_required_secrets
from emuwarez_uploadrr.services.settings import set_setting_canonical


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def test_ve_las_claves_que_escribe_la_interfaz(db_conn):
    set_setting_canonical(db_conn, "tmdb.api_key", "clave-tmdb")
    set_setting_canonical(db_conn, "emu.api_key", "clave-emu")
    db_conn.commit()

    r = check_required_secrets()
    assert r["status"] == "ok", r["message"]


def test_sigue_viendo_las_de_una_instalacion_antigua(db_conn):
    """El alias con guion bajo no desaparece: una instalación que venga del
    CLI antiguo lo tiene escrito y debe seguir contando como configurado."""
    db_conn.execute("INSERT INTO settings (key, value) VALUES ('tmdb_api_key', 'vieja-tmdb')")
    db_conn.execute("INSERT INTO settings (key, value) VALUES ('emu_api_key', 'vieja-emu')")
    db_conn.commit()

    r = check_required_secrets()
    assert r["status"] == "ok", r["message"]


def test_avisa_de_verdad_cuando_falta_una(db_conn):
    set_setting_canonical(db_conn, "tmdb.api_key", "clave-tmdb")
    db_conn.commit()

    r = check_required_secrets()
    assert r["status"] == "warning"
    assert "eMuwarez" in r["message"] and "TMDb" not in r["message"], r["message"]


def test_una_clave_vacia_no_cuenta_como_configurada(db_conn):
    set_setting_canonical(db_conn, "tmdb.api_key", "")
    set_setting_canonical(db_conn, "emu.api_key", "   ")
    db_conn.commit()

    r = check_required_secrets()
    assert r["status"] == "warning"
    assert "TMDb" in r["message"] and "eMuwarez" in r["message"]
