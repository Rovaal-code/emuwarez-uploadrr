"""eMuwarez catalog sync + comparison.

On-demand (button, 1/hour, no scheduled task): download the whole eMuwarez
torrent catalog, index it, and for every movie/season in the local library work
out whether it's already on eMuwarez and, if so, what your copy would *add*
(resolution / source / a more efficient codec / Spanish audio it lacks).

eMuwarez has no language field, so "has Spanish" is parsed from the torrent name
(same nomenclature the tracker uses). Language comparison is deliberately
conservative — see _compute_aportes.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from typing import Any, Optional

from ..database import get_setting_canonical, get_state, set_state
from ..integrations import emu
from ..integrations.base import IntegrationError

SYNC_STATE_KEY = "last_emu_catalog_sync_utc"
MIN_SYNC_SECONDS = 3600

# --- Parsing -----------------------------------------------------------------

_CODEC_TIER = {"AV1": 3, "HEVC": 2, "X265": 2, "H265": 2, "AVC": 1, "H264": 1, "X264": 1, "VP9": 1}
_CODEC_LABEL = {"AV1": "AV1", "HEVC": "H.265", "X265": "H.265", "H265": "H.265",
                "AVC": "H.264", "H264": "H.264", "X264": "H.264", "VP9": "VP9"}
_CODEC_RE = re.compile(r"\b(AV1|x265|H\.?265|HEVC|x264|H\.?264|AVC|VP9)\b", re.I)

_ES_TOKENS = {"ESP", "CAST", "CASTELLANO", "ESPANOL", "LATINO", "LAT", "DUAL", "MULTI"}
_ORIG_TOKENS = {"ING", "ENG", "JAP", "JPN", "KOR", "ITA", "FRA", "GER", "RUS", "POR", "VO", "VOSE", "VOST", "VOSTFR"}
_SEASON_RE = re.compile(r"\bS(\d{1,3})(?:E\d{1,4})?\b", re.I)


def _norm_codec(name: str) -> Optional[str]:
    m = _CODEC_RE.search(name or "")
    if not m:
        return None
    key = m.group(1).upper().replace(".", "")
    return _CODEC_LABEL.get(key)


def _codec_tier(codec: Optional[str]) -> int:
    if not codec:
        return 0
    return _CODEC_TIER.get(codec.upper().replace(".", ""), 0)


def _has_spanish(name: str) -> Optional[int]:
    """1 = Spanish audio, 0 = explicitly non-Spanish, None = unknown."""
    tokens = set(re.findall(r"[A-Za-z0-9+]+", (name or "").upper()))
    if tokens & _ES_TOKENS:
        return 1
    if tokens & _ORIG_TOKENS:
        return 0
    return None


def _parse_season(name: str) -> Optional[int]:
    m = _SEASON_RE.search(name or "")
    return int(m.group(1)) if m else None


# --- Throttle ----------------------------------------------------------------

def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_iso(v: Optional[str]) -> Optional[dt.datetime]:
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(v)
    except ValueError:
        return None


def seconds_until_next_sync(conn: sqlite3.Connection) -> int:
    last = _parse_iso(get_state(conn, SYNC_STATE_KEY))
    if not last:
        return 0
    return max(0, int(MIN_SYNC_SECONDS - (_utcnow() - last).total_seconds()))


def get_sync_status(conn: sqlite3.Connection) -> dict:
    last = get_state(conn, SYNC_STATE_KEY)
    wait = seconds_until_next_sync(conn)
    return {"last_sync_at": last, "can_sync": wait <= 0, "wait_seconds": wait,
            "min_interval_seconds": MIN_SYNC_SECONDS}


# --- Catalog storage ---------------------------------------------------------

def _index_catalog(torrents: list[dict]) -> list[dict]:
    """Flatten raw torrent objects into catalog rows."""
    rows: list[dict] = []
    for t in torrents:
        a = t.get("attributes", {})
        name = a.get("name") or ""
        rows.append({
            "torrent_id": str(t.get("id") or ""),
            "category": a.get("category"),
            "tmdb_id": str(a["tmdb_id"]) if a.get("tmdb_id") else None,
            "tvdb_id": str(a["tvdb_id"]) if a.get("tvdb_id") else None,
            "season_number": _parse_season(name) if (a.get("category") == "Series") else None,
            "resolution": a.get("resolution"),
            "source": a.get("type"),
            "codec": _norm_codec(name),
            "has_spanish": _has_spanish(name),
            "size": a.get("size"),
            "name": name,
        })
    return rows


def _store_catalog(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.execute("DELETE FROM emu_catalog")
    conn.executemany(
        "INSERT INTO emu_catalog (torrent_id, category, tmdb_id, tvdb_id, season_number, "
        "resolution, source, codec, has_spanish, size, name) VALUES "
        "(:torrent_id, :category, :tmdb_id, :tvdb_id, :season_number, :resolution, :source, "
        ":codec, :has_spanish, :size, :name)",
        rows,
    )
    conn.commit()


# --- Comparison --------------------------------------------------------------

def _fmt_size(n: Optional[int]) -> str:
    if not n:
        return ""
    gb = n / 1e9
    return f"{gb:.1f} GB" if gb >= 1 else f"{n / 1e6:.0f} MB"


# Real-quality ranking. An "aporte" only counts when your copy *improves* on
# the best eMuwarez has — a lower resolution or a worse source is not a
# contribution, even if it's a combo the tracker technically lacks. Ranks are
# case-insensitive and span BOTH vocabularies: Radarr/Sonarr's source labels
# (BluRay, BDRemux, WEBRip…) and eMuwarez's UNIT3D `type` values (Encode = a
# BluRay re-encode ≈ local "BluRay"; Remux ≈ "BDRemux"; Full Disc = untouched
# disc; WEBRIP is uppercase there; SD is low).
_RES_RANK = {"4320p": 8, "2160p": 7, "1080p": 6, "1080i": 5, "720p": 4, "576p": 3, "540p": 2, "480p": 1}
_SRC_RANK = {
    "full disc": 7, "bdremux": 6, "remux": 6, "bluray": 5, "encode": 5,
    "web-dl": 4, "webdl": 4, "webrip": 3, "hdtv": 2, "dvd": 1, "sd": 1,
}


def _res_rank(v: Optional[str]) -> int:
    return _RES_RANK.get((v or "").strip(), 0)


def _src_rank(v: Optional[str]) -> int:
    return _SRC_RANK.get((v or "").strip().lower(), 0)


# Source tokens as they appear in release names — used to recover the true
# source when eMuwarez's `type` field is mislabeled (e.g. a BluRay encode
# tagged "WEBRIP"). Order doesn't matter; we take the best-ranked hit.
_NAME_SRC_RE = re.compile(
    r"\b(BDRemux|BD-Remux|Remux|Full[\s.]?Disc|BluRay|Blu-Ray|BDRip|BRRip|WEB[\s.-]?DL|WEBRip|WEB|HDTV|DVDRip|DVD)\b",
    re.I,
)
_NAME_SRC_NORM = {"bd-remux": "bdremux", "blu-ray": "bluray", "bdrip": "bluray", "brrip": "bluray",
                  "web": "web-dl", "web.dl": "web-dl", "webdl": "web-dl", "dvdrip": "dvd", "full disc": "full disc"}


def _name_src_rank(name: Optional[str]) -> int:
    """Best source rank among the source tokens found in a release name."""
    best = 0
    for tok in _NAME_SRC_RE.findall(name or ""):
        key = re.sub(r"[\s.]+", " ", tok).strip().lower()
        key = _NAME_SRC_NORM.get(key, key)
        best = max(best, _src_rank(key))
    return best


def _match_src_rank(m: dict) -> int:
    """Effective source rank of an eMuwarez torrent: the better of its `type`
    field and whatever the release name reveals (names beat mislabeled types)."""
    return max(_src_rank(m.get("source")), _name_src_rank(m.get("name")))


def _compute_aportes(mine: dict, matches: list[dict]) -> list[dict]:
    """mine: {resolution, source, codec, has_es, size}. Returns list of
    {dim, detail} describing what your copy adds over eMuwarez's best. Only
    called when matches is non-empty."""
    aportes: list[dict] = []
    res, src = mine.get("resolution"), mine.get("source")
    my_res_rank = _res_rank(res)
    my_src_rank = _src_rank(src)
    my_tier = _codec_tier(mine.get("codec"))

    best_res_rank = max((_res_rank(m["resolution"]) for m in matches), default=0)
    if my_res_rank > best_res_rank and res:
        # A strictly higher resolution than anything on eMuwarez.
        aportes.append({"dim": "resolucion", "detail": res})
    elif my_res_rank == best_res_rank and my_res_rank > 0:
        # Same top resolution — does your source improve on theirs at it?
        at_res = [m for m in matches if _res_rank(m["resolution"]) == my_res_rank]
        best_src_rank = max((_match_src_rank(m) for m in at_res), default=0)
        if my_src_rank > best_src_rank and src:
            aportes.append({"dim": "source", "detail": src})
        elif my_src_rank == best_src_rank and my_src_rank > 0:
            # Same res + source — a more efficient codec (smaller for equal quality).
            combo = [m for m in at_res if _match_src_rank(m) == my_src_rank]
            best_tier = max((_codec_tier(m["codec"]) for m in combo), default=0)
            # Only a genuinely efficient codec (HEVC/AV1, tier >= 2) is an
            # "aporte" — H.264 winning over an unparsed name is not meaningful.
            if my_tier > best_tier and my_tier >= 2:
                sizes = [m["size"] for m in combo if m["size"]]
                saving = (min(sizes) - mine["size"]) if (sizes and mine.get("size")) else None
                detail = mine.get("codec") or "códec más eficiente"
                if saving and saving > 0:
                    detail += f" (−{_fmt_size(saving)})"
                aportes.append({"dim": "codec", "detail": detail})

    # Language (conservative): you have Spanish and EVERY match is explicitly
    # non-Spanish (no match is Spanish and none is unknown).
    if mine.get("has_es") and matches and all(m["has_spanish"] == 0 for m in matches):
        aportes.append({"dim": "idioma", "detail": "ESP"})
    return aportes


def _episode_lang_has_es(langs: Optional[str]) -> bool:
    if not langs:
        return False
    up = langs.upper()
    return any(tok in up for tok in ("ESP", "ES ", "SPA", "CAST", "DUAL", "MULTI", "LATINO"))


def _compute_and_store_item_status(conn: sqlite3.Connection) -> int:
    """Compute emu_in_catalog/emu_aportes for every movie, season and series."""
    # Load the catalog into in-memory indexes.
    cat = [dict(r) for r in conn.execute("SELECT * FROM emu_catalog").fetchall()]
    by_tmdb: dict[str, list] = {}
    by_tvdb_season: dict[tuple, list] = {}
    for c in cat:
        if c["tmdb_id"] and c["category"] != "Series":
            by_tmdb.setdefault(c["tmdb_id"], []).append(c)
        if c["tvdb_id"] and c["season_number"] is not None:
            by_tvdb_season.setdefault((c["tvdb_id"], c["season_number"]), []).append(c)

    # Honor the same "Ignorar especiales" setting the Estado/Nomenclatura
    # rollups use, so the three series statuses stay consistent. Default True
    # (only an explicit "false" counts specials).
    ignore_specials = (get_setting_canonical(conn, "series.ignore_specials") or "true") != "false"

    updated = 0

    def save(item_id: int, in_cat: Optional[int], aportes: list[dict]) -> None:
        nonlocal updated
        conn.execute(
            "UPDATE library_items SET emu_in_catalog = ?, emu_aportes = ? WHERE id = ?",
            (in_cat, json.dumps(aportes, ensure_ascii=False), item_id),
        )
        updated += 1

    # Movies
    for m in conn.execute("SELECT id, tmdb_id, resolution, source, video_codec, audio_languages, size_bytes "
                          "FROM library_items WHERE item_type = 'movie'").fetchall():
        m = dict(m)
        matches = by_tmdb.get(str(m["tmdb_id"]), []) if m["tmdb_id"] else []
        if not matches:
            save(m["id"], 0, [])
            continue
        mine = {"resolution": m["resolution"], "source": m["source"],
                "codec": _norm_codec(m["video_codec"] or "") or m["video_codec"],
                "has_es": _episode_lang_has_es(m["audio_languages"]), "size": m["size_bytes"]}
        save(m["id"], 1, _compute_aportes(mine, matches))

    # Seasons (aggregate their episodes) — series' tvdb_id + id come from the join.
    seasons = conn.execute(
        "SELECT se.id AS id, se.season_number AS season_number, "
        "sr.id AS series_id, sr.tvdb_id AS tvdb_id "
        "FROM library_items se JOIN library_items sr ON se.parent_id = sr.id "
        "WHERE se.item_type = 'season'"
    ).fetchall()
    # For the series rollup we count real seasons on/off eMuwarez. Specials
    # (season 0/None) are excluded from the count — the tracker rarely carries
    # them, so counting them would flag almost every complete series as partial
    # (the special still gets its own "No" badge when you expand the series).
    series_total: dict[int, int] = {}
    series_in_count: dict[int, int] = {}
    series_aportes: dict[int, list] = {}
    for s in seasons:
        s = dict(s)
        eps = [dict(e) for e in conn.execute(
            "SELECT resolution, source, video_codec, audio_languages, size_bytes "
            "FROM library_items WHERE parent_id = ? AND item_type = 'episode'", (s["id"],)
        ).fetchall()]
        matches = by_tvdb_season.get((str(s["tvdb_id"]), s["season_number"]), []) if s["tvdb_id"] else []
        mine = {
            "resolution": _mode([e["resolution"] for e in eps]),
            "source": _mode([e["source"] for e in eps]),
            "codec": _best_codec([e["video_codec"] for e in eps]),
            "has_es": any(_episode_lang_has_es(e["audio_languages"]) for e in eps),
            "size": sum(e["size_bytes"] or 0 for e in eps) or None,
        }
        aportes = _compute_aportes(mine, matches) if matches else []
        save(s["id"], 1 if matches else 0, aportes)
        # Accumulate into the parent series' rollup. A numberless season is
        # never counted; season 0 (specials) counts unless "Ignorar especiales".
        pid = s["series_id"]
        sn = s["season_number"]
        counts = sn is not None and not (ignore_specials and sn == 0)
        if counts:
            series_total[pid] = series_total.get(pid, 0) + 1
            series_in_count[pid] = series_in_count.get(pid, 0) + (1 if matches else 0)
        for a in aportes:
            series_aportes.setdefault(pid, [])
            if a["detail"] not in [x["detail"] for x in series_aportes[pid]]:
                series_aportes[pid].append(a)

    # Series rollup: 0 = no seasons on eMuwarez, 1 = all seasons on eMuwarez,
    # 2 = partial (some seasons on, some off) — so a mixed series is no longer
    # hidden behind a plain "Sí".
    for sr in conn.execute("SELECT id FROM library_items WHERE item_type = 'series'").fetchall():
        sid = sr["id"]
        total = series_total.get(sid, 0)
        incount = series_in_count.get(sid, 0)
        if total == 0 or incount == 0:
            status = 0
        elif incount == total:
            status = 1
        else:
            status = 2
        save(sid, status, series_aportes.get(sid, []))

    conn.commit()
    return updated


def _mode(values: list) -> Optional[str]:
    vals = [v for v in values if v]
    if not vals:
        return None
    return max(set(vals), key=vals.count)


def _best_codec(codecs: list) -> Optional[str]:
    best, best_tier = None, -1
    for c in codecs:
        nc = _norm_codec(c or "") or c
        t = _codec_tier(nc)
        if t > best_tier:
            best, best_tier = nc, t
    return best


# --- Per-item comparison detail (for the detail card) ------------------------

def get_item_comparison(conn: sqlite3.Connection, item_id: int) -> dict:
    """Your copy vs every eMuwarez torrent that matches this movie/season, for
    the detail-card comparison table. Movies match by tmdb_id, seasons by
    (series tvdb_id, season_number)."""
    item = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return {"available": False, "message": "Elemento no encontrado", "matches": []}
    item = dict(item)
    itype = item["item_type"]

    if itype == "movie":
        rows = conn.execute(
            "SELECT * FROM emu_catalog WHERE tmdb_id = ? AND category != 'Series'",
            (str(item["tmdb_id"]),),
        ).fetchall() if item["tmdb_id"] else []
        mine = {"resolution": item["resolution"], "source": item["source"],
                "codec": _norm_codec(item["video_codec"] or "") or item["video_codec"],
                "has_es": _episode_lang_has_es(item["audio_languages"]), "size": item["size_bytes"]}
    elif itype == "season":
        parent = conn.execute("SELECT tvdb_id FROM library_items WHERE id = ?", (item["parent_id"],)).fetchone()
        tvdb = parent["tvdb_id"] if parent else None
        rows = conn.execute(
            "SELECT * FROM emu_catalog WHERE tvdb_id = ? AND season_number = ?",
            (str(tvdb), item["season_number"]),
        ).fetchall() if tvdb else []
        eps = [dict(e) for e in conn.execute(
            "SELECT resolution, source, video_codec, audio_languages, size_bytes "
            "FROM library_items WHERE parent_id = ? AND item_type = 'episode'", (item_id,)
        ).fetchall()]
        mine = {
            "resolution": _mode([e["resolution"] for e in eps]),
            "source": _mode([e["source"] for e in eps]),
            "codec": _best_codec([e["video_codec"] for e in eps]),
            "has_es": any(_episode_lang_has_es(e["audio_languages"]) for e in eps),
            "size": sum(e["size_bytes"] or 0 for e in eps) or None,
        }
    else:
        # Series/episode rows don't have a direct catalog match table — series
        # is a rollup (drill into its seasons), episodes roll into their season.
        return {"available": False, "message": "La comparación es a nivel de película o temporada",
                "matches": [], "in_catalog": item.get("emu_in_catalog"),
                "aportes": _safe_json(item.get("emu_aportes"))}

    matches = [{"name": r["name"], "resolution": r["resolution"], "source": r["source"],
                "codec": r["codec"], "has_spanish": r["has_spanish"], "size": r["size"]}
               for r in map(dict, rows)]
    return {
        "available": True,
        "message": None,
        "mine": mine,
        "matches": matches,
        "in_catalog": 1 if matches else 0,
        "aportes": _compute_aportes(mine, [dict(r) for r in rows]) if matches else [],
    }


def _safe_json(raw):
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


# --- Public sync -------------------------------------------------------------

def sync_emu_catalog(conn: sqlite3.Connection, *, force: bool = False) -> dict:
    """Download the eMuwarez catalog and recompute per-item status. 1/hour."""
    wait = seconds_until_next_sync(conn)
    if wait > 0 and not force:
        return {"status": "throttled", "wait_seconds": wait, "torrents": 0, "items": 0}

    api_key = get_setting_canonical(conn, "emu.api_key")
    if not api_key:
        raise IntegrationError("No hay API Key de eMuwarez configurada")

    torrents = emu.emu_fetch_all_torrents(api_key)
    rows = _index_catalog(torrents)
    _store_catalog(conn, rows)
    items = _compute_and_store_item_status(conn)
    set_state(conn, SYNC_STATE_KEY, _utcnow().isoformat())
    conn.commit()
    return {"status": "ok", "torrents": len(rows), "items": items}
