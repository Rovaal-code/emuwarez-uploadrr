"""Source/provider assistant for eMuwarez nomenclature (Phase 10A).

SAFETY: Read-only service. Never modifies filesystem or calls external APIs
directly — TMDb calls are delegated to integrations/tmdb.py.
"""
from __future__ import annotations

import json
from typing import Any

from ..database import connect

# --- Official EMU sources ---
EMU_SOURCES: list[dict] = [
    {"code": "Full BluRay", "label": "Full BluRay"},
    {"code": "BDRemux",     "label": "BDRemux"},
    {"code": "BluRay",      "label": "BluRay"},
    {"code": "MHD",         "label": "MHD"},
    {"code": "WEB-DL",      "label": "WEB-DL"},
    {"code": "WEBRip",      "label": "WEBRip"},
    {"code": "HDTV",        "label": "HDTV"},
]

# sources that accept a provider prefix
PROVIDER_SOURCES: frozenset[str] = frozenset({"WEB-DL"})

# --- Official EMU providers ---
EMU_PROVIDERS: list[dict] = [
    {"code": "AMZN",  "name": "Amazon"},
    {"code": "ATVP",  "name": "AppleTVPlus"},
    {"code": "DSNP",  "name": "DisneyPlus"},
    {"code": "F1TV",  "name": "F1tv"},
    {"code": "GLB",   "name": "Globoplay"},
    {"code": "HS",    "name": "Hotstar"},
    {"code": "HULU",  "name": "Hulu"},
    {"code": "M+",    "name": "Movistar+"},
    {"code": "IT",    "name": "iTunes"},
    {"code": "MA",    "name": "MoviesAnywhere"},
    {"code": "MAX",   "name": "HBO Max"},
    {"code": "HMAX",  "name": "HBO Max"},
    {"code": "SKY",   "name": "Sky"},
    {"code": "PCOK",  "name": "Peacock"},
    {"code": "PMTP",  "name": "ParamountPlus"},
    {"code": "iP",    "name": "BBC iPlayer"},
    {"code": "PLAY",  "name": "Google Play"},
    {"code": "MUBI",  "name": "Mubi"},
    {"code": "NF",    "name": "Netflix"},
    {"code": "RKTN",  "name": "RakutenTV"},
    {"code": "SL",    "name": "SonyLiv"},
    {"code": "SNXT",  "name": "Sunnxt"},
    {"code": "VIU",   "name": "Viu"},
    {"code": "RTVE",  "name": "RTVE"},
    {"code": "HBO",   "name": "HBO"},
    {"code": "CR",     "name": "Crunchyroll"},
    {"code": "ADN",    "name": "AnimeDigitalNetwork"},
    {"code": "HIDIVE", "name": "HIDIVE"},
    {"code": "VRV",    "name": "VRV"},
    {"code": "BILI",   "name": "Bilibili"},
    # Added from auditing eMuwarez's real torrent catalog (11k torrents): these
    # provider codes are already in active use on the tracker but were missing
    # from our list. Codes are the exact tokens used in the tracker's names.
    {"code": "ANIMEBOX", "name": "Animebox"},
    {"code": "A3P",      "name": "Atresplayer"},
    {"code": "SKST",     "name": "SkyShowtime"},
    {"code": "FLMN",     "name": "Filmin"},
    {"code": "FLIXOLE",  "name": "FlixOlé"},
    {"code": "MGMP",     "name": "MGM+"},
    {"code": "STRP",     "name": "Star+"},
    {"code": "STZ",      "name": "Starz"},
    {"code": "CNLP",     "name": "Canal+"},
]

