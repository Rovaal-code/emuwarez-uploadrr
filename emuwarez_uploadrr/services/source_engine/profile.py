"""Normalizes MediaInfo/ffprobe/mkvmerge's raw JSON into one canonical
`MediaProfile` dict (spec section 8-9) that every evidence detector reads
instead of touching tool-specific field names directly.

Field-source priority, per spec section 8 (keep original values + which tool
won when they disagree):
  - video/audio technical detail (codec, profile, HDR, encoder strings):
    MediaInfo — richest and most consistent field set of the three.
  - track flags (default/forced/name/language) for MKV: mkvmerge — it reads
    the container's own track-flags directly, not inferred.
  - track flags for MP4/other containers (no mkvmerge): ffprobe disposition.
  - container-level structure (fragmentation, brands): ffprobe format tags.
"""
from __future__ import annotations

from typing import Any, Optional

_LOSSLESS_AUDIO_FORMATS = {
    "flac", "truehd", "mlp", "pcm", "dts-hd ma", "dts-hd master audio", "alac",
}
_LOSSLESS_COMPRESSION_MODES = {"lossless"}


def _f(x: Any, default: float | None = None) -> Optional[float]:
    if x is None:
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x: Any, default: int | None = None) -> Optional[int]:
    v = _f(x)
    return int(v) if v is not None else default


def _mi_tracks(mediainfo_json: Optional[dict], type_: str) -> list[dict]:
    if not mediainfo_json:
        return []
    tracks = ((mediainfo_json.get("media") or {}).get("track")) or []
    return [t for t in tracks if t.get("@type") == type_]


def _mi_general(mediainfo_json: Optional[dict]) -> dict:
    gs = _mi_tracks(mediainfo_json, "General")
    return gs[0] if gs else {}


def _mi_video(mediainfo_json: Optional[dict]) -> dict:
    vs = _mi_tracks(mediainfo_json, "Video")
    return vs[0] if vs else {}


def build_container(mediainfo_json: Optional[dict], ffprobe_json: Optional[dict],
                     mkvmerge_json: Optional[dict], *, extension: str) -> dict:
    general = _mi_general(mediainfo_json)
    fmt_container = (ffprobe_json or {}).get("format") or {}
    tags = fmt_container.get("tags") or {}

    is_fragmented = False
    major_brand = tags.get("major_brand")
    if extension in ("mp4", "m4v", "mov"):
        # A fragmented MP4 has no single moov-derived duration and ffprobe
        # can't report a bit_rate for the overall format in that case; a
        # cheap, header-only signal (no box walking needed).
        is_fragmented = fmt_container.get("duration") is None and fmt_container.get("bit_rate") is None

    chapter_count = len((ffprobe_json or {}).get("chapters") or []) or _i(general.get("MenuCount"), 0) or 0
    if mkvmerge_json is not None:
        chapter_count = len(mkvmerge_json.get("chapters") or []) or chapter_count
    attachment_count = len((mkvmerge_json or {}).get("attachments") or []) if mkvmerge_json else _i(general.get("Attachments"), None)

    return {
        "format": general.get("Format") or fmt_container.get("format_long_name") or (mkvmerge_json or {}).get("container", {}).get("type"),
        "muxing_application": general.get("Encoded_Application") or (mkvmerge_json or {}).get("container", {}).get("properties", {}).get("muxing_application"),
        "writing_application": general.get("Encoded_Library") or (mkvmerge_json or {}).get("container", {}).get("properties", {}).get("writing_application"),
        "is_fragmented": is_fragmented,
        "major_brand": major_brand,
        "chapter_count": chapter_count or 0,
        "attachment_count": attachment_count or 0,
        "tag_count": len(tags),
    }


def _hdr_info(video_mi: dict) -> dict:
    hdr_format = (video_mi.get("HDR_Format") or "") + " " + (video_mi.get("HDR_Format_Compatibility") or "")
    transfer = (video_mi.get("transfer_characteristics") or video_mi.get("colour_primaries") or "")
    dolby_vision = "dolby vision" in hdr_format.lower() or "dvhe" in (video_mi.get("CodecID") or "").lower()
    hdr10plus = "hdr10+" in hdr_format.lower()
    hdr = bool(video_mi.get("HDR_Format")) or "pq" in transfer.lower() or "hlg" in transfer.lower()
    return {"hdr": hdr, "hdr10_plus": hdr10plus, "dolby_vision": dolby_vision,
            "hdr_format_raw": video_mi.get("HDR_Format")}


