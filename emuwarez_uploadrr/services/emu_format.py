"""eMuwarez naming spec formatters.

Normalizes MediaInfo *and* Radarr/Sonarr raw values (which come in a different
shape) to the official eMuwarez naming spec: resolution + suffix, video codec
(AVC/HEVC/…), HDR/DV tokens, audio codec (DD+/DD/…), languages (ESP/ING/DUAL/
MULTI…), channels (5.1/7.1…) and SUBS.

All functions are pure and never raise.
"""
from __future__ import annotations

import re
from typing import Optional


# --- Language codes (ISO/name → eMuwarez) ------------------------------------
LANG_MAP: dict[str, str] = {
    "es": "ESP", "spa": "ESP", "spanish": "ESP", "castellano": "ESP", "castilian": "ESP", "es-es": "ESP",
    "es-419": "LAT", "latino": "LAT", "latam": "LAT", "latin american spanish": "LAT", "spa-lat": "LAT",
    "en": "ING", "eng": "ING", "english": "ING",
    "fr": "FRA", "fra": "FRA", "fre": "FRA", "french": "FRA",
    "de": "ALE", "deu": "ALE", "ger": "ALE", "german": "ALE",
    "ja": "JAP", "jpn": "JAP", "japanese": "JAP",
    "ko": "COR", "kor": "COR", "korean": "COR",
    "it": "ITA", "ita": "ITA", "italian": "ITA",
    "pt": "POR", "por": "POR", "portuguese": "POR",
    "ca": "CAT", "cat": "CAT", "catalan": "CAT",
    # El valenciano va aparte del catalán. MediaInfo lo da como
    # "cat-valencia" o "ca-valencia" (BCP-47), que es la única forma de
    # distinguirlo: el código ISO a secas ("cat") es el mismo para los dos.
    "val": "VAL", "valencian": "VAL", "valenciano": "VAL", "valencia": "VAL",
    "ca-valencia": "VAL", "cat-valencia": "VAL", "ca-valencia-es": "VAL",
}

_CHANNELS_MAP = {1: "Mono", 2: "2.0", 3: "3.0", 4: "3.1", 5: "5.0", 6: "5.1", 7: "6.1", 8: "7.1"}


# La resolución tal como la escribe eMuwarez. Está en la Guía
# (frontend/src/pages/GuidePage.tsx, RESOLUTION_ROWS) y un test vigila que las
# dos listas digan lo mismo.
#
# Las dos de arriba llevan el "4K"/"8K" además de la sigla, que es como se
# nombran en la práctica. Las de abajo NO llevan "SD": la resolución ya lo dice
# todo, y el token sobraba.
_RESOLUCIONES = (
    (("4320", "8k", "fuhd"), "4320p 8K FUHD"),
    (("2160", "4k", "uhd"), "2160p 4K UHD"),
    (("1080",), "1080p"),
    (("720",), "720p"),
    (("576",), "576p"),
    (("540",), "540p"),
    (("480",), "480p"),
)


def format_resolution(res: Optional[str]) -> Optional[str]:
    if not res:
        return None
    r = str(res).lower()
    for marcas, token in _RESOLUCIONES:
        if any(m in r for m in marcas):
            return token
    return str(res).strip() or None


def format_video_codec(codec: Optional[str], hint: str = "") -> Optional[str]:
    text = f"{codec or ''} {hint or ''}".lower()
    if "x264" in text:
        return "x264"
    if "x265" in text:
        return "x265"
    if "av1" in text:
        return "AV1"
    if "vp9" in text:
        return "VP9"
    if "vp8" in text:
        return "VP8"
    if "vvc" in text or "h266" in text or "h.266" in text:
        return "VVC"
    if "hevc" in text or "h265" in text or "h.265" in text:
        return "HEVC"
    if "avc" in text or "h264" in text or "h.264" in text:
        return "AVC"
    if "vc-1" in text or "vc1" in text:
        return "VC-1"
    if "mpeg" in text:
        return "MPEG"
    return (codec or "").strip() or None