# TMDb provider name → EMU provider code mapping
_TMDB_PROVIDER_MAP: dict[str, str] = {
    "amazon prime video": "AMZN",
    "amazon video": "AMZN",
    "netflix": "NF",
    "disney plus": "DSNP",
    "disney+": "DSNP",
    "apple tv plus": "ATVP",
    "apple tv+": "ATVP",
    "apple tv": "ATVP",
    "max": "MAX",
    "hbo max": "MAX",
    "movistar plus+": "M+",
    "movistar+": "M+",
    "itunes": "IT",
    "movies anywhere": "MA",
    "google play movies": "PLAY",
    "rakuten tv": "RKTN",
    "mubi": "MUBI",
    "peacock": "PCOK",
    "paramount plus": "PMTP",
    "paramount+": "PMTP",
    "skyshowtime": "SKST",  # canonical per user; SKY is Sky (a different service)
    "atresplayer": "A3P",
    "atres player": "A3P",
    "filmin": "FLMN",
    "flixolé": "FLIXOLE",
    "flixole": "FLIXOLE",
    "mgm plus": "MGMP",
    "mgm+": "MGMP",
    "animebox": "ANIMEBOX",
    "star plus": "STRP",
    "star+": "STRP",
    "starz": "STZ",
    "canal+": "CNLP",
    "canal plus": "CNLP",
    "rtve play": "RTVE",
    "hbo": "HBO",
    "f1 tv": "F1TV",
    "globoplay": "GLB",
    "hotstar": "HS",
    "hulu": "HULU",
    "bbc iplayer": "iP",
    "sony liv": "SL",
    "crunchyroll": "CR",
    "adn": "ADN",
    "anime digital network": "ADN",
    "hidive": "HIDIVE",
    "vrv": "VRV",
    "bilibili": "BILI",
    # Ad-supported / sub-brand / "via Amazon Channel" variants of platforms we
    # already map — same underlying source, so same EMU code (found by auditing
    # the WEB-DL library against TMDb watch providers, region ES).
    "amazon prime video with ads": "AMZN",
    "netflix standard with ads": "NF",
    "movistar plus+ ficción total": "M+",
    "hbo max amazon channel": "MAX",
    "crunchyroll amazon channel": "CR",
    "apple tv amazon channel": "ATVP",  # Apple TV+ delivered via Amazon Channel
    "apple tv store": "IT",             # transactional Apple = iTunes (rent/buy)
    "rtve": "RTVE",
}


def list_emu_sources() -> list[dict]:
    return list(EMU_SOURCES)


def list_emu_providers() -> list[dict]:
    # Alphabetical by code so the dropdowns are ordered.
    return sorted(EMU_PROVIDERS, key=lambda p: p["code"].lower())


def map_tmdb_provider_to_emu_provider(provider_name: str) -> str | None:
    """Map a TMDb provider display name to an EMU provider code."""
    if not provider_name:
        return None
    key = provider_name.strip().lower()
    return _TMDB_PROVIDER_MAP.get(key)


def _get_tmdb_available_providers_raw(tmdb_id: int, media_type: str, region: str = "ES") -> list[str]:
    """Call TMDb Watch Providers API. Returns list of EMU provider codes. Never raises."""
    try:
        from ..integrations.tmdb import get_movie_watch_providers, get_tv_watch_providers
        if media_type in ("movie",):
            data = get_movie_watch_providers(tmdb_id, region=region)
        else:
            data = get_tv_watch_providers(tmdb_id, region=region)

        region_data = data.get("results", {}).get(region, {})

        def _codes_for(categories: tuple[str, ...]) -> list[str]:
            codes: list[str] = []
            for category in categories:
                for provider in region_data.get(category, []):
                    name = (provider.get("provider_name") or "").strip()
                    code = map_tmdb_provider_to_emu_provider(name)
                    if code and code not in codes:
                        codes.append(code)
            return codes

        # Two tiers: subscription streaming takes priority (a WEB-DL is most
        # likely ripped from the platform it streams on, so Disney+ must beat an
        # Amazon *rental* of the same title). Only when there's no subscription
        # source do we fall back to transactional/free listings — a title only
        # available to rent/buy can still have been sourced from there.
        return _codes_for(("flatrate",)) or _codes_for(("free", "ads", "rent", "buy"))
    except Exception:
        return []


def get_tmdb_available_providers(tmdb_id: int, media_type: str, region: str = "ES") -> list[str]:
    """Return list of EMU provider codes available on TMDb for this item/region."""
    return _get_tmdb_available_providers_raw(tmdb_id, media_type, region)


def _get_provider_priority(conn) -> list[str]:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'provider_priority_order'").fetchone()
        if row:
            return json.loads(row["value"])
    except Exception:
        pass
    return ["AMZN", "NF", "DSNP", "MAX", "ATVP"]


def _get_tmdb_watch_region(conn) -> str:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'tmdb_watch_region'").fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
    return "ES"


def _get_default_tag(conn) -> str:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'default_release_tag'").fetchone()
        if row and row["value"]:
            return row["value"]
        row2 = conn.execute("SELECT value FROM app_state WHERE key = 'release_tag'").fetchone()
        if row2 and row2["value"]:
            return row2["value"]
    except Exception:
        pass
    return "EMUWAREZ"