def build_video(mediainfo_json: Optional[dict], ffprobe_json: Optional[dict]) -> dict:
    video_mi = _mi_video(mediainfo_json)
    streams = (ffprobe_json or {}).get("streams") or []
    video_ff = next((s for s in streams if s.get("codec_type") == "video"), {})

    width = _i(video_mi.get("Width")) or _i(video_ff.get("width"))
    height = _i(video_mi.get("Height")) or _i(video_ff.get("height"))
    coded_width = _i(video_mi.get("Stored_Width")) or _i(video_ff.get("coded_width")) or width
    coded_height = _i(video_mi.get("Stored_Height")) or _i(video_ff.get("coded_height")) or height

    fps = _f(video_mi.get("FrameRate"))
    if fps is None and video_ff.get("avg_frame_rate"):
        num, _, den = str(video_ff["avg_frame_rate"]).partition("/")
        try:
            fps = float(num) / float(den) if float(den) else None
        except (ValueError, ZeroDivisionError):
            fps = None

    reported_bitrate = _f(video_mi.get("BitRate")) or _f(video_ff.get("bit_rate"))
    stream_size = _i(video_mi.get("StreamSize"))
    duration_s = _f(video_mi.get("Duration")) or _f(video_ff.get("duration"))

    hdr = _hdr_info(video_mi)

    return {
        "codec": video_mi.get("Format") or video_ff.get("codec_name"),
        "profile": video_mi.get("Format_Profile") or video_ff.get("profile"),
        "level": video_mi.get("Format_Level") or video_ff.get("level"),
        "width": width, "height": height,
        "coded_width": coded_width, "coded_height": coded_height,
        "fps": fps,
        "bit_depth": _i(video_mi.get("BitDepth")) or _i(video_ff.get("bits_per_raw_sample")) or 8,
        "chroma_subsampling": video_mi.get("ChromaSubsampling") or video_ff.get("pix_fmt"),
        **hdr,
        "scan_type": (video_mi.get("ScanType") or "Progressive"),
        "reported_bitrate_bps": reported_bitrate,
        "stream_size_bytes": stream_size,
        "duration_s": duration_s,
        "frame_count": _i(video_mi.get("FrameCount")) or _i(video_ff.get("nb_frames")),
        "encoder": video_mi.get("Encoded_Library") or video_mi.get("Encoded_Library_Name"),
        "encoder_settings": video_mi.get("Encoded_Library_Settings"),
        "writing_library": video_mi.get("Writing_library"),
    }


def _is_lossless_audio(codec: str, compression_mode: Optional[str]) -> bool:
    # MediaInfo da "Lossless / Lossy" a un DTS-HD MA con núcleo: es sin pérdida.
    if compression_mode and any(m in compression_mode.lower() for m in _LOSSLESS_COMPRESSION_MODES):
        return True
    c = (codec or "").lower()
    return any(k in c for k in _LOSSLESS_AUDIO_FORMATS)


