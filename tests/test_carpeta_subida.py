"""La carpeta de enlaces que se le entrega a Uploadrr para un pack.

Existe porque `torf` toma el nombre del torrent del nombre de la carpeta, y esa
es la carpeta que recibe quien se descargue el release. Antes se resolvía
renombrando la carpeta de Sonarr; ahora se enlaza aparte y la biblioteca no se
toca.

Lo que más importa aquí es lo que NO hace: no copiar datos, no tocar los
ficheros originales, y no borrar nada que no haya creado.
"""
from __future__ import annotations

import os

import pytest

from emuwarez_uploadrr.services.carpeta_subida import (asegurar_raiz, borrar_carpeta_de_pack,
                                                       comprobar_enlace,
                                                       preparar_carpeta_de_pack)


@pytest.fixture
def biblioteca(tmp_path):
    """Una temporada con dos capítulos y una carpeta de subidas al lado."""
    temporada = tmp_path / "Serie" / "Season 1"
    temporada.mkdir(parents=True)
    ficheros = []
    for n in (1, 2):
        f = temporada / f"Serie S01E0{n}.mkv"
        f.write_bytes(b"video" * 100)
        ficheros.append(str(f))
    return {"temporada": temporada, "ficheros": ficheros,
            "uploads": str(tmp_path / "uploads")}


def test_prepara_la_carpeta_con_el_nombre_del_release(biblioteca):
    r = preparar_carpeta_de_pack("Serie S01 2020 1080p WEB-DL x264",
                                 biblioteca["ficheros"], raiz=biblioteca["uploads"])
    assert r["status"] == "ready"
    assert os.path.basename(r["carpeta"]) == "Serie S01 2020 1080p WEB-DL x264"
    assert r["cuantos"] == 2


def test_no_toca_la_carpeta_original(biblioteca):
    """Lo que motivó todo el cambio."""
    antes = sorted(p.name for p in biblioteca["temporada"].iterdir())
    preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"], raiz=biblioteca["uploads"])
    assert biblioteca["temporada"].is_dir()
    assert biblioteca["temporada"].name == "Season 1"
    assert sorted(p.name for p in biblioteca["temporada"].iterdir()) == antes


def test_no_duplica_los_datos(biblioteca):
    """Un enlace duro es otro nombre para los mismos datos: mismo inodo."""
    r = preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"], raiz=biblioteca["uploads"])
    for original in biblioteca["ficheros"]:
        enlace = os.path.join(r["carpeta"], os.path.basename(original))
        assert os.stat(enlace).st_ino == os.stat(original).st_ino


def test_los_nombres_de_los_capitulos_se_conservan(biblioteca):
    r = preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"], raiz=biblioteca["uploads"])
    assert sorted(os.listdir(r["carpeta"])) == sorted(
        os.path.basename(f) for f in biblioteca["ficheros"])


def test_rehacerla_no_arrastra_capitulos_viejos(biblioteca, tmp_path):
    """Un reintento tiene que dejarla como si fuera nueva."""
    preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"], raiz=biblioteca["uploads"])
    sobra = tmp_path / "Serie" / "Season 1" / "Serie S01E99.mkv"
    sobra.write_bytes(b"viejo")
    r = preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"] + [str(sobra)],
                                 raiz=biblioteca["uploads"])
    assert len(os.listdir(r["carpeta"])) == 3
    r2 = preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"], raiz=biblioteca["uploads"])
    assert len(os.listdir(r2["carpeta"])) == 2


def test_un_capitulo_que_no_existe_la_bloquea(biblioteca):
    r = preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"] + ["/no/existe.mkv"],
                                 raiz=biblioteca["uploads"])
    assert r["status"] == "blocked"
    assert any("/no/existe.mkv" in e for e in r["errors"])


def test_sin_capitulos_la_bloquea(biblioteca):
    assert preparar_carpeta_de_pack("Serie S01", [], raiz=biblioteca["uploads"])["status"] == "blocked"


# --- Borrado -----------------------------------------------------------------

def test_borrarla_no_toca_los_ficheros_de_verdad(biblioteca):
    """La razón de ser de los enlaces: borrar la carpeta de subida deja los
    capítulos exactamente donde estaban."""
    r = preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"], raiz=biblioteca["uploads"])
    assert borrar_carpeta_de_pack(r["carpeta"], raiz=biblioteca["uploads"]) is True
    assert not os.path.exists(r["carpeta"])
    for f in biblioteca["ficheros"]:
        assert os.path.isfile(f)
        assert os.path.getsize(f) > 0


def test_nunca_borra_fuera_de_la_carpeta_de_subidas(biblioteca):
    """Salvaguarda: `prepared_path` puede apuntar a la biblioteca (una
    película suelta), y borrar una subida no puede llevarse el fichero."""
    assert borrar_carpeta_de_pack(str(biblioteca["temporada"]),
                                  raiz=biblioteca["uploads"]) is False
    assert biblioteca["temporada"].is_dir()


def test_borrar_lo_que_no_existe_no_lanza(biblioteca):
    assert borrar_carpeta_de_pack("/no/existe", raiz=biblioteca["uploads"]) is False
    assert borrar_carpeta_de_pack(None, raiz=biblioteca["uploads"]) is False


# --- La comprobación del asistente -------------------------------------------

def test_la_comprobacion_dice_que_si_y_de_que_tipo(biblioteca):
    r = comprobar_enlace(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])
    assert r["ok"] is True
    assert r["tipo"] in ("duro", "simbólico")


def test_la_comprobacion_no_deja_rastro(biblioteca):
    comprobar_enlace(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])
    assert os.listdir(biblioteca["uploads"]) == []


def test_la_comprobacion_crea_la_carpeta_si_falta(biblioteca):
    assert not os.path.exists(biblioteca["uploads"])
    comprobar_enlace(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])
    assert os.path.isdir(biblioteca["uploads"])


def test_la_comprobacion_falla_sin_fichero(biblioteca):
    r = comprobar_enlace("/no/existe.mkv", raiz=biblioteca["uploads"])
    assert r["ok"] is False and r["error"]


def test_asegurar_raiz_es_idempotente(biblioteca):
    assert asegurar_raiz(biblioteca["uploads"]) is True
    assert asegurar_raiz(biblioteca["uploads"]) is True
