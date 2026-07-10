"""Real MediaInfo invocation for the web nomenclature-apply flow (Phase 6B).

`legacy.py` already has working MediaInfo parsing code
(`run_mediainfo_json`/`read_media_info`, shell-out to `mediainfo
--Output=JSON`) but it's part of the interactive legacy CLI: on an
unrecognized audio language, `map_audio_language()` calls `prompt()`,
which blocks on `input()`. That's fine for a terminal session, fatal for
a web request handler — a single unmapped language track would hang the
server process indefinitely.

This module reuses every *pure* piece of that parsing (run_mediainfo_json,
media_tracks/first_track, detect_video_codec, audio_codec, LANG_MAP) but
replaces the interactive language lookup with a plain non-interactive
fallback. It never raises: a missing `mediainfo` binary or any parse
failure returns None, letting callers fall back to the cheaper
Radarr/Sonarr-sourced mediaInfo from Phase 6A instead of failing the
whole "Adaptar nomenclatura" flow.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from .. import legacy

logger = logging.getLogger(__name__)


def mediainfo_available() -> bool:
    """Whether the `mediainfo` binary is on PATH. The dev/test sandbox for
    this project doesn't have it installed — only the Docker homelab image
    does (via apt) — so callers must treat its absence as a normal,
    expected condition, not an error."""
    return shutil.which("mediainfo") is not None


def _map_audio_language_noninteractive(value: str) -> str:
    key = (value or "").strip().lower()
    if key in legacy.LANG_MAP:
        return legacy.LANG_MAP[key]
    # No prompt() here (unlike legacy.map_audio_language) — an unmapped
    # language just falls back to a 3-letter best-effort code so the web
    # request always completes.
    return (value or "UND").strip().upper()[:3] or "UND"


def read_media_info_summary(path: str) -> Optional[dict]:
    """Invoke real MediaInfo against `path` and return a flat summary
    compatible with library_items' video_codec/audio_codec/audio_languages/
    subtitle_languages columns (Phase 6A), or None if unavailable/failed.

    Never raises."""
    if not path or not mediainfo_available():
        return None
    try:
        file_path = Path(path)
        if not file_path.is_file():
            return None
        info = legacy.run_mediainfo_json(file_path)
        video = legacy.first_track(info, "Video")

        audio_langs: list[str] = []
        audio_codecs: list[str] = []
        for track in legacy.media_tracks(info):
            if track.get("@type") != "Audio":
                continue
            lang = _map_audio_language_noninteractive(
                track.get("Language") or track.get("Language_String") or ""
            )
            if lang not in audio_langs:
                audio_langs.append(lang)
            codec = legacy.audio_codec(track)
            if codec not in audio_codecs:
                audio_codecs.append(codec)

        subtitle_langs: list[str] = []
        for track in legacy.media_tracks(info):
            if track.get("@type") != "Text":
                continue
            lang = _map_audio_language_noninteractive(
                track.get("Language") or track.get("Language_String") or ""
            )
            if lang not in subtitle_langs:
                subtitle_langs.append(lang)

        return {
            "video_codec": legacy.detect_video_codec(video, file_path) if video else None,
            "audio_codec": " / ".join(audio_codecs) or None,
            "audio_languages": " / ".join(audio_langs) or None,
            "subtitle_languages": " / ".join(subtitle_langs) or None,
        }
    except Exception:
        logger.warning("MediaInfo falló para %s", path, exc_info=True)
        return None


def build_mediainfo_report(path: str) -> dict:
    """Run MediaInfo on the actual file and return, for each field, the raw
    MediaInfo value alongside the value that goes to eMuwarez. Never raises;
    returns {available: False, message} when the binary/file isn't there.

    Shape: {available: bool, message: str|None, rows: [{field, mediainfo, emu}],
            audio_summary: str|None}
    """
    from . import emu_format

    if not path:
        return {"available": False, "message": "El item no tiene ruta de archivo.", "rows": []}
    if not mediainfo_available():
        return {"available": False, "message": "El binario `mediainfo` no está instalado en este entorno.", "rows": []}
    p = Path(path)
    if not p.is_file():
        return {"available": False, "message": f"Archivo no accesible desde la app: {path}", "rows": []}
    try:
        info = legacy.run_mediainfo_json(p)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": f"MediaInfo falló: {exc}", "rows": []}

    video = legacy.first_track(info, "Video")
    rows: list[dict] = []

    def add(field: str, mi, emu):
        rows.append({"field": field, "mediainfo": str(mi) if mi not in (None, "") else "—",
                     "emu": str(emu) if emu not in (None, "") else "—"})

    # Resolution
    w = video.get("Width") or video.get("Stored_Width")
    h = video.get("Height") or video.get("Stored_Height")
    add("Resolución", f"{w}x{h}" if w and h else None, legacy.map_resolution(video) if video else None)
    # Source (detected from the filename, not from MediaInfo)
    add("Source", p.name, legacy.detect_source(p))
    # HDR / Dolby Vision
    hdr = legacy.detect_hdr(video) if video else []
    add("HDR/DV", video.get("HDR_Format") or video.get("HDR_Format_String"), " ".join(hdr) or None)
    # Video codec
    add("Códec de vídeo", video.get("Format") or video.get("CodecID"),
        legacy.detect_video_codec(video, p) if video else None)

    # Audio tracks (one row each) + combined eMuwarez segment
    audio_tracks = [t for t in legacy.media_tracks(info) if t.get("@type") == "Audio"]
    codecs, langs, channels = [], [], []
    for i, tr in enumerate(audio_tracks, 1):
        raw_lang = tr.get("Language") or tr.get("Language_String") or ""
        lang = emu_format.format_language(raw_lang) or "UND"
        codec = legacy.audio_codec(tr)
        ch = legacy.audio_channels(tr)
        codecs.append(codec)
        channels.append(ch)
        if lang not in langs:
            langs.append(lang)
        mi = " ".join(x for x in (tr.get("Format"), raw_lang or "?", tr.get("Channel_s_") or tr.get("Channels")) if x)
        add(f"Audio {i}", mi, f"{lang} {codec} {ch}")

    audio_summary = None
    if audio_tracks:
        same = len({(c, ch) for c, ch in zip(codecs, channels)}) == 1
        if same and len(langs) == 2 and "ESP" in langs and "ING" in langs:
            audio_summary = f"DUAL {codecs[0]} {channels[0]}"
        elif same and len(langs) >= 4:
            audio_summary = f"MULTI {codecs[0]} {channels[0]}"
        else:
            audio_summary = " ".join(f"{l} {c} {ch}" for l, c, ch in zip(langs, codecs, channels))
        add("Audio (eMuwarez)", f"{len(audio_tracks)} pista(s)", audio_summary)

    # Subtitles
    sub_tracks = [t for t in legacy.media_tracks(info) if t.get("@type") == "Text"]
    sub_langs = ", ".join(
        emu_format.format_language(t.get("Language") or t.get("Language_String") or "") or "UND"
        for t in sub_tracks
    )
    add("Subtítulos", sub_langs or None, "SUBS" if sub_tracks else None)

    return {"available": True, "message": None, "rows": rows, "audio_summary": audio_summary}
