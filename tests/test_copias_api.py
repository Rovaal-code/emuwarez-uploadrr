"""Bajar y subir backups desde el navegador (/api/maintenance/backups/...).

N18 de la revisión de 2026-10-31. Restaurar sigue siendo /restore.
"""
from __future__ import annotations

import asyncio
import io
import tarfile

import pytest

from emuwarez_uploadrr.services import backup_service as bs

BUENA = {"emuwarez_uploadrr.db": b"base", "settings.json": b"{}"}


def _tar_gz(miembros: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for nombre, datos in miembros.items():
            info = tarfile.TarInfo(nombre)
            info.size = len(datos)
            tar.addfile(info, io.BytesIO(datos))
    return buf.getvalue()


def _subir(client, auth_headers, datos: bytes):
    return client.post(
        "/api/maintenance/backups/upload", content=datos,
        headers={**auth_headers, "Content-Type": "application/gzip"},
    )


# ---------------------------------------------------------------------------
# Descargar
# ---------------------------------------------------------------------------

def test_descargar_pide_sesion(client):
    assert client.get("/api/maintenance/backups/emuwarez_config_x.tar.gz/download").status_code == 401


def test_se_descarga_el_backup_tal_cual_y_sin_comprimirlo_otra_vez(client, auth_headers):
    creado = client.post("/api/maintenance/backup", json={}, headers=auth_headers).json()
    original = open(creado["archive_path"], "rb").read()

    # httpx pide gzip por defecto: el middleware de compresión no puede comprimirlo de nuevo.
    r = client.get(f"/api/maintenance/backups/{creado['archive_name']}/download", headers=auth_headers)

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"
    assert f'filename="{creado["archive_name"]}"' in r.headers["content-disposition"]
    assert r.headers["content-disposition"].startswith("attachment")
    assert "content-encoding" not in r.headers
    assert r.content == original
    assert tarfile.is_tarfile(io.BytesIO(r.content))


@pytest.mark.parametrize("nombre", [
    "emuwarez_config_inexistente.tar.gz",
    "pre-migracion-20260101_000000-v40.db",
    "..%2F..%2Femuwarez_uploadrr.db",
    "emuwarez_config_a%2F..%2F..%2Fx.tar.gz",
    "settings.json",
])
def test_descargar_solo_entrega_backups_de_la_carpeta(client, auth_headers, nombre):
    assert client.get(f"/api/maintenance/backups/{nombre}/download", headers=auth_headers).status_code == 404


# ---------------------------------------------------------------------------
# Subir
# ---------------------------------------------------------------------------

def test_subir_pide_sesion(client):
    assert client.post("/api/maintenance/backups/upload", content=_tar_gz(BUENA)).status_code == 401


def test_un_backup_subido_aparece_en_la_lista_y_se_puede_volver_a_bajar(client, auth_headers):
    datos = _tar_gz(BUENA)

    r = _subir(client, auth_headers, datos)

    assert r.status_code == 200, r.text
    nombre = r.json()["name"]
    assert nombre.startswith("emuwarez_config_subida_")
    lista = client.get("/api/maintenance/backups", headers=auth_headers).json()["backups"]
    assert [(b["name"], b["tipo"]) for b in lista] == [(nombre, "subida")]
    assert client.get(f"/api/maintenance/backups/{nombre}/download", headers=auth_headers).content == datos


def test_subir_algo_que_no_es_un_backup_da_422_y_no_guarda_nada(client, auth_headers):
    r = _subir(client, auth_headers, b"no soy un tar.gz")

    assert r.status_code == 422
    assert "no es un backup" in r.json()["detail"]
    assert client.get("/api/maintenance/backups", headers=auth_headers).json()["count"] == 0
    assert not list(bs.get_backup_dir().glob(".subida_*"))


def test_subir_un_backup_sin_base_de_datos_da_422(client, auth_headers):
    r = _subir(client, auth_headers, _tar_gz({"settings.json": b"{}"}))
    assert r.status_code == 422 and "base de datos" in r.json()["detail"]


def test_subir_algo_demasiado_grande_da_413_sin_leerlo(client, auth_headers, monkeypatch):
    monkeypatch.setattr(bs, "LIMITE_SUBIDA_BYTES", 10)
    r = _subir(client, auth_headers, _tar_gz(BUENA))
    assert r.status_code == 413
    assert not list(bs.get_backup_dir().glob(".subida_*"))


def test_subir_un_cuerpo_que_se_pasa_del_limite_sin_avisar_se_corta(client, auth_headers, monkeypatch):
    """Sin Content-Length declarado (chunked) el límite también vale."""
    monkeypatch.setattr(bs, "LIMITE_SUBIDA_BYTES", 10)

    def trozos():
        yield from (b"x" * 8, b"y" * 8)

    r = client.post("/api/maintenance/backups/upload", content=trozos(), headers=auth_headers)

    assert r.status_code == 422 and "pasa de" in r.json()["detail"]
    assert not list(bs.get_backup_dir().glob(".subida_*"))


def test_la_escritura_de_la_subida_no_corre_en_el_bucle_de_eventos(client, auth_headers, monkeypatch):
    """En un disco lento de la NAS cada escritura frenaría el servidor entero (avisos incluidos)."""
    en_el_bucle = []
    original = bs.CopiaSubida.escribir

    def espia(self, trozo):
        try:
            asyncio.get_running_loop()
            en_el_bucle.append(True)
        except RuntimeError:  # sin bucle en este hilo: es un hilo de trabajo
            en_el_bucle.append(False)
        return original(self, trozo)

    monkeypatch.setattr(bs.CopiaSubida, "escribir", espia)

    assert _subir(client, auth_headers, _tar_gz(BUENA)).status_code == 200
    assert en_el_bucle and not any(en_el_bucle)