def suggest_provider_for_item(library_item_id: int, conn=None) -> dict:
    """Suggest the best EMU provider code for a library item using TMDb + priority config."""
    own = conn is None
    conn = conn or connect()
    try:
        item_row = conn.execute("SELECT * FROM library_items WHERE id = ?", (library_item_id,)).fetchone()
        if not item_row:
            return {"suggested": None, "tmdb_providers": [], "reason": "Item no encontrado"}
        item = dict(item_row)

        tmdb_id_raw = item.get("tmdb_id")
        if not tmdb_id_raw:
            return {"suggested": None, "tmdb_providers": [], "reason": "Sin TMDb ID"}

        try:
            tmdb_id = int(str(tmdb_id_raw).split("/")[-1].strip())
        except (ValueError, TypeError):
            return {"suggested": None, "tmdb_providers": [], "reason": "TMDb ID inválido"}

        media_type = item.get("item_type") or "movie"
        region = _get_tmdb_watch_region(conn)
        priority = _get_provider_priority(conn)

        available = get_tmdb_available_providers(tmdb_id, media_type, region)

        if not available:
            return {"suggested": None, "tmdb_providers": [], "reason": "Sin providers en TMDb"}

        for code in priority:
            if code in available:
                return {
                    "suggested": code,
                    "tmdb_providers": available,
                    "reason": f"Prioridad configurada: {code}",
                }
        return {
            "suggested": available[0],
            "tmdb_providers": available,
            "reason": f"Primer disponible: {available[0]}",
        }
    finally:
        if own:
            conn.close()


def _resolve_series_title(item: dict, conn) -> str | None:
    """Walk parent_id up from an episode/season row to the series row and
    return its (clean) title, so episode nomenclature uses the series name
    instead of the per-episode "Serie S01E01 - Nombre" title."""
    seen: set[int] = set()
    pid = item.get("parent_id")
    while pid and pid not in seen:
        seen.add(pid)
        row = conn.execute(
            "SELECT title, item_type, parent_id FROM library_items WHERE id = ?", (pid,)
        ).fetchone()
        if not row:
            break
        row = dict(row)
        if row.get("item_type") == "series":
            return row.get("title")
        pid = row.get("parent_id")
    return None


def build_editable_nomenclature_fields(library_item_id: int, conn=None) -> dict:
    """Build the editable field set for the nomenclature modal."""
    own = conn is None
    conn = conn or connect()
    try:
        from .nomenclature import (
            get_library_item_for_nomenclature,
            _infer_resolution_from_item,
            _infer_source_from_item,
            get_latest_nomenclature_proposal,
            infer_provider_from_item,
        )

        item = get_library_item_for_nomenclature(library_item_id, conn=conn)
        if not item:
            return {"error": "Item no encontrado"}

        # The technical fields (codec/audio/subtitles) come from Radarr/Sonarr's
        # sync-time metadata — fast and offline. A fresh MediaInfo read of the
        # real file is a separate, on-demand action (the MediaInfo button), so
        # generating the nomenclature no longer blocks on reading the file.

        title = item.get("title") or ""
        year = item.get("year")
        media_type = item.get("item_type") or "movie"
        resolution = _infer_resolution_from_item(item)
        source = _infer_source_from_item(item)

        # For episodes/seasons the eMuwarez title must be the SERIES name (not
        # the per-episode title like "Serie S01E01 - Nombre"), with the
        # season/episode carried separately. Resolve the series title by
        # walking up parent_id to the series row.
        season_num = item.get("season_number")
        episode_num = item.get("episode_number")
        if media_type in ("season", "episode"):
            series_title = _resolve_series_title(item, conn)
            if series_title:
                title = series_title

        def _se_token() -> str | None:
            if season_num is None:
                return "S01"
            token = f"S{int(season_num):02d}"
            if media_type == "episode" and episode_num is not None:
                token += f"E{int(episode_num):02d}"
            return token

        proposal = get_latest_nomenclature_proposal(library_item_id, conn=conn)
        if proposal:
            resolution = resolution or proposal.get("resolution")
            source = source or proposal.get("source")

        tag = _get_default_tag(conn)

        season_episode = None
        if media_type in ("season", "episode"):
            season_episode = _se_token()
        elif media_type in ("tv", "series", "anime"):
            season_episode = "S01"

        tmdb_providers: list[str] = []
        suggested_provider: str | None = None
        if source and source.upper() == "WEB-DL":
            suggestion = suggest_provider_for_item(library_item_id, conn=conn)
            tmdb_providers = suggestion.get("tmdb_providers", [])
            suggested_provider = suggestion.get("suggested")

        tmdb_set = set(tmdb_providers)
        provider_options = []
        for p in list_emu_providers():
            provider_options.append({
                "code": p["code"],
                "name": p["name"],
                "label": f"{p['code']} ({p['name']})",
                "tmdb_available": p["code"] in tmdb_set,
            })

        # Auto-fill per the eMuwarez naming spec: normalize the raw Radarr/Sonarr
        # (or mediainfo) values to the spec format — resolution + suffix, codec
        # (AVC/HEVC…), HDR/DV, and the audio segment (DUAL/MULTI + codec + channels).
        from .emu_format import (
            format_resolution, format_video_codec, format_hdr, build_audio_string,
        )
        spec_audio = build_audio_string(
            item.get("audio_codec"), item.get("audio_languages"), item.get("audio_channels")
        )
        raw_video = (proposal.get("video_codec") if proposal else None) or item.get("video_codec")

        # The eMuwarez name needs the PER-TRACK audio, which Radarr/Sonarr's
        # summary metadata can't give — so read MediaInfo of the real file for
        # the technical fields (audio, exact códec, HDR/DV). Falls back to the
        # sync-time values when MediaInfo isn't available (no file / no
        # `mediainfo` binary) so generation never blocks or fails.
        mi_audio = mi_video = mi_hdr = None
        try:
            from .media_info_service import build_mediainfo_report
            report = build_mediainfo_report(item.get("path") or "")
            if report.get("available"):
                mi_audio = report.get("audio_summary")
                emu_by_field = {
                    r["field"]: (None if r["emu"] in (None, "—", "") else r["emu"])
                    for r in report.get("rows", [])
                }
                mi_video = emu_by_field.get("Códec de vídeo")
                mi_hdr = emu_by_field.get("HDR/DV")
        except Exception:  # noqa: BLE001 — MediaInfo is best-effort here
            pass

        fields: dict[str, Any] = {
            "title": title,
            "complement": None,
            "season_episode": season_episode,
            "year": year,
            "resolution": format_resolution(resolution),
            "source": source,
            "provider": suggested_provider or infer_provider_from_item(item),
            "dynamic_range": mi_hdr or format_hdr(item.get("dynamic_range")),
            "video_codec": mi_video or format_video_codec(raw_video),
            "audio_summary": mi_audio or (proposal.get("audio_summary") if proposal else None) or spec_audio,
            "subs": "SUBS",
            "tag": tag,
        }

        preview = update_nomenclature_fields_preview(library_item_id, fields, conn=conn)

        return {
            "library_item_id": library_item_id,
            "fields": fields,
            "torrent_name": preview.get("torrent_name"),
            "internal_mkv_title": preview.get("internal_mkv_title"),
            "provider_options": provider_options,
            "tmdb_available_providers": tmdb_providers,
            "sources": list_emu_sources(),
        }
    finally:
        if own:
            conn.close()


