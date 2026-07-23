"""Boundary between the engine's own vocabulary (CANDIDATES, matching the
official eMuwarez guide letter-for-letter) and the app's existing selectable
source field (`services/source_assistant.py::EMU_SOURCES`), which still uses
"Full BluRay"/"WEBRip" for backward compatibility with data already stored
under those codes.

Only this module needs to know both vocabularies exist — everything inside
`source_engine/` speaks the guide's codes exclusively.
"""
from __future__ import annotations

import logging

from .constants import DEFAULT_BUDGET_S
from .engine import analyze

logger = logging.getLogger(__name__)

# Engine candidate -> app EMU_SOURCES code. Identity except the two codes the
# app still spells out the old way; see module docstring.
ENGINE_TO_APP_SOURCE: dict[str, str] = {
    "FBD": "Full BluRay",
    "FDVD": "FDVD",
    "BDRemux": "BDRemux",
    "BluRay": "BluRay",
    "MHD": "MHD",
    "WEB-DL": "WEB-DL",
    "WEBRIP": "WEBRip",
    "HDTV": "HDTV",
    "SD": "SD",
}


def analyze_for_app(path: str, *, radarr_source: str | None = None, conn=None) -> dict | None:
    """Runs the engine and returns its raw result, or None if analysis
    couldn't run at all (missing file, every tool unavailable/failed) —
    callers should fall back to their own simpler heuristic in that case,
    never crash the request over it."""
    try:
        result = analyze(path, radarr_source=radarr_source, budget_s=DEFAULT_BUDGET_S, conn=conn)
    except Exception:  # noqa: BLE001 — this is a best-effort refinement, not a hard dependency
        logger.warning("source_engine analysis failed for %s", path, exc_info=True)
        return None
    if result.get("error"):
        return None
    return result


def winning_app_source(result: dict | None) -> str | None:
    if not result:
        return None
    label = (result.get("prediction") or {}).get("label")
    return ENGINE_TO_APP_SOURCE.get(label) if label else None
