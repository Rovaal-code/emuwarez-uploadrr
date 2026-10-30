"""La copia normal no lleva claves, y restaurarla no borra las que ya tienes.

Hasta ahora include_secrets solo pedía confirmación y le ponía "_with_secrets"
al nombre: las dos copias llevaban lo mismo, todas las claves. La interfaz
decía "sin secretos en el nombre", y quien lo leía entendía "sin secretos".
"""
from __future__ import annotations

import sqlite3
import tarfile
from pathlib import Path

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.backup_service import (
    RESTORE_CONFIRMATION,
    create_config_backup,
    get_config_inventory,
    restore_config_backup,
)
from emuwarez_uploadrr.services.settings import (
    get_setting_canonical,
    get_setting_raw,
    set_setting,
)

CLAVES = {
    "tmdb.api_key": "tmdb-0123456789abcdef",
    "emu.api_key": "emu-fedcba9876543210",
    "emu_api_key": "emu-alias-antiguo-55555",
    "emu.endpoint_url": "https://emu-warez.com/api/torrents?api_token=emu-fedcba9876543210",
    "qbit.password": "qbit-contrasena-secreta",
    "imghost.key.imgbb": "imgbb-abcdefabcdef1234",
    "notify.discord.webhook_url": "https://discord.com/api/webhooks/1/discord-secreto",
    "notify.telegram.bot_token": "123456:telegram-secreto",
}
RADARR_KEY = "radarr-1111222233334444"


