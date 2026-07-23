"""Multi-tool video source detector (MediaInfo + FFprobe + MKVToolNix).

Public entry point: `analyze(path, radarr_source=None)` — see `engine.analyze`
for the full contract. Everything here is read-only: no file is modified, no
network call is made, and every subprocess call carries a timeout budget (see
`proc.py`).
"""
from .engine import analyze
from .constants import CANDIDATES, ENGINE_VERSION
from .integration import analyze_for_app, winning_app_source, ENGINE_TO_APP_SOURCE

__all__ = [
    "analyze", "CANDIDATES", "ENGINE_VERSION",
    "analyze_for_app", "winning_app_source", "ENGINE_TO_APP_SOURCE",
]
