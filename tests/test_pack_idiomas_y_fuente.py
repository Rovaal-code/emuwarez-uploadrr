"""El idioma elegido para las pistas de audio sin idioma de un pack de
temporada, y el aviso de Source cuando MediaInfo dice otra cosa.

- Un pack solo avisaba de que una pista no tenía idioma y no dejaba elegirlo.
  Ahora se elige una vez por posición de audio y llega al nombre del pack, al
  de cada capítulo y al remux de cada capítulo al subir (mismas posiciones).
- Cuando la Internal Source Tool (MediaInfo) apunta a otro source que el nombre
  o Radarr/Sonarr, el asistente lo dice con una frase, sin bloquear.
"""
from __future__ import annotations

import json

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services import upload_queue as uq
from emuwarez_uploadrr.services.mkv_remux import (build_remux_plan, idiomas_elegidos, idiomas_por_posicion,
                                                  overrides_de_idiomas)
from emuwarez_uploadrr.services.season_pack import (build_season_pack_plan, get_season_episode_names,
                                                    get_season_episode_remux_previews, recalcular_audio_del_pack)
from emuwarez_uploadrr.services.source_assistant import aviso_source_discrepante

from .mkv_sinteticos import hacer_mkv, requiere_herramientas


def _open(isolated_db):
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _temporada(conn, carpeta, audios_por_capitulo):
    """Una serie con una temporada completa; un MKV de verdad por capítulo."""
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status, updated_at)
           VALUES ('series', 'Serie', 2020, 'Parcial', 'Sin petición', 'N/A', CURRENT_TIMESTAMP)""")
    serie = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                      parent_id, season_number, updated_at)
           VALUES ('season', 'Serie - Temporada 1', 2020, 'Parcial', 'Sin petición', 'N/A', ?, 1, CURRENT_TIMESTAMP)""",
        (serie,))
    temporada = cur.lastrowid
    capitulos = []
    for n, audios in enumerate(audios_por_capitulo, 1):
        ruta = hacer_mkv(carpeta / f"Serie.S01E0{n}.1080p.WEB-DL.mkv", audios=audios)
        cur = conn.execute(
            """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                          parent_id, season_number, episode_number, path, quality,
                                          subtitle_languages, updated_at)
               VALUES ('episode', ?, 2020, 'Disponible', 'Sin petición', 'No adaptada', ?, 1, ?, ?, 'WEBDL-1080p',
                       'spa', CURRENT_TIMESTAMP)""",
            (f"Serie S01E0{n}", temporada, n, str(ruta)))
        capitulos.append((cur.lastrowid, str(ruta)))
    conn.commit()
    return temporada, capitulos


# --- Idiomas por posición (puro) ----------------------------------------------

def test_los_idiomas_por_posicion_se_limpian():
    # Del JSON del trabajo vuelven con la clave en texto; lo que no es una opción se descarta.
    assert idiomas_por_posicion({"2": "spa", "1": "klingon", "x": "eng", "0": "eng"}) == {2: "spa"}
    assert idiomas_por_posicion(None) == {}


def test_los_overrides_de_un_fichero_solo_tocan_pistas_sin_idioma():
    datos = {"tracks": [
        {"id": 0, "type": "video", "properties": {}},
        {"id": 1, "type": "audio", "properties": {"language": "und"}},
        {"id": 2, "type": "audio", "properties": {"language": "eng"}},
    ]}
    # La posición 2 ya trae inglés: un pack que la elige para otro capítulo no la pisa aquí.
    assert overrides_de_idiomas(datos, {"1": "spa", "2": "cat", "7": "eng"}) == {1: {"language": "spa"}}


# --- El pack, con MKV de verdad -----------------------------------------------

