"""MediaInfo probing: the raw technical read of a file.

Moved out of legacy.py, which was the original monolith. The pieces of "what
is actually inside this file" that the report in media_info_service is built
from: resolution, video codec, HDR, audio codecs and channels, duration, and
the source estimates. Deliberately free of terminal I/O, so it can run inside
an HTTP request.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from ..constants import SOURCE_PATTERNS
from .emu_format import format_channels


def run_mediainfo_json(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["mediainfo", "--Output=JSON", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "mediainfo falló")
    return json.loads(proc.stdout)


def media_tracks(info: dict[str, Any]) -> list[dict[str, Any]]:
    return info.get("media", {}).get("track", []) or []


def first_track(info: dict[str, Any], track_type: str) -> dict[str, Any]:
    return next((x for x in media_tracks(info) if x.get("@type") == track_type), {})


# Escalones de resolución: (anchura mínima, altura mínima, código). El código
# es el vocabulario canónico de la aplicación ("1080p", "480p"), el que se
# guarda en la biblioteca y el que entiende el contrato de subida.
#
# Se mira también la ANCHURA, no solo la altura: en cinemascope un 1080p real
# puede venir como 1920x800 por recorte vertical.
_ESCALONES_RESOLUCION: list[tuple[int, int, str]] = [
    (7600, 4000, "4320p"),
    (3800, 2000, "2160p"),
    (1900, 1000, "1080p"),
    (1200, 700, "720p"),
    (0, 560, "576p"),
    (0, 520, "540p"),
]


def resolution_code(width: int, height: int) -> Optional[str]:
    """El código canónico para unas dimensiones: "1080p", "480p"…

    None si no hay dimensiones. Es lo que se guarda en la biblioteca y lo que
    compara la regla del pack de temporada."""
    for min_w, min_h, codigo in _ESCALONES_RESOLUCION:
        if (min_w and width >= min_w) or (min_h and height >= min_h):
            return codigo
    if width or height:
        return "480p"
    return None


def video_resolution_code(video: dict[str, Any]) -> Optional[str]:
    """resolution_code de la pista de vídeo de MediaInfo."""
    def number(value: Any) -> int:
        match = re.search(r"\d+", str(value or "0"))
        return int(match.group()) if match else 0

    return resolution_code(number(video.get("Width") or video.get("Stored_Width")),
                           number(video.get("Height") or video.get("Stored_Height")))


def _detect_source_by_name(path: Path) -> Optional[str]:
    """Source from the file/folder NAME only (most reliable). None if the name
    has no source keyword."""
    text = " ".join([path.name, path.parent.name, path.parent.parent.name])
    for pattern, value in SOURCE_PATTERNS:
        if pattern.search(text):
            return value
    return None


# Lossless audio → the file comes from a disc (streaming services never ship
# lossless), so it's BluRay or a BDRemux, never WEB-DL.
_LOSSLESS_AUDIO = ("dts-hd ma", "dts-hd hra", "dts:x", "truehd", "pcm", "lpcm", "flac", "mlp")
# Size (GiB) at/above which an untouched-disc BDRemux is assumed, per resolution.
_REMUX_MIN_GB = {"2160p": 40.0, "1080p": 20.0, "720p": 8.0}


# Encoder CLI tags left behind by a hand re-encode (scene WEBRip or a
# BluRay/MicroHD encode). Their absence is the strongest signal available for
# an untouched, unmodified release: streaming platforms and disc authoring
# tools never leave an x264/x265/x266/AV1 settings dump — only a manual CLI
# encode does. It can't tell a WEBRip re-encode apart from a BluRay/MicroHD
# re-encode (both leave the same fingerprint), only "re-encoded" from "not".
_REENCODE_LIBS = ("x264", "x265", "x266", "svt-av1", "aomenc", "rav1e")


def looks_reencoded(video: Optional[dict]) -> bool:
    """Whether the video track carries a hand-encoder fingerprint (x264/x265
    CLI settings dump), as opposed to an untouched platform/disc stream."""
    if not video:
        return False
    if video.get("Encoded_Library_Settings"):
        return True
    lib = f"{video.get('Encoded_Library') or ''} {video.get('Writing_library') or ''}".lower()
    return any(tag in lib for tag in _REENCODE_LIBS)


def heuristic_source(audio_codecs: list[str], size_gb: float, resolution: Optional[str]) -> Optional[str]:
    """Best-effort source guess from MediaInfo, used ONLY when the name has no
    source keyword. Returns None if it can't decide (caller keeps the default).

    - Lossless audio (DTS-HD MA / TrueHD / PCM…) → disc: BDRemux if the size is
      near-untouched, else BluRay.
    - DD+/E-AC3 as audio → typical of streaming → WEB-DL.
    """
    codecs = " ".join(c or "" for c in audio_codecs).lower()
    if any(k in codecs for k in _LOSSLESS_AUDIO):
        thr = _REMUX_MIN_GB.get(resolution or "", 20.0)
        return "BDRemux" if size_gb >= thr else "BluRay"
    if "dd+" in codecs or "e-ac-3" in codecs or "eac3" in codecs:
        return "WEB-DL"
    return None


# Overall bitrate (Mbps) thresholds per resolution: (BDRemux, BluRay, WEB-DL).
# Below the WEB-DL threshold with lossy audio → HDTV. Derived from the size
# thresholds above assuming a ~2h runtime, but bitrate normalizes for length.
_BITRATE_MBPS = {
    "2160p": (45.0, 16.0, 8.0),
    "1080p": (22.0, 9.0, 4.0),
    "720p":  (9.0, 4.0, 2.0),
}
_DEFAULT_BITRATE_MBPS = (22.0, 9.0, 4.0)


def bitrate_thresholds(resolution: Optional[str]) -> tuple[float, float, float]:
    """(remux, bluray, webdl) Mbps thresholds `estimate_source_from_bitrate`
    uses for this resolution — exposed for the UI's bitrate reference table."""
    return _BITRATE_MBPS.get(resolution or "", _DEFAULT_BITRATE_MBPS)


