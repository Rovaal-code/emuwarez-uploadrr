"""Shared constants for the source-detection engine.

Candidate codes match the official eMuwarez nomenclature guide exactly
(references/nomenclatura-emuwarez.md, "Formato (Source)" table) — this is a
different vocabulary from `services/source_assistant.py::EMU_SOURCES` (the
app's *selectable* source field, which still says "Full BluRay"/"WEBRip" for
backward compatibility with data already stored under those codes). The
mapping between the two lives in `integration.py`.
"""
from __future__ import annotations

# Order matters only for display; scoring/ranking always sorts by score.
CANDIDATES: tuple[str, ...] = (
    "FBD", "FDVD", "BDRemux", "BluRay", "MHD", "WEB-DL", "WEBRIP", "HDTV", "SD",
)

# Bumped whenever scoring rules or the extracted feature set change in a way
# that could change past results — invalidates the on-disk cache (cache.py).
ENGINE_VERSION = "1.0.0"

# Global wall-clock budget for one full analysis (spec section 5). Individual
# tool/sampling steps carry their own smaller sub-budgets (see proc.py callers)
# so a single slow step degrades gracefully instead of blowing the whole run.
DEFAULT_BUDGET_S = 10.0

# Per-tool subprocess timeout — generous relative to typical runtimes (a full
# `mediainfo --Full` or `mkvmerge -J` on a multi-GB file finishes in under a
# second; ffprobe's bounded frame sampling is the only step that can approach
# a couple of seconds) while still bounding a hung/corrupt-file call.
TOOL_TIMEOUT_S = 6.0

# Bitstream sampling: 5 relative positions across the video, each a short
# window of frames — never a full decode (spec section 13).
SAMPLE_POSITIONS = (0.02, 0.25, 0.50, 0.75, 0.95)
SAMPLE_FRAMES_PER_WINDOW = 96

# Certainty labels by normalized-score margin (percentage points between
# winner and runner-up). Purely descriptive — the winner is chosen by raw
# score regardless of how these are labeled.
CERTAINTY_THRESHOLDS = (
    (40.0, "alto"),
    (15.0, "medio"),
    (0.0, "bajo"),
)


def certainty_label(margin_pp: float) -> str:
    for threshold, label in CERTAINTY_THRESHOLDS:
        if margin_pp >= threshold:
            return label
    return "bajo"