def format_hdr(dynamic_range: Optional[str]) -> Optional[str]:
    """Dolby Vision / HDR token that goes BEFORE the video codec."""
    if not dynamic_range:
        return None
    t = str(dynamic_range).lower()
    dv = "dolby vision" in t or re.search(r"\bdv\b", t) is not None
    hdr = "hdr" in t or "hlg" in t or "pq" in t or "st 2086" in t or "st2086" in t
    if dv and hdr:
        return "DV HDR"
    if dv:
        return "DV"
    if hdr:
        return "HDR"
    return None


def format_audio_codec(codec: Optional[str]) -> Optional[str]:
    if not codec:
        return None
    t = str(codec).lower()
    atmos = "atmos" in t
    if "truehd" in t:
        base = "TrueHD"
    elif "mlp" in t:
        base = "MLP"
    elif "dts-hd ma" in t or "dts-hd master" in t:
        base = "DTS-HD MA"
    elif "dts-hd hra" in t or "dts-hd high" in t:
        base = "DTS-HD HRA"
    elif "dts:x" in t or "dts-x" in t:
        base = "DTS:X"
    elif "dts" in t:
        base = "DTS"
    elif "eac3" in t or "e-ac-3" in t or "e-ac3" in t or "ddp" in t or "dd+" in t or "digital plus" in t:
        base = "DD+"
    elif "ac3" in t or "ac-3" in t or ("dolby digital" in t and "plus" not in t):
        base = "DD"
    elif "aac" in t:
        base = "AAC LC" if " lc" in t or "low complexity" in t else "AAC LD" if " ld" in t or "low delay" in t else "AAC HE" if " he" in t or "high efficiency" in t else "AAC"
    elif "opus" in t:
        base = "OPUS"
    elif "flac" in t:
        base = "FLAC"
    elif "alac" in t:
        base = "ALAC"
    elif "mp3" in t:
        base = "MP3"
    elif "pcm" in t:
        base = "PCM"
    else:
        base = str(codec).strip()
    if atmos and "atmos" not in base.lower():
        base = f"{base} Atmos"
    return base


def format_channels(channels) -> Optional[str]:
    """Los canales como los escribe el tracker ("5.1"). None si no se sabe
    cuántos son: mejor no decirlo que poner un "2.0" inventado. Lo usan el
    nombre del release y el nombre de las pistas del remux."""
    if channels in (None, ""):
        return None
    s = str(channels).strip()
    # Already a layout like "5.1" / "7.1" (Radarr often reports it this way).
    if re.fullmatch(r"\d+\.\d+", s):
        return s
    if s.lower() == "mono":
        return "Mono"
    m = re.search(r"\d+", s)
    if not m:
        return None
    return _CHANNELS_MAP.get(int(m.group()))


# Lo que no es ningún idioma: sin etiquetar, sin contenido o varios a la vez.
_SIN_IDIOMA = {"", "und", "mis", "zxx", "mul"}

# Palabras del nombre de la pista que dicen el idioma cuando la etiqueta no.
_IDIOMA_POR_TITULO = (
    (("latino", "latin america", "latinoameric"), "LAT"),
    (("valenci",), "VAL"),
    (("castellano", "español", "espanol", "castilian"), "ESP"),
    (("catal",), "CAT"),
    (("english", "inglés", "ingles"), "ING"),
)


def _codigo(texto: str) -> str:
    """El código de una etiqueta ISO o BCP-47 ("spa", "es-MX", "ca-valencia")."""
    key = texto.strip().lower().replace("_", "-")
    if "valencia" in key:
        return "VAL"
    if key in LANG_MAP:
        return LANG_MAP[key]
    partes = key.split("-")
    base = LANG_MAP.get(partes[0])
    if base == "ESP":
        # El español solo es castellano sin región, con ES, o con una
        # subetiqueta privada (es-x-01, que pone MAX también al castellano).
        for sub in partes[1:]:
            if sub == "x":
                break
            if (len(sub) == 2 and sub.isalpha()) or (len(sub) == 3 and sub.isdigit()):
                return "ESP" if sub == "es" else "LAT"
        return "ESP"
    # Un BCP-47 desconocido ("pt-br", "zh-hans"): vale su idioma base, que es
    # más cierto que inventarse un código con media región dentro.
    return base or partes[0].upper()[:3] or "UND"