def estimate_source_from_bitrate(
    size_bytes: Optional[int], duration_s: Optional[float],
    audio_codecs: list[str], resolution: Optional[str],
    video: Optional[dict] = None,
) -> Optional[str]:
    """Source guess from the file's overall bitrate (size / duration) + audio,
    used ONLY when the name/Radarr give no source. Bitrate normalizes for
    content length, unlike raw size. Returns None if duration is unknown.

    - Lossless audio → disc: BDRemux if bitrate is near-untouched, else BluRay.
    - Lossy audio, NOT hand re-encoded (no x264/x265 fingerprint) → confidently
      WEB-DL: an untouched platform rip, regardless of its bitrate.
    - Lossy audio, hand re-encoded (or unknown) → by definition NOT a WEB-DL
      (that name means untouched), so never returned here. At disc-tier
      bitrate (≥ the BluRay threshold — streaming 1080p/2160p rarely gets
      that high) it's almost certainly a hand encode of a disc: MHD. Below
      that it's WEBRip-or-HDTV by bitrate — can't be told apart from a
      MicroHD re-encode this way, both leave an identical encoder fingerprint.
    """
    if not size_bytes or not duration_s or duration_s <= 0:
        return None
    mbps = (size_bytes * 8) / duration_s / 1_000_000
    remux_thr, bluray_thr, webdl_thr = _BITRATE_MBPS.get(resolution or "", _DEFAULT_BITRATE_MBPS)
    codecs = " ".join(c or "" for c in audio_codecs).lower()
    if any(k in codecs for k in _LOSSLESS_AUDIO):
        return "BDRemux" if mbps >= remux_thr else "BluRay"
    if video is not None and not looks_reencoded(video):
        return "WEB-DL"
    if mbps >= bluray_thr:
        return "MHD"
    return "WEBRip" if mbps >= webdl_thr else "HDTV"


