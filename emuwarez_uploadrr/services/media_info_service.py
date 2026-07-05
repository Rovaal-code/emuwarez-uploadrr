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
