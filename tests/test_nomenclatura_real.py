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
from emuwarez_uploadrr.services.nomenclature import build_nomenclature_proposal

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
    prop = build_nomenclature_proposal(item["id"], conn=conn, guardar=False)
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


# --- Idiomas: un solo traductor para el nombre, la biblioteca y las pistas ----

LATINOS = ({"lang": "es-MX"}, {"lang": "es-AR"}, {"lang": "es-US"}, {"lang": "es", "titulo": "Latino"})


@pytest.mark.parametrize("pista", LATINOS, ids=lambda p: p.get("titulo") or p["lang"])
def test_el_latino_sale_LAT_en_todas_partes(pista, tmp_path):
    from emuwarez_uploadrr.services.emu_format import has_castellano
    from emuwarez_uploadrr.services.media_info_service import (build_mediainfo_report,
                                                               read_media_info_summary)
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan, read_tracks_json

    ruta = str(hacer_mkv(tmp_path / "Peli.mkv", audios=(pista, {"lang": "en"})))

    informe = build_mediainfo_report(ruta)
    assert informe["audio_summary"] == "LAT-ING DD 5.1"
    resumen = read_media_info_summary(ruta)
    assert resumen["audio_languages"] == "LAT / ING"
    assert has_castellano(resumen["audio_languages"]) == 0

    plan = build_track_plan(read_tracks_json(ruta)["data"])
    audio = [t for t in plan["ordered_tracks"] if t["type"] == "audio"]
    assert audio[0]["new_name"] == "Inglés - DD 5.1"     # el latino no pasa delante
    assert audio[1]["new_name"].startswith("Español (Latinoamérica) - DD 5.1")


def test_el_castellano_de_MAX_sigue_siendo_castellano(tmp_path):
    from emuwarez_uploadrr.services.media_info_service import build_mediainfo_report
    ruta = str(hacer_mkv(tmp_path / "Peli.mkv", audios=({"lang": "es-x-01"}, {"lang": "en"})))
    assert build_mediainfo_report(ruta)["audio_summary"] == "DUAL DD 5.1"


def test_una_pista_sin_idioma_avisa_y_el_nombre_sale_sin_ella(conn, tmp_path):
    """Decidido por Gabriel: avisa, no bloquea, y nunca se escribe "UND"."""
    import json
    ruta = hacer_mkv(tmp_path / "Peli.WEB-DL.mkv", audios=({"lang": "es"}, {"lang": "und", "codec": "aac", "canales": 2}))
    item = _fila(conn, title="Peli", year=2024, path=str(ruta), resolution="1080p")
    prop = build_nomenclature_proposal(item["id"], conn=conn, guardar=False)
    assert prop["status"] == "warning"
    assert prop["proposed_torrent_name"] == "Peli 2024 1080p WEB-DL x264 ESP DD 5.1-EMUWAREZ"
    assert any("pista de audio 2 no tiene idioma" in w for w in json.loads(prop["warnings_json"]))


def test_el_idioma_elegido_en_el_asistente_llega_al_nombre_y_a_la_pista(conn, tmp_path):
    """Lo elegido en Ver Pistas para la pista sin idioma: entra en el nombre del
    release, en el nombre de la pista y en la etiqueta de idioma del MKV, aunque
    el trabajo guarde los overrides con la clave en texto."""
    import json
    import subprocess
    from emuwarez_uploadrr.services.mkv_remux import (_idiomas_de, build_mkvpropedit_args,
                                                      build_track_plan, read_tracks_json)
    from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
    ruta = hacer_mkv(tmp_path / "Peli.WEB-DL.mkv", audios=({"lang": "und"}, {"lang": "en"}))
    item = _fila(conn, title="Peli", year=2024, path=str(ruta), resolution="1080p")

    sin_elegir = build_editable_nomenclature_fields(item["id"], conn=conn)
    assert sin_elegir["fields"]["audio_summary"] == "ING DD 5.1"
    assert "pista de audio 1" in sin_elegir["audio_warning"]
    elegido = build_editable_nomenclature_fields(item["id"], conn=conn, idiomas_audio={1: "spa"})
    assert elegido["fields"]["audio_summary"] == "DUAL DD 5.1" and elegido["audio_warning"] is None

    datos = read_tracks_json(str(ruta))["data"]
    pista = next(t["id"] for t in datos["tracks"] if t["type"] == "audio")
    overrides = json.loads(json.dumps({pista: {"language": "spa"}}))      # como vuelve del trabajo
    plan = build_track_plan(datos, idiomas=_idiomas_de(overrides))
    audio = [t for t in plan["ordered_tracks"] if t["type"] == "audio"]
    assert [(t["new_name"], t["default_after"]) for t in audio] == [
        ("Español (Castellano) - DD 5.1", True), ("Inglés - DD 5.1", False)]
    subprocess.run(build_mkvpropedit_args(str(ruta), plan), check=True, capture_output=True)
    idiomas = [t["properties"]["language"] for t in read_tracks_json(str(ruta))["data"]["tracks"]
               if t["type"] == "audio"]
    assert idiomas == ["spa", "eng"]


def test_la_resolucion_sale_del_fichero_y_no_de_la_etiqueta(conn, tmp_path):
    """Radarr etiquetó 1080p un fichero que es 720p: manda el fichero."""
    ruta = hacer_mkv(tmp_path / "Peli.1080p.WEB-DL.mkv", ancho=1280, alto=720, audios=({"lang": "es"},))
    item = _fila(conn, title="Peli", year=2024, path=str(ruta), resolution="1080p",
                 quality="WEBDL-1080p")
    prop = build_nomenclature_proposal(item["id"], conn=conn, guardar=False)
    assert prop["resolution"] == "720p"
    assert " 720p WEB-DL " in prop["proposed_torrent_name"]
    assert not any("Resolución" in w for w in __import__("json").loads(prop["warnings_json"]))


# --- Integridad: un MKV vacío o con basura no pasa ---------------------------

@pytest.mark.parametrize("contenido", [b"", b"\x13\x37basura" * 600], ids=["vacio", "basura"])
def test_un_mkv_roto_no_pasa_la_comprobacion_de_integridad(contenido, tmp_path):
    from emuwarez_uploadrr.services.media_info_service import read_media_info_summary
    from emuwarez_uploadrr.services.mkv_remux import read_tracks_json
    f = tmp_path / "roto.mkv"
    f.write_bytes(contenido)
    assert read_media_info_summary(str(f)) is None
    assert read_tracks_json(str(f))["ok"] is False


def test_un_mkv_bueno_si_pasa(tmp_path):
    from emuwarez_uploadrr.services.media_info_service import read_media_info_summary
    from emuwarez_uploadrr.services.mkv_remux import read_tracks_json
    ruta = str(hacer_mkv(tmp_path / "Peli.mkv", audios=({"lang": "es"},)))
    assert read_media_info_summary(ruta)["audio_languages"] == "ESP"
    assert read_tracks_json(ruta)["ok"] is True
