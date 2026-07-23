"""Thin JSON-producing wrappers around the three tools this engine uses.

Each function returns `(data, ToolResult)` — `data` is the parsed JSON (or
None on any failure), `ToolResult` carries timing/error/availability detail
for the output's `tools` section. Callers never need to catch exceptions.
"""
from __future__ import annotations

from typing import Any, Optional

from . import proc
from .constants import TOOL_TIMEOUT_S


def mediainfo_full(path: str, *, timeout: float = TOOL_TIMEOUT_S) -> tuple[Optional[dict], proc.ToolResult]:
    result = proc.run("mediainfo", ["--Output=JSON", "--Full", path], timeout=timeout)
    return result.json(), result


def ffprobe_format_streams(path: str, *, timeout: float = TOOL_TIMEOUT_S) -> tuple[Optional[dict], proc.ToolResult]:
    result = proc.run(
        "ffprobe",
        [
            "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", "-show_chapters",
            path,
        ],
        timeout=timeout,
    )
    return result.json(), result


def ffprobe_frames_window(
    path: str, *, start_pct: float, stream_index: int = 0, frame_count: int,
    timeout: float,
) -> tuple[Optional[dict], proc.ToolResult]:
    """Frame-level info (type/size/keyframe) for a short window starting at
    `start_pct` of the file's `-read_intervals` position — ffprobe seeks near
    that point and decodes only `frame_count` frames from there, never the
    whole stream. `start_pct` is a percentage string understood by ffprobe's
    `-read_intervals` mini-language (e.g. "25%+#96")."""
    interval = f"{start_pct:.2f}%+#{frame_count}"
    result = proc.run(
        "ffprobe",
        [
            "-v", "quiet", "-print_format", "json",
            "-select_streams", f"v:{stream_index}",
            "-read_intervals", interval,
            "-show_entries", "frame=pict_type,pkt_size,key_frame,pkt_pts_time",
            path,
        ],
        timeout=timeout,
    )
    return result.json(), result


def mkvmerge_identify(path: str, *, timeout: float = TOOL_TIMEOUT_S) -> tuple[Optional[dict], proc.ToolResult]:
    result = proc.run("mkvmerge", ["-J", path], timeout=timeout)
    return result.json(), result


def tool_versions() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for tool, args in (
        ("mediainfo", ("--Version",)),
        ("ffprobe", ("-version",)),
        ("mkvmerge", ("--version",)),
    ):
        avail = proc.availability(tool, args)
        out[tool] = {"available": avail.available, "version": avail.version}
    return out
