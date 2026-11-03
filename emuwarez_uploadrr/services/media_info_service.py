"""Real MediaInfo invocation for the web nomenclature flow (Phase 6B).

Builds on the pure pieces of `media_probe.py` (run_mediainfo_json,
media_tracks/first_track, detect_video_codec, audio_codec) and resolves each
track's language with `emu_format.resolve_language`, the one language table
of the app. Nothing here prompts: a web request must always complete. It
never raises: a missing `mediainfo` binary or any parse failure returns None
(or `available: False`), letting callers fall back to the cheaper
Radarr/Sonarr-sourced mediaInfo from Phase 6A instead of failing the whole
"Adaptar nomenclatura" flow.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from . import emu_format, media_probe


logger = logging.getLogger(__name__)

# Cache of build_mediainfo_report() results, keyed by (resolved path, idiomas
# elegidos) → ((path, mtime, size), report). Los idiomas van en la clave: el
# pack pide el mismo fichero con y sin ellos, y con una entrada por ruta cada
# petición echaba a la otra y volvía a leer el fichero. Avoids re-reading MediaInfo of the same file
# (slow over remote mounts) within the upload wizard / nomenclature flow.
_REPORT_CACHE: dict[tuple, tuple[tuple, dict]] = {}
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
            from .settings import leer_ajuste
            valor = leer_ajuste(conn, "source_engine_enabled")
        finally:
            conn.close()
    except Exception:                      # nunca romper una lectura de MediaInfo por esto
        return False
    return valor


def mediainfo_available() -> bool:
    """Whether the `mediainfo` binary is on PATH. The dev/test sandbox for
    this project doesn't have it installed — only the Docker homelab image
    does (via apt) — so callers must treat its absence as a normal,
    expected condition, not an error."""
    return shutil.which("mediainfo") is not None


def track_language(track: dict) -> str:
    """El código de eMuwarez de una pista de MediaInfo, con su BCP-47
    ("es-MX") y su nombre ("Latino")."""
    return emu_format.resolve_language(track.get("Language") or track.get("Language_String"),
                                       title=track.get("Title"))


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
        info = media_probe.run_mediainfo_json(file_path)
        video = media_probe.first_track(info, "Video")
        # Un MKV vacío o roto también da JSON, solo sin pistas: eso no es leerlo.
        if not video:
            logger.warning("MediaInfo no encuentra pista de vídeo en %s", path)
            return None

        audio_langs: list[str] = []
        audio_codecs: list[str] = []
        for track in media_probe.media_tracks(info):
            if track.get("@type") != "Audio":
                continue
            lang = track_language(track)
            if lang not in audio_langs:
                audio_langs.append(lang)
            codec = media_probe.audio_codec(track)
            if codec not in audio_codecs:
                audio_codecs.append(codec)

        subtitle_langs: list[str] = []
        for track in media_probe.media_tracks(info):
            if track.get("@type") != "Text":
                continue
            lang = track_language(track)
            if lang not in subtitle_langs:
                subtitle_langs.append(lang)

        return {
            "video_codec": media_probe.detect_video_codec(video, file_path),
            "audio_codec": " / ".join(audio_codecs) or None,
            "audio_languages": " / ".join(audio_langs) or None,
            "subtitle_languages": " / ".join(subtitle_langs) or None,
        }
    except Exception:
        logger.warning("MediaInfo falló para %s", path, exc_info=True)
        return None


def build_mediainfo_report(path: str, radarr_source: str | None = None,
                           idiomas_audio: dict[int, str] | None = None) -> dict:
    """Run MediaInfo on the actual file and return, for each field, the raw
    MediaInfo value alongside the value that goes to eMuwarez. Never raises;
    returns {available: False, message} when the binary/file isn't there.

    `radarr_source` is Radarr/Sonarr's own reported source (library_items.
    source) — needed only for the Source row's eMuwarez column, which follows
    the same name → Radarr/Sonarr → MediaInfo-bitrate priority used for the
    actually-applied nomenclature (see nomenclature.py::_infer_source_from_item).

    `idiomas_audio` ({posición de la pista de audio, desde 1: idioma}) es el
    idioma que el usuario eligió en el asistente para una pista que no lo trae.
    Solo cuenta para una pista sin idioma (igual que mkv_remux.build_track_plan):
    así el nombre y el remux nunca dicen cosas distintas. Una pista que sigue sin idioma no entra en el nombre y sale en
    `pistas_sin_idioma`.

    Shape: {available: bool, message: str|None, rows: [{field, mediainfo, emu}],
            audio_summary: str|None, pistas_sin_idioma: [int]}
    """
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
        cache_key = (str(p), int(st.st_mtime), int(st.st_size), radarr_source, _engine_on,
                     tuple(sorted((idiomas_audio or {}).items())))
        cached = _REPORT_CACHE.get((str(p), cache_key[-1]))
        if cached and cached[0] == cache_key:
            return cached[1]
    except OSError:
        cache_key = None

    try:
        info = media_probe.run_mediainfo_json(p)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": f"MediaInfo falló: {exc}", "rows": []}

    video = media_probe.first_track(info, "Video")
    rows: list[dict] = []

    def add(field: str, mi, emu, help_text: str | None = None):
        rows.append({"field": field, "mediainfo": str(mi) if mi not in (None, "") else "—",
                     "emu": str(emu) if emu not in (None, "") else "—", "help": help_text})

    # Resolution
    w = video.get("Width") or video.get("Stored_Width")
    h = video.get("Height") or video.get("Stored_Height")
    resolution = media_probe.video_resolution_code(video) if video else None
    add("Resolución", f"{w}x{h}" if w and h else None, emu_format.format_resolution(resolution))
    # Source: MediaInfo doesn't literally report a "source" field.
    # - "MediaInfo" column: always the bitrate/audio tool's own estimate,
    #   deliberately ignoring the name/Radarr — what the file itself suggests.
    # - "eMuwarez" column: the value that would actually be applied, following
    #   the same priority as the real nomenclature (nombre del archivo →
    #   Radarr/Sonarr → MediaInfo bitrate tool — see
    #   nomenclature.py::_infer_source_from_item).
    _audio_codecs = [media_probe.audio_codec(t) for t in media_probe.media_tracks(info) if t.get("@type") == "Audio"]
    _general = media_probe.first_track(info, "General")
    _duration = media_probe.duration_seconds(_general)
    _name_source = media_probe._detect_source_by_name(p)
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
        _bitrate_source = media_probe.estimate_source_from_bitrate(_size_bytes, _duration, _audio_codecs, resolution, video=video)
        if _bitrate_source is None:
            _bitrate_source = media_probe.heuristic_source(_audio_codecs, _size_bytes / (1024 ** 3), resolution)
    _final_source = _name_source or radarr_source or _bitrate_source
    # Whether the video has a hand-encoder fingerprint — used by the bitrate
    # reference table (below) to explain why a given bitrate range does or
    # doesn't confirm WEB-DL, and by source_comparison's mediainfo_confirmed.
    _reencoded = media_probe.looks_reencoded(video)
    _source_help = ("MediaInfo: se calcula a través de una tool interna de la aplicación (analiza audio y "
                    "bitrate del archivo), sin mirar el nombre del archivo. "
                    "eMuwarez: nombre del archivo → Radarr/Sonarr → tool interna de la aplicación.")
    # Que se vea cuando la herramienta no ha podido hacer su trabajo entero.
    if _engine_on and _engine_result is None:
        _source_help += " Herramienta de Source: no ha podido analizar el archivo; se usa la estimación simple por bitrate."
    elif _engine_result and _engine_result.get("partial"):
        _source_help += (f" Herramienta de Source: análisis parcial (falta {_engine_result['partial']}); "
                         "se repetirá la próxima vez.")
    add("Source", _bitrate_source, _final_source, help_text=_source_help)

    # Bitrate reference table (Ver MediaInfo's "MediaInfo (bitrate)" link):
    # every eMuwarez source code and the bitrate range that maps to it at
    # THIS file's resolution, so the user can see where their file lands and
    # why. Full BluRay/MHD are name-only — the tool can't tell them apart
    # from BDRemux/BluRay or from a WEBRip by bitrate alone.
    _remux_thr, _bluray_thr, _webdl_thr = media_probe.bitrate_thresholds(resolution)
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
    hdr = media_probe.detect_hdr(video) if video else []
    add("HDR/DV", video.get("HDR_Format") or video.get("HDR_Format_String"), " ".join(hdr) or None)
    # Video codec — when the real encoder fingerprint says x264/x265 (the
    # eMuwarez value below), the raw MediaInfo Format alone (AVC/HEVC, the
    # generic codec family) looks contradictory next to it. Showing "AVC
    # (x264)" here makes both true facts visible at once instead of one
    # column apparently disagreeing with the other.
    _video_codec_label = media_probe.detect_video_codec(video, p) if video else None
    _mi_video_codec = video.get("Format") or video.get("CodecID")
    if _mi_video_codec and _video_codec_label in ("x264", "x265") and _video_codec_label not in str(_mi_video_codec).lower():
        _mi_video_codec = f"{_mi_video_codec} ({_video_codec_label})"
    add("Códec de vídeo", _mi_video_codec, _video_codec_label)

    # Audio tracks (one row each) + combined eMuwarez segment
    audio_tracks = [t for t in media_probe.media_tracks(info) if t.get("@type") == "Audio"]
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
    sin_idioma: list[int] = []
    for i, tr in enumerate(audio_tracks, 1):
        raw_lang = tr.get("Language") or tr.get("Language_String") or ""
        lang = track_language(tr)
        elegido = (idiomas_audio or {}).get(i)
        if elegido and lang == "UND":
            lang = emu_format.resolve_language(elegido)
        codec = media_probe.audio_codec(tr)
        ch = media_probe.audio_channels(tr)
        codecs.append(codec)
        channels.append(ch)
        if lang == "UND":
            # Sin idioma no se escribe "UND" en el nombre: la pista se queda fuera.
            sin_idioma.append(i)
        elif lang not in langs:
            langs.append(lang)
        quality = emu_format.audio_track_quality(codec, ch)
        previous = best_by_lang.get(lang)
        if lang != "UND" and (previous is None or quality < previous[0]):
            best_by_lang[lang] = (quality, codec, ch)
        mi = " ".join(x for x in (tr.get("Format"), raw_lang or "?", tr.get("Channel_s_") or tr.get("Channels")) if x)
        # La ficha técnica SÍ sigue enseñando todas las pistas, una por fila:
        # ahí lo que interesa es qué hay dentro del archivo de verdad. Lo que
        # se recorta es solo el segmento que va al nombre.
        add(f"Audio {i}", mi, f"{lang} {codec} {ch or '?'}")

    groups: dict[tuple[str, str], list[str]] = {}
    for lang in langs:
        chosen = best_by_lang.get(lang)
        if not chosen:
            continue
        groups.setdefault((chosen[1], chosen[2]), []).append(lang)

    # La mejor pista de cada idioma, en estructura y no en cadena. El pack de
    # temporada la necesita para comparar capítulo con capítulo: volver a
    # parsear "ING DD+ Atmos 5.1 ESP-JAP DD+ 5.1" sería frágil, y esto ya está
    # calculado aquí arriba.
    audio_by_language = {lang: {"codec": best_by_lang[lang][1], "channels": best_by_lang[lang][2]}
                         for lang in langs if lang in best_by_lang}

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
        audio_summary = " ".join(entries) or None
        add("Audio (eMuwarez)", f"{len(audio_tracks)} pista(s)", audio_summary)

    # Subtitles
    sub_tracks = [t for t in media_probe.media_tracks(info) if t.get("@type") == "Text"]
    sub_langs = ", ".join(track_language(t) for t in sub_tracks)
    add("Subtítulos", sub_langs or None, "SUBS" if sub_tracks else None)

    report = {"available": True, "message": None, "rows": rows, "audio_summary": audio_summary,
              "resolution": resolution, "pistas_sin_idioma": sin_idioma,
               "audio_by_language": audio_by_language,
               "source_signals": source_signals}
    # A medias no se guarda: la próxima lectura vuelve a pasar la herramienta.
    _incompleto = _engine_on and (_engine_result is None or bool(_engine_result.get("partial")))
    if cache_key is not None and not _incompleto:
        if len(_REPORT_CACHE) >= _REPORT_CACHE_MAX:
            _REPORT_CACHE.clear()
        _REPORT_CACHE[(str(p), cache_key[-1])] = (cache_key, report)
    return report
