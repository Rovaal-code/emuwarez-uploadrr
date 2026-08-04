"""De qué fichero se lee un elemento cuando las dos rutas guardadas discrepan.

`path` es lo que dice Radarr/Sonarr y la sincronización lo refresca en cada
pasada. `prepared_path` es dónde dejó el fichero la última subida, y nadie lo
refresca nunca. La regla de siempre era `prepared_path or path`: mientras las
dos apuntan al mismo sitio da igual, y por eso pareció inofensiva durante
meses.

EL CASO QUE LA ROMPIÓ (The Tudors S03, 2026-08-04). La versión vieja renombraba
la carpeta real de Sonarr al título del release. El usuario deshizo ese
renombrado a mano, actualizó en Sonarr y sincronizó: `path` quedó bien y
`prepared_path` se quedó apuntando a una carpeta que ya no existe. Como iba
primero, ganaba, y subir contestaba "Archivo no accesible" con una ruta que la
ficha del contenido enseñaba correcta.

No es un caso único de aquel renombrado: pasa igual borrando a mano los enlaces
de la carpeta de subidas, o si el contenido se vuelve a descargar y Sonarr lo
deja en otro sitio.

La regla nueva mira cuál EXISTE. Con la subida a medias la ruta preparada está
viva y manda; en cuanto muere se vuelve solo a la biblioteca, que es lo que la
sincronización mantiene al día.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.path_mapping import ruta_de_lectura


@pytest.fixture
def biblioteca(tmp_path):
    """La carpeta real de Sonarr, con el capítulo dentro."""
    carpeta = tmp_path / "media" / "series" / "The Tudors" / "Season 3"
    carpeta.mkdir(parents=True)
    fichero = carpeta / "Los.Tudor.S03E01.1080p.BluRay.x264.mkv"
    fichero.write_bytes(b"x")
    return fichero


def test_el_caso_de_the_tudors(biblioteca, tmp_path):
    """La ruta preparada apunta a la carpeta renombrada, que ya no existe."""
    muerta = (tmp_path / "media" / "series" / "The Tudors"
              / "Los Tudor S03 2007 1080p BluRay x264 DUAL DD 5.1 SUBS-CCX94"
              / "Los.Tudor.S03E01.1080p.BluRay.x264.mkv")
    assert not muerta.exists()
    item = {"path": str(biblioteca), "prepared_path": str(muerta)}
    assert ruta_de_lectura(item) == str(biblioteca)


def test_con_la_ruta_preparada_viva_manda_ella(biblioteca, tmp_path):
    """Una subida a medias: los enlaces de uploads existen y son el fichero
    bueno. Si esto se rompiera, el remux y la nomenclatura leerían el original
    en vez de lo que se va a subir."""
    subidas = tmp_path / "config" / "Uploadrr" / "uploads"
    subidas.mkdir(parents=True)
    enlace = subidas / "Los.Tudor.S03E01.1080p.BluRay.x264.mkv"
    enlace.write_bytes(b"x")
    item = {"path": str(biblioteca), "prepared_path": str(enlace)}
    assert ruta_de_lectura(item) == str(enlace)


def test_un_enlace_simbolico_vale(biblioteca, tmp_path):
    """En la mayoría de instalaciones la carpeta de subidas cae en otro disco y
    lo que hay son enlaces simbólicos, no duros. Tienen que contar como vivos."""
    subidas = tmp_path / "config" / "Uploadrr" / "uploads"
    subidas.mkdir(parents=True)
    enlace = subidas / "cap.mkv"
    enlace.symlink_to(biblioteca)
    item = {"path": str(biblioteca), "prepared_path": str(enlace)}
    assert ruta_de_lectura(item) == str(enlace)


def test_un_enlace_simbolico_roto_no_vale(biblioteca, tmp_path):
    """Y si el original desaparece, el enlace sigue ahí pero no lleva a nada:
    eso es justo lo que no se puede leer."""
    subidas = tmp_path / "config" / "Uploadrr" / "uploads"
    subidas.mkdir(parents=True)
    enlace = subidas / "cap.mkv"
    enlace.symlink_to(tmp_path / "no-existe.mkv")
    item = {"path": str(biblioteca), "prepared_path": str(enlace)}
    assert ruta_de_lectura(item) == str(biblioteca)


def test_sin_ruta_preparada_se_usa_la_de_la_biblioteca(biblioteca):
    assert ruta_de_lectura({"path": str(biblioteca), "prepared_path": None}) == str(biblioteca)
    assert ruta_de_lectura({"path": str(biblioteca)}) == str(biblioteca)


def test_sin_ninguna_de_las_dos_no_revienta():
    assert ruta_de_lectura({}) is None
    assert ruta_de_lectura({"path": None, "prepared_path": None}) is None


def test_con_las_dos_muertas_no_se_pierde_la_ruta(tmp_path):
    """Sin nada que leer hay que fallar igual, pero diciendo QUÉ ruta falta:
    devolver None dejaría el mensaje de error en "(sin ruta)"."""
    item = {"path": str(tmp_path / "a.mkv"), "prepared_path": str(tmp_path / "b.mkv")}
    assert ruta_de_lectura(item) == str(tmp_path / "a.mkv")


def test_solo_ruta_preparada_y_muerta_se_devuelve_ella(tmp_path):
    item = {"path": None, "prepared_path": str(tmp_path / "b.mkv")}
    assert ruta_de_lectura(item) == str(tmp_path / "b.mkv")


class TestConMapeoDeRutas:
    """La comprobación de si existe tiene que hacerse sobre la ruta LOCAL.

    Radarr/Sonarr dicen /data/media/… y esta aplicación puede llegar al fichero
    por otro sitio (un montaje SSHFS/NFS). Mirando la ruta cruda, en esas
    instalaciones ninguna de las dos existiría nunca y siempre ganaría `path`
    aunque la preparada estuviera viva.
    """

    @pytest.fixture
    def conn(self, isolated_db, tmp_path):
        import json
        from emuwarez_uploadrr.database import connect, init_db
        conn = connect(isolated_db / "emuwarez_uploadrr.db")
        init_db(conn)
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("library.path_mappings",
             json.dumps([{"from": "/data/media", "to": str(tmp_path / "montaje")}])),
        )
        conn.commit()
        return conn

    def test_la_preparada_viva_se_ve_a_traves_del_mapeo(self, conn, tmp_path):
        real = tmp_path / "montaje" / "series" / "cap.mkv"
        real.parent.mkdir(parents=True)
        real.write_bytes(b"x")
        item = {"path": "/data/media/series/vieja.mkv",
                "prepared_path": "/data/media/series/cap.mkv"}
        assert ruta_de_lectura(item, conn) == "/data/media/series/cap.mkv"

    def test_la_preparada_muerta_se_detecta_a_traves_del_mapeo(self, conn, tmp_path):
        (tmp_path / "montaje" / "series").mkdir(parents=True)
        item = {"path": "/data/media/series/vieja.mkv",
                "prepared_path": "/data/media/series/no-existe.mkv"}
        assert ruta_de_lectura(item, conn) == "/data/media/series/vieja.mkv"

    def test_devuelve_la_ruta_CRUDA_no_la_mapeada(self, conn, tmp_path):
        """Lo guardado sigue en el convenio de Radarr/Sonarr, y quien llame
        aplica el mapeo. Devolviendo ya la mapeada se mapearía dos veces."""
        real = tmp_path / "montaje" / "series" / "cap.mkv"
        real.parent.mkdir(parents=True)
        real.write_bytes(b"x")
        item = {"path": None, "prepared_path": "/data/media/series/cap.mkv"}
        assert ruta_de_lectura(item, conn) == "/data/media/series/cap.mkv"
