"""La base se comprueba y migra una vez al arrancar: una más nueva se rechaza,
una más vieja se copia antes de migrar, y cerrar la conexión ya no es cosa de cada llamada.

C1 e INFRA-1 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from emuwarez_uploadrr import database
from emuwarez_uploadrr.database import (
    SCHEMA_VERSION,
    BaseMasNuevaError,
    connect,
    db,
    db_path,
    get_state,
    init_db,
    olvidar_esquema,
    preparar_base,
    set_state,
)


@pytest.fixture(autouse=True)
def _esquema_limpio():
    olvidar_esquema()
    yield
    olvidar_esquema()


def _version(ruta) -> str:
    conn = sqlite3.connect(str(ruta))
    try:
        return conn.execute("SELECT value FROM app_state WHERE key = 'schema_version'").fetchone()[0]
    finally:
        conn.close()


def _poner_version(ruta, version) -> None:
    conn = sqlite3.connect(str(ruta))
    try:
        conn.execute("UPDATE app_state SET value = ? WHERE key = 'schema_version'", (str(version),))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# C1: db()
# ---------------------------------------------------------------------------

def test_db_confirma_al_salir_bien_y_cierra():
    with db() as conn:
        set_state(conn, "prueba", "uno")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    with db() as otra:
        assert get_state(otra, "prueba") == "uno"


def test_db_deshace_si_falla_y_cierra():
    with pytest.raises(ValueError):
        with db() as conn:
            set_state(conn, "prueba", "uno")
            raise ValueError("a medias")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    with db() as otra:
        assert get_state(otra, "prueba") is None


# ---------------------------------------------------------------------------
# C1: el esquema se comprueba una vez
# ---------------------------------------------------------------------------

def test_tras_preparar_la_base_init_db_ya_no_la_mira():
    preparar_base()
    ruta = db_path()
    _poner_version(ruta, SCHEMA_VERSION - 1)

    conn = connect()
    init_db(conn)
    conn.close()
    assert _version(ruta) == str(SCHEMA_VERSION - 1)   # no ha migrado: no la ha mirado

    olvidar_esquema()
    conn = connect()
    init_db(conn)
    conn.close()
    assert _version(ruta) == str(SCHEMA_VERSION)


def test_sin_preparar_la_base_init_db_comprueba_como_siempre():
    """Los tests y los scripts que llaman a init_db sin arrancar la app."""
    with db():
        pass
    ruta = db_path()
    _poner_version(ruta, SCHEMA_VERSION - 1)
    with db():
        pass
    assert _version(ruta) == str(SCHEMA_VERSION)


def test_cada_carpeta_de_config_se_prepara_por_separado(tmp_path):
    """El aviso va por fichero: otra CONFIG_DIR no hereda el de la anterior."""
    preparar_base()
    otra = tmp_path / "otra"
    otra.mkdir()
    conn = connect(otra / "x.db")
    init_db(conn)
    try:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'users'").fetchone()[0] == 1
    finally:
        conn.close()


def test_restaurar_una_copia_de_otro_esquema_vuelve_a_comprobar_la_base(tmp_path):
    from emuwarez_uploadrr.services.backup_service import (
        RESTORE_CONFIRMATION,
        create_config_backup,
        restore_config_backup,
    )

    preparar_base()
    ruta = db_path()
    _poner_version(ruta, SCHEMA_VERSION - 1)
    copia = create_config_backup(output_dir=tmp_path / "copias")["archive_path"]
    _poner_version(ruta, SCHEMA_VERSION)

    res = restore_config_backup(copia, dry_run=False, apply=True, confirmation=RESTORE_CONFIRMATION)
    assert res["ok"], res
    assert _version(ruta) == str(SCHEMA_VERSION - 1)

    conn = connect()
    init_db(conn)
    conn.close()
    assert _version(ruta) == str(SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# INFRA-1: una base más nueva se rechaza, una más vieja se copia antes de migrar
# ---------------------------------------------------------------------------

def test_una_base_mas_nueva_se_rechaza_sin_tocarla():
    with db() as conn:
        set_state(conn, "schema_version", str(SCHEMA_VERSION + 1))
    ruta = db_path()

    with pytest.raises(BaseMasNuevaError) as exc:
        init_db(connect())
    assert str(SCHEMA_VERSION + 1) in str(exc.value)
    assert _version(ruta) == str(SCHEMA_VERSION + 1)   # no le pone el número viejo encima


def test_la_aplicacion_no_arranca_con_una_base_mas_nueva(caplog):
    from emuwarez_uploadrr.web.app import create_app

    with db() as conn:
        set_state(conn, "schema_version", str(SCHEMA_VERSION + 1))

    with caplog.at_level(logging.CRITICAL, logger="emuwarez.web"):
        with pytest.raises(BaseMasNuevaError):
            with TestClient(create_app()):
                pass
    assert any("más nueva" in r.getMessage() for r in caplog.records)


def test_el_arranque_de_la_aplicacion_prepara_la_base():
    from emuwarez_uploadrr.web.app import create_app

    with TestClient(create_app()):
        assert str(db_path()) in database._esquema_listo


def test_web_serve_rechaza_una_base_mas_nueva_con_un_mensaje(capsys):
    from emuwarez_uploadrr.cli import modern_main

    with db() as conn:
        set_state(conn, "schema_version", str(SCHEMA_VERSION + 1))

    assert modern_main(["--db", str(db_path()), "web", "serve"]) == 1
    assert "más nueva" in capsys.readouterr().out


def test_migrar_una_base_vieja_deja_antes_una_copia():
    with db() as conn:
        conn.execute("INSERT INTO app_state(key, value) VALUES ('marca', 'antes')")
        set_state(conn, "schema_version", str(SCHEMA_VERSION - 1))
    ruta = db_path()

    with db():
        pass

    assert _version(ruta) == str(SCHEMA_VERSION)
    copias = list((ruta.parent / "backups").glob("pre-migracion-*.db"))
    assert len(copias) == 1 and copias[0].name.endswith(f"-v{SCHEMA_VERSION - 1}.db")
    copia = sqlite3.connect(str(copias[0]))
    try:
        assert copia.execute("SELECT value FROM app_state WHERE key = 'schema_version'").fetchone()[0] == str(SCHEMA_VERSION - 1)
        assert copia.execute("SELECT value FROM app_state WHERE key = 'marca'").fetchone()[0] == "antes"
    finally:
        copia.close()


def test_una_base_nueva_o_al_dia_no_deja_copia():
    with db():
        pass
    with db():
        pass
    assert not list((db_path().parent / "backups").glob("pre-migracion-*.db"))


def test_solo_se_guardan_las_ultimas_copias_antes_de_migrar():
    carpeta = db_path().parent / "backups"
    carpeta.mkdir()
    for dia in range(1, 6):
        (carpeta / f"pre-migracion-2026010{dia}_000000-v1.db").write_bytes(b"x")
    with db() as conn:
        set_state(conn, "schema_version", str(SCHEMA_VERSION - 1))

    with db():
        pass

    nombres = sorted(p.name for p in carpeta.glob("pre-migracion-*.db"))
    assert nombres[:2] == ["pre-migracion-20260104_000000-v1.db", "pre-migracion-20260105_000000-v1.db"]
    assert len(nombres) == 3 and nombres[2].endswith(f"-v{SCHEMA_VERSION - 1}.db")


def test_si_la_copia_falla_la_migracion_sigue(caplog):
    with db() as conn:
        set_state(conn, "schema_version", str(SCHEMA_VERSION - 1))
    ruta = db_path()
    (ruta.parent / "backups").write_text("un fichero donde debería ir la carpeta")

    with caplog.at_level(logging.WARNING, logger="emuwarez_uploadrr.database"):
        with db():
            pass

    assert _version(ruta) == str(SCHEMA_VERSION)
    assert any("copiar la base" in r.getMessage() for r in caplog.records)
