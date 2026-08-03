"""La copia de configuración no se lleva lo que se está subiendo.

En /config/Uploadrr/uploads viven los enlaces de lo que se sube y se siembra
(services/carpeta_subida.py). Con enlaces SIMBÓLICOS entrarían como enlaces
rotos, inútiles; con enlaces DUROS —que es lo que se usa cuando /config y los
medios comparten sistema de ficheros— tar no los distingue de un fichero normal
y metería cada película ENTERA en la copia.

Lo pilló Alvaro preguntando qué se lleva la copia, justo después de meter
uploads dentro de /config.
"""
from __future__ import annotations

import os
import tarfile
from pathlib import Path

import pytest

from emuwarez_uploadrr.services.backup_service import create_config_backup, get_config_inventory


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Un /config con su base de datos y una película enlazada en uploads."""
    cfg = tmp_path / "config"
    (cfg / "Uploadrr" / "uploads").mkdir(parents=True)
    (cfg / "emuwarez_uploadrr.db").write_bytes(b"db" * 500)
    (cfg / "Uploadrr" / "data").mkdir()
    (cfg / "Uploadrr" / "data" / "config.yaml").write_text("clave: valor\n")

    medios = tmp_path / "media"; medios.mkdir()
    peli = medios / "Peli 2020 1080p x264-EMU.mkv"
    peli.write_bytes(b"V" * 200_000)

    monkeypatch.setenv("CONFIG_DIR", str(cfg))
    return {"cfg": cfg, "peli": peli, "uploads": cfg / "Uploadrr" / "uploads"}


def _miembros(ruta: str) -> list[str]:
    with tarfile.open(ruta) as tar:
        return [m.name for m in tar.getmembers()]


def test_la_copia_no_lleva_los_enlaces_duros(config):
    """El caso grave: tar no distingue un enlace duro de un fichero, así que
    se llevaría la película entera."""
    os.link(config["peli"], config["uploads"] / config["peli"].name)
    r = create_config_backup()
    assert r["ok"], r
    assert not any("uploads" in n for n in _miembros(r["archive_path"]))
    # Y la copia sigue siendo del tamaño de una configuración, no de un catálogo.
    assert Path(r["archive_path"]).stat().st_size < 50_000


def test_la_copia_no_lleva_los_enlaces_simbolicos(config):
    """Menos grave —entrarían como enlaces rotos— pero igual de inútil."""
    os.symlink(config["peli"], config["uploads"] / config["peli"].name)
    r = create_config_backup()
    assert not any("uploads" in n for n in _miembros(r["archive_path"]))


def test_la_copia_sigue_llevando_lo_que_importa(config):
    """Que excluir uploads no se lleve por delante nada más."""
    os.symlink(config["peli"], config["uploads"] / config["peli"].name)
    miembros = _miembros(create_config_backup()["archive_path"])
    assert "emuwarez_uploadrr.db" in miembros
    assert "Uploadrr/data/config.yaml" in miembros


def test_el_inventario_dice_lo_mismo_que_la_copia(config):
    """El inventario es lo que se le enseña al usuario como "esto es lo que se
    va a copiar": contar aquí algo que la copia no lleva sería mentir."""
    os.link(config["peli"], config["uploads"] / config["peli"].name)
    inv = get_config_inventory()
    nombres = [f["name"] for f in inv["files"]]
    assert not any("uploads" in n for n in nombres)
    assert inv["total_size_bytes"] < 50_000
