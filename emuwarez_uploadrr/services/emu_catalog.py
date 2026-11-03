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
import logging
import re
import sqlite3
import threading
from typing import Optional

from ..database import get_setting_canonical, get_state, set_state, get_json_state, set_json_state
from .settings import leer_ajuste
from ..integrations import emu
from ..integrations.base import IntegrationError
from .tasks import start_task, finish_task
from .eventos import EVENTO_SYNC_EMPEZADA, EVENTO_SYNC_TERMINADA, publicar

logger = logging.getLogger("emuwarez.emu")

SYNC_STATE_KEY = "last_emu_catalog_sync_utc"
# Written only when a sync genuinely finishes (unlike SYNC_STATE_KEY, which is
# stamped at the START of a sync — before anything is downloaded — so a page
# refresh can't relaunch a stalled one). get_item_comparison() must check THIS
# key, not SYNC_STATE_KEY: otherwise a sync that started but got stuck/crashed
# before finishing still reads as "synced", and every item confidently shows
# "no está en eMuwarez" against a catalog table that's actually still empty.
SYNC_COMPLETED_STATE_KEY = "last_emu_catalog_completed_utc"
# Highest torrent id stored, so the next sync only fetches newer torrents
# (incremental). Empty/unset → the catalog has never been fully downloaded, so
# the next sync is a full pass.
MAX_ID_STATE_KEY = "last_emu_catalog_max_id"
# Torrent count of the last full download, used only to estimate the progress
# bar's total on a (rare) subsequent full sync.
COUNT_STATE_KEY = "last_emu_catalog_torrents"
# Timestamp of the last FULL download, throttled apart from the incremental one.
FULL_SYNC_STATE_KEY = "last_emu_catalog_full_utc"
# Last {movies, seasons, episodes} "contenido único" counts we notified about —
# so a resync that doesn't change anything doesn't re-notify (see
# _notify_if_unique_content_changed below).
UNIQUE_CONTENT_COUNTS_STATE_KEY = "notify.content_unique_last_counts"
MIN_SYNC_SECONDS = 3600        # incremental: 1/hour
MIN_FULL_SYNC_SECONDS = 86400  # full re-download: 1/day
# Una descarga completa que trae menos que esto de lo que se esperaba no sustituye al catálogo guardado.
MIN_CATALOG_VS_TOTAL = 0.98     # contra el meta.total de eMuwarez, si lo manda
MIN_CATALOG_VS_PREVIOUS = 0.90  # contra lo que había, si no

# --- Parsing -----------------------------------------------------------------

_CODEC_TIER = {"AV1": 3, "HEVC": 2, "X265": 2, "H265": 2, "AVC": 1, "H264": 1, "X264": 1, "VP9": 1}
_CODEC_LABEL = {"AV1": "AV1", "HEVC": "H.265", "X265": "H.265", "H265": "H.265",
                "AVC": "H.264", "H264": "H.264", "X264": "H.264", "VP9": "VP9"}
_CODEC_RE = re.compile(r"\b(AV1|x265|H\.?265|HEVC|x264|H\.?264|AVC|VP9)\b", re.I)

_ES_TOKENS = {"ESP", "CAST", "CASTELLANO", "ESPANOL", "LATINO", "LAT", "DUAL", "MULTI"}
_ORIG_TOKENS = {"ING", "ENG", "JAP", "JPN", "KOR", "ITA", "FRA", "GER", "RUS", "POR", "VO", "VOSE", "VOST", "VOSTFR"}
_SEASON_RE = re.compile(r"\bS(\d{1,3})(?:E\d{1,4})?\b", re.I)
_SEASON_RANGE_RE = re.compile(r"\bS(\d{1,3})\s*-\s*S?(\d{1,3})\b", re.I)
_SEASON_WORD_RE = re.compile(r"\b(?:temporadas?|seasons?)\s+(\d{1,3})(?:\s*-\s*(\d{1,3}))?\b", re.I)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


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


def _season_range(first: int, last: int) -> list[int]:
    return list(range(first, last + 1)) if first <= last and last - first < 100 else [first]


def _seasons_in(text: str) -> list[int]:
    m = _SEASON_RANGE_RE.search(text)
    if m:
        return _season_range(int(m.group(1)), int(m.group(2)))
    tokens = _SEASON_RE.findall(text)
    if tokens:
        return [int(tokens[-1])]  # el último: «The S1 Files S02» es la 2
    m = _SEASON_WORD_RE.search(text)
    if m:
        return _season_range(int(m.group(1)), int(m.group(2) or m.group(1)))
    return []


