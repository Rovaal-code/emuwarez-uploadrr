"""Restaurar una copia: solo por nombre, sin salirse de la carpeta y sin una base más nueva.

F8 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import io
import sqlite3
import tarfile

import pytest

from emuwarez_uploadrr.database import SCHEMA_VERSION, db, get_state, olvidar_esquema, set_state
from emuwarez_uploadrr.services.backup_service import (
    RESTORE_CONFIRMATION,
    create_config_backup,
    restore_config_backup,
)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    monkeypatch.setenv("CONFIG_DIR", str(d))
    olvidar_esquema()
    with db() as conn:
        set_state(conn, "marca", "antes")
    return d


def _tar_malo(ruta, miembro: tarfile.TarInfo, datos: bytes = b"x") -> str:
    with tarfile.open(ruta, "w:gz") as tar:
        tar.addfile(miembro, io.BytesIO(datos))
    return str(ruta)


def _marca(cfg) -> str | None:
    conn = sqlite3.connect(str(cfg / "emuwarez_uploadrr.db"))
    try:
        fila = conn.execute("SELECT value FROM app_state WHERE key = 'marca'").fetchone()
        return fila[0] if fila else None
    finally:
        conn.close()


def _aplicar(archivo: str) -> dict:
    return restore_config_backup(archivo, dry_run=False, apply=True, confirmation=RESTORE_CONFIRMATION)


# ---------------------------------------------------------------------------
# Un miembro que se sale de la carpeta no se extrae
# ---------------------------------------------------------------------------

def test_un_miembro_con_barras_dobles_no_escribe_fuera(cfg, tmp_path):
    info = tarfile.TarInfo("../escapado.txt")
    info.size = 1
    archivo = _tar_malo(tmp_path / "malo.tar.gz", info)

    r = _aplicar(archivo)

    assert r["ok"] is False and "no es segura" in r["error"]
    assert not (tmp_path / "escapado.txt").exists()
    assert _marca(cfg) == "antes"


def test_un_enlace_que_apunta_fuera_no_se_extrae(cfg, tmp_path):
    info = tarfile.TarInfo("enlace")
    info.type = tarfile.SYMTYPE
    info.linkname = "../fuera"
    archivo = _tar_malo(tmp_path / "malo.tar.gz", info, b"")

    r = _aplicar(archivo)

    assert r["ok"] is False and "no es segura" in r["error"]
    assert not (cfg / "enlace").exists() and not (cfg / "enlace").is_symlink()


def test_la_previsualizacion_tambien_avisa(cfg, tmp_path):
    info = tarfile.TarInfo("../escapado.txt")
    info.size = 1
    archivo = _tar_malo(tmp_path / "malo.tar.gz", info)

    r = restore_config_backup(archivo, dry_run=True)

    assert r["ok"] is False and "no es segura" in r["error"]


def test_un_miembro_malo_tras_la_base_no_deja_la_base_cambiada(cfg, tmp_path):
    """La base se coloca primero: sin mirar todo antes, un rechazo tardío dejaba la instalación a medias."""
    bueno = create_config_backup(output_dir=tmp_path / "copias")["archive_path"]
    with db() as conn:
        set_state(conn, "marca", "despues")
    malo = tmp_path / "mezcla.tar.gz"
    with tarfile.open(bueno, "r:gz") as origen, tarfile.open(malo, "w:gz") as destino:
        for m in origen.getmembers():
            destino.addfile(m, origen.extractfile(m) if m.isfile() else None)
        info = tarfile.TarInfo("../escapado.txt")
        info.size = 1
        destino.addfile(info, io.BytesIO(b"x"))

    r = _aplicar(str(malo))

    assert r["ok"] is False
    assert _marca(cfg) == "despues"
    assert not (tmp_path / "escapado.txt").exists()


# ---------------------------------------------------------------------------
# Una copia con la base de un esquema más nuevo
# ---------------------------------------------------------------------------

def _copia_de_esquema(cfg, tmp_path, version: int) -> str:
    conn = sqlite3.connect(str(cfg / "emuwarez_uploadrr.db"))
    try:
        conn.execute("UPDATE app_state SET value = ? WHERE key = 'schema_version'", (str(version),))
        conn.commit()
    finally:
        conn.close()
    archivo = create_config_backup(output_dir=tmp_path / "copias")["archive_path"]
    conn = sqlite3.connect(str(cfg / "emuwarez_uploadrr.db"))
    try:
        conn.execute("UPDATE app_state SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION),))
        conn.execute("UPDATE app_state SET value = 'despues' WHERE key = 'marca'")
        conn.commit()
    finally:
        conn.close()
    return archivo


def test_una_copia_de_un_esquema_mas_nuevo_no_se_restaura(cfg, tmp_path):
    """Restaurarla dejaba toda petición en 503: la base no la abre este código."""
    archivo = _copia_de_esquema(cfg, tmp_path, SCHEMA_VERSION + 1)

    r = _aplicar(archivo)

    assert r["ok"] is False and "más nueva" in r["error"] and str(SCHEMA_VERSION + 1) in r["error"]
    assert _marca(cfg) == "despues"
    with db() as conn:
        assert get_state(conn, "schema_version") == str(SCHEMA_VERSION)


def test_la_previsualizacion_de_una_copia_mas_nueva_tambien_avisa(cfg, tmp_path):
    archivo = _copia_de_esquema(cfg, tmp_path, SCHEMA_VERSION + 1)
    r = restore_config_backup(archivo, dry_run=True)
    assert r["ok"] is False and "más nueva" in r["error"]


@pytest.mark.parametrize("delta", [0, -1])
def test_una_copia_del_esquema_actual_o_anterior_si_se_restaura(cfg, tmp_path, delta):
    archivo = _copia_de_esquema(cfg, tmp_path, SCHEMA_VERSION + delta)

    r = _aplicar(archivo)

    assert r["ok"] is True, r
    assert _marca(cfg) == "antes"


def test_una_copia_sin_base_se_restaura_y_deja_la_actual(cfg, tmp_path):
    info = tarfile.TarInfo("settings.json")
    info.size = 2
    archivo = _tar_malo(tmp_path / "sin-base.tar.gz", info, b"{}")

    r = _aplicar(archivo)

    assert r["ok"] is True, r
    assert (cfg / "settings.json").read_text() == "{}"
    assert _marca(cfg) == "antes"


def test_una_copia_cuya_base_no_es_sqlite_no_se_confunde_con_una_mas_nueva(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    (d / "emuwarez_uploadrr.db").write_text("no es una base")
    monkeypatch.setenv("CONFIG_DIR", str(d))
    archivo = create_config_backup(output_dir=tmp_path / "copias")["archive_path"]

    r = _aplicar(archivo)

    assert r["ok"] is True, r


# ---------------------------------------------------------------------------
# La API: por nombre, no por ruta
# ---------------------------------------------------------------------------

def _crear_copia_por_api(client, auth_headers) -> str:
    r = client.post("/api/maintenance/backup", json={}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"], r.text
    return r.json()["archive_name"]


def test_la_api_restaura_una_copia_por_su_nombre(client, auth_headers):
    nombre = _crear_copia_por_api(client, auth_headers)

    previa = client.post("/api/maintenance/restore", json={"backup_name": nombre}, headers=auth_headers).json()
    assert previa["ok"] is True and previa["action"] == "preview"

    real = client.post(
        "/api/maintenance/restore",
        json={"backup_name": nombre, "dry_run": False, "apply": True, "confirmation": RESTORE_CONFIRMATION},
        headers=auth_headers,
    ).json()
    assert real["ok"] is True and real["action"] == "restored"


def test_la_api_ya_no_acepta_una_ruta(client, auth_headers):
    resp = client.post("/api/maintenance/restore", json={"backup_path": "/tmp/x.tar.gz"}, headers=auth_headers)
    assert resp.status_code == 422


def test_la_api_no_sale_de_la_carpeta_de_copias(client, auth_headers, isolated_db):
    # Un tar válido fuera de backups/, con un nombre que cumple el patrón.
    fuera = isolated_db / "emuwarez_config_fuera.tar.gz"
    with tarfile.open(fuera, "w:gz") as tar:
        info = tarfile.TarInfo("settings.json")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"{}"))

    for nombre in (str(fuera), "../emuwarez_config_fuera.tar.gz", "..\\emuwarez_config_fuera.tar.gz",
                   "/etc/passwd", "otra.tar.gz", "emuwarez_config_no_existe.tar.gz"):
        r = client.post("/api/maintenance/restore", json={"backup_name": nombre}, headers=auth_headers).json()
        assert r["ok"] is False and "no encontrado" in r["error"].lower(), nombre


def test_resolver_copia_solo_devuelve_las_de_la_carpeta(cfg, tmp_path):
    from emuwarez_uploadrr.services.backup_service import resolver_copia

    nombre = create_config_backup()["archive_name"]
    assert resolver_copia(nombre) == cfg / "backups" / nombre
    assert resolver_copia("../" + nombre) is None
    assert resolver_copia(nombre + "\x00") is None
    assert resolver_copia("pre-migracion-1-v1.db") is None
