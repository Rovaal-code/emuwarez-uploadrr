"""Copias automáticas con retención y backups que se suben desde el navegador.

N18 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import io
import os
import stat
import tarfile
from pathlib import Path

import pytest

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


def _copia(nombre: str, dir_: Path, contenido: bytes = b"x") -> Path:
    ruta = dir_ / nombre
    ruta.write_bytes(contenido)
    return ruta


def _tar_gz(miembros: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for nombre, datos in miembros.items():
            info = tarfile.TarInfo(nombre)
            info.size = len(datos)
            tar.addfile(info, io.BytesIO(datos))
    return buf.getvalue()


BUENA = {"emuwarez_uploadrr.db": b"base", "settings.json": b"{}"}


# ---------------------------------------------------------------------------
# Copias automáticas y retención
# ---------------------------------------------------------------------------

def test_la_copia_automatica_lleva_su_nombre_y_no_lleva_claves(config_dir):
    r = bs.crear_copia_automatica(conservar=7)
    assert r["ok"] and r["include_secrets"] is False
    assert r["archive_name"].startswith("emuwarez_config_auto_") and r["archive_name"].endswith(".tar.gz")
    assert r["retiradas"] == []
    assert bs.list_config_backups()[0]["tipo"] == "automatica"


def test_la_retencion_deja_las_ultimas_n_automaticas(config_dir):
    carpeta = bs._get_backup_dir()
    for dia in range(1, 6):
        _copia(f"emuwarez_config_auto_2026010{dia}_030000.tar.gz", carpeta)

    retiradas = bs.retirar_copias_automaticas(2)

    assert retiradas == [f"emuwarez_config_auto_2026010{d}_030000.tar.gz" for d in (1, 2, 3)]
    assert sorted(p.name for p in carpeta.glob("*.tar.gz")) == [
        "emuwarez_config_auto_20260104_030000.tar.gz", "emuwarez_config_auto_20260105_030000.tar.gz"]


def test_la_retencion_nunca_borra_lo_que_no_es_automatico(config_dir):
    """Manuales, con claves, subidas y las copias de antes de migrar se quedan por antiguas que sean."""
    carpeta = bs._get_backup_dir()
    intocables = [
        "emuwarez_config_20200101_000000.tar.gz",
        "emuwarez_config_20200101_000000_with_secrets.tar.gz",
        "emuwarez_config_subida_20200101_000000.tar.gz",
        "pre-migracion-20200101_000000-v40.db",
        "pre-migracion-20200102_000000-v41.db",
    ]
    for nombre in intocables:
        _copia(nombre, carpeta)
    for dia in range(1, 4):
        _copia(f"emuwarez_config_auto_2026010{dia}_030000.tar.gz", carpeta)

    bs.retirar_copias_automaticas(1)

    assert all((carpeta / n).exists() for n in intocables)
    assert [p.name for p in carpeta.glob("emuwarez_config_auto_*")] == ["emuwarez_config_auto_20260103_030000.tar.gz"]


@pytest.mark.parametrize("conservar", [0, -3])
def test_la_retencion_siempre_deja_al_menos_una(config_dir, conservar):
    carpeta = bs._get_backup_dir()
    _copia("emuwarez_config_auto_20260101_030000.tar.gz", carpeta)
    _copia("emuwarez_config_auto_20260102_030000.tar.gz", carpeta)
    assert bs.retirar_copias_automaticas(conservar) == ["emuwarez_config_auto_20260101_030000.tar.gz"]


def test_si_la_copia_falla_no_se_retira_ninguna_antigua(tmp_path, monkeypatch):
    sin_carpeta = tmp_path / "no-existe"
    monkeypatch.setenv("CONFIG_DIR", str(sin_carpeta))
    antiguas = [_copia(f"emuwarez_config_auto_2026010{d}_030000.tar.gz", tmp_path) for d in (1, 2)]

    r = bs.crear_copia_automatica(conservar=1, output_dir=tmp_path)

    assert r["ok"] is False
    assert all(a.exists() for a in antiguas)


def test_la_copia_automatica_no_se_mete_en_la_siguiente(config_dir):
    bs.crear_copia_automatica(conservar=7)
    nombre = bs.list_config_backups()[0]["path"]
    with tarfile.open(nombre) as tar:
        assert not [n for n in tar.getnames() if "backups" in n]


# ---------------------------------------------------------------------------
# Nombres y tipos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", [
    "../emuwarez_config_x.tar.gz", "emuwarez_config_x.tar.gz/../a", "emuwarez_config_..tar.gz",
    "pre-migracion-20260101_000000-v40.db", "otro.tar.gz", "emuwarez_config_x.tar", "emuwarez_config_.tar.gz",
    "emuwarez_config_a/b.tar.gz", "emuwarez_config_a\\b.tar.gz", "",
])
def test_resolver_copia_rechaza_lo_que_no_es_el_nombre_de_una_copia(config_dir, nombre):
    (config_dir.parent / "emuwarez_config_x.tar.gz").write_bytes(b"fuera")
    assert bs.resolver_copia(nombre) is None


def test_resolver_copia_devuelve_la_copia_que_existe_y_none_si_no(config_dir):
    ruta = _copia("emuwarez_config_20260101_000000.tar.gz", bs._get_backup_dir())
    assert bs.resolver_copia(ruta.name) == ruta
    assert bs.resolver_copia("emuwarez_config_20260102_000000.tar.gz") is None


def test_la_lista_dice_de_que_tipo_es_cada_copia(config_dir):
    carpeta = bs._get_backup_dir()
    for nombre in ("emuwarez_config_20260101_000000.tar.gz", "emuwarez_config_20260101_000001_with_secrets.tar.gz",
                   "emuwarez_config_auto_20260101_000002.tar.gz", "emuwarez_config_subida_20260101_000003.tar.gz"):
        _copia(nombre, carpeta)
    tipos = {b["name"]: (b["tipo"], b["con_claves"]) for b in bs.list_config_backups()}
    assert tipos == {
        "emuwarez_config_20260101_000000.tar.gz": ("manual", False),
        "emuwarez_config_20260101_000001_with_secrets.tar.gz": ("manual", True),
        "emuwarez_config_auto_20260101_000002.tar.gz": ("automatica", False),
        "emuwarez_config_subida_20260101_000003.tar.gz": ("subida", False),
    }


# ---------------------------------------------------------------------------
# Subir un backup: CopiaSubida
# ---------------------------------------------------------------------------

def _subir(datos: bytes, trozo: int = 7) -> dict:
    subida = bs.CopiaSubida()
    try:
        for i in range(0, len(datos), trozo):
            subida.escribir(datos[i:i + trozo])
        return subida.terminar()
    finally:
        subida.descartar()


def _sin_restos(carpeta: Path) -> bool:
    return not list(carpeta.glob(".subida_*"))


@solo_posix
def test_una_copia_valida_se_guarda_con_su_nombre_y_en_0600(config_dir):
    datos = _tar_gz(BUENA)
    r = _subir(datos)

    assert r["ok"] and r["name"].startswith("emuwarez_config_subida_") and r["size_bytes"] == len(datos)
    destino = bs._get_backup_dir() / r["name"]
    assert destino.read_bytes() == datos
    assert stat.S_IMODE(os.stat(destino).st_mode) == 0o600
    assert _sin_restos(destino.parent)
    assert bs.list_config_backups()[0]["tipo"] == "subida"


@pytest.mark.parametrize("datos, motivo", [
    (b"", "no es un backup"),
    (b"esto no es un tar.gz", "no es un backup"),
    (_tar_gz(BUENA)[:60], "no es un backup"),
    (_tar_gz({"settings.json": b"{}"}), "no lleva la base de datos"),
    (_tar_gz({**BUENA, "../fuera.txt": b"x"}), "no es segura"),
    (_tar_gz({**BUENA, "/etc/passwd": b"x"}), "no canónico"),
    (_tar_gz({**BUENA, "./emuwarez_uploadrr.db": b"x"}), "no canónico"),
])
def test_lo_que_no_es_un_backup_se_rechaza_y_no_deja_nada(config_dir, datos, motivo):
    with pytest.raises(ValueError, match=motivo):
        _subir(datos)
    carpeta = bs._get_backup_dir()
    assert _sin_restos(carpeta) and not list(carpeta.glob("emuwarez_config_*"))


def test_una_copia_subida_con_un_enlace_hacia_fuera_se_rechaza(config_dir):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for nombre, datos in BUENA.items():
            info = tarfile.TarInfo(nombre)
            info.size = len(datos)
            tar.addfile(info, io.BytesIO(datos))
        enlace = tarfile.TarInfo("enlace")
        enlace.type = tarfile.SYMTYPE
        enlace.linkname = "../../fuera"
        tar.addfile(enlace)
    with pytest.raises(ValueError, match="no es segura"):
        _subir(buf.getvalue())
    assert not list(bs._get_backup_dir().glob("emuwarez_config_*"))


def test_un_archivo_demasiado_grande_se_corta_y_no_deja_nada(config_dir, monkeypatch):
    monkeypatch.setattr(bs, "LIMITE_SUBIDA_BYTES", 50)
    with pytest.raises(ValueError, match="pasa de"):
        _subir(_tar_gz(BUENA))
    assert _sin_restos(bs._get_backup_dir())


def test_el_nombre_no_depende_de_nada_que_mande_el_cliente(config_dir):
    r = _subir(_tar_gz(BUENA))
    assert bs.resolver_copia(r["name"]) is not None
    assert list(bs._get_backup_dir().iterdir()) == [bs._get_backup_dir() / r["name"]]
