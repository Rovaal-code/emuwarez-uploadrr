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
    "es-419": "LAT", "latino": "LAT", "latin american spanish": "LAT", "spa-lat": "LAT",
    "en": "ING", "eng": "ING", "english": "ING",
    "fr": "FRA", "fra": "FRA", "fre": "FRA", "french": "FRA",
    "de": "ALE", "deu": "ALE", "ger": "ALE", "german": "ALE",
    "ja": "JAP", "jpn": "JAP", "japanese": "JAP",
    "ko": "COR", "kor": "COR", "korean": "COR",
    "it": "ITA", "ita": "ITA", "italian": "ITA",
    "pt": "POR", "por": "POR", "portuguese": "POR",
    "ca": "CAT", "cat": "CAT", "catalan": "CAT",
}

_CHANNELS_MAP = {1: "Mono", 2: "2.0", 3: "3.0", 4: "3.1", 5: "5.0", 6: "5.1", 7: "6.1", 8: "7.1"}


def format_resolution(res: Optional[str]) -> Optional[str]:
    if not res:
        return None
    r = str(res).lower()
    if "4320" in r or "8k" in r or "fuhd" in r:
        return "4320p FUHD"
    if "2160" in r or "4k" in r or "uhd" in r:
        return "2160p UHD"
    if "1080" in r:
        return "1080p"
    if "720" in r:
        return "720p"
    if "576" in r:
        return "576p SD"
    if "540" in r:
        return "540p SD"
    if "480" in r:
        return "480p SD"
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
    if channels in (None, ""):
        return None
    s = str(channels).strip()
    # Already a layout like "5.1" / "7.1" (Radarr often reports it this way).
    if re.fullmatch(r"\d+\.\d+", s):
        return s
    m = re.search(r"\d+", s)
    if not m:
        return None
    return _CHANNELS_MAP.get(int(m.group()), s)


def format_language(lang: Optional[str]) -> Optional[str]:
    if not lang:
        return None
    key = str(lang).strip().lower()
    if key in LANG_MAP:
        return LANG_MAP[key]
    return str(lang).strip().upper()[:3] or None


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
