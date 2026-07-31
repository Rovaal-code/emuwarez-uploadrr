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

# Cache of build_mediainfo_report() results, keyed by resolved path →
# ((path, mtime, size), report). Avoids re-reading MediaInfo of the same file
# (slow over remote mounts) within the upload wizard / nomenclature flow.
_REPORT_CACHE: dict[str, tuple[tuple, dict]] = {}
_REPORT_CACHE_MAX = 256


def source_engine_enabled() -> bool:
    """Whether the Internal Source Tool (services/source_engine) may run.

    Off by default: the tool analyses the real file with FFprobe/MKVToolNix
    and is still in development, so it stays opt-in from Ajustes -> Otros
    rather than deciding sources for everyone out of the box.
    """
    from ..database import connect
    try:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'source_engine.enabled'"
            ).fetchone()
        finally:
            conn.close()
    except Exception:                      # nunca romper una lectura de MediaInfo por esto
        return False
    return (row["value"] if row else "") == "true"


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
    from .path_mapping import resolve_local_path
    path = resolve_local_path(path)
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


def build_mediainfo_report(path: str, radarr_source: str | None = None) -> dict:
    """Run MediaInfo on the actual file and return, for each field, the raw
    MediaInfo value alongside the value that goes to eMuwarez. Never raises;
    returns {available: False, message} when the binary/file isn't there.

    `radarr_source` is Radarr/Sonarr's own reported source (library_items.
    source) — needed only for the Source row's eMuwarez column, which follows
    the same name → Radarr/Sonarr → MediaInfo-bitrate priority used for the
    actually-applied nomenclature (see nomenclature.py::_infer_source_from_item).

    Shape: {available: bool, message: str|None, rows: [{field, mediainfo, emu}],
            audio_summary: str|None}
    """
    from . import emu_format
    from .path_mapping import resolve_local_path

    if not path:
        return {"available": False, "message": "El item no tiene ruta de archivo.", "rows": []}
    path = resolve_local_path(path)
    if not mediainfo_available():
        return {"available": False, "message": "El binario `mediainfo` no está instalado en este entorno.", "rows": []}
    p = Path(path)
    if not p.is_file():
        return {"available": False, "message": f"Archivo no accesible desde la app: {path}", "rows": []}

    _engine_on = source_engine_enabled()

    # MediaInfo over a remote (SSHFS/NFS) mount is slow, and the upload wizard
    # reads the same file twice (once to generate the nomenclature, once for
    # the "Ver MediaInfo" button). Cache the report per file (invalidated by
    # mtime+size, or by radarr_source changing) so the second read is instant.
    try:
        st = p.stat()
        # `_engine_on` entra en la clave: sin él, apagar la herramienta no se
        # notaría hasta que el fichero cambiase de tamaño o de fecha.
        cache_key = (str(p), int(st.st_mtime), int(st.st_size), radarr_source, _engine_on)
        cached = _REPORT_CACHE.get(str(p))
        if cached and cached[0] == cache_key:
            return cached[1]
    except OSError:
        cache_key = None

    try:
        info = legacy.run_mediainfo_json(p)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": f"MediaInfo falló: {exc}", "rows": []}

    video = legacy.first_track(info, "Video")
    rows: list[dict] = []

    def add(field: str, mi, emu, help_text: str | None = None):
        rows.append({"field": field, "mediainfo": str(mi) if mi not in (None, "") else "—",
                     "emu": str(emu) if emu not in (None, "") else "—", "help": help_text})

    # Resolution
    w = video.get("Width") or video.get("Stored_Width")
    h = video.get("Height") or video.get("Stored_Height")
    resolution = legacy.map_resolution(video) if video else None
    add("Resolución", f"{w}x{h}" if w and h else None, resolution)
    # Source: MediaInfo doesn't literally report a "source" field.
    # - "MediaInfo" column: always the bitrate/audio tool's own estimate,
    #   deliberately ignoring the name/Radarr — what the file itself suggests.
    # - "eMuwarez" column: the value that would actually be applied, following
    #   the same priority as the real nomenclature (nombre del archivo →
    #   Radarr/Sonarr → MediaInfo bitrate tool — see
    #   nomenclature.py::_infer_source_from_item).
    _audio_codecs = [legacy.audio_codec(t) for t in legacy.media_tracks(info) if t.get("@type") == "Audio"]
    _general = legacy.first_track(info, "General")
    _duration = legacy.duration_seconds(_general)
    _name_source = legacy._detect_source_by_name(p)
    try:
        _size_bytes = p.stat().st_size
    except OSError:
        _size_bytes = 0

    # Internal Source Tool (services/source_engine) — multi-tool (MediaInfo +
    # FFprobe + MKVToolNix), bitrate normalized by resolution/fps, always
    # scores all 9 eMuwarez source candidates. Falls back to the old simple
    # bitrate/audio heuristic only if the engine couldn't run at all (missing
    # tools, unreadable file) so this row never goes empty.
    if _engine_on:
        from . import source_engine
        _engine_result = source_engine.analyze_for_app(str(p), radarr_source=radarr_source)
        _engine_source = source_engine.winning_app_source(_engine_result)
    else:
        _engine_result = _engine_source = None
    if _engine_source is not None:
        _bitrate_source = _engine_source
    else:
        _bitrate_source = legacy.estimate_source_from_bitrate(_size_bytes, _duration, _audio_codecs, resolution, video=video)
        if _bitrate_source is None:
            _bitrate_source = legacy.heuristic_source(_audio_codecs, _size_bytes / (1024 ** 3), resolution)
    _final_source = _name_source or radarr_source or _bitrate_source
    # Whether the video has a hand-encoder fingerprint — used by the bitrate
    # reference table (below) to explain why a given bitrate range does or
    # doesn't confirm WEB-DL, and by source_comparison's mediainfo_confirmed.
    _reencoded = legacy.looks_reencoded(video)
    add("Source", _bitrate_source, _final_source,
        help_text="MediaInfo: se calcula a través de una tool interna de la aplicación (analiza audio y "
                   "bitrate del archivo), sin mirar el nombre del archivo. "
                   "eMuwarez: nombre del archivo → Radarr/Sonarr → tool interna de la aplicación.")

    # Bitrate reference table (Ver MediaInfo's "MediaInfo (bitrate)" link):
    # every eMuwarez source code and the bitrate range that maps to it at
    # THIS file's resolution, so the user can see where their file lands and
    # why. Full BluRay/MHD are name-only — the tool can't tell them apart
    # from BDRemux/BluRay or from a WEBRip by bitrate alone.
    _remux_thr, _bluray_thr, _webdl_thr = legacy.bitrate_thresholds(resolution)
    def _mbps(v: float) -> str:
        return f"{v:g}"
    bitrate_table = [
        {"source": "Full BluRay", "bitrate": "—",
         "comment": "Solo se detecta por el nombre del archivo; no hay heurística de bitrate que lo distinga de un BDRemux/BluRay normal."},
        {"source": "BDRemux", "bitrate": f"≥ {_mbps(_remux_thr)} Mbps, con audio sin pérdida (DTS-HD MA, TrueHD, PCM…)",
         "comment": "Bitrate cercano al disco original, prácticamente sin recomprimir."},
        {"source": "BluRay", "bitrate": f"< {_mbps(_remux_thr)} Mbps, con audio sin pérdida",
         "comment": "Audio sin pérdida pero bitrate menor que un remux: recompresión del disco."},
        {"source": "MHD", "bitrate": "—",
         "comment": "Solo se detecta por el nombre del archivo (MicroHD); con audio normal y re-encode es indistinguible de un WEBRip por bitrate."},
        {"source": "WEB-DL", "bitrate": f"≥ {_mbps(_webdl_thr)} Mbps con audio con pérdida, o cualquier bitrate si el archivo NO está re-encodeado",
         "comment": "Si el archivo no está re-encodeado y el bitrate cae aquí, es un WEB-DL confirmado (rip directo de la plataforma)."},
        {"source": "WEBRip", "bitrate": f"≥ {_mbps(_webdl_thr)} Mbps con audio con pérdida, con el archivo re-encodeado",
         "comment": "Mismo rango que un WEB-DL re-encodeado, indistinguible por bitrate de un WEB-DL recomprimido o de un MicroHD."},
        {"source": "HDTV", "bitrate": f"< {_mbps(_webdl_thr)} Mbps con audio con pérdida",
         "comment": "Bitrate bajo, típico de una captura de TV o una recompresión agresiva."},
    ]

    # Three-way source cross-check (name / MediaInfo bitrate tool), used by
    # the nomenclature field editor to warn when Radarr/Sonarr's own source
    # disagrees with what the file itself suggests — Radarr/Sonarr wins
    # silently otherwise whenever it happens to report *a* valid-looking
    # source, even a wrong one (e.g. "BluRay" for an actual MicroHD rip).
    source_signals = {
        "from_name": _name_source,
        # Con la herramienta apagada su columna sale vacía y queda fuera de la
        # comparación (ver source_assistant), pero _bitrate_source se sigue
        # calculando arriba: es el último recurso de _final_source cuando ni
        # el nombre ni Radarr/Sonarr dicen nada, y sin él esos ficheros se
        # quedarían sin source ninguno.
        "from_mediainfo_bitrate": _bitrate_source if _engine_on else None,
        "mediainfo_reencoded": _reencoded,
        "bitrate_table": bitrate_table,
        # Full Internal Source Tool result (9-candidate ranking, evidence,
        # explanation) — None when the engine couldn't run at all.
        "engine": _engine_result,
    }
    # HDR / Dolby Vision
    hdr = legacy.detect_hdr(video) if video else []
    add("HDR/DV", video.get("HDR_Format") or video.get("HDR_Format_String"), " ".join(hdr) or None)
    # Video codec — when the real encoder fingerprint says x264/x265 (the
    # eMuwarez value below), the raw MediaInfo Format alone (AVC/HEVC, the
    # generic codec family) looks contradictory next to it. Showing "AVC
    # (x264)" here makes both true facts visible at once instead of one
    # column apparently disagreeing with the other.
    _video_codec_label = legacy.detect_video_codec(video, p) if video else None
    _mi_video_codec = video.get("Format") or video.get("CodecID")
    if _mi_video_codec and _video_codec_label in ("x264", "x265") and _video_codec_label not in str(_mi_video_codec).lower():
        _mi_video_codec = f"{_mi_video_codec} ({_video_codec_label})"
    add("Códec de vídeo", _mi_video_codec, _video_codec_label)

    # Audio tracks (one row each) + combined eMuwarez segment
    audio_tracks = [t for t in legacy.media_tracks(info) if t.get("@type") == "Audio"]
    codecs, langs, channels = [], [], []
    # One "IDIOMA CÓDEC CANALES" per real track, in track order. Built here
    # rather than zipped together afterwards from the three parallel lists,
    # because `langs` is de-duplicated (it has to be: the DUAL/MULTI rules
    # below count DISTINCT languages) while codecs/channels are not. Zipping
    # them shifted every entry after the first repeated language onto the wrong
    # codec and silently dropped the last track — a release with two Japanese
    # tracks came out as "JAP TrueHD 5.1 CAT DD 5.1 ESP DD+ 2.0", giving
    # Catalan the second Japanese track's codec and losing the fourth track
    # entirely. And this string is not just for show: it goes into the release
    # name (services/source_assistant.py's audio_summary).
    # Grouped by (codec, channels): tracks that share both are ONE entry whose
    # languages join with a hyphen, which is what the spec asks for — see the
    # guide's own "ESP-CAT TrueHD 5.1". Listing them separately would claim two
    # audio tracks where the release states one shared one.
    # Un idioma que viene en varias pistas se queda con UNA sola: la de mejor
    # códec (emu_format.audio_codec_quality). El nombre del release dice qué
    # calidad ofrece, no cuántas pistas trae, así que "JAP TrueHD 5.1 JAP DD
    # 5.1" es "JAP TrueHD 5.1": quien lo lea busca lo mejor que va a oír.
    best_by_lang: dict[str, tuple[tuple[int, int], str, str]] = {}
    for i, tr in enumerate(audio_tracks, 1):
        raw_lang = tr.get("Language") or tr.get("Language_String") or ""
        lang = emu_format.format_language(raw_lang) or "UND"
        codec = legacy.audio_codec(tr)
        ch = legacy.audio_channels(tr)
        codecs.append(codec)
        channels.append(ch)
        if lang not in langs:
            langs.append(lang)
        quality = emu_format.audio_track_quality(codec, ch)
        previous = best_by_lang.get(lang)
        if previous is None or quality < previous[0]:
            best_by_lang[lang] = (quality, codec, ch)
        mi = " ".join(x for x in (tr.get("Format"), raw_lang or "?", tr.get("Channel_s_") or tr.get("Channels")) if x)
        # La ficha técnica SÍ sigue enseñando todas las pistas, una por fila:
        # ahí lo que interesa es qué hay dentro del archivo de verdad. Lo que
        # se recorta es solo el segmento que va al nombre.
        add(f"Audio {i}", mi, f"{lang} {codec} {ch}")

    groups: dict[tuple[str, str], list[str]] = {}
    for lang in langs:
        chosen = best_by_lang.get(lang)
        if not chosen:
            continue
        groups.setdefault((chosen[1], chosen[2]), []).append(lang)

    audio_summary = None
    if audio_tracks:
        # Same DUAL/MULTI rules as emu_format.build_audio_string, but applied
        # per group instead of once over every track: they describe ONE audio
        # entry, so a file whose tracks don't all share a codec still gets them
        # on the entries that do.
        entries = []
        for (codec, ch), group_langs in groups.items():
            ordered = sorted(group_langs, key=lambda c: (0 if c == "ESP" else 1))
            if len(ordered) == 2 and "ESP" in ordered and "ING" in ordered:
                token = "DUAL"
            elif len(ordered) >= 4:
                token = "MULTI"
            else:
                token = "-".join(ordered)
            entries.append(" ".join(x for x in (token, codec, ch) if x))
        audio_summary = " ".join(entries)
        add("Audio (eMuwarez)", f"{len(audio_tracks)} pista(s)", audio_summary)

    # Subtitles
    sub_tracks = [t for t in legacy.media_tracks(info) if t.get("@type") == "Text"]
    sub_langs = ", ".join(
        emu_format.format_language(t.get("Language") or t.get("Language_String") or "") or "UND"
        for t in sub_tracks
    )
    add("Subtítulos", sub_langs or None, "SUBS" if sub_tracks else None)

    report = {"available": True, "message": None, "rows": rows, "audio_summary": audio_summary,
               "source_signals": source_signals}
    if cache_key is not None:
        if len(_REPORT_CACHE) >= _REPORT_CACHE_MAX:
            _REPORT_CACHE.clear()
        _REPORT_CACHE[str(p)] = (cache_key, report)
    return report