def _parse_seasons(name: str) -> list[int]:
    """Las temporadas que trae un torrent: S02, S01-S03, S01-03, «Temporada 2». Lo que va antes del año es el título."""
    name = name or ""
    year = _YEAR_RE.search(name)
    return (_seasons_in(name[year.end():]) if year else []) or _seasons_in(name)


def _row_seasons(row: dict) -> list[int]:
    """Las temporadas de una fila del catálogo: se leen del nombre, y lo guardado (la primera) es el respaldo."""
    return _parse_seasons(row["name"]) or ([row["season_number"]] if row["season_number"] is not None else [])


def _is_series(row: dict) -> bool:
    return row["category"] == "Series" or bool(_row_seasons(row))


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


def seconds_until_next_sync(conn: sqlite3.Connection, mode: str = "incremental") -> int:
    """Seconds left on the throttle for a given mode. Incremental is gated by the
    last sync of any kind (1/hour); full by the last full sync (1/day)."""
    if mode == "full":
        last = _parse_iso(get_state(conn, FULL_SYNC_STATE_KEY))
        interval = MIN_FULL_SYNC_SECONDS
    else:
        last = _parse_iso(get_state(conn, SYNC_STATE_KEY))
        interval = MIN_SYNC_SECONDS
    if not last:
        return 0
    return max(0, int(interval - (_utcnow() - last).total_seconds()))


def get_sync_status(conn: sqlite3.Connection) -> dict:
    last = get_state(conn, SYNC_STATE_KEY)
    last_full = get_state(conn, FULL_SYNC_STATE_KEY)
    wait = seconds_until_next_sync(conn, "incremental")
    wait_full = seconds_until_next_sync(conn, "full")
    return {
        "last_sync_at": last, "can_sync": wait <= 0, "wait_seconds": wait,
        "min_interval_seconds": MIN_SYNC_SECONDS,
        # Per-mode throttles for the two-button sync card.
        "incremental_can_sync": wait <= 0, "incremental_wait_seconds": wait,
        "full_can_sync": wait_full <= 0, "full_wait_seconds": wait_full,
        "last_full_sync_at": last_full,
    }


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
            "season_number": min(_parse_seasons(name), default=None),
            "resolution": a.get("resolution"),
            "source": a.get("type"),
            "codec": _norm_codec(name),
            "has_spanish": _has_spanish(name),
            "size": a.get("size"),
            "name": name,
        })
    return rows


_INSERT_CATALOG_SQL = (
    "INSERT INTO emu_catalog (torrent_id, category, tmdb_id, tvdb_id, season_number, "
    "resolution, source, codec, has_spanish, size, name) VALUES "
    "(:torrent_id, :category, :tmdb_id, :tvdb_id, :season_number, :resolution, :source, "
    ":codec, :has_spanish, :size, :name)"
)