def resolve_language(lang: Optional[str], lang_ietf: Optional[str] = None,
                     title: Optional[str] = None) -> str:
    """El código de eMuwarez de UNA pista. Lo usan el nombre del release, las
    columnas Español/Idioma de la biblioteca y los nombres de pista del remux.

    `lang_ietf` es el BCP-47 de mkvmerge ("es-MX") y gana al ISO ("spa"), que
    no distingue el latino del castellano ni el valenciano del catalán. El
    nombre de la pista ("Latino") completa lo que la etiqueta no dice.
    "UND" si nada dice qué idioma es."""
    codigo = None
    for texto in (lang_ietf, lang):
        if texto and str(texto).strip().lower() not in _SIN_IDIOMA:
            codigo = _codigo(str(texto))
            break
    nombre = (title or "").strip().lower()
    for palabras, por_titulo in _IDIOMA_POR_TITULO:
        if not any(p in nombre for p in palabras):
            continue
        # El título solo matiza la variante (ESP→LAT, CAT→VAL) o pone el idioma
        # que falta; nunca contradice una etiqueta de otro idioma.
        if codigo is None or (codigo, por_titulo) in (("ESP", "LAT"), ("CAT", "VAL")):
            codigo = por_titulo
        break
    return codigo or "UND"


def format_language(lang: Optional[str]) -> Optional[str]:
    """El código de eMuwarez para un idioma. None si no viene nada.

    Lo que no está en LANG_MAP sale en mayúsculas y recortado a tres letras,
    que es la longitud de todos los códigos del tracker. Ese recorte se hace
    sobre la PARTE PRINCIPAL y no sobre la cadena entera: con un BCP-47 como
    "ca-valencia" cortar a ciegas daba "CA-", un token con un guion suelto que
    llegaba tal cual al nombre del torrent (visto en un pack real).
    """
    if not lang or not str(lang).strip():
        return None
    return resolve_language(lang)


def _split_languages(raw: Optional[str]) -> list[str]:
    """Radarr/Sonarr give languages as one string, e.g. 'spa / eng' or
    'jpn/spa/spa'. Return a de-duplicated, ESP-first list of eMuwarez codes."""
    if not raw:
        return []
    parts = re.split(r"[\s/,;]+", str(raw))
    langs: list[str] = []
    for p in parts:
        code = format_language(p)
        if code and code not in langs:
            langs.append(code)
    langs.sort(key=lambda c: (0 if c == "ESP" else 1))
    return langs


def has_castellano(languages: Optional[str]) -> Optional[int]:
    """1 = Castilian Spanish is present in this language list, 0 = it is not,
    None = unknown (no MediaInfo read yet, so the field is empty).

    Takes either an audio_languages or a subtitle_languages string: both come
    from the same *arr mediaInfo shape ("spa / eng"), and both are asked the
    same question, so the Español column and the season pack's subtitle rule
    can't drift apart.

    Deliberately strict about which Spanish counts: es/spa/castellano/es-ES
    are ESP, but any other region (es-419, es-MX, es-US…) or "latino" is LAT,
    so a Latin-American-only track answers 0, not 1. Radarr/Sonarr rarely tag
    the region at all (a Latin-only rip usually arrives as plain "spa"); the
    MediaInfo read (media_info_service) also looks at the track name.

    Shares _split_languages with build_audio_string on purpose: the column can
    never disagree with the ESP/DUAL/MULTI token the nomenclature builds.
    """
    if not languages or not str(languages).strip():
        return None
    return 1 if "ESP" in _split_languages(languages) else 0