def _abrir(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Un /config con todas las claves puestas, en la base y en Uploadrr."""
    d = tmp_path / "config"
    d.mkdir()
    monkeypatch.setenv("CONFIG_DIR", str(d))
    conn = connect(d / "emuwarez_uploadrr.db")
    init_db(conn)
    for key, value in CLAVES.items():
        set_setting(conn, key, value)
    set_setting(conn, "emu.username", "gabriel")
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key) VALUES ('radarr', 'Radarr', 'http://radarr:7878', ?)",
        (RADARR_KEY,),
    )
    conn.commit()
    conn.close()

    data = d / "Uploadrr" / "data"
    (data / "cookies").mkdir(parents=True)
    (data / "templates").mkdir()
    (data / "config.yaml").write_text("api_key: tracker-en-config\n")
    (data / "config.yaml.bak").write_text("api_key: tracker-en-bak\n")
    (data / "cookies" / "EMU.pkl").write_bytes(b"cookie-de-sesion")
    (data / "templates" / "plantilla.txt").write_text("sin claves\n")
    return d


def _miembros(archivo: str) -> list[str]:
    with tarfile.open(archivo) as tar:
        return tar.getnames()


def _base_de_la_copia(archivo: str, destino: Path) -> Path:
    with tarfile.open(archivo) as tar:
        datos = tar.extractfile("emuwarez_uploadrr.db").read()
    db = destino / "base_de_la_copia.db"
    db.write_bytes(datos)
    return db


# ---------- Crear ----------

def test_la_copia_normal_lleva_las_claves_vacias(cfg, tmp_path):
    r = create_config_backup()
    assert r["ok"] and r["include_secrets"] is False
    conn = _abrir(_base_de_la_copia(r["archive_path"], tmp_path))
    for key in CLAVES:
        assert get_setting_raw(conn, key) == "", key
    assert get_setting_raw(conn, "emu.username") == "gabriel"
    assert conn.execute("SELECT api_key FROM instances").fetchone()["api_key"] == ""
    assert conn.execute("SELECT url FROM instances").fetchone()["url"] == "http://radarr:7878"
    conn.close()


def test_ni_un_byte_de_las_claves_en_el_fichero(cfg, tmp_path):
    """Vaciar la fila no basta: el valor viejo se queda en los bytes del .db.
    Incluidas las claves que ya se habían cambiado antes de la copia."""
    conn = connect(cfg / "emuwarez_uploadrr.db")
    set_setting(conn, "tmdb.api_key", "tmdb-la-de-antes-de-cambiarla-9999")
    conn.commit()
    set_setting(conn, "tmdb.api_key", CLAVES["tmdb.api_key"])
    conn.commit()
    conn.close()

    r = create_config_backup()
    datos = _base_de_la_copia(r["archive_path"], tmp_path).read_bytes()
    for valor in [*CLAVES.values(), RADARR_KEY, "tmdb-la-de-antes-de-cambiarla-9999"]:
        assert valor.encode() not in datos, valor


def test_la_copia_normal_no_lleva_los_ficheros_con_claves_de_uploadrr(cfg):
    miembros = _miembros(create_config_backup()["archive_path"])
    assert "Uploadrr/data/config.yaml" not in miembros
    assert "Uploadrr/data/config.yaml.bak" not in miembros
    assert not any(m.startswith("Uploadrr/data/cookies") for m in miembros)
    assert "Uploadrr/data/templates/plantilla.txt" in miembros
    assert "emuwarez_uploadrr.db" in miembros


def test_ni_las_configuraciones_antiguas_de_uploadrr(cfg):
    """Uploadrr-EMU aún reconoce config.py (y su .gitignore deja fuera también
    config.json y backup/old_config*): quien se trajo una, se trajo sus claves."""
    data = cfg / "Uploadrr" / "data"
    (data / "backup").mkdir()
    (data / "config.py").write_text("config = {'api_key': 'antigua-py'}\n")
    (data / "config.json").write_text('{"api_key": "antigua-json"}')
    (data / "backup" / "old_config.py").write_text("config = {'api_key': 'antigua-old'}\n")
    (data / "backup" / "example_config.yaml").write_text("api_key: ''\n")
    miembros = _miembros(create_config_backup()["archive_path"])
    assert "Uploadrr/data/config.py" not in miembros
    assert "Uploadrr/data/config.json" not in miembros
    assert "Uploadrr/data/backup/old_config.py" not in miembros
    assert "Uploadrr/data/backup/example_config.yaml" in miembros
    con_secretos = create_config_backup(include_secrets=True, confirmation=RESTORE_CONFIRMATION)
    assert "Uploadrr/data/config.py" in _miembros(con_secretos["archive_path"])


def test_ni_el_config_del_cli_antiguo(cfg):
    (cfg / "config.json").write_text('{"emu_api_key": "cli-antiguo"}')
    (cfg / "config.enc.json").write_text("{}")
    miembros = _miembros(create_config_backup()["archive_path"])
    assert "config.json" not in miembros
    assert "config.enc.json" not in miembros


def test_el_inventario_cuenta_lo_que_lleva_la_copia_normal(cfg):
    nombres = {Path(f["name"]).as_posix() for f in get_config_inventory()["files"]}
    assert "Uploadrr/data/config.yaml" not in nombres
    assert "Uploadrr/data/cookies/EMU.pkl" not in nombres
    assert "Uploadrr/data/templates/plantilla.txt" in nombres


def test_la_copia_con_secretos_lo_lleva_todo(cfg, tmp_path):
    r = create_config_backup(include_secrets=True, confirmation=RESTORE_CONFIRMATION)
    assert r["ok"] and r["archive_name"].endswith("_with_secrets.tar.gz")
    miembros = _miembros(r["archive_path"])
    assert "Uploadrr/data/config.yaml" in miembros
    assert "Uploadrr/data/config.yaml.bak" in miembros
    assert "Uploadrr/data/cookies/EMU.pkl" in miembros
    conn = _abrir(_base_de_la_copia(r["archive_path"], tmp_path))
    for key, value in CLAVES.items():
        assert get_setting_raw(conn, key) == value, key
    assert conn.execute("SELECT api_key FROM instances").fetchone()["api_key"] == RADARR_KEY
    conn.close()


def test_la_base_viva_no_se_toca_al_hacer_la_copia(cfg):
    create_config_backup()
    conn = _abrir(cfg / "emuwarez_uploadrr.db")
    assert get_setting_raw(conn, "tmdb.api_key") == CLAVES["tmdb.api_key"]
    assert conn.execute("SELECT api_key FROM instances").fetchone()["api_key"] == RADARR_KEY
    conn.close()


# ---------- Restaurar ----------

def _restaurar(archivo: str) -> dict:
    r = restore_config_backup(archivo, dry_run=False, apply=True, confirmation=RESTORE_CONFIRMATION)
    assert r["ok"], r
    return r


def test_restaurar_una_copia_normal_conserva_las_claves_actuales(cfg):
    archivo = create_config_backup()["archive_path"]
    # Lo que cambia después de la copia: la restauración tiene que deshacer el
    # ajuste normal y dejar las claves y el config.yaml de Uploadrr como están.
    conn = connect(cfg / "emuwarez_uploadrr.db")
    set_setting(conn, "emu.username", "otro")
    conn.commit()
    conn.close()
    (cfg / "Uploadrr" / "data" / "config.yaml").write_text("api_key: la-de-ahora\n")

    r = _restaurar(archivo)

    conn = _abrir(cfg / "emuwarez_uploadrr.db")
    assert get_setting_raw(conn, "emu.username") == "gabriel"
    for key, value in CLAVES.items():
        assert get_setting_raw(conn, key) == value, key
    assert conn.execute("SELECT api_key FROM instances").fetchone()["api_key"] == RADARR_KEY
    conn.close()
    assert (cfg / "Uploadrr" / "data" / "config.yaml").read_text() == "api_key: la-de-ahora\n"
    assert set(r["secrets_kept"]) == {*CLAVES, "radarr:Radarr"}
    assert "conservado" in r["message"]


def test_restaurar_una_copia_con_secretos_pone_las_suyas(cfg):
    archivo = create_config_backup(include_secrets=True, confirmation=RESTORE_CONFIRMATION)["archive_path"]
    conn = connect(cfg / "emuwarez_uploadrr.db")
    set_setting(conn, "tmdb.api_key", "tmdb-puesta-despues")
    conn.execute("UPDATE instances SET api_key = 'radarr-puesta-despues'")
    conn.commit()
    conn.close()
    (cfg / "Uploadrr" / "data" / "config.yaml").write_text("api_key: la-de-ahora\n")

    r = _restaurar(archivo)

    conn = _abrir(cfg / "emuwarez_uploadrr.db")
    assert get_setting_raw(conn, "tmdb.api_key") == CLAVES["tmdb.api_key"]
    assert conn.execute("SELECT api_key FROM instances").fetchone()["api_key"] == RADARR_KEY
    conn.close()
    assert (cfg / "Uploadrr" / "data" / "config.yaml").read_text() == "api_key: tracker-en-config\n"
    assert r["secrets_kept"] == []


def test_el_alias_antiguo_de_la_copia_cuenta_como_clave(cfg):
    """Si la copia trae la clave con la grafía antigua, esa es la que vale: poner
    al lado la actual con punto la taparía (get_setting_canonical lee antes el punto)."""
    conn = connect(cfg / "emuwarez_uploadrr.db")
    conn.execute("DELETE FROM settings WHERE key = 'tmdb.api_key'")
    set_setting(conn, "tmdb_api_key", "tmdb-de-la-copia-alias")
    conn.commit()
    conn.close()
    archivo = create_config_backup(include_secrets=True, confirmation=RESTORE_CONFIRMATION)["archive_path"]
    conn = connect(cfg / "emuwarez_uploadrr.db")
    set_setting(conn, "tmdb.api_key", "tmdb-actual-con-punto")
    conn.commit()
    conn.close()

    _restaurar(archivo)

    conn = _abrir(cfg / "emuwarez_uploadrr.db")
    assert get_setting_canonical(conn, "tmdb.api_key") == "tmdb-de-la-copia-alias"
    conn.close()


def test_restaurar_en_una_instalacion_nueva_deja_las_claves_vacias(cfg, monkeypatch):
    archivo = create_config_backup()["archive_path"]
    nueva = cfg.parent / "nueva"
    monkeypatch.setenv("CONFIG_DIR", str(nueva))

    r = _restaurar(archivo)

    conn = _abrir(nueva / "emuwarez_uploadrr.db")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert get_setting_raw(conn, "emu.username") == "gabriel"
    assert get_setting_raw(conn, "tmdb.api_key") == ""
    conn.close()
    assert r["secrets_kept"] == []


def test_restaurar_con_la_app_en_marcha_no_rompe_la_base(cfg):
    """Con la app abierta la base vive con su -wal al lado. Sobrescribir el .db a
    pelo deja ese -wal aplicándose encima del fichero nuevo."""
    archivo = create_config_backup()["archive_path"]
    app = connect(cfg / "emuwarez_uploadrr.db")
    app.execute("CREATE TABLE ruido (pad TEXT)")
    app.executemany("INSERT INTO ruido VALUES (?)", [("x" * 500,)] * 500)
    app.commit()
    assert (cfg / "emuwarez_uploadrr.db-wal").exists()

    _restaurar(archivo)

    assert app.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert app.execute(
        "SELECT count(*) FROM sqlite_master WHERE name = 'ruido'"
    ).fetchone()[0] == 0
    assert get_setting_raw(app, "tmdb.api_key") == CLAVES["tmdb.api_key"]
    app.close()
