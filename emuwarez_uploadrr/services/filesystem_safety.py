"""Read-only filesystem inspection utilities.

SAFETY CONTRACT: This module never modifies the filesystem.
No rename, delete, move, hardlink, mkdir, or subprocess execution.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts", ".wmv", ".flv", ".webm", ".iso", ".m4v"
}


def path_exists(path: str) -> bool:
    return bool(path) and Path(path).exists()


def is_file(path: str) -> bool:
    return bool(path) and Path(path).is_file()


def is_video_file(path: str) -> bool:
    if not is_file(path):
        return False
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def safe_stat(path: str) -> dict[str, Any]:
    """Return basic stat info for a path, never raises."""
    result: dict[str, Any] = {
        "exists": False,
        "is_file": False,
        "is_dir": False,
        "is_video": False,
        "size_bytes": None,
        "extension": None,
        "name": None,
        "parent": None,
    }
    try:
        p = Path(path)
        result["name"] = p.name
        result["parent"] = str(p.parent)
        result["extension"] = p.suffix.lower()
        if p.exists():
            result["exists"] = True
            result["is_file"] = p.is_file()
            result["is_dir"] = p.is_dir()
            result["is_video"] = p.suffix.lower() in VIDEO_EXTENSIONS
            if p.is_file():
                result["size_bytes"] = p.stat().st_size
    except (OSError, PermissionError):
        pass
    return result
