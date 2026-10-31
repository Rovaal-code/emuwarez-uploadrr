"""Nombres y banderas de las pistas, sobre MKV de verdad y con mkvpropedit real."""
from __future__ import annotations

import subprocess

from emuwarez_uploadrr.services.mkv_remux import (build_mkvmerge_args, build_mkvpropedit_args,
                                                  build_track_plan, read_tracks_json)

from .mkv_sinteticos import hacer_mkv, requiere_herramientas

pytestmark = requiere_herramientas


def _pistas(ruta) -> list[dict]:
    return read_tracks_json(str(ruta))["data"]["tracks"]


def test_solo_reordenar_no_llama_None_a_las_pistas(tmp_path):
    """Con "Solo reordenar" las pistas sin nombre acababan llamándose "None"."""
    ruta = hacer_mkv(tmp_path / "Peli.mkv", audios=({"lang": "en"}, {"lang": "es"}), subs=({"lang": "es"},))
    plan = build_track_plan(read_tracks_json(str(ruta))["data"], reorder=False, rename=False)
    args = build_mkvpropedit_args(str(ruta), plan)
    assert not any("None" in a for a in args), args
    subprocess.run(args, check=True, capture_output=True)
    assert all(not (t["properties"].get("track_name")) for t in _pistas(ruta))

    plan = build_track_plan(read_tracks_json(str(ruta))["data"], reorder=True, rename=False)
    assert "--track-name" not in build_mkvmerge_args("/tmp/o.mkv", str(ruta), plan)


def test_renombrar_conserva_comentarios_y_sdh(tmp_path):
    """Dos castellanos (normal y comentarios) y dos subtítulos (completo y
    SDH) ya no salen con el mismo nombre, y los comentarios no quedan como
    audio predeterminado aunque vengan primero."""
    ruta = hacer_mkv(
        tmp_path / "Peli.mkv",
        audios=({"lang": "es", "canales": 2, "comentario": True}, {"lang": "es"}),
        subs=({"lang": "es"}, {"lang": "es", "sdh": True}),
    )
    plan = build_track_plan(read_tracks_json(str(ruta))["data"])
    audio = [t for t in plan["ordered_tracks"] if t["type"] == "audio"]
    assert [(t["new_name"], t["default_after"]) for t in audio] == [
        ("Español (Castellano) - DD 5.1", True),
        ("Español (Castellano) - DD 2.0 - Comentarios", False),
    ]
    subs = [t["new_name"] for t in plan["ordered_tracks"] if t["type"] == "subtitles"]
    assert subs == ["Español (Castellano)", "Español (Castellano) - SDH"]


def test_un_forzado_por_el_nombre_se_marca_en_el_contenedor(tmp_path):
    """El reproductor obedece la bandera, no el nombre: antes quedaba a 0."""
    ruta = hacer_mkv(tmp_path / "Peli.mkv", audios=({"lang": "es"},),
                     subs=({"lang": "es", "titulo": "Spanish Forced"}, {"lang": "es"}))
    plan = build_track_plan(read_tracks_json(str(ruta))["data"])
    subprocess.run(build_mkvpropedit_args(str(ruta), plan), check=True, capture_output=True)
    subs = [t for t in _pistas(ruta) if t["type"] == "subtitles"]
    forzados = {t["properties"]["track_name"]: bool(t["properties"].get("forced_track")) for t in subs}
    assert forzados == {"Español (Castellano) - Forzado": True, "Español (Castellano)": False}
