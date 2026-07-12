"""Compatibility engine for matching EMU requests to local library items.

Priority order for ranking:
  1. Compatible + Disponible + Nomenclatura correcta
  2. Compatible + Disponible + Nomenclatura no adaptada
  3. Compatible + not available
  4. Parcial (one mismatch)
  5. No compatible (multiple mismatches)
  6. Sin coincidencia / Llena
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Pixel height ranks — higher is better
_RESOLUTION_RANK: dict[str, int] = {
    "480p": 480, "480i": 480, "480": 480,
    "576p": 576, "576": 576,
    "720p": 720, "720i": 720, "720": 720,
    "1080p": 1080, "1080i": 1080, "1080": 1080,
    "2160p": 2160, "4k": 2160, "uhd": 2160, "2160": 2160,
    "8k": 4320, "4320p": 4320,
}

# Source quality ranks — higher is better
_SOURCE_CANONICAL: dict[str, str] = {
    "bluray": "bluray", "blu-ray": "bluray", "blu ray": "bluray",
    "bdrip": "bdrip", "bd rip": "bdrip",
    "bdremux": "bdremux", "bd remux": "bdremux",
    "webdl": "webdl", "web-dl": "webdl", "web dl": "webdl",
    "webrip": "webrip", "web rip": "webrip", "web-rip": "webrip",
    "web": "web",
    "hdtv": "hdtv", "hd tv": "hdtv",
    "dvdrip": "dvdrip", "dvd rip": "dvdrip", "dvd": "dvd",
    "cam": "cam", "ts": "ts", "tc": "tc",
    "hdcam": "hdcam",
}

_SOURCE_RANK: dict[str, int] = {
    "bdremux": 100,
    "bluray": 95,
    "bdrip": 85,
    "webdl": 80,
    "web": 75,
    "webrip": 70,
    "hdtv": 60,
    "dvdrip": 50,
    "dvd": 45,
    "hdcam": 20,
    "cam": 10,
    "ts": 12,
    "tc": 11,
}


def normalize_title(value: str | None) -> str:
    """Strip accents, casefold, keep only alphanumeric tokens, collapse whitespace."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def compact_title(value: str | None) -> str:
    """Remove articles and all whitespace — for fuzzy identity checks."""
    t = normalize_title(value)
    for art in ("the ", "a ", "an ", "el ", "la ", "los ", "las ", "un ", "una "):
        if t.startswith(art):
            t = t[len(art):]
            break
    return re.sub(r"\s+", "", t)


def parse_resolution(value: str | None) -> Optional[int]:
    """Return pixel height or None if unrecognised."""
    if not value:
        return None
    key = value.strip().lower().replace(" ", "")
    return _RESOLUTION_RANK.get(key)


def parse_source(value: str | None) -> Optional[str]:
    """Return canonical source key or None."""
    if not value:
        return None
    key = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    return _SOURCE_CANONICAL.get(key)


def _no_restriction(value: str | None) -> bool:
    return not value or value.strip().lower() in (
        "any", "cualquiera", "todos", "all", "none", ""
    )


def compare_resolution(requested: str | None, local: str | None) -> Optional[bool]:
    """
    None  = no restriction (request is 'any')
    True  = local satisfies request (>= requested)
    False = local does NOT satisfy request
    """
    if _no_restriction(requested):
        return None
    req_rank = parse_resolution(requested)
    if req_rank is None:
        return None
    loc_rank = parse_resolution(local)
    if loc_rank is None:
        return False
    return loc_rank >= req_rank


def compare_source(requested: str | None, local: str | None) -> Optional[bool]:
    """
    None  = no restriction
    True  = local meets or exceeds requested source quality
    False = local does not meet quality requirement
    """
    if _no_restriction(requested):
        return None
    req_can = parse_source(requested)
    if req_can is None:
        return None
    loc_can = parse_source(local)
    if loc_can is None:
        return False
    req_rank = _SOURCE_RANK.get(req_can, 0)
    loc_rank = _SOURCE_RANK.get(loc_can, 0)
    return loc_rank >= req_rank


