"""Una serie SD no se queda sin resolución.

Reportado con un caso real: una temporada mostraba "-" en resolución, y sus
capítulos también, pero en Sonarr se veía 640x480 y en "Ver MediaInfo" también.
Consecuencia: esa temporada no se podía subir como pack, porque la regla exige
que todos los capítulos coincidan en resolución y "vacío" no coincide con nada.

La causa: la resolución salía SOLO del NOMBRE del perfil de calidad
("Bluray-1080p" -> 1080p). Los nombres de contenido SD no llevan número
("SDTV", "DVD", "Raw-HD", "Unknown"), así que devolvía None — mientras el dato
real venía en el mismo payload, en mediaInfo.resolution, sin leerse.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations import radarr, sonarr
from emuwarez_uploadrr.integrations.base import extract_media_info


def _episode_file(quality: str, resolution: str | None):
    return {
        "id": 1, "quality": {"quality": {"name": quality}},
        "mediaInfo": {"resolution": resolution, "videoCodec": "x264",
                      "audioCodec": "AC3", "audioLanguages": "spa"},
        "path": "/data/serie/S01E01.mkv", "size": 700_000_000,
    }


@pytest.mark.parametrize("dimensiones,esperado", [
    ("640x480", "480p"),
    ("720x576", "576p"),
    ("1920x1080", "1080p"),
    ("1280x720", "720p"),
    ("3840x2160", "2160p"),
    ("1920x800", "1080p"),      # cinemascope: manda la anchura
    (None, None),
    ("", None),
    ("basura", None),
])
def test_la_resolucion_de_arr_se_lee(dimensiones, esperado):
    info = extract_media_info(_episode_file("SDTV", dimensiones))
    assert info["resolution"] == esperado


def test_el_nombre_de_calidad_manda_cuando_lo_dice():
    """Si el perfil ya dice la resolución, esa gana: es la que el usuario ve en
    Sonarr y la que espera en el nombre."""
    assert sonarr._resolution_from_quality("Bluray-1080p") == "1080p"


def test_una_serie_sd_ya_no_se_queda_sin_resolucion():
    """El caso reportado, de punta a punta por el mapeador de capítulos."""
    item = sonarr.episode_to_library_item(
        {"id": 10, "seasonNumber": 1, "episodeNumber": 1, "title": "Piloto",
         "hasFile": True, "monitored": True},
        _episode_file("SDTV", "640x480"),
        {"id": 7, "title": "Serie SD", "tmdbId": 1, "path": "/data/serie"},
        instance_id=1, instance_name="Sonarr",
    )
    assert item.resolution == "480p", "la temporada seguiría sin poder subirse como pack"


def test_sin_resolucion_en_ningun_sitio_sigue_vacia():
    """Y no se inventa nada: si *Arr no manda dimensiones, sigue vacío."""
    item = sonarr.episode_to_library_item(
        {"id": 11, "seasonNumber": 1, "episodeNumber": 2, "hasFile": True, "monitored": True},
        _episode_file("SDTV", None),
        {"id": 7, "title": "Serie SD", "tmdbId": 1, "path": "/data/serie"},
        instance_id=1, instance_name="Sonarr",
    )
    assert item.resolution is None


def test_radarr_igual():
    info = extract_media_info({"mediaInfo": {"resolution": "640x480"}})
    assert info["resolution"] == "480p"
    assert radarr._resolution_from_quality("DVD") is None