def _store_catalog(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Full replace — used on the first (complete) download."""
    conn.execute("DELETE FROM emu_catalog")
    conn.executemany(_INSERT_CATALOG_SQL, rows)
    conn.commit()


def _append_catalog(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Incremental — add newly-uploaded torrents without dropping the rest."""
    if rows:
        conn.executemany(_INSERT_CATALOG_SQL, rows)
        conn.commit()


def _check_catalog_complete(rows: list[dict], total: Optional[int], previous: int) -> None:
    """Sustituir el catálogo con una descarga cortada a mitad (una página vacía o corta con un 200) lo dejaría
    sin torrents y daría por únicos los que ya están en eMuwarez: sin cambiar nada, se avisa del fallo."""
    got = len({r["torrent_id"] for r in rows})
    expected, minimum = (total, MIN_CATALOG_VS_TOTAL) if total else (previous, MIN_CATALOG_VS_PREVIOUS)
    if expected and got < expected * minimum:
        raise IntegrationError(
            f"La descarga del catálogo está incompleta ({got} de unos {expected} torrents); se conserva el anterior")


def _max_torrent_id(rows: list[dict]) -> int:
    best = 0
    for r in rows:
        try:
            best = max(best, int(r.get("torrent_id") or 0))
        except (TypeError, ValueError):
            pass
    return best


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


def recompute_emu_catalog_status(conn: sqlite3.Connection) -> int:
    """Re-run the (purely local, no network) eMuwarez comparison against
    whatever catalog snapshot is already stored — safe to call after a plain
    Radarr/Sonarr library sync so newly-added/changed items get emu_in_catalog
    computed right away, instead of staying NULL (and so invisible to
    Recomendaciones' Group 2/3, which require it resolved to exactly 0) until
    someone happens to also run a full eMuwarez catalog sync.

    No-ops (returns 0) if eMuwarez has never actually finished a catalog sync
    — same SYNC_COMPLETED_STATE_KEY guard get_item_comparison() uses — so a
    fresh install with no eMu API key yet doesn't get every single item
    confidently marked "not on eMuwarez" against an empty catalog table."""
    if not get_state(conn, SYNC_COMPLETED_STATE_KEY):
        return 0
    return _compute_and_store_item_status(conn)


def _compute_and_store_item_status(conn: sqlite3.Connection) -> int:
    """Compute emu_in_catalog/emu_aportes for every movie, season and series."""
    # Load the catalog into in-memory indexes.
    cat = [dict(r) for r in conn.execute("SELECT * FROM emu_catalog").fetchall()]
    # TMDb numera aparte películas y series: un mismo id no es el mismo contenido. Las series se indexan por su
    # tvdb y por su tmdb (hay torrents con uno solo), y una temporada de un pack S01-S03 está en las tres.
    movies: dict[str, list] = {}
    seasons_idx: dict[tuple, list] = {}
    for c in cat:
        if _is_series(c):
            for n in _row_seasons(c):
                for kind in ("tvdb", "tmdb"):
                    if c[f"{kind}_id"]:
                        seasons_idx.setdefault((kind, c[f"{kind}_id"], n), []).append(c)
        elif c["tmdb_id"]:
            movies.setdefault(c["tmdb_id"], []).append(c)

    def season_rows(tvdb, tmdb, n) -> list[dict]:
        found: dict[int, dict] = {}
        for kind, ident in (("tvdb", tvdb), ("tmdb", tmdb)):
            if ident:
                for c in seasons_idx.get((kind, str(ident), n), []):
                    found[c["id"]] = c
        return list(found.values())

    # Honor the same "Ignorar especiales" setting the Estado/Nomenclatura
    # rollups use, so the three series statuses stay consistent. Default True
    # (only an explicit "false" counts specials).
    ignore_specials = leer_ajuste(conn, "series_ignore_specials")

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
        matches = movies.get(str(m["tmdb_id"]), []) if m["tmdb_id"] else []
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
        "sr.id AS series_id, sr.tvdb_id AS tvdb_id, sr.tmdb_id AS tmdb_id "
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
        matches = season_rows(s["tvdb_id"], s["tmdb_id"], s["season_number"]) if s["season_number"] is not None else []
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

    # Episodes — each matched to its own eMuwarez torrent (parsed SxxExx), so a
    # series that only exists as loose episodes still shows "Sí" per capítulo.
    for e in conn.execute(
        "SELECT e.id AS id, e.season_number AS season_number, e.episode_number AS episode_number, "
        "e.resolution AS resolution, e.source AS source, e.video_codec AS video_codec, "
        "e.audio_languages AS audio_languages, e.size_bytes AS size_bytes, sr.tvdb_id AS tvdb_id, "
        "sr.tmdb_id AS tmdb_id "
        "FROM library_items e JOIN library_items se ON e.parent_id = se.id "
        "JOIN library_items sr ON se.parent_id = sr.id "
        "WHERE e.item_type = 'episode'"
    ).fetchall():
        e = dict(e)
        matches = []
        if e["season_number"] is not None and e["episode_number"] is not None:
            # The catalog has no episode_number column — parse it from the name (e.g. "…S01E08…") so each
            # episode can be matched to its torrent.
            matches = [c for c in season_rows(e["tvdb_id"], e["tmdb_id"], e["season_number"])
                       if _parse_episode_number(c["name"] or "") == e["episode_number"]]
        if not matches:
            save(e["id"], 0, [])
            continue
        mine = {"resolution": e["resolution"], "source": e["source"],
                "codec": _norm_codec(e["video_codec"] or "") or e["video_codec"],
                "has_es": _episode_lang_has_es(e["audio_languages"]), "size": e["size_bytes"]}
        save(e["id"], 1, _compute_aportes(mine, matches))

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


_SXXEXX_RE = re.compile(r"S\d{1,3}\s*E(\d{1,4})", re.I)


def _parse_episode_number(name: str) -> Optional[int]:
    """Episode number from a torrent name (…S01E08… → 8). None for a season
    pack / anything without an SxxExx marker."""
    m = _SXXEXX_RE.search(name or "")
    return int(m.group(1)) if m else None


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


# --- Per-item catalog rows ----------------------------------------------------

def _series_ids(conn: sqlite3.Connection, series_id: Optional[int]) -> tuple[Optional[str], Optional[str]]:
    row = conn.execute("SELECT tvdb_id, tmdb_id FROM library_items WHERE id = ?", (series_id,)).fetchone()
    return (row["tvdb_id"], row["tmdb_id"]) if row else (None, None)


def _series_rows(conn: sqlite3.Connection, tvdb, tmdb) -> list[dict]:
    """Los torrents de series con ese tvdb o ese tmdb: el mismo criterio que _compute_and_store_item_status."""
    ids = [(col, str(v)) for col, v in (("tvdb_id", tvdb), ("tmdb_id", tmdb)) if v]
    if not ids:
        return []
    rows = conn.execute("SELECT * FROM emu_catalog WHERE " + " OR ".join(f"{col} = ?" for col, _ in ids),
                        [v for _, v in ids]).fetchall()
    return [r for r in map(dict, rows) if _is_series(r)]


def filas_del_catalogo(conn: sqlite3.Connection, item: dict) -> list[dict]:
    """Los torrents de eMuwarez de una película, temporada, capítulo o serie de la biblioteca."""
    kind = item["item_type"]
    if kind == "movie":
        if not item["tmdb_id"]:
            return []
        rows = conn.execute("SELECT * FROM emu_catalog WHERE tmdb_id = ?", (str(item["tmdb_id"]),)).fetchall()
        return [r for r in map(dict, rows) if not _is_series(r)]
    if kind == "series":
        return _series_rows(conn, item["tvdb_id"], item["tmdb_id"])
    if kind == "season":
        if item["season_number"] is None:
            return []
        tvdb, tmdb = _series_ids(conn, item["parent_id"])
        return [r for r in _series_rows(conn, tvdb, tmdb) if item["season_number"] in _row_seasons(r)]
    if kind == "episode":
        # Series → temporada → capítulo: el tvdb/tmdb salen de la serie y el capítulo se reconoce por su SxxExx.
        season = conn.execute("SELECT parent_id FROM library_items WHERE id = ?", (item["parent_id"],)).fetchone()
        tvdb, tmdb = _series_ids(conn, season["parent_id"] if season else None)
        season_n, ep_n = item["season_number"], item["episode_number"]
        if season_n is None or ep_n is None:
            return []
        return [r for r in _series_rows(conn, tvdb, tmdb)
                if season_n in _row_seasons(r) and _parse_episode_number(r["name"]) == ep_n]
    return []


def catalogo_cubre(conn: sqlite3.Connection, item_id: int, resolucion: Optional[str], tipo: Optional[str]) -> bool:
    """Si eMuwarez ya tiene un torrent de ese contenido con la resolución y el tipo pedidos (None = da igual)."""
    item = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return False
    item = dict(item)
    filas = filas_del_catalogo(conn, item)
    if item["item_type"] in ("season", "series"):
        # Un capítulo suelto no cubre una temporada entera.
        filas = [r for r in filas if _parse_episode_number(r["name"] or "") is None]
    cumplen = [r for r in filas
               if (not resolucion or r["resolution"] == resolucion)
               and (not tipo or (r["source"] or "").lower() == tipo.lower())]
    if item["item_type"] != "series":
        return bool(cumplen)
    # Una serie entera está cubierta si cada temporada que cuenta (como en el resumen de la serie) tiene la variante.
    ignorar_especiales = leer_ajuste(conn, "series_ignore_specials")
    temporadas = [n for (n,) in conn.execute(
        "SELECT season_number FROM library_items WHERE parent_id = ? AND item_type = 'season' "
        "AND season_number IS NOT NULL", (item_id,)) if not (ignorar_especiales and n == 0)]
    return bool(temporadas) and all(any(n in _row_seasons(r) for r in cumplen) for n in temporadas)


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

    # The catalog table is empty both when it's genuinely never been synced
    # AND (indistinguishably, by row count alone) when it HAS been synced but
    # this specific title just isn't there — an empty `matches` list further
    # down can't tell those apart. Check the *completed* marker (not the
    # attempt-started throttle timestamp), so a never-finished sync (stuck,
    # crashed, or still running) reads as "not yet synced" instead of
    # confidently claiming "contenido único" for every single item.
    if not get_state(conn, SYNC_COMPLETED_STATE_KEY):
        return {"available": False, "message": "Sincroniza con eMuwarez para ver la comparación.", "matches": []}

    rows = filas_del_catalogo(conn, item)
    if itype == "movie":
        mine = {"resolution": item["resolution"], "source": item["source"],
                "codec": _norm_codec(item["video_codec"] or "") or item["video_codec"],
                "has_es": _episode_lang_has_es(item["audio_languages"]), "size": item["size_bytes"]}
    elif itype == "season":
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
    elif itype == "episode":
        mine = {"resolution": item["resolution"], "source": item["source"],
                "codec": _norm_codec(item["video_codec"] or "") or item["video_codec"],
                "has_es": _episode_lang_has_es(item["audio_languages"]), "size": item["size_bytes"]}
    else:
        # Series is a rollup (drill into its seasons).
        return {"available": False, "message": "La comparación es a nivel de película, temporada o capítulo",
                "matches": [], "in_catalog": item.get("emu_in_catalog"),
                "aportes": _safe_json(item.get("emu_aportes"))}

    matches = [{"name": r["name"], "resolution": r["resolution"], "source": r["source"],
                "codec": r["codec"], "has_spanish": r["has_spanish"], "size": r["size"]}
               for r in rows]
    result = {
        "available": True,
        "message": None,
        "mine": mine,
        # Whether you actually have the file on disk. For a "Faltante" item there
        # is no local copy, so the "Tu copia" comparison would be meaningless.
        "mine_available": mine.get("size") is not None,
        "matches": matches,
        "in_catalog": 1 if matches else 0,
        "aportes": _compute_aportes(mine, rows) if matches else [],
    }
    if itype == "season":
        # Distinguish "there is a season pack" from "only loose episodes". When
        # only episodes exist, contributing the pack could be new — but only if
        # you actually have all the episodes.
        cat_ep_nums = {n for n in (_parse_episode_number(m["name"]) for m in matches) if n is not None}
        has_pack = any(_parse_episode_number(m["name"]) is None for m in matches)
        my_ep_nums = {r[0] for r in conn.execute(
            "SELECT episode_number FROM library_items WHERE parent_id = ? AND item_type = 'episode' "
            "AND local_status IN ('Disponible','Subido','Subiendo') AND episode_number IS NOT NULL", (item_id,)
        )}
        result["only_episodes"] = bool(cat_ep_nums) and not has_pack
        result["have_all_episodes"] = bool(cat_ep_nums) and cat_ep_nums.issubset(my_ep_nums)
    return result


def _safe_json(raw):
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


# --- Public sync -------------------------------------------------------------

# Live progress of the eMuwarez sync, so the UI can show a card of what it's
# doing. Single-process app → an in-memory dict is enough (the sync is on-demand,
# 1/hour). Polled via GET /library/emu-sync-progress.
_SYNC_LOCK = threading.Lock()
_SYNC_PROGRESS: dict = {"active": False, "done": False, "phase": "", "torrents": 0, "items": 0,
                        "page": 0, "total_pages": None, "eta_seconds": None, "error": None}


def get_sync_progress() -> dict:
    with _SYNC_LOCK:
        return dict(_SYNC_PROGRESS)


def _set_progress(**kw) -> None:
    with _SYNC_LOCK:
        _SYNC_PROGRESS.update(kw)


def start_emu_sync_background(force: bool = False, mode: str = "incremental") -> dict:
    """Start the catalog sync in a background thread (so the UI can poll
    progress). Returns {status:'started'} or {status:'throttled', wait_seconds}.
    mode: "incremental" (only new torrents) or "full" (re-download + reconcile)."""
    from ..database import connect, db_path, get_state
    conn = connect(db_path())
    is_full = mode == "full"
    try:
        wait = seconds_until_next_sync(conn, mode)
        if wait > 0 and not force:
            return {"status": "throttled", "wait_seconds": wait}
        with _SYNC_LOCK:
            if _SYNC_PROGRESS.get("active"):
                return {"status": "started"}  # one already running
        # Record the throttle NOW (at start), not at the end — otherwise a slow
        # or stalled download leaves no throttle and a page refresh lets you
        # relaunch it. Saved so a failed run can restore it. A full pass also
        # counts as a sync, so it bumps both timestamps.
        prev = get_state(conn, SYNC_STATE_KEY)
        prev_full = get_state(conn, FULL_SYNC_STATE_KEY)
        now_iso = _utcnow().isoformat()
        set_state(conn, SYNC_STATE_KEY, now_iso)
        if is_full:
            set_state(conn, FULL_SYNC_STATE_KEY, now_iso)
        conn.commit()
    finally:
        conn.close()
    _set_progress(active=True, done=False, error=None, phase="Iniciando…", torrents=0, items=0,
                  page=0, total_pages=None, eta_seconds=None)
    publicar(EVENTO_SYNC_EMPEZADA, {"que": "catalogo"})

    def _run() -> None:
        c = connect(db_path())
        try:
            sync_emu_catalog(c, force=True, mode=mode)  # throttle already recorded above
        except Exception as exc:  # noqa: BLE001 — surface the error to the card
            _set_progress(error=str(exc), phase="Error")
            # A failed sync shouldn't lock you out — restore the previous
            # throttle timestamp(s).
            try:
                cc = connect(db_path())
                set_state(cc, SYNC_STATE_KEY, prev or "")
                if is_full:
                    set_state(cc, FULL_SYNC_STATE_KEY, prev_full or "")
                cc.commit()
                cc.close()
            except Exception:  # noqa: BLE001
                pass
        finally:
            c.close()
            _set_progress(active=False, done=True)
            # Aquí termina la sincronización del catálogo, salga bien o mal.
            publicar(EVENTO_SYNC_TERMINADA, {"que": "catalogo"})

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


def _notify_if_unique_content_changed(conn: sqlite3.Connection) -> None:
    """"Contenido único" (movies/seasons/episodes not yet on eMuwarez) just got
    recomputed above — reuse the exact same counts already shown on the
    Dashboard (get_dashboard_summary) so the notification always matches what
    the user sees there, and only actually notify when they changed since the
    last sync (comparing every sync would spam the same numbers repeatedly).
    Best-effort — never raises, mirrors services/library.py::_notify_new_missing.
    """
    try:
        from .library import get_dashboard_summary
        from .notification_center import emit
        summary = get_dashboard_summary(conn)
        counts = {
            "movies": summary["unique_movies"],
            "seasons": summary["unique_seasons"],
            "episodes": summary["unique_episodes"],
        }
        prev = get_json_state(conn, UNIQUE_CONTENT_COUNTS_STATE_KEY)
        set_json_state(conn, UNIQUE_CONTENT_COUNTS_STATE_KEY, counts)
        if prev == counts:
            return
        emit(
            conn, "content_unique_changed",
            "Nuevo contenido único",
            f"Tu biblioteca tiene {counts['movies']} películas, {counts['seasons']} temporadas y "
            f"{counts['episodes']} episodios que todavía no están en eMuwarez.",
            link="/library",
            level="info",
        )
    except Exception:
        logger.exception("No se pudo emitir la notificación de contenido único")


def sync_emu_catalog(conn: sqlite3.Connection, *, force: bool = False, mode: str = "incremental") -> dict:
    """Download the eMuwarez catalog and recompute per-item status. 1/hour.

    mode="full" re-downloads the whole catalog and replaces it (reconciles
    torrents deleted on the tracker); mode="incremental" only fetches torrents
    newer than the last sync and appends them (fast, but can't detect deletions).
    A first sync with no baseline is always full regardless of mode."""
    wait = seconds_until_next_sync(conn, mode)
    if wait > 0 and not force:
        return {"status": "throttled", "wait_seconds": wait, "torrents": 0, "items": 0}

    task_id = start_task(conn, "sync-emu-catalog", f"Sincronizando catálogo eMuwarez ({'completo' if mode == 'full' else 'nuevo'})")
    try:
        api_key = get_setting_canonical(conn, "emu.api_key")
        if not api_key:
            raise IntegrationError("No hay API Key de eMuwarez configurada")

        # Fail fast (and clearly) if eMuwarez itself is unreachable, instead of only
        # discovering it mid-download — this is a single cheap request (perPage=1)
        # bound by request_json's own timeout, so a down/unreachable tracker surfaces
        # as an error within seconds rather than the sync silently hanging.
        _set_progress(phase="Comprobando conexión con eMuwarez…", page=0, total_pages=None, eta_seconds=None)
        try:
            emu.emu_test_connection(api_key, interactiva=False)  # primer paso del recorrido: espera su turno
        except IntegrationError as exc:
            raise IntegrationError(f"No se pudo conectar con eMuwarez: {exc}") from exc

        import time
        # Incremental: only fetch torrents newer than the highest id we already have.
        # First sync ever (no stored max) → full download.
        try:
            known_max_id = int(get_state(conn, MAX_ID_STATE_KEY) or 0)
        except (TypeError, ValueError):
            known_max_id = 0
        # Incremental unless a full pass is requested (or there's no baseline yet).
        incremental = (mode != "full") and known_max_id > 0
        # Estimate the page total (the API doesn't send last_page): a full pass is
        # ~ceil(previous_count / 100). Only meaningful for a full re-download.
        try:
            prev_count = int(get_state(conn, COUNT_STATE_KEY) or 0)
        except (TypeError, ValueError):
            prev_count = 0
        if not prev_count:
            # Fall back to whatever is already stored (e.g. a catalog downloaded
            # before this bookkeeping existed) so the first full bar has an estimate.
            prev_count = int(conn.execute("SELECT COUNT(*) AS n FROM emu_catalog").fetchone()["n"])
        est_full_pages = ((prev_count + 99) // 100) if (prev_count and not incremental) else None

        phase_label = "Buscando torrents nuevos en eMuwarez…" if incremental else "Descargando catálogo de eMuwarez…"
        logger.info("Sincronización de eMuwarez iniciada (modo %s)", "incremental" if incremental else "completo")
        _set_progress(phase=phase_label, page=0, total_pages=None, eta_seconds=None)
        _dl_start = time.time()
        reported_total: dict[str, Optional[int]] = {"n": None}

        def _on_page(page: int, total_pages, items_so_far: int, total_items) -> None:
            reported_total["n"] = total_items or reported_total["n"]
            tp = total_pages or est_full_pages
            elapsed = time.time() - _dl_start
            eta = None
            if tp and page > 0 and page < tp:
                eta = max(0, int(elapsed / page * (tp - page)))
            _set_progress(phase=phase_label, page=page,
                          total_pages=tp, torrents=items_so_far, eta_seconds=eta)

        torrents = emu.emu_fetch_all_torrents(
            api_key, progress=_on_page,
            stop_after_id=known_max_id if incremental else None,
        )
        rows = _index_catalog(torrents)

        if incremental:
            _set_progress(phase="Guardando torrents nuevos…", torrents=len(rows), eta_seconds=None)
            _append_catalog(conn, rows)
        else:
            _check_catalog_complete(rows, reported_total["n"], prev_count)
            _set_progress(phase="Guardando catálogo…", torrents=len(rows), eta_seconds=None)
            _store_catalog(conn, rows)

        # Track the highest id + total count for the next incremental / estimate.
        new_max_id = max(known_max_id, _max_torrent_id(rows))
        total_now = int(conn.execute("SELECT COUNT(*) AS n FROM emu_catalog").fetchone()["n"])
        if new_max_id > 0:
            set_state(conn, MAX_ID_STATE_KEY, str(new_max_id))
        set_state(conn, COUNT_STATE_KEY, str(total_now))

        _set_progress(phase="Calculando comparaciones con tu biblioteca…")
        items = _compute_and_store_item_status(conn)
        _set_progress(phase="Listo", items=items)
        now_iso = _utcnow().isoformat()
        set_state(conn, SYNC_STATE_KEY, now_iso)
        set_state(conn, SYNC_COMPLETED_STATE_KEY, now_iso)
        if not incremental:  # a full pass also refreshes the 1/day full throttle
            set_state(conn, FULL_SYNC_STATE_KEY, now_iso)
        _notify_if_unique_content_changed(conn)
        conn.commit()
        summary = f"{len(rows)} torrents {'nuevos' if incremental else 'descargados'}, {total_now} en catálogo, {items} elementos comparados"
        finish_task(conn, task_id, "completed", summary)
        logger.info("Sincronización de eMuwarez terminada (%s): %d torrents %s, %d en catálogo, %d elementos comparados",
                    "incremental" if incremental else "completo", len(rows),
                    "nuevos" if incremental else "descargados", total_now, items)
        return {"status": "ok", "torrents": len(rows), "items": items, "incremental": incremental}
    except Exception as exc:
        finish_task(conn, task_id, "failed", str(exc))
        raise
