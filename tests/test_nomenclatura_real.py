"""El nombre que genera la app, sobre MKV de verdad, y lo que dice de él
Comprobar nomenclatura.

Antes había dos constructores: el de la subida y el del comprobador, y cada
uno daba un nombre distinto para el mismo fichero (4K, SD, mudo, tres audios…).
El comprobador marcaba "No adaptada" justo los ficheros que la app acababa de
renombrar. Ahora el comprobador llama al generador; estas pruebas fijan además
qué nombre sale en cada caso.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services import nomenclature_check as nc
from emuwarez_uploadrr.services.nomenclature import compute_nomenclature_proposal

from .mkv_sinteticos import hacer_mkv, requiere_herramientas

pytestmark = requiere_herramientas


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    c = connect(tmp_path / "test.db")
    init_db(c)
    yield c
    c.close()


def _fila(conn, **kw) -> dict:
    kw.setdefault("item_type", "movie")
    kw.setdefault("local_status", "Disponible")
    kw.setdefault("request_status", "Sin petición")
    cols = ", ".join(kw)
    cur = conn.execute(f"INSERT INTO library_items ({cols}) VALUES ({', '.join('?' * len(kw))})",
                       tuple(kw.values()))
    conn.commit()
    return dict(conn.execute("SELECT * FROM library_items WHERE id = ?", (cur.lastrowid,)).fetchone())


def _renombrar_como_la_app(conn, item: dict) -> str:
    """Renombra el fichero al nombre que propone la app y devuelve el título."""
    import os
    prop = compute_nomenclature_proposal(item, conn=conn)
    nuevo = os.path.join(os.path.dirname(item["path"]), prop["proposed_filename"] + ".mkv")
    os.replace(item["path"], nuevo)
    conn.execute("UPDATE library_items SET path = ? WHERE id = ?", (nuevo, item["id"]))
    conn.commit()
    return prop["proposed_torrent_name"]


CASOS = {
    "uhd": (dict(ancho=3840, alto=2160, audios=({"lang": "es"}, {"lang": "en"})),
            "Pelicula 2024 2160p 4K UHD WEB-DL x264 DUAL DD 5.1-EMUWAREZ"),
    "sd480": (dict(ancho=720, alto=480, audios=({"lang": "es"},)),
              "Pelicula 2024 480p WEB-DL x264 ESP DD 5.1-EMUWAREZ"),
    "esp_jap": (dict(audios=({"lang": "es"}, {"lang": "ja"})),
                "Pelicula 2024 1080p WEB-DL x264 ESP-JAP DD 5.1-EMUWAREZ"),
    "mudo": (dict(audios=()), "Pelicula 2024 1080p WEB-DL x264-EMUWAREZ"),
    "tres": (dict(audios=({"lang": "es"}, {"lang": "en"}, {"lang": "fr"})),
             "Pelicula 2024 1080p WEB-DL x264 ESP-ING-FRA DD 5.1-EMUWAREZ"),
    "compatibilidad": (dict(audios=({"lang": "es", "codec": "eac3"}, {"lang": "en", "codec": "eac3"},
                                    {"lang": "es", "codec": "ac3"})),
                       "Pelicula 2024 1080p WEB-DL x264 DUAL DD+ 5.1-EMUWAREZ"),
}


@pytest.mark.parametrize("caso", sorted(CASOS))
def test_el_comprobador_acepta_lo_que_genera_la_app(caso, conn, tmp_path):
    opciones, esperado = CASOS[caso]
    carpeta = tmp_path / caso
    carpeta.mkdir()
    ruta = hacer_mkv(carpeta / "Pelicula.WEB-DL.mkv", **opciones)
    resolucion = {3840: "2160p", 720: "480p"}.get(opciones.get("ancho"), "1080p")
    item = _fila(conn, title="Pelicula", year=2024, path=str(ruta), resolution=resolucion)

    assert _renombrar_como_la_app(conn, item) == esperado
    resumen = nc.check_item(conn, item["id"], force=True)
    assert resumen["correct"] == 1, resumen["results"]


def test_un_especial_conserva_su_S00(conn, tmp_path):
    serie = _fila(conn, item_type="series", title="Serie", year=2020, path=None)
    temporada = _fila(conn, item_type="season", title="Especiales", parent_id=serie["id"],
                      season_number=0, path=None)
    ruta = hacer_mkv(tmp_path / "Serie.WEB-DL.mkv", audios=({"lang": "es"},))
    ep = _fila(conn, item_type="episode", title="Serie S00E05", parent_id=temporada["id"],
               season_number=0, episode_number=5, year=2020, path=str(ruta))

    assert _renombrar_como_la_app(conn, ep).startswith("Serie S00E05 2020 ")
    assert nc.check_item(conn, ep["id"], force=True)["correct"] == 1


def test_un_nombre_mal_puesto_dice_que_falta(conn, tmp_path):
    ruta = hacer_mkv(tmp_path / "Pelicula.2024.1080p.WEB-DL.x264.DD.5.1-GRUPO.mkv",
                     ancho=3840, alto=2160, audios=({"lang": "es"},))
    item = _fila(conn, title="Pelicula", year=2024, path=str(ruta), resolution="2160p")
    r = nc.check_item(conn, item["id"], force=True)["results"][0]
    assert r["status"] == nc.STATUS_NOT_ADAPTED
    # Alineado por tokens: lo que falta se nombra, sin desplazar el resto.
    assert r["diff"] == ["'1080p' ≠ esperado '2160p'", "falta '4K'", "falta 'UHD'", "falta 'ESP'"]