def build_audio_tracks(mediainfo_json: Optional[dict], ffprobe_json: Optional[dict],
                        mkvmerge_json: Optional[dict]) -> list[dict]:
    mi_tracks = _mi_tracks(mediainfo_json, "Audio")
    ff_tracks = [s for s in ((ffprobe_json or {}).get("streams") or []) if s.get("codec_type") == "audio"]
    mkv_tracks = [t for t in ((mkvmerge_json or {}).get("tracks") or []) if t.get("type") == "audio"]

    n = max(len(mi_tracks), len(ff_tracks), len(mkv_tracks))
    out = []
    for i in range(n):
        mi = mi_tracks[i] if i < len(mi_tracks) else {}
        ff = ff_tracks[i] if i < len(ff_tracks) else {}
        mkv = mkv_tracks[i] if i < len(mkv_tracks) else {}
        mkv_props = mkv.get("properties") or {}
        ff_disp = ff.get("disposition") or {}
        ff_tags = ff.get("tags") or {}

        codec = mi.get("Format") or mi.get("Format_Commercial_IfAny") or ff.get("codec_name") or mkv.get("codec")
        # El nombre comercial es lo que distingue un DTS-HD MA ("DTS") o un TrueHD ("MLP FBA").
        texto = f"{codec or ''} {mi.get('Format_Commercial_IfAny') or ''}".lower()
        extras = (mi.get("Format_AdditionalFeatures") or "").upper().split()
        title = mkv_props.get("track_name") or ff_tags.get("title") or mi.get("Title")
        language = mkv_props.get("language") or ff_tags.get("language") or mi.get("Language")
        default = mkv_props.get("default_track") if mkv_props else bool(ff_disp.get("default"))
        forced = mkv_props.get("forced_track") if mkv_props else bool(ff_disp.get("forced"))

        atmos = "atmos" in texto or "ATMOS" in extras
        # DTS:X son los extras "XLL X"; XLL solo es MA, XBR HRA y XCH DTS-ES.
        dts_x = "dts:x" in texto or ("dts" in texto and "XLL" in extras and "X" in extras)

        out.append({
            "index": i,
            "codec": codec,
            "profile": mi.get("Format_Profile"),
            "lossless": _is_lossless_audio(texto, mi.get("Compression_Mode")),
            "bitrate_bps": _f(mi.get("BitRate")) or _f(ff.get("bit_rate")),
            "sample_rate": _i(mi.get("SamplingRate")) or _i(ff.get("sample_rate")),
            "bit_depth": _i(mi.get("BitDepth")),
            "channels": _i(mi.get("Channels")) or _i(ff.get("channels")),
            "channel_layout": mi.get("ChannelLayout") or ff.get("channel_layout"),
            "language": language,
            "title": title,
            "default": bool(default),
            "forced": bool(forced),
            "atmos": atmos,
            "dts_x": dts_x,
            "truehd": "truehd" in texto,
        })
    return out


_SUB_TEXT_CODECS = {"srt", "subrip", "ass", "ssa", "webvtt", "ttml", "text"}
_SUB_BITMAP_CODECS = {"pgs", "hdmv pgs", "vobsub", "dvd_subtitle", "dvb_subtitle", "dvbsub"}


def build_subtitle_tracks(mediainfo_json: Optional[dict], ffprobe_json: Optional[dict],
                           mkvmerge_json: Optional[dict]) -> list[dict]:
    mi_tracks = _mi_tracks(mediainfo_json, "Text")
    ff_tracks = [s for s in ((ffprobe_json or {}).get("streams") or []) if s.get("codec_type") == "subtitle"]
    mkv_tracks = [t for t in ((mkvmerge_json or {}).get("tracks") or []) if t.get("type") == "subtitles"]

    n = max(len(mi_tracks), len(ff_tracks), len(mkv_tracks))
    out = []
    for i in range(n):
        mi = mi_tracks[i] if i < len(mi_tracks) else {}
        ff = ff_tracks[i] if i < len(ff_tracks) else {}
        mkv = mkv_tracks[i] if i < len(mkv_tracks) else {}
        mkv_props = mkv.get("properties") or {}
        ff_disp = ff.get("disposition") or {}
        ff_tags = ff.get("tags") or {}

        codec = (mi.get("Format") or ff.get("codec_name") or mkv.get("codec") or "").strip()
        codec_l = codec.lower()
        kind = "bitmap" if any(k in codec_l for k in _SUB_BITMAP_CODECS) else (
            "text" if any(k in codec_l for k in _SUB_TEXT_CODECS) else "unknown")
        title = mkv_props.get("track_name") or ff_tags.get("title") or mi.get("Title")
        language = mkv_props.get("language") or ff_tags.get("language") or mi.get("Language")
        default = mkv_props.get("default_track") if mkv_props else bool(ff_disp.get("default"))
        forced = mkv_props.get("forced_track") if mkv_props else bool(ff_disp.get("forced"))
        hi = bool(ff_disp.get("hearing_impaired"))

        out.append({
            "index": i, "codec": codec, "kind": kind,
            "language": language, "title": title,
            "default": bool(default), "forced": bool(forced),
            "hearing_impaired": hi,
        })
    return out