@requiere_herramientas
def test_el_idioma_elegido_llega_al_nombre_del_pack_y_a_cada_capitulo(isolated_db, tmp_path):
    conn = _open(isolated_db)
    audios = ({"lang": "und"}, {"lang": "en"})
    temporada, capitulos = _temporada(conn, tmp_path, [audios, audios])

    sin = build_season_pack_plan(temporada, conn=conn)
    assert sin["status"] == "valid"
    assert " ING DD 5.1" in sin["season_pack_title"]
    assert "Capítulo(s) 1, 2" in sin["audio_warning"]
    assert [(p["posicion"], p["capitulos"], p["idioma"]) for p in sin["pistas_sin_idioma"]] == [(1, [1, 2], None)]
    assert sin["pistas_sin_idioma"][0]["pista"] == "DD 5.1"
    assert any(o["code"] == "spa" for o in sin["idiomas_elegibles"])

    con = build_season_pack_plan(temporada, conn=conn, idiomas_audio={"1": "spa"})
    assert con["status"] == "valid"
    assert " DUAL DD 5.1" in con["season_pack_title"]
    assert all("DUAL" in ep["nombre"] for ep in con["episodes"])
    assert con["audio_warning"] is None
    # La pista sigue en el selector, ya con lo elegido: se puede cambiar.
    assert con["pistas_sin_idioma"][0]["idioma"] == "spa"
    assert con["idiomas_audio"] == {1: "spa"}

    # El recálculo barato del asistente da lo mismo que el plan entero.
    audio = recalcular_audio_del_pack(temporada, {"1": "spa"}, conn=conn)
    assert (audio["audio_summary"], audio["custom"], audio["audio_warning"]) == (
        con["audio_summary"], con["custom"], None)

    # "Ver nombre de todos los capítulos" y "Ver Pistas" dicen lo mismo.
    nombres = get_season_episode_names(temporada, conn=conn, idiomas_audio={"1": "spa"})["episodes"]
    assert all("DUAL" in e["torrent_name"] for e in nombres)
    pistas = get_season_episode_remux_previews(temporada, conn=conn, idiomas_audio={"1": "spa"})["episodes"]
    for e in pistas:
        audio_tracks = [t for t in e["plan"]["tracks"] if t["type"] == "audio"]
        assert audio_tracks[0]["language_after"] == "spa"
    conn.close()


@requiere_herramientas
def test_el_idioma_elegido_no_se_guarda_como_propuesta_del_capitulo(isolated_db, tmp_path):
    from emuwarez_uploadrr.services.nomenclature import get_latest_nomenclature_proposal
    conn = _open(isolated_db)
    audios = ({"lang": "und"}, {"lang": "en"})
    temporada, capitulos = _temporada(conn, tmp_path, [audios])
    build_season_pack_plan(temporada, conn=conn, idiomas_audio={"1": "spa"})
    guardada = get_latest_nomenclature_proposal(capitulos[0][0], conn=conn)
    assert guardada is None or "DUAL" not in (guardada.get("proposed_torrent_name") or "")
    conn.close()


@requiere_herramientas
def test_el_remux_de_cada_capitulo_lleva_el_idioma_que_dice_el_nombre(isolated_db, tmp_path):
    conn = _open(isolated_db)
    temporada, capitulos = _temporada(conn, tmp_path, [({"lang": "und"}, {"lang": "en"})] * 2)
    ajustes = {"idiomas": {"1": "spa"}}
    for item_id, ruta in capitulos:
        overrides = uq._overrides_de_pack(ruta, ajustes)
        assert list(overrides.values()) == [{"language": "spa"}]
        plan = build_remux_plan(item_id, conn=conn, ruta=ruta, idiomas=idiomas_elegidos(overrides))
        audio = [t for t in plan["tracks"] if t["type"] == "audio"]
        assert [t["language_after"] for t in audio][0] == "spa"
    # Sin nada elegido, el remux de un pack sigue sin overrides.
    assert uq._overrides_de_pack(capitulos[0][1], {}) is None
    conn.close()