def detect_video_codec(video: dict[str, Any], path: Path) -> str:
    # Real MediaInfo encoder fields ONLY — never the filename. The guide
    # itself draws a hard line between "H264 → AVC" (generic codec) and
    # "x264 → x264" (the specific hand encoder was actually used), which is
    # a claim about the real video stream, not about what some past release
    # happened to call itself. Trusting the filename here let a file with
    # "x264" baked into its (possibly already-renamed) name keep reporting
    # x264 forever, even once MediaInfo's own Format/encoder fields showed
    # plain, untouched AVC/HEVC with no encoder fingerprint at all.
    text = f"{video.get('Writing_library','')} {video.get('Encoded_Library','')}".lower()
    fmt = str(video.get("Format") or video.get("CodecID") or "").lower()

    if "x264" in text:
        return "x264"
    if "x265" in text:
        return "x265"
    if "av1" in fmt:
        return "AV1"
    if "vp9" in fmt:
        return "VP9"
    if "vp8" in fmt:
        return "VP8"
    if "vvc" in fmt or "h.266" in fmt or "h266" in fmt:
        return "VVC"
    if "hevc" in fmt or "h.265" in fmt or "h265" in fmt:
        return "HEVC"
    if "avc" in fmt or "h.264" in fmt or "h264" in fmt:
        return "AVC"
    if "vc-1" in fmt or "vc1" in fmt:
        return "VC-1"
    if "mpeg" in fmt:
        return "MPEG"
    return str(video.get("Format") or "AVC").strip()


def detect_hdr(video: dict[str, Any]) -> list[str]:
    text = " ".join(str(video.get(k) or "") for k in ("HDR_Format", "HDR_Format_String", "Format_Profile")).lower()
    dv = bool("dolby vision" in text or re.search(r"\bdv\b", text))
    hdr = "hdr" in text or "smpte st 2086" in text or "hlg" in text
    if dv and hdr:
        return ["DV", "HDR"]
    if dv:
        return ["DV"]
    if hdr:
        return ["HDR"]
    return []


def audio_codec(audio: dict[str, Any]) -> str:
    text = " ".join(
        str(audio.get(k) or "")
        for k in ("Format", "Format_Profile", "Format_Commercial_IfAny", "Format_AdditionalFeatures")
    ).lower()

    if "dts-hd master" in text or "dts-hd ma" in text:
        base = "DTS-HD MA"
    elif "dts-hd high" in text or "dts-hd hra" in text:
        base = "DTS-HD HRA"
    elif "dts:x" in text:
        base = "DTS:X"
    elif "truehd" in text:
        base = "TrueHD"
    elif "mlp" in text:
        base = "MLP"
    elif "e-ac-3" in text or "eac3" in text:
        base = "DD+"
    elif "ac-3" in text or "ac3" in text:
        base = "DD"
    elif "dts" in text:
        base = "DTS"
    elif "aac" in text:
        base = "AAC LC" if "lc" in text or "low complexity" in text else "AAC HE" if "he" in text else "AAC"
    elif "opus" in text:
        base = "OPUS"
    elif "flac" in text:
        base = "FLAC"
    elif "alac" in text:
        base = "ALAC"
    elif "mp3" in text or "mpeg audio" in text:
        base = "MP3"
    elif "pcm" in text:
        base = "PCM"
    else:
        base = str(audio.get("Format") or "DD").strip()

    if "atmos" in text and "Atmos" not in base:
        base += " Atmos"
    return base


def audio_channels(audio: dict[str, Any]) -> Optional[str]:
    """"5.1", "2.0"… o None si MediaInfo no dice un número de canales conocido."""
    return format_channels(audio.get("Channel_s_") or audio.get("Channels"))


def duration_seconds(general: dict[str, Any]) -> Optional[float]:
    """Content duration in seconds from a MediaInfo General track."""
    try:
        return float(general.get("Duration"))
    except (TypeError, ValueError):
        return None