def build_topology(audio_tracks: list[dict], subtitle_tracks: list[dict], container: dict,
                    name_tags: dict[int, dict[str, bool]] | None = None) -> dict:
    name_tags = name_tags or {}
    languages = {t["language"] for t in audio_tracks if t.get("language") and t["language"] != "und"}
    languages |= {t["language"] for t in subtitle_tracks if t.get("language") and t["language"] != "und"}

    commentary_audio = sum(1 for i, t in enumerate(audio_tracks) if name_tags.get(i, {}).get("commentary"))
    forced_subs = sum(1 for t in subtitle_tracks if t.get("forced"))
    hi_subs = sum(1 for t in subtitle_tracks if t.get("hearing_impaired"))
    pgs = sum(1 for t in subtitle_tracks if t.get("kind") == "bitmap" and "pgs" in (t.get("codec") or "").lower())
    vobsub = sum(1 for t in subtitle_tracks if "vobsub" in (t.get("codec") or "").lower() or "dvd" in (t.get("codec") or "").lower())
    text_subs = sum(1 for t in subtitle_tracks if t.get("kind") == "text")

    return {
        "video_track_count": 1,
        "audio_track_count": len(audio_tracks),
        "subtitle_track_count": len(subtitle_tracks),
        "lossless_audio_count": sum(1 for t in audio_tracks if t.get("lossless")),
        "lossy_audio_count": sum(1 for t in audio_tracks if not t.get("lossless")),
        "commentary_audio_count": commentary_audio,
        "pgs_count": pgs,
        "vobsub_count": vobsub,
        "text_subtitle_count": text_subs,
        "forced_subtitle_count": forced_subs,
        "hearing_impaired_subtitle_count": hi_subs,
        "language_count": len(languages),
        "chapter_count": container.get("chapter_count", 0),
        "font_attachment_count": container.get("attachment_count", 0),
    }


def build_file_info(size_bytes: int, duration_s: Optional[float]) -> dict:
    total_bitrate = (size_bytes * 8 / duration_s) if duration_s and duration_s > 0 else None
    bytes_per_minute = (size_bytes / (duration_s / 60.0)) if duration_s and duration_s > 0 else None
    return {
        "size_bytes": size_bytes,
        "duration_seconds": duration_s,
        "total_bitrate_calculated_bps": total_bitrate,
        "bytes_per_minute": bytes_per_minute,
    }


def build_normalization(video: dict, file_info: dict, audio_tracks: list[dict]) -> dict:
    """Bitrate normalized by resolution/fps (spec section 12) — the whole
    point being that raw Mbps means nothing without pixel count and frame
    rate in the denominator."""
    w = video.get("width") or 0
    h = video.get("height") or 0
    fps = video.get("fps") or 0
    pixel_count = w * h

    audio_bitrate_total = sum(t.get("bitrate_bps") or 0 for t in audio_tracks)
    video_bitrate = video.get("reported_bitrate_bps")
    if not video_bitrate and file_info.get("total_bitrate_calculated_bps"):
        # Estimate: total minus known audio, floor at a tiny fraction of total
        # so a rounding error can't make video bitrate negative/zero.
        est = file_info["total_bitrate_calculated_bps"] - audio_bitrate_total
        video_bitrate = est if est > 0 else file_info["total_bitrate_calculated_bps"] * 0.5

    bits_per_pixel_per_frame = None
    bitrate_per_megapixel = None
    if pixel_count and fps and video_bitrate:
        bits_per_pixel_per_frame = video_bitrate / (pixel_count * fps)
        bitrate_per_megapixel = video_bitrate / (pixel_count / 1_000_000)

    total_bitrate = file_info.get("total_bitrate_calculated_bps") or 0
    video_share = (video_bitrate / total_bitrate) if (video_bitrate and total_bitrate) else None
    audio_share = (audio_bitrate_total / total_bitrate) if (audio_bitrate_total and total_bitrate) else None

    return {
        "pixel_count": pixel_count,
        "video_bitrate_used_bps": video_bitrate,
        "audio_bitrate_total_bps": audio_bitrate_total,
        "bits_per_pixel_per_frame": bits_per_pixel_per_frame,
        "bitrate_per_megapixel_bps": bitrate_per_megapixel,
        "video_share_of_file": video_share,
        "audio_share_of_file": audio_share,
    }
