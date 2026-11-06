"""Subprocess wrapper for the engine's external tools.

Every call to mediainfo/ffprobe/mkvmerge goes through `run()` below: a fixed
argv list (never a shell string — no injection surface), a timeout, captured
stdout/stderr, a size cap on captured output, and a uniform result shape so
callers never need to special-case "tool missing" vs "tool crashed" vs
"tool timed out" vs "tool produced garbage".
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Optional

from .constants import TOOL_TIMEOUT_S
from ...integrations.base import texto_de_error

log = logging.getLogger("emuwarez.source_engine")

# Captured stdout above this size is truncated — a pathological file (huge
# chapter/tag list) shouldn't let a tool call balloon memory or the cache row.
MAX_OUTPUT_BYTES = 32 * 1024 * 1024


@dataclass
class ToolResult:
    tool: str
    ok: bool
    returncode: Optional[int]
    duration_s: float
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    truncated: bool = False

    def json(self) -> Optional[Any]:
        if not self.ok or not self.stdout:
            return None
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError as exc:
            log.warning("%s produced invalid JSON: %s", self.tool, exc)
            return None


@dataclass
class ToolAvailability:
    available: bool
    path: Optional[str] = None
    version: Optional[str] = None


_VERSION_CACHE: dict[str, ToolAvailability] = {}


def which(tool: str) -> Optional[str]:
    return shutil.which(tool)


def run(tool: str, args: list[str], *, timeout: float = TOOL_TIMEOUT_S) -> ToolResult:
    """Run `tool` with `args` (argv list — never shell-interpolated), bounded
    by `timeout` seconds. Never raises: any failure mode (missing binary,
    non-zero exit, timeout, huge output) comes back as a ToolResult with
    `ok=False` and a human-readable `error`."""
    path = which(tool)
    if not path:
        return ToolResult(tool=tool, ok=False, returncode=None, duration_s=0.0,
                           error=f"{tool} no está instalado en este entorno")

    argv = [path, *args]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - started
        return ToolResult(tool=tool, ok=False, returncode=None, duration_s=duration,
                           error=f"{tool} superó el timeout de {timeout:.0f}s")
    except OSError as exc:
        duration = time.monotonic() - started
        return ToolResult(tool=tool, ok=False, returncode=None, duration_s=duration,
                           error=f"{tool} falló al ejecutarse: {texto_de_error(exc)}")

    duration = time.monotonic() - started
    stdout, truncated = _cap(proc.stdout or "")
    stderr, _ = _cap(proc.stderr or "", limit=8192)
    if proc.returncode != 0:
        return ToolResult(tool=tool, ok=False, returncode=proc.returncode, duration_s=duration,
                           stdout=stdout, stderr=stderr, truncated=truncated,
                           error=(stderr.strip() or f"{tool} devolvió el código {proc.returncode}"))
    return ToolResult(tool=tool, ok=True, returncode=0, duration_s=duration,
                       stdout=stdout, stderr=stderr, truncated=truncated)


def _cap(text: str, limit: int = MAX_OUTPUT_BYTES) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def availability(tool: str, version_args: tuple[str, ...] = ("--version",)) -> ToolAvailability:
    """Cached (per-process) availability + version probe — called once per
    tool per analysis at most, never per-evidence-detector."""
    cached = _VERSION_CACHE.get(tool)
    if cached is not None:
        return cached
    path = which(tool)
    if not path:
        result = ToolAvailability(available=False)
        _VERSION_CACHE[tool] = result
        return result
    probe = run(tool, list(version_args), timeout=3.0)
    version = None
    if probe.ok or probe.stdout or probe.stderr:
        first_line = (probe.stdout or probe.stderr or "").strip().splitlines()
        version = first_line[0] if first_line else None
    result = ToolAvailability(available=True, path=path, version=version)
    _VERSION_CACHE[tool] = result
    return result