def test_los_idiomas_viajan_con_los_ajustes_del_pack(isolated_db):
    conn = _open(isolated_db)
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                      season_number, updated_at)
           VALUES ('season', 'Serie - Temporada 1', 2020, 'Parcial', 'Sin petición', 'N/A', 1, CURRENT_TIMESTAMP)""")
    conn.commit()
    r = uq.queue_upload_for_item(cur.lastrowid, idiomas_audio={"1": "spa", "2": "nada"}, conn=conn)
    fila = conn.execute("SELECT season_overrides_json FROM upload_jobs WHERE id = ?", (r["job"]["id"],)).fetchone()
    guardado = json.loads(fila["season_overrides_json"])
    assert guardado["idiomas"] == {"1": "spa"}
    assert uq._ajustes_de_pack(guardado)["idiomas_audio"] == {"1": "spa"}
    conn.close()


def test_el_endpoint_del_audio_del_pack(client, auth_headers, isolated_db, monkeypatch):
    from emuwarez_uploadrr.web.api import season_pack as api
    visto = {}

    def falso(season_id, idiomas, conn=None):
        visto["idiomas"] = idiomas
        return {"audio_summary": "DUAL DD 5.1", "custom": False, "audio_warning": None,
                "pistas_sin_idioma": [], "idiomas_audio": {1: "spa"}}

    monkeypatch.setattr(api, "recalcular_audio_del_pack", falso)
    r = client.get("/api/library/season/5/pack-audio", params={"idiomas": '{"1": "spa"}'}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["audio_summary"] == "DUAL DD 5.1"
    assert visto["idiomas"] == {"1": "spa"}
    # Un JSON roto es "nada elegido", no un 500.
    client.get("/api/library/season/5/pack-audio", params={"idiomas": "{roto"}, headers=auth_headers)
    assert visto["idiomas"] is None


# --- Aviso de Source -----------------------------------------------------------

@pytest.mark.parametrize("comparacion, esperado", [
    (None, None),
    ({"from_name": "WEB-DL", "from_radarr": "WEB-DL", "from_mediainfo": None}, None),
    ({"from_name": "WEB-DL", "from_radarr": None, "from_mediainfo": "WEB-DL"}, None),
    # Solo el nombre y Radarr/Sonarr discrepan: no es lo que dice MediaInfo.
    ({"from_name": "WEB-DL", "from_radarr": "BluRay", "from_mediainfo": None}, None),
])
def test_sin_discrepancia_de_mediainfo_no_hay_aviso(comparacion, esperado):
    assert aviso_source_discrepante(comparacion) is esperado


def test_el_aviso_dice_que_dice_cada_lado_y_donde_cambiarlo():
    aviso = aviso_source_discrepante({"from_name": "WEB-DL", "from_radarr": "WEB-DL",
                                      "from_mediainfo": "BDRemux", "mediainfo_confirmed": False})
    assert aviso.startswith("MediaInfo (por el bitrate y el audio) sugiere BDRemux")
    assert "el nombre del archivo dice WEB-DL" in aviso and "Radarr/Sonarr dice WEB-DL" in aviso
    assert "cámbialo en Source" in aviso and "No bloquea" in aviso
    # Con la detección confirmada se dice con más seguridad, y un lado que coincide no se nombra.
    aviso = aviso_source_discrepante({"from_name": "WEB-DL", "from_radarr": "BluRay",
                                      "from_mediainfo": "BluRay", "mediainfo_confirmed": True})
    assert aviso.startswith("MediaInfo indica BluRay, pero el nombre del archivo dice WEB-DL.")


@requiere_herramientas
def test_el_asistente_devuelve_el_aviso_de_source(isolated_db, tmp_path):
    from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
    conn = _open(isolated_db)
    ruta = hacer_mkv(tmp_path / "Peli.2024.1080p.WEB-DL.mkv", audios=({"lang": "es"},))
    cur = conn.execute(
        "INSERT INTO library_items (item_type, title, year, local_status, request_status, path, resolution) "
        "VALUES ('movie', 'Peli', 2024, 'Disponible', 'Sin petición', ?, '1080p')", (str(ruta),))
    conn.commit()
    campos = build_editable_nomenclature_fields(cur.lastrowid, conn=conn)
    assert campos["source_mismatch_warning"] == aviso_source_discrepante(campos["source_comparison"])
    conn.close()


def test_el_pack_lleva_el_aviso_de_source_del_capitulo_representativo(isolated_db, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import source_assistant
    conn = _open(isolated_db)
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                      season_number, updated_at)
           VALUES ('season', 'Serie - Temporada 1', 2020, 'Parcial', 'Sin petición', 'N/A', 1, CURRENT_TIMESTAMP)""")
    temporada = cur.lastrowid
    f = tmp_path / "S01E03.mkv"
    f.write_bytes(b"video")
    conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                      parent_id, season_number, episode_number, path, quality, subtitle_languages)
           VALUES ('episode', 'Serie S01E03', 2020, 'Disponible', 'Sin petición', 'No adaptada', ?, 1, 3, ?,
                   'WEBDL-1080p', 'spa')""", (temporada, str(f)))
    conn.commit()
    comparacion = {"from_name": "WEB-DL", "from_radarr": None, "from_mediainfo": "BDRemux",
                   "mediainfo_confirmed": True, "agree": False}
    monkeypatch.setattr(source_assistant, "build_editable_nomenclature_fields",
                        lambda *a, **k: {"source_comparison": comparacion,
                                         "source_mismatch_warning": aviso_source_discrepante(comparacion)})
    plan = build_season_pack_plan(temporada, conn=conn)
    assert plan["status"] == "valid"
    assert plan["source_mismatch_warning"] == (
        "Capítulo 3: MediaInfo indica BDRemux, pero el nombre del archivo dice WEB-DL. Si el bueno es BDRemux, "
        "cámbialo en Source; si no, déjalo como está. No bloquea la subida.")
    conn.close()


def test_el_idioma_elegido_no_pisa_una_pista_que_ya_lo_trae(tmp_path):
    """Como el remux (build_track_plan): el nombre solo cambia las pistas sin idioma."""
    from unittest.mock import patch
    from emuwarez_uploadrr.services import media_info_service as svc
    f = tmp_path / "cap.mkv"
    f.write_bytes(b"x" * 100)
    info = {"media": {"track": [
        {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080"},
        {"@type": "Audio", "Format": "AC-3", "Channels": "6", "Language": "en"},
    ]}}
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=info),
    ):
        informe = svc.build_mediainfo_report(str(f), idiomas_audio={1: "spa"})
    assert informe["audio_summary"] == "ING DD 5.1"
