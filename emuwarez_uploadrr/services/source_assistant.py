"""Source/provider assistant for eMuwarez nomenclature (Phase 10A).

SAFETY: Read-only service. Never modifies filesystem or calls external APIs
directly — TMDb calls are delegated to integrations/tmdb.py.
"""
from __future__ import annotations

import json
import os
from typing import Any

from ..database import connect

# --- Official EMU sources ---
# Matches references/nomenclatura-emuwarez.md's "Formato (Source)" table.
# "Full BluRay" and "WEBRip" keep their existing app-internal spelling (data
# already stored under those codes) rather than the guide's literal "FBD"/
# "WEBRIP" — see services/source_engine/integration.py for the mapping
# between the new detector's vocabulary and this one. FDVD/SD were missing
# entirely until the source-detection engine made the gap obvious (it can
# legitimately predict either and there was no dropdown value to hold it).
EMU_SOURCES: list[dict] = [
    {"code": "Full BluRay", "label": "Full BluRay"},
    {"code": "BDRemux",     "label": "BDRemux"},
    {"code": "BluRay",      "label": "BluRay"},
    {"code": "MHD",         "label": "MHD"},
    {"code": "WEB-DL",      "label": "WEB-DL"},
    {"code": "WEBRip",      "label": "WEBRip"},
    {"code": "HDTV",        "label": "HDTV"},
    {"code": "FDVD",        "label": "FDVD"},
    {"code": "SD",          "label": "SD"},
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


# Official site domain per provider code, used to show its real favicon and to
# link the icon to the provider's page. Best-effort; a wrong/missing domain just
# falls back to a generic glyph in the UI.
PROVIDER_DOMAINS: dict[str, str] = {
    "AMZN": "primevideo.com",
    "ATVP": "tv.apple.com",
    "DSNP": "disneyplus.com",
    "F1TV": "f1tv.formula1.com",
    "GLB": "globoplay.globo.com",
    "HS": "hotstar.com",
    "HULU": "hulu.com",
    "M+": "movistarplus.es",
    "IT": "apple.com",
    "MA": "moviesanywhere.com",
    "MAX": "max.com",
    "HMAX": "max.com",
    "SKY": "sky.com",
    "PCOK": "peacocktv.com",
    "PMTP": "paramountplus.com",
    "iP": "bbc.co.uk",
    "PLAY": "play.google.com",
    "MUBI": "mubi.com",
    "NF": "netflix.com",
    "RKTN": "rakuten.tv",
    "SL": "sonyliv.com",
    "SNXT": "sunnxt.com",
    "VIU": "viu.com",
    "RTVE": "rtve.es",
    "HBO": "hbo.com",
    "CR": "crunchyroll.com",
    "ADN": "animationdigitalnetwork.com",
    "HIDIVE": "hidive.com",
    "VRV": "vrv.co",
    "BILI": "bilibili.com",
    "ANIMEBOX": "animebox.es",
    "A3P": "atresplayer.com",
    "SKST": "skyshowtime.com",
    "FLMN": "filmin.es",
    "FLIXOLE": "flixole.com",
    "MGMP": "mgmplus.com",
    "STRP": "starplus.com",
    "STZ": "starz.com",
    "CNLP": "canalplus.com",
}


def list_emu_providers() -> list[dict]:
    # Alphabetical by code so the dropdowns are ordered. Each entry carries its
    # official-site domain (for the favicon + link) when known.
    return [
        {**p, "domain": PROVIDER_DOMAINS.get(p["code"])}
        for p in sorted(EMU_PROVIDERS, key=lambda p: p["code"].lower())
    ]


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
    """Suggest the best EMU provider code for a library item.

    Checks the filename FIRST (infer_provider_from_item — cheap, deterministic,
    no network) before ever calling TMDb: if the file is already named e.g.
    "...WEB-DL AMZN x265..." there's nothing to guess, and re-detecting via
    TMDb could disagree with what's already in the name (see the historical
    NF-vs-AMZN bug this same precedence already fixed elsewhere). Only when
    the filename doesn't reveal a provider does this fall back to TMDb +
    the configured priority order."""
    own = conn is None
    conn = conn or connect()
    try:
        item_row = conn.execute("SELECT * FROM library_items WHERE id = ?", (library_item_id,)).fetchone()
        if not item_row:
            return {"suggested": None, "tmdb_providers": [], "reason": "Item no encontrado"}
        item = dict(item_row)

        from .nomenclature import infer_provider_from_item
        from_filename = infer_provider_from_item(item)
        if from_filename:
            return {
                "suggested": from_filename,
                "tmdb_providers": [],
                "reason": "Detectado en el nombre del archivo",
            }

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


def check_auto_upload_source(item_id: int, conn=None) -> dict:
    """Quick pre-flight check run right before an "Automático" upload is
    queued: do the file's name, Radarr/Sonarr, and the Internal Source Tool
    all agree on the source? At minimum, Radarr/Sonarr must agree with the
    Internal Source Tool — the name is the most reliable signal when it's
    there, but it's often just plain absent (a rip with no source keyword in
    its filename), so requiring all three to be PRESENT before comparing
    would silently skip exactly the disagreements worth surfacing. Any two
    (or three) values that are both present and don't match counts as a
    disparity — even when the name already "won" and would still be applied
    (nomenclature.py::_infer_source_from_item name-first priority is
    unaffected either way), the user gets a chance to catch a case like the
    one that motivated this: name and Radarr both say BluRay, but the
    Internal Source Tool's own evidence points at BDRemux instead.

    For a season, checks ONE representative available episode — every
    episode in a pack must already share the same source to be uploadable
    (season_pack.py::_consistency_errors), so one stands in for all.

    Does NOT fail open on an inaccessible file: `accessible` comes back False
    (with a human-readable `message`) when the path is missing or MediaInfo
    couldn't read it, so the caller can pause the batch there instead of
    silently queuing a job doomed to fail later in upload_queue.py's own
    accessibility check — same failure the manual wizard would otherwise
    surface first, just moved earlier for the "Automático" path since nothing
    else stops to show it beforehand there."""
    own = conn is None
    conn = conn or connect()
    no_disparity = {"disparity": False, "from_name": None, "from_radarr": None, "from_mediainfo": None,
                     "accessible": True, "message": None}
    try:
        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return no_disparity
        item = dict(row)

        if item.get("item_type") == "season":
            from .season_pack import _get_season_episodes
            from ..models import LocalStatus
            available = [
                e for e in _get_season_episodes(item_id, conn)
                if e.get("local_status") == LocalStatus.AVAILABLE.value
            ]
            if not available:
                return no_disparity
            representative = available[0]
        else:
            representative = item

        path = representative.get("path")
        if not path:
            return {**no_disparity, "accessible": False, "message": "El elemento no tiene ruta de archivo."}

        from .path_mapping import resolve_local_path
        from .media_info_service import build_mediainfo_report
        local_path = resolve_local_path(path, conn=conn) or path
        radarr_source = representative.get("source")
        report = build_mediainfo_report(local_path, radarr_source=radarr_source)
        if not report.get("available"):
            return {**no_disparity, "from_radarr": radarr_source, "accessible": False,
                     "message": report.get("message") or "No se pudo leer el archivo."}

        sig = report.get("source_signals") or {}
        from_name = sig.get("from_name")
        from_mediainfo = sig.get("from_mediainfo_bitrate")
        present_values = {v for v in (from_name, radarr_source, from_mediainfo) if v}
        disparity = len(present_values) > 1
        return {
            "disparity": disparity,
            "from_name": from_name,
            "from_radarr": radarr_source,
            "accessible": True,
            "message": None,
            "from_mediainfo": from_mediainfo,
        }
    finally:
        if own:
            conn.close()


def _resolve_series_row(item: dict, conn) -> dict | None:
    """Walk parent_id up from an episode/season row to the series row and return
    it (title + tmdb_id), so episode nomenclature uses the series name and can
    localize it via the series' own TMDb id."""
    seen: set[int] = set()
    pid = item.get("parent_id")
    while pid and pid not in seen:
        seen.add(pid)
        row = conn.execute(
            "SELECT title, tmdb_id, item_type, parent_id FROM library_items WHERE id = ?", (pid,)
        ).fetchone()
        if not row:
            break
        row = dict(row)
        if row.get("item_type") == "series":
            return row
        pid = row.get("parent_id")
    return None


def _resolve_series_title(item: dict, conn) -> str | None:
    """The series title for an episode/season row (see _resolve_series_row)."""
    row = _resolve_series_row(item, conn)
    return row.get("title") if row else None


def build_editable_nomenclature_fields(
    library_item_id: int, conn=None,
    source_override: str | None = None, provider_override: str | None = None,
    tag_override: str | None = None,
) -> dict:
    """Build the editable field set for the nomenclature modal.

    `source_override`/`provider_override`/`tag_override` let a caller that
    already resolved these by hand (a season pack's own Source/Proveedor/Tag
    fields, applied uniformly across every episode) force that choice
    instead of the usual name -> Radarr/Sonarr -> bitrate-tool inference —
    without this, "Ver nombre de todos los capítulos" kept showing each
    episode's own auto-detected values even after overriding the season
    pack's title, so the individual names disagreed with it."""
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

        # The technical fields (códec/audio/HDR) are read with MediaInfo from the
        # real file and are mandatory for the eMuwarez name — so if the file
        # isn't reachable there's no complete/correct name to generate. Check
        # accessibility up front (applying the remote path mapping) and block
        # instead of producing a misleading name with empty technical fields.
        #
        # Prefer prepared_path over the raw path — same convention
        # mkv_remux.py/mkv_title.py already use: once nomenclature has been
        # applied, `path` may be stale (the original file was renamed/
        # hardlinked away) while prepared_path is the real current file.
        from .path_mapping import resolve_local_path
        raw_path = item.get("path")
        prepared_path = item.get("prepared_path")
        candidate_path = prepared_path or raw_path
        local_path = resolve_local_path(candidate_path, conn=conn) or candidate_path
        if not (local_path and os.path.isfile(local_path)):
            return {
                "library_item_id": library_item_id,
                "blocked": True,
                "error": (f"Archivo no accesible desde la app: {candidate_path or '(sin ruta)'}. "
                          "Los campos técnicos (códec, audio, HDR) se leen con MediaInfo del "
                          "archivo real; sin acceso al archivo no se puede generar la nomenclatura."),
            }

        # The technical fields (codec/audio/subtitles) come from Radarr/Sonarr's
        # sync-time metadata — fast and offline. A fresh MediaInfo read of the
        # real file is a separate, on-demand action (the MediaInfo button), so
        # generating the nomenclature no longer blocks on reading the file.

        title = item.get("title") or ""
        year = item.get("year")
        media_type = item.get("item_type") or "movie"
        tmdb_id = item.get("tmdb_id")
        resolution = _infer_resolution_from_item(item)
        source = source_override or _infer_source_from_item(item)

        # For episodes/seasons the eMuwarez title must be the SERIES name (not
        # the per-episode title like "Serie S01E01 - Nombre"), with the
        # season/episode carried separately. Resolve the series title by
        # walking up parent_id to the series row.
        season_num = item.get("season_number")
        episode_num = item.get("episode_number")
        # Title always in Spanish via TMDb (forced here, regardless of the
        # library-sync localize setting). For series, resolve the series row so
        # we localize with the series' own TMDb id.
        title_tmdb_id = tmdb_id
        if media_type in ("season", "episode"):
            srow = _resolve_series_row(item, conn)
            if srow:
                title = srow.get("title") or title
                title_tmdb_id = srow.get("tmdb_id") or title_tmdb_id
        from .tmdb_titles import resolve_localized_title
        title, title_warning = resolve_localized_title(conn, media_type, title_tmdb_id, title)

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

        tag = tag_override or _get_default_tag(conn)

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

        from .emu_format import format_resolution

        # The technical fields (per-track audio, exact códec, HDR/DV) come ONLY
        # from MediaInfo of the real file — Radarr/Sonarr's summary metadata is
        # NOT used here (it can't give per-track audio). If MediaInfo isn't
        # available the fields are left empty (the user sees they must fix
        # access / install `mediainfo`), rather than filling with sync values.
        mi_audio = mi_video = mi_hdr = mi_source = None
        mi_source_estimated = False
        from .media_info_service import build_mediainfo_report
        report = build_mediainfo_report(candidate_path or "", radarr_source=item.get("source"))
        mediainfo_ok = bool(report.get("available"))

        # Distinct from MediaInfo: mkvtoolnix (mkvmerge -J) is what the track
        # remux step needs to reorder/rename audio/subs — a file can be
        # readable by one tool and not the other (or neither), and each case
        # points the user at a different fix, so they're reported separately
        # instead of collapsing into one generic "no se puede leer".
        mkvtoolnix_ok = True
        if local_path.lower().endswith(".mkv"):
            from .mkv_remux import check_mkvmerge_available, read_tracks_json
            if check_mkvmerge_available().get("available"):
                mkvtoolnix_ok = bool(read_tracks_json(local_path).get("ok"))

        if not mediainfo_ok and not mkvtoolnix_ok:
            return {
                "library_item_id": library_item_id,
                "blocked": True,
                "error": ("El archivo es accesible, pero ni MediaInfo ni mkvtoolnix han podido leerlo "
                          "(probable corrupción)." + (f" {report.get('message')}" if report.get("message") else "")),
            }
        if not mediainfo_ok:
            # File reachable but MediaInfo couldn't read it (binary missing or
            # parse failure) → block: no technical fields, no valid name.
            return {
                "library_item_id": library_item_id,
                "blocked": True,
                "error": report.get("message") or "El archivo es accesible, pero MediaInfo no ha podido leerlo.",
            }
        if not mkvtoolnix_ok:
            return {
                "library_item_id": library_item_id,
                "blocked": True,
                "error": ("El archivo es accesible y MediaInfo lo lee correctamente, pero mkvtoolnix no ha "
                          "podido leerlo (probable corrupción) — hace falta para reordenar/renombrar las pistas."),
            }
        mi_audio = report.get("audio_summary")
        emu_by_field = {
            r["field"]: (None if r["emu"] in (None, "—", "") else r["emu"])
            for r in report.get("rows", [])
        }
        mi_video = emu_by_field.get("Códec de vídeo")
        mi_hdr = emu_by_field.get("HDR/DV")
        mi_source = emu_by_field.get("Source")
        mi_subs = emu_by_field.get("Subtítulos")  # "SUBS" if the file has subtitle tracks
        # Whether `mi_source` came from the name (reliable) or had to fall
        # back to the bitrate/audio tool (a guess) — read from the structured
        # signal, not by sniffing row text (the "Source" row's own text no
        # longer carries that description; it moved to its help tooltip).
        _sig_early = report.get("source_signals") or {}
        mi_source_estimated = bool(mi_source) and not _sig_early.get("from_name")

        # Source: `source` here is already name → Radarr/Sonarr (see
        # _infer_source_from_item). Only when NEITHER gave anything valid do
        # we fall back to the MediaInfo estimate (bitrate + audio); flag it
        # so the user reviews it — it's a guess, not a certainty.
        valid_sources = {s["code"] for s in EMU_SOURCES}
        source_warning = None
        if (not source or source not in valid_sources) and mi_source:
            source = mi_source
            if mi_source_estimated:
                source_warning = ("Source estimado por MediaInfo (bitrate y audio): "
                                  "ni el nombre del archivo ni Radarr/Sonarr dieron un source válido. Revísalo.")

        # Three-way cross-check for the Source field's alert icon: the name,
        # Radarr/Sonarr's raw value, and the MediaInfo bitrate-tool estimate
        # (forced — bypasses the name-first shortcut, unlike `mi_source`
        # above). `source` above already applies name → Radarr/Sonarr
        # priority, so this is purely informational (and covers the case
        # where the bitrate tool itself disagrees with both).
        source_comparison = {
            "from_name": _sig_early.get("from_name"),
            "from_radarr": item.get("source"),
            "from_mediainfo": _sig_early.get("from_mediainfo_bitrate"),
            # Whether "from_mediainfo" is actually confirmed (no re-encode
            # fingerprint → WEB-DL is decisive) or just a bitrate-threshold
            # guess that can't tell a WEB-DL re-encode from a disc re-encode
            # (MicroHD/BluRay-encode) apart.
            "mediainfo_confirmed": _sig_early.get("from_mediainfo_bitrate") is not None and not _sig_early.get("mediainfo_reencoded", True),
            # Full Internal Source Tool result (9-candidate ranking, evidence,
            # explanation) — None when the engine couldn't run at all, in
            # which case the UI falls back to the plain 3-column comparison.
            "engine": _sig_early.get("engine"),
        }
        _vals = [source_comparison["from_name"], source_comparison["from_radarr"], source_comparison["from_mediainfo"]]
        source_comparison["agree"] = all(_vals) and len(set(_vals)) == 1

        fields: dict[str, Any] = {
            "title": title,
            "complement": None,
            "season_episode": season_episode,
            "year": year,
            "resolution": format_resolution(resolution),
            "source": source,
            # Provider: from the file name first; only if the name has none (and
            # the source is WEB-DL) fall back to the TMDb suggestion.
            "provider": provider_override or infer_provider_from_item(item) or suggested_provider,
            "dynamic_range": mi_hdr,
            "video_codec": mi_video,
            "audio_summary": mi_audio,
            "subs": mi_subs,
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
            # Set when the title couldn't be confirmed in Spanish via TMDb, so
            # the wizard can flag the Title field.
            "title_warning": title_warning,
            # Set when the source had to be estimated from MediaInfo.
            "source_warning": source_warning,
            # Name vs Radarr/Sonarr vs MediaInfo-bitrate cross-check for the
            # Source field's alert icon.
            "source_comparison": source_comparison,
            # Reference table: every eMuwarez source code, the bitrate range
            # that maps to it at this file's resolution, and why — opened from
            # a link in the comparison table's "MediaInfo (bitrate)" cell.
            "source_bitrate_table": _sig_early.get("bitrate_table"),
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
