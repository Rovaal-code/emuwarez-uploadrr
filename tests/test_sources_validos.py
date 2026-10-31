"""Todo source que se guarde tiene que existir en eMuwarez.

Radarr y Sonarr traducen su nombre de calidad ("Bluray-1080p") a un source
nuestro, cada uno con su propia función. Ninguna comprobaba que el resultado
existiera en el vocabulario del tracker: una película con calidad DVD acababa
guardada con source "DVD", que en eMuwarez no existe (allí es "SD").

Se salvaba a medias porque el editor de campos descarta un source que no sea
válido y cae en la estimación de MediaInfo, pero eso es un parche río abajo:
lo que se guarda en la biblioteca estaba mal.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations import radarr, sonarr
from emuwarez_uploadrr.services.source_assistant import EMU_SOURCES

VALIDOS = {s["code"] for s in EMU_SOURCES}

# Nombres de calidad tal cual los reporta *Arr, incluidos los raros.
CALIDADES = [
    "Bluray-2160p", "Bluray-1080p", "Bluray-720p", "Bluray-480p",
    "Remux-2160p", "Remux-1080p",
    "WEBDL-2160p", "WEBDL-1080p", "WEBDL-720p", "WEB-DL 1080p",
    "WEBRip-1080p", "WEBRip-720p", "web-rip 480p",
    "HDTV-1080p", "HDTV-720p", "HDTV-480p",
    "DVD", "DVD-R", "SDTV", "Raw-HD", "Unknown", "Bluray-1080p Remux",
]


@pytest.mark.parametrize("calidad", CALIDADES)
def test_radarr_nunca_inventa_un_source(calidad):
    valor = radarr._source_from_quality(calidad)
    assert valor is None or valor in VALIDOS, (
        f"Radarr traduce {calidad!r} a {valor!r}, que no existe en eMuwarez.\n"
        f"Válidos: {sorted(VALIDOS)}"
    )


@pytest.mark.parametrize("calidad", CALIDADES)
def test_sonarr_nunca_inventa_un_source(calidad):
    valor = sonarr._source_from_quality(calidad)
    assert valor is None or valor in VALIDOS, (
        f"Sonarr traduce {calidad!r} a {valor!r}, que no existe en eMuwarez.\n"
        f"Válidos: {sorted(VALIDOS)}"
    )


def test_el_dvd_de_radarr_es_sd():
    """El caso concreto que estaba mal."""
    assert radarr._source_from_quality("DVD") == "SD"
    assert sonarr._source_from_quality("DVD-R") == "SD"


def test_la_deteccion_por_nombre_tampoco_inventa():
    """Y la otra vía, la que mira el nombre del archivo."""
    from emuwarez_uploadrr.constants import SOURCE_PATTERNS

    for _patron, valor in SOURCE_PATTERNS:
        assert valor in VALIDOS, f"SOURCE_PATTERNS produce {valor!r}, que no existe en eMuwarez"


@pytest.mark.parametrize("calidad", CALIDADES)
def test_la_nomenclatura_tampoco_inventa_un_source(calidad):
    """La reserva de nomenclature.py, cuando el nombre no dice nada: escribía
    "BDReMux" y "DVD", que no existen."""
    from emuwarez_uploadrr.services.nomenclature import _infer_source_from_item
    valor = _infer_source_from_item({"quality": calidad, "path": "/pelis/sin_pistas.mkv"})
    assert valor is None or valor in VALIDOS, (calidad, valor)


def test_el_full_bluray_que_escribe_la_app_se_reconoce():
    """Si no, al renombrar un Full BluRay el nombre nuevo se leía como BluRay."""
    from pathlib import Path
    from emuwarez_uploadrr.services.media_probe import _detect_source_by_name
    assert _detect_source_by_name(Path("Peli.2020.1080p.Full.BluRay.AVC.ESP.DTS-HD.MA.5.1-EMUWAREZ.mkv")) == "Full BluRay"
