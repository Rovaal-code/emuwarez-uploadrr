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
                                                       borrar_de_subidas, comprobar_enlace,
                                                       preparar_carpeta_de_pack,
                                                       preparar_fichero_suelto)


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


# --- Un fichero suelto (película o capítulo) ---------------------------------

def test_un_fichero_suelto_va_en_la_raiz(biblioteca):
    """Y NO dentro de una carpeta propia: metido en una, torf haría un torrent
    de varios ficheros con esa carpeta dentro, y el release dejaría de ser un
    fichero suelto (comprobado: singlefile vs multifile)."""
    r = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])
    assert r["status"] == "ready"
    assert os.path.dirname(r["ruta"]) == biblioteca["uploads"]


def test_conserva_el_nombre_del_fichero(biblioteca):
    """Es lo que torf usa para nombrar el torrent, y la nomenclatura ya lo dejó
    como debe: tocarlo aquí cambiaría el nombre del release."""
    origen = biblioteca["ficheros"][0]
    r = preparar_fichero_suelto(origen, raiz=biblioteca["uploads"])
    assert os.path.basename(r["ruta"]) == os.path.basename(origen)


def test_el_fichero_suelto_tampoco_se_duplica(biblioteca):
    r = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])
    assert os.stat(r["ruta"]).st_ino == os.stat(biblioteca["ficheros"][0]).st_ino


def test_reenlazar_el_mismo_fichero_no_falla(biblioteca):
    """Un reintento, o volver a subir lo mismo."""
    for _ in range(2):
        r = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])
        assert r["status"] == "ready"
    assert len(os.listdir(biblioteca["uploads"])) == 1


def test_un_fichero_que_no_existe_lo_bloquea(biblioteca):
    r = preparar_fichero_suelto("/no/existe.mkv", raiz=biblioteca["uploads"])
    assert r["status"] == "blocked"


def test_borrar_de_subidas_sirve_para_las_dos_formas(biblioteca):
    """El borrado es uno solo: un pack es una carpeta y una película un
    fichero, y al borrar la subida no se sabe cuál era."""
    pack = preparar_carpeta_de_pack("Serie S01", biblioteca["ficheros"], raiz=biblioteca["uploads"])
    suelto = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])
    assert borrar_de_subidas(pack["carpeta"], raiz=biblioteca["uploads"]) is True
    assert borrar_de_subidas(suelto["ruta"], raiz=biblioteca["uploads"]) is True
    assert os.listdir(biblioteca["uploads"]) == []
    for f in biblioteca["ficheros"]:
        assert os.path.isfile(f)


def test_borrar_un_enlace_simbolico_no_sigue_hasta_el_original(biblioteca, tmp_path):
    """La salvaguarda mira el PADRE y no la ruta resuelta: un enlace simbólico
    apunta a la biblioteca, y resolverlo lo dejaría "fuera" de la raíz — o
    peor, borraría el fichero de verdad."""
    import os as _os
    up = str(tmp_path / "otro-fs")
    _os.makedirs(up)
    enlace = _os.path.join(up, "peli.mkv")
    _os.symlink(biblioteca["ficheros"][0], enlace)
    assert borrar_de_subidas(enlace, raiz=up) is True
    assert not _os.path.lexists(enlace)
    assert _os.path.isfile(biblioteca["ficheros"][0]), "el original NO se toca"


def _subida(conn, status, prepared_path, retry_of=None):
    return conn.execute(
        "INSERT INTO upload_jobs (title, path, status, stage, prepared_path, retry_of_job_id, created_at, updated_at)"
        " VALUES ('X', '', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (status, status, prepared_path, retry_of),
    ).lastrowid


def test_borrar_una_subida_completada_deja_lo_que_siembra_qbittorrent(biblioteca, monkeypatch, isolated_db):
    """El enlace de una subida completada es de donde siembra qBittorrent. El
    intento fallido de antes apunta al mismo enlace y tampoco puede llevárselo."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.upload_execution import DELETE_CONFIRMATION_TOKEN, delete_upload_job

    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", biblioteca["uploads"])
    enlace = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])["ruta"]
    conn = connect()
    init_db(conn)
    fallido = _subida(conn, "failed", enlace)
    _subida(conn, "completed", enlace, retry_of=fallido)
    conn.commit()

    assert delete_upload_job(fallido, confirmation=DELETE_CONFIRMATION_TOKEN, conn=conn)["ok"]
    assert os.path.lexists(enlace)


def test_borrar_una_subida_fallida_quita_su_enlace(biblioteca, monkeypatch, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.upload_execution import DELETE_CONFIRMATION_TOKEN, delete_upload_job

    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", biblioteca["uploads"])
    enlace = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])["ruta"]
    conn = connect()
    init_db(conn)
    fallido = _subida(conn, "failed", enlace)
    conn.commit()

    assert delete_upload_job(fallido, confirmation=DELETE_CONFIRMATION_TOKEN, conn=conn)["ok"]
    assert not os.path.lexists(enlace)
    assert os.path.exists(biblioteca["ficheros"][0])


def test_un_symlink_fuera_de_la_carpeta_de_subidas_no_vale_para_subir(biblioteca, monkeypatch, isolated_db, tmp_path):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.upload_execution import validate_upload_job_start

    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", biblioteca["uploads"])
    fuera = tmp_path / "otro.mkv"
    os.symlink(biblioteca["ficheros"][0], fuera)
    conn = connect()
    init_db(conn)
    job = _subida(conn, "ready", str(fuera))
    conn.commit()

    errores = validate_upload_job_start(job, conn=conn)["errors"]
    assert any("symlink" in e for e in errores)


def test_una_carpeta_hermana_no_cuenta_como_la_de_subidas(tmp_path):
    from emuwarez_uploadrr.services.carpeta_subida import en_carpeta_de_subidas
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads-old").mkdir()
    assert en_carpeta_de_subidas(str(tmp_path / "uploads" / "x.mkv"), raiz=str(tmp_path / "uploads"))
    assert not en_carpeta_de_subidas(str(tmp_path / "uploads-old" / "x.mkv"), raiz=str(tmp_path / "uploads"))


def test_borrar_no_quita_el_enlace_que_siembra_otra_subida(biblioteca, monkeypatch, isolated_db):
    """Otra cadena completada que apunta al mismo enlace tampoco puede perderlo."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.upload_execution import DELETE_CONFIRMATION_TOKEN, delete_upload_job

    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", biblioteca["uploads"])
    enlace = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])["ruta"]
    conn = connect()
    init_db(conn)
    _subida(conn, "completed", enlace)
    fallida = _subida(conn, "failed", enlace)
    conn.commit()

    assert delete_upload_job(fallida, confirmation=DELETE_CONFIRMATION_TOKEN, conn=conn)["ok"]
    assert os.path.lexists(enlace)


def test_borrar_no_quita_el_enlace_de_una_subida_en_marcha(biblioteca, monkeypatch, isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.upload_execution import DELETE_CONFIRMATION_TOKEN, delete_upload_job

    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", biblioteca["uploads"])
    enlace = preparar_fichero_suelto(biblioteca["ficheros"][0], raiz=biblioteca["uploads"])["ruta"]
    conn = connect()
    init_db(conn)
    _subida(conn, "running", enlace)
    fallida = _subida(conn, "failed", enlace)
    conn.commit()

    assert delete_upload_job(fallida, confirmation=DELETE_CONFIRMATION_TOKEN, conn=conn)["ok"]
    assert os.path.lexists(enlace)