# Calidad de los códecs de audio, de mejor a peor. Está documentada para el
# usuario en la Guía (frontend/src/pages/GuidePage.tsx, AUDIO_QUALITY_ROWS):
# si tocas esta lista, actualiza aquella. El frontend no puede llamar a
# Python, así que la copia es inevitable; que mienta, no.
#
# La guía los lista pero no
# los ordena, así que el orden es este: primero los que no pierden nada
# (PCM sin comprimir, luego los lossless), después los de alta resolución con
# pérdida, y al final los comprimidos corrientes.
#
# Sirve para una sola cosa: cuando un idioma aparece en dos pistas con códecs
# distintos, el nombre del release se queda solo con la mejor. "JAP TrueHD 5.1
# JAP DD 5.1" pasa a "JAP TrueHD 5.1", porque el nombre describe la calidad
# que ofrece el release, no un inventario de pistas.
_AUDIO_CODEC_QUALITY = (
    "PCM",          # sin comprimir
    "MLP",          # sin pérdida (la base de TrueHD)
    "TrueHD",       # sin pérdida
    "DTS-HD MA",    # sin pérdida
    "FLAC",         # sin pérdida
    "ALAC",         # sin pérdida
    "DTS:X",        # objetos, sobre núcleo DTS
    "DTS-HD HRA",   # alta resolución, con pérdida
    "DD+",          # E-AC3
    "DTS",
    "DD",           # AC3
    "AAC LC",
    "AAC HE",
    "AAC LD",
    "AAC",
    "OPUS",
    "MP3",
)


def audio_codec_quality(codec: Optional[str]) -> tuple[int, int]:
    """Posición del códec en el ranking de calidad. Menor es mejor.

    Devuelve (códec base, Atmos), para que entre dos pistas del MISMO códec
    gane la que trae Atmos: es una capa por encima de TrueHD o DD+, no un
    códec aparte, y audio_codec() lo pega al nombre ("TrueHD Atmos").

    Un códec que no esté en la lista se va al final: preferir lo conocido es
    más seguro que colar algo sin clasificar por delante.
    """
    text = (codec or "").strip()
    atmos = 0 if "atmos" in text.lower() else 1
    base = re.sub(r"\s*atmos\s*", " ", text, flags=re.I).strip()
    try:
        rank = _AUDIO_CODEC_QUALITY.index(base)
    except ValueError:
        rank = len(_AUDIO_CODEC_QUALITY)
    return (rank, atmos)


def audio_track_quality(codec: Optional[str], channels: Optional[str]) -> tuple:
    """Calidad de una pista entera: códec primero, canales para desempatar.

    Con el mismo códec, más canales es mejor: entre "ESP DD 5.1" y
    "ESP DD 2.0" el release ofrece 5.1. Sin esto el desempate lo decidía el
    orden en que mkvmerge listara las pistas, que no significa nada.
    """
    n = re.search(r"\d+", str(channels or ""))
    count = int(n.group()) if n else 0
    return audio_codec_quality(codec) + (-count,)


def build_audio_string(
    audio_codec: Optional[str],
    audio_languages: Optional[str],
    channels=None,
) -> Optional[str]:
    """Build the audio segment per the eMuwarez spec, in the order
    '{idioma} {códec} {canales}'. Applies the DUAL/MULTI rules:
      - 2 langs including ESP+ING (same codec) → 'DUAL {codec} {channels}'
      - 4+ langs → 'MULTI {codec} {channels}'
      - 2-3 langs → 'ESP-ING {codec} {channels}'
      - 1 lang → '{lang} {codec} {channels}'
    We only have aggregate codec/channels (not per-track) from Radarr/Sonarr,
    so per-track V.O./VOSE/comment distinctions are approximated.
    """
    codec = format_audio_codec(audio_codec)
    ch = format_channels(channels)
    langs = _split_languages(audio_languages)

    if not langs:
        lang_token = None
    elif len(langs) >= 4:
        lang_token = "MULTI"
    elif len(langs) == 2 and "ESP" in langs and "ING" in langs:
        lang_token = "DUAL"
    else:
        lang_token = "-".join(langs)

    parts = [p for p in (lang_token, codec, ch) if p]
    return " ".join(parts) or None
