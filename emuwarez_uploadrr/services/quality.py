"""Helpers for extracting quality, resolution and source from *Arr responses."""
from __future__ import annotations

import re
from typing import Optional

_RE_RES = re.compile(r"\b(2160p?|4k|1080p?|720p?|576p?|480p?)\b", re.I)
_RE_SOURCE = re.compile(
    r"\b(remux|bdrip|bremux|bdremux|web[-\s]?dl|webrip|web[-\s]?rip|bluray|blu[-\s]?ray|hdtv|dvd|hdcam|cam)\b",
    re.I,
)

_RES_MAP = {
    "2160": "2160p", "4k": "2160p",
    "1080": "1080p",
    "720": "720p",
    "576": "576p",
    "480": "480p",
}

_SOURCE_MAP = {
    "remux": "BDRemux", "bdremux": "BDRemux", "bdrip": "BDRemux", "bremux": "BDRemux",
    "web-dl": "WEB-DL", "webdl": "WEB-DL",
    "webrip": "WEBRip", "web-rip": "WEBRip",
    "bluray": "BluRay", "blu-ray": "BluRay", "blu ray": "BluRay",
    "hdtv": "HDTV",
    "dvd": "DVD",
    "hdcam": "HDCAM",
    "cam": "CAM",
}


def _norm_res(m: str) -> str:
    key = re.sub(r"p$", "", m.lower().replace(" ", ""))
    return _RES_MAP.get(key, m.upper())


def _norm_source(m: str) -> str:
    key = re.sub(r"[\s-]", "", m.lower())
    return _SOURCE_MAP.get(key, m)


def extract_quality_name(raw: dict) -> Optional[str]:
    """Return quality.quality.name from a *Arr quality wrapper, or None."""
    quality = raw.get("quality") or {}
    if isinstance(quality, dict):
        inner = quality.get("quality") or {}
        if isinstance(inner, dict):
            return inner.get("name") or None
    return None


def extract_resolution(raw: dict) -> Optional[str]:
    """Return resolution string (e.g. '1080p') from quality wrapper or None."""
    name = extract_quality_name(raw) or ""
    # Try resolution from quality name first
    m = _RE_RES.search(name)
    if m:
        return _norm_res(m.group(1))
    # Try from a path if available
    path = raw.get("path") or raw.get("relativePath") or ""
    m = _RE_RES.search(path)
    if m:
        return _norm_res(m.group(1))
    return None


def extract_source_from_quality(raw: dict) -> Optional[str]:
    """Return source string from quality.quality.name."""
    name = extract_quality_name(raw) or ""
    m = _RE_SOURCE.search(name)
    if m:
        return _norm_source(m.group(1))
    return None


def extract_source_from_title_or_path(
    title: Optional[str], path: Optional[str]
) -> Optional[str]:
    """Return source string by scanning title and/or file path."""
    for text in (title or "", path or ""):
        m = _RE_SOURCE.search(text)
        if m:
            return _norm_source(m.group(1))
    return None
