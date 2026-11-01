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


def _base_en_bytes(cfg, tmp_path, version: int | None = None, marca: str | None = None) -> bytes:
    """Una copia de la base viva, con otro esquema y/u otra marca."""
    copia = tmp_path / f"base-{version}-{marca}.db"
    conn = sqlite3.connect(str(cfg / "emuwarez_uploadrr.db"))
    dst = sqlite3.connect(str(copia))
    conn.backup(dst)
    conn.close()
    if version is not None:
        dst.execute("UPDATE app_state SET value = ? WHERE key = 'schema_version'", (str(version),))
    if marca is not None:
        dst.execute("UPDATE app_state SET value = ? WHERE key = 'marca'", (marca,))
    dst.commit()
    dst.close()
    return copia.read_bytes()


def _anadir(tar: tarfile.TarFile, nombre: str, datos: bytes = b"x", tipo=tarfile.REGTYPE, enlace: str = "") -> None:
    info = tarfile.TarInfo(nombre)
    info.type = tipo
    info.linkname = enlace
    info.size = len(datos) if tipo == tarfile.REGTYPE else 0
    tar.addfile(info, io.BytesIO(datos) if tipo == tarfile.REGTYPE else None)


def test_una_segunda_base_con_otro_esquema_no_se_cuela(cfg, tmp_path):
    """El esquema se miraba en la primera: la segunda, más nueva, se colocaba sin mirarla."""
    archivo = tmp_path / "doble.tar.gz"
    with tarfile.open(archivo, "w:gz") as tar:
        _anadir(tar, "emuwarez_uploadrr.db", _base_en_bytes(cfg, tmp_path, marca="una"))
        _anadir(tar, "emuwarez_uploadrr.db", _base_en_bytes(cfg, tmp_path, version=SCHEMA_VERSION + 1, marca="dos"))

    r = _aplicar(str(archivo))

    assert r["ok"] is False and "repite" in r["error"]
    assert _marca(cfg) == "antes"
    with db() as conn:
        assert get_state(conn, "schema_version") == str(SCHEMA_VERSION)


def test_la_base_que_es_un_enlace_no_se_restaura(cfg, tmp_path):
    archivo = tmp_path / "enlace.tar.gz"
    with tarfile.open(archivo, "w:gz") as tar:
        _anadir(tar, "emuwarez_uploadrr.db", tipo=tarfile.SYMTYPE, enlace="otra.db")

    r = _aplicar(str(archivo))

    assert r["ok"] is False and "no es un fichero normal" in r["error"]
    assert not (cfg / "emuwarez_uploadrr.db").is_symlink()
    assert _marca(cfg) == "antes"


def test_un_fichero_que_a_la_vez_es_carpeta_se_rechaza_antes_de_tocar_la_base(cfg, tmp_path):
    """La extracción fallaba al crear el hijo, con la base ya cambiada: una restauración a medias."""
    archivo = tmp_path / "choque.tar.gz"
    with tarfile.open(archivo, "w:gz") as tar:
        _anadir(tar, "emuwarez_uploadrr.db", _base_en_bytes(cfg, tmp_path, marca="otra"))
        _anadir(tar, "settings.json", b"{}")
        _anadir(tar, "settings.json/hijo", b"x")

    r = _aplicar(str(archivo))

    assert r["ok"] is False and "a la vez un fichero y una carpeta" in r["error"]
    assert _marca(cfg) == "antes"
    assert not (cfg / "settings.json").exists()


def test_una_carpeta_con_ficheros_dentro_no_es_un_choque(cfg, tmp_path):
    archivo = tmp_path / "bien.tar.gz"
    with tarfile.open(archivo, "w:gz") as tar:
        _anadir(tar, "emuwarez_uploadrr.db", _base_en_bytes(cfg, tmp_path, marca="otra"))
        _anadir(tar, "Uploadrr", tipo=tarfile.DIRTYPE)
        _anadir(tar, "Uploadrr/data/a.txt", b"a")
        _anadir(tar, "Uploadrr/data/b.txt", b"b")

    r = _aplicar(str(archivo))

    assert r["ok"] is True, r
    assert _marca(cfg) == "otra"
    assert (cfg / "Uploadrr" / "data" / "b.txt").read_text() == "b"


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


@pytest.mark.parametrize("nombre", ["./emuwarez_uploadrr.db", "x/../emuwarez_uploadrr.db", "/emuwarez_uploadrr.db", "a//b.txt"])
def test_un_nombre_no_canonico_se_rechaza_sin_tocar_la_base(cfg, tmp_path, nombre):
    """«./emuwarez_uploadrr.db» se saltaba la comprobación del esquema y caía encima de la base."""
    info = tarfile.TarInfo(nombre)
    info.size = 1
    archivo = _tar_malo(tmp_path / "malo.tar.gz", info)

    r = _aplicar(archivo)

    assert r["ok"] is False and "canónico" in r["error"]
    assert _marca(cfg) == "antes"


def test_resolver_copia_no_sigue_un_enlace(cfg, tmp_path):
    from emuwarez_uploadrr.services.backup_service import resolver_copia

    fuera = tmp_path / "fuera.tar.gz"
    fuera.write_bytes(b"x")
    (cfg / "backups").mkdir(exist_ok=True)
    (cfg / "backups" / "emuwarez_config_enlace.tar.gz").symlink_to(fuera)
    assert resolver_copia("emuwarez_config_enlace.tar.gz") is None


def test_una_base_que_no_es_sqlite_no_pisa_una_que_si_lo_es(cfg, tmp_path):
    """_colocar_base la copiaría en crudo encima de la base viva, sin copia previa."""
    info = tarfile.TarInfo("emuwarez_uploadrr.db")
    datos = b"esto no es una base"
    info.size = len(datos)
    archivo = _tar_malo(tmp_path / "malo.tar.gz", info, datos)

    assert restore_config_backup(archivo, dry_run=True)["ok"] is False
    r = _aplicar(archivo)

    assert r["ok"] is False and "no es una base SQLite" in r["error"]
    assert _marca(cfg) == "antes"


def test_una_base_sqlite_truncada_se_rechaza(cfg, tmp_path):
    from emuwarez_uploadrr.database import db_path
    entera = open(db_path(), "rb").read()
    info = tarfile.TarInfo("emuwarez_uploadrr.db")
    datos = entera[: len(entera) // 2]
    info.size = len(datos)
    archivo = _tar_malo(tmp_path / "malo.tar.gz", info, datos)

    r = _aplicar(archivo)

    assert r["ok"] is False and "dañada" in r["error"]
    assert _marca(cfg) == "antes"