def update_nomenclature_fields_preview(library_item_id: int, fields: dict, conn=None) -> dict:
    """Recalculate torrent_name and internal_mkv_title from editable fields."""
    from .nomenclature import _normalize_title_for_emu

    title = _normalize_title_for_emu(fields.get("title") or "")
    complement = fields.get("complement")
    season_episode = fields.get("season_episode")
    year = fields.get("year")
    resolution = fields.get("resolution")
    source = fields.get("source")
    provider = fields.get("provider")
    dynamic_range = fields.get("dynamic_range")
    video_codec = fields.get("video_codec")
    audio_summary = fields.get("audio_summary")
    subs = fields.get("subs")
    tag = fields.get("tag")

    parts: list[str] = []

    title_part = title
    if complement:
        title_part = f"{title} - {complement}".strip(" -")
    if title_part:
        parts.append(title_part)

    if season_episode:
        parts.append(season_episode)

    if year:
        parts.append(str(year))

    # eMuwarez order: Resolución (+ suffix) · Source · HDR/DV · Códec vídeo · Audio.
    from .emu_format import format_resolution, format_hdr
    if resolution:
        parts.append(format_resolution(resolution) or resolution)

    source_str = _build_source_string(source, provider)
    if source_str:
        parts.append(source_str)

    # Dolby Vision / HDR goes right before the video codec.
    hdr = format_hdr(dynamic_range) if dynamic_range else None
    if hdr:
        parts.append(hdr)

    if video_codec:
        parts.append(video_codec)

    if audio_summary:
        parts.append(audio_summary)

    if subs:
        parts.append(subs)

    torrent_name = " ".join(p for p in parts if p)
    if tag:
        # Tag attaches to the hyphen with no surrounding spaces: "…SUBS-EMUWAREZ".
        torrent_name = f"{torrent_name}-{tag}"
    internal_mkv_title = _build_internal_mkv_title_from_name(torrent_name)

    return {
        "torrent_name": torrent_name,
        "internal_mkv_title": internal_mkv_title,
    }


def _build_source_string(source: str | None, provider: str | None) -> str | None:
    """Build the source segment: 'AMZN WEB-DL' or 'BluRay' etc."""
    if not source:
        return None
    if source in PROVIDER_SOURCES and provider:
        return f"{provider} {source}"
    return source


def _build_internal_mkv_title_from_name(torrent_name: str) -> str:
    """Derive internal MKV title: strip accents/special chars and dot it (the
    torrent/aporte title keeps accents; the internal title does not)."""
    from .mkv_title import to_filesystem_name
    return to_filesystem_name(torrent_name)
