"""La resolución en el nombre, y el valenciano.

Dos cambios que se piden juntos y comparten un test porque comparten el mismo
riesgo: la tabla de resoluciones está escrita en el código Y en la Guía, y los
idiomas se resuelven en dos capas distintas (el nombre del torrent y la columna
Idioma de "Ver Pistas"). Si una copia se mueve sin la otra, nada falla: solo
dicen cosas distintas.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from emuwarez_uploadrr.services.emu_format import (build_audio_string, format_language,
                                                   format_resolution)
from emuwarez_uploadrr.services.mkv_remux import lang_display_name

RAIZ = pathlib.Path(__file__).resolve().parents[1]

# La tabla, tal como la quiere eMuwarez.
RESOLUCIONES = [
    ("4320p", "4320p 8K FUHD"),
    ("2160p", "2160p 4K UHD"),
    ("1080p", "1080p"),
    ("720p", "720p"),
    ("576p", "576p"),
    ("540p", "540p"),
    ("480p", "480p"),
]


@pytest.mark.parametrize("entrada,esperado", RESOLUCIONES)
def test_la_resolucion_sale_como_toca(entrada, esperado):
    assert format_resolution(entrada) == esperado


@pytest.mark.parametrize("alias,esperado", [
    ("8K", "4320p 8K FUHD"), ("FUHD", "4320p 8K FUHD"),
    ("4K", "2160p 4K UHD"), ("UHD", "2160p 4K UHD"),
])
def test_los_alias_tambien(alias, esperado):
    """Radarr y Sonarr no siempre dicen "2160p": a veces es "4K" o "UHD"."""
    assert format_resolution(alias) == esperado


@pytest.mark.parametrize("baja", ["576p", "540p", "480p"])
def test_las_bajas_ya_no_llevan_SD(baja):
    """El token sobraba: la resolución ya lo dice."""
    assert "SD" not in (format_resolution(baja) or "")


def test_una_resolucion_rara_sale_tal_cual(baja="1440p"):
    """Sin inventarse un token que eMuwarez no tiene."""
    assert format_resolution("1440p") == "1440p"


def test_la_guia_dice_lo_mismo_que_el_codigo():
    """RESOLUTION_ROWS es una copia literal de esta tabla, y la Guía es lo que
    el usuario lee antes de subir: si se separan, una de las dos miente."""
    fuente = (RAIZ / "frontend/src/pages/GuidePage.tsx").read_text()
    m = re.search(r"const RESOLUTION_ROWS: \[string, string\]\[\] = \[(.*?)\n\]", fuente, re.S)
    assert m, "no se encontró RESOLUTION_ROWS"
    de_la_guia = re.findall(r"'[^']*', '([^']+)'", m.group(1))
    assert de_la_guia == [token for _, token in RESOLUCIONES]


# --- Valenciano --------------------------------------------------------------

@pytest.mark.parametrize("codigo", ["val", "valencian", "valenciano",
                                    "ca-valencia", "cat-valencia"])
def test_el_valenciano_tiene_su_propio_codigo(codigo):
    """Va aparte del catalán, no colapsado en CAT."""
    assert format_language(codigo) == "VAL"


@pytest.mark.parametrize("codigo", ["ca", "cat", "catalan"])
def test_el_catalan_sigue_siendo_catalan(codigo):
    assert format_language(codigo) == "CAT"


def test_el_valenciano_llega_al_nombre_del_torrent():
    assert build_audio_string("AAC LC", "spa / cat-valencia / eng", 2) == "ESP-VAL-ING AAC LC 2.0"


# --- Lo que producía "CA-" ---------------------------------------------------

@pytest.mark.parametrize("codigo,esperado", [
    ("ca-valencia", "VAL"),   # daba "CA-"
    ("pt-br", "POR"),         # daba "PT-"
    ("es-419", "LAT"),        # daba "ES-"
    ("zh-hans", "ZH"),        # daba "ZH-"
])
def test_un_codigo_regional_no_sale_troceado(codigo, esperado):
    """Lo desconocido se recortaba a tres letras sobre la cadena ENTERA, así
    que un BCP-47 daba un token con un guion suelto ("CA-") que llegaba tal
    cual al nombre del torrent. Visto en un pack real."""
    assert format_language(codigo) == esperado


def test_ningun_idioma_acaba_en_guion():
    """La forma general del fallo, por si aparece otro código raro."""
    for codigo in ["ca-valencia", "pt-br", "es-419", "zh-hans", "sr-latn", "az-arab"]:
        assert not (format_language(codigo) or "").endswith("-"), codigo


# --- La columna Idioma de "Ver Pistas" ---------------------------------------

def test_la_columna_distingue_el_valenciano():
    """mkvmerge da dos campos: `language` ("cat", sin variante) y
    `language_ietf` ("ca-valencia", con ella). Leyendo solo el primero, una
    pista en valenciano salía como catalán."""
    assert lang_display_name("cat", "ca-valencia") == "Valencià"
    assert lang_display_name("cat", None) == "Català"


def test_y_sigue_distinguiendo_el_latino():
    """El mismo mecanismo que ya existía para el castellano: no se rompe."""
    assert lang_display_name("spa", "es-419") == "Español (Latinoamérica)"
    assert lang_display_name("spa", None) == "Español (Castellano)"


# --- El latino no es castellano ------------------------------------------------

@pytest.mark.parametrize("lang,ietf,titulo,esperado", [
    ("spa", "es-MX", None, "LAT"),
    ("spa", "es-AR", None, "LAT"),
    ("spa", "es-US", None, "LAT"),
    ("spa", "es-419", None, "LAT"),
    ("spa", None, "Latino", "LAT"),
    ("spa", None, "Español Latinoamérica", "LAT"),
    ("spa", "es-ES", None, "ESP"),
    ("spa", "es-x-01", None, "ESP"),     # subetiqueta privada de MAX, no región
    ("spa", "es", "Castellano", "ESP"),
    ("und", None, "Castellano", "ESP"),  # el nombre pone el idioma que falta
    ("eng", None, "Latino", "ING"),      # pero no contradice la etiqueta
    ("cat", "ca-ES-valencia", None, "VAL"),
    ("und", None, None, "UND"),
    (None, None, None, "UND"),
])
def test_un_solo_traductor_de_idiomas(lang, ietf, titulo, esperado):
    from emuwarez_uploadrr.services.emu_format import resolve_language
    assert resolve_language(lang, ietf, titulo) == esperado


@pytest.mark.parametrize("raw", ["es-MX", "es-AR / eng", "es-US", "spa-lat"])
def test_el_latino_no_da_castellano(raw):
    from emuwarez_uploadrr.services.emu_format import has_castellano
    assert has_castellano(raw) == 0
