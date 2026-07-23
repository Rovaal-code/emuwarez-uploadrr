"""Bounded bitstream sampling — spec section 13.

Reads a handful of short frame windows (never the whole file) at ~5 relative
positions across the video, using ffprobe's `-read_intervals` to seek near
each position and decode only a fixed number of frames from there. This is
the one part of the engine whose cost depends on the storage backend (a
network mount can make even a "cheap" seek slow), so it is always optional
and budget-bounded: on a slow/degraded mount it silently contributes fewer
samples (or none) rather than blocking the analysis.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import tools
from .budget import Budget
from .constants import SAMPLE_FRAMES_PER_WINDOW, SAMPLE_POSITIONS

log = logging.getLogger("emuwarez.source_engine")

# Per-call timeout for one sampling window — short on purpose; a call that
# doesn't return in this long is abandoned (proc.py kills the subprocess),
# and that sample position is simply missing from the result.
PER_SAMPLE_TIMEOUT_S = 2.5
# Never spend more of the global budget on sampling than this, even if the
# rest of the analysis finished early — sampling is a refinement, not the
# primary signal.
MAX_SAMPLING_BUDGET_S = 4.0


@dataclass
class FrameWindow:
    position_pct: float
    ok: bool
    frame_count: int = 0
    avg_frame_bytes: float = 0.0
    local_bitrate_bps: float = 0.0
    i_count: int = 0
    p_count: int = 0
    b_count: int = 0
    keyframe_count: int = 0
    gop_lengths: list[int] = field(default_factory=list)
    error: str | None = None


@dataclass
class SampleResult:
    windows: list[FrameWindow]
    positions_requested: int
    positions_completed: int
    coverage: float  # positions_completed / positions_requested
    duration_s: float
    skipped_reason: str | None = None

    @property
    def any_ok(self) -> bool:
        return any(w.ok for w in self.windows)


def _one_window(path: str, fps: float | None, position_pct: float, timeout: float) -> FrameWindow:
    data, result = tools.ffprobe_frames_window(
        path, start_pct=position_pct, frame_count=SAMPLE_FRAMES_PER_WINDOW, timeout=timeout,
    )
    if not result.ok or not data:
        return FrameWindow(position_pct=position_pct, ok=False, error=result.error or "sin datos")

    frames = data.get("frames") or []
    if not frames:
        return FrameWindow(position_pct=position_pct, ok=False, error="ffprobe no devolvió frames en esa ventana")

    i = p = b = kf = 0
    sizes: list[int] = []
    gop_lengths: list[int] = []
    since_keyframe = 0
    for fr in frames:
        pict = (fr.get("pict_type") or "").upper()
        if pict == "I":
            i += 1
        elif pict == "P":
            p += 1
        elif pict == "B":
            b += 1
        try:
            sizes.append(int(fr.get("pkt_size") or 0))
        except (TypeError, ValueError):
            pass
        is_key = str(fr.get("key_frame")) == "1"
        if is_key:
            kf += 1
            if since_keyframe > 0:
                gop_lengths.append(since_keyframe)
            since_keyframe = 0
        else:
            since_keyframe += 1

    avg_bytes = (sum(sizes) / len(sizes)) if sizes else 0.0
    local_bitrate = (avg_bytes * 8 * fps) if (fps and fps > 0) else 0.0
    return FrameWindow(
        position_pct=position_pct, ok=True, frame_count=len(frames),
        avg_frame_bytes=avg_bytes, local_bitrate_bps=local_bitrate,
        i_count=i, p_count=p, b_count=b, keyframe_count=kf, gop_lengths=gop_lengths,
    )


def sample_bitstream(path: str, *, fps: float | None, budget: Budget) -> SampleResult:
    """Best-effort: tries up to len(SAMPLE_POSITIONS) windows in parallel,
    bounded by both the per-call timeout and the smaller of the remaining
    global budget / MAX_SAMPLING_BUDGET_S. Never raises."""
    import time
    started = time.monotonic()
    sampling_budget = min(budget.remaining(), MAX_SAMPLING_BUDGET_S)
    if sampling_budget < 0.5:
        return SampleResult(windows=[], positions_requested=len(SAMPLE_POSITIONS),
                             positions_completed=0, coverage=0.0, duration_s=0.0,
                             skipped_reason="presupuesto de tiempo agotado antes del muestreo")

    per_call_timeout = min(PER_SAMPLE_TIMEOUT_S, sampling_budget)
    windows: list[FrameWindow] = []
    with ThreadPoolExecutor(max_workers=len(SAMPLE_POSITIONS)) as pool:
        futures = {
            pool.submit(_one_window, path, fps, pct * 100.0, per_call_timeout): pct
            for pct in SAMPLE_POSITIONS
        }
        try:
            for fut in as_completed(futures, timeout=sampling_budget):
                try:
                    windows.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    log.warning("sampling window failed: %s", exc)
        except TimeoutError:
            pass  # whatever completed, completed — the rest is simply missing

    completed = sum(1 for w in windows if w.ok)
    return SampleResult(
        windows=windows, positions_requested=len(SAMPLE_POSITIONS),
        positions_completed=completed,
        coverage=(completed / len(SAMPLE_POSITIONS)) if SAMPLE_POSITIONS else 0.0,
        duration_s=time.monotonic() - started,
    )