def _word_overlap(t1: str, t2: str) -> float:
    w1 = set(t1.split())
    w2 = set(t2.split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / max(len(w1), len(w2))


def match_request_to_library(
    req: dict,
    library: list[dict],
) -> list[dict]:
    """
    Find library items that could satisfy this request.

    Returns list of dicts sorted by confidence desc:
      {item, id_match, title_match, confidence}
    """
    results: list[dict] = []
    req_tmdb = str(req.get("tmdb_id") or "").strip()
    req_imdb = str(req.get("imdb_id") or "").strip()
    req_title_norm = normalize_title(req.get("title"))
    req_title_compact = compact_title(req.get("title"))

    for item in library:
        id_match = False
        title_match = False
        confidence = 0.0

        itm_tmdb = str(item.get("tmdb_id") or "").strip()
        itm_imdb = str(item.get("imdb_id") or "").strip()

        if req_tmdb and itm_tmdb and req_tmdb == itm_tmdb:
            id_match = True
            confidence = 1.0
        elif req_imdb and itm_imdb and req_imdb == itm_imdb:
            id_match = True
            confidence = 0.95
        else:
            itm_title_norm = normalize_title(item.get("title"))
            itm_title_compact = compact_title(item.get("title"))
            if (
                req_title_compact
                and req_title_compact == itm_title_compact
            ) or req_title_norm == itm_title_norm:
                title_match = True
                confidence = 0.90
            else:
                sim = _word_overlap(req_title_norm, itm_title_norm)
                if sim >= 0.75:
                    title_match = True
                    confidence = 0.55 + sim * 0.35

        if confidence > 0:
            results.append({
                "item": item,
                "id_match": id_match,
                "title_match": title_match,
                "confidence": confidence,
            })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results


# Local statuses that mean the file is actually present (can fulfil a request).
_AVAILABLE_LOCAL_STATUS = {"Disponible", "Subido", "Subiendo", "Parcial"}


def _item_available(item: dict) -> bool:
    return (item.get("local_status") or "") in _AVAILABLE_LOCAL_STATUS


def classify_request_match(
    req: dict,
    item: dict,
    *,
    id_match: bool = False,
    title_match: bool = False,
    base_confidence: float = 0.90,
) -> dict:
    """
    Given a matched (request, library_item) pair, classify compatibility.

    Returns dict:
      status: Compatible | Parcial | No compatible | Llena
      confidence: float
      resolution_match: bool|None
      source_match: bool|None
      id_match: bool
      title_match: bool
      reasons: list[str]
    """
    req_res = req.get("requested_resolution")
    req_src = req.get("requested_source")
    local_res = item.get("resolution")
    local_src = item.get("source")

    res_match = compare_resolution(req_res, local_res)
    src_match = compare_source(req_src, local_src)

    reasons: list[str] = []
    if id_match:
        reasons.append("Coincidencia por ID (TMDb/IMDb)")
    elif title_match:
        reasons.append("Coincidencia por título")

    if res_match is None:
        reasons.append("Sin restricción de resolución")
    elif res_match:
        reasons.append(f"Resolución satisface: local={local_res or 'N/D'} ≥ pedido={req_res or 'N/D'}")
    else:
        reasons.append(f"Resolución no satisface: local={local_res or 'N/D'} < pedido={req_res or 'N/D'}")

    if src_match is None:
        reasons.append("Sin restricción de source")
    elif src_match:
        reasons.append(f"Source satisface: local={local_src or 'N/D'} ≥ pedido={req_src or 'N/D'}")
    else:
        reasons.append(f"Source no satisface: local={local_src or 'N/D'} < pedido={req_src or 'N/D'}")

    # eMuwarez request states that override the library-compatibility verdict:
    # if the request is claimed/pending/filled on the tracker, that status wins
    # (you can't act on it regardless of what your library holds).
    status_text = str(req.get("emu_status") or "").lower()
    emu_state: Optional[str] = None
    if "reclam" in status_text or "claim" in status_text:
        emu_state = "Reclamado"
    elif "pend" in status_text or "pending" in status_text:
        emu_state = "Pendiente"
    elif "lleno" in status_text or "llena" in status_text or "filled" in status_text or status_text == "1":
        emu_state = "Llena"
    if emu_state:
        return {
            "status": emu_state,
            "confidence": base_confidence,
            "resolution_match": None if res_match is None else bool(res_match),
            "source_match": None if src_match is None else bool(src_match),
            "id_match": id_match,
            "title_match": title_match,
            "reasons": reasons,
        }

    res_fails = res_match is False
    src_fails = src_match is False

    if not res_fails and not src_fails:
        status = "Compatible"
        confidence = base_confidence
    elif res_fails and src_fails:
        status = "No compatible"
        confidence = base_confidence * 0.30
    else:
        status = "Parcial"
        confidence = base_confidence * 0.60

    # A spec-compatible match whose file isn't actually on disk (Faltante, en
    # cola, error…) can't fulfil the request — surface it as "No disponible" so
    # it doesn't pollute the "Compatible" filter, while still telling you the
    # library has an entry for it (worth re-downloading).
    if status == "Compatible" and not _item_available(item):
        status = "No disponible"

    return {
        "status": status,
        "confidence": confidence,
        "resolution_match": None if res_match is None else bool(res_match),
        "source_match": None if src_match is None else bool(src_match),
        "id_match": id_match,
        "title_match": title_match,
        "reasons": reasons,
    }


def rank_request_matches(matches: list[dict]) -> list[dict]:
    """
    Sort enriched request dicts by compatibility priority.

    Each dict must have: compatibility_status, library_item (optional).
    """
    _STATUS = {"Compatible": 0, "No disponible": 1, "Parcial": 2, "No compatible": 3,
               "Pendiente": 4, "Reclamado": 5, "Llena": 6}
    # "Parcial" here is a series/season rollup local_status (some but not
    # all children available) — explicit entry documenting it ranks at the
    # same default as everything else not fully available/uploaded, rather
    # than leaving it an unexplained gap.
    _LOCAL = {"Disponible": 0, "Subido": 1, "Parcial": 2}
    _NOMEN = {"Correcta": 0, "No adaptada": 1, "N/A": 2}

    def _key(m: dict) -> tuple:
        s = _STATUS.get(m.get("compatibility_status", ""), 5)
        lib = m.get("library_item") or {}
        l = _LOCAL.get(lib.get("local_status", ""), 2)
        n = _NOMEN.get(lib.get("nomenclature_status", ""), 2)
        c = -(m.get("compatibility_confidence") or 0.0)
        return (s, l, n, c)

    return sorted(matches, key=_key)


__all__ = [
    "normalize_title", "compact_title",
    "parse_resolution", "parse_source",
    "compare_resolution", "compare_source",
    "match_request_to_library", "classify_request_match",
    "rank_request_matches",
]
