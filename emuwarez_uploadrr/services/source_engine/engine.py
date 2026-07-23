"""Orchestrator: ties tools -> profile -> evidence -> scoring into the one
public `analyze()` call (spec section 20 output shape).

Performance strategy (spec sections 5-7):
  - The 3 primary tools (mediainfo, ffprobe format/streams, mkvmerge) run in
    parallel — their cost is dominated by I/O (reading the container's own
    index/headers), not CPU, so wall time is roughly the slowest of the
    three rather than their sum.
  - Bitstream sampling (sampling.py) only runs with whatever budget is left
    after those three return, and is skipped entirely rather than blocking
    the result if the budget's gone (e.g. a slow network mount).
  - Everything is wrapped in one global `Budget`; nothing waits past it.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from . import cache, evidence, names, profile, scoring, tools, transcode
from .budget import Budget
from .constants import CANDIDATES, DEFAULT_BUDGET_S, ENGINE_VERSION
from .sampling import MAX_SAMPLING_BUDGET_S, sample_bitstream

log = logging.getLogger("emuwarez.source_engine")


def analyze(path: str, *, radarr_source: Optional[str] = None,
            budget_s: float = DEFAULT_BUDGET_S, use_cache: bool = True,
            conn=None) -> dict:
    if use_cache:
        cached = cache.get(path, conn=conn)
        if cached is not None:
            cached = dict(cached)
            cached["performance"] = {**cached.get("performance", {}), "cache_hit": True}
            return cached

    budget = Budget(budget_s)
    p = Path(path)
    extension = p.suffix.lstrip(".").lower()
    is_mkv = extension in ("mkv", "mka", "mks")

    try:
        size_bytes = p.stat().st_size
    except OSError as exc:
        return _error_result(f"Archivo no accesible: {exc}")

    # --- 1. Run the 3 primary tools in parallel -----------------------------
    # They run concurrently, so giving each nearly the whole remaining budget
    # costs at most the SLOWEST of the three in wall time, not their sum —
    # only a slice is held back for the optional sampling phase afterward.
    primary_timeout = max(2.0, budget.remaining() - MAX_SAMPLING_BUDGET_S)
    with ThreadPoolExecutor(max_workers=3) as pool:
        mi_future = pool.submit(tools.mediainfo_full, str(p), timeout=primary_timeout)
        ff_future = pool.submit(tools.ffprobe_format_streams, str(p), timeout=primary_timeout)
        mkv_future = (pool.submit(tools.mkvmerge_identify, str(p), timeout=primary_timeout)
                      if is_mkv else None)

        mediainfo_json, mi_result = mi_future.result()
        ffprobe_json, ff_result = ff_future.result()
        if mkv_future is not None:
            mkvmerge_json, mkv_result = mkv_future.result()
        else:
            mkvmerge_json, mkv_result = None, None

    if mediainfo_json is None and ffprobe_json is None and mkvmerge_json is None:
        return _error_result(
            "Ninguna herramienta (MediaInfo/FFprobe/MKVToolNix) pudo leer el archivo: "
            + (mi_result.error or ff_result.error or "error desconocido")
        )

    # --- 2. Build the canonical profile -------------------------------------
    container = profile.build_container(mediainfo_json, ffprobe_json, mkvmerge_json, extension=extension)
    video = profile.build_video(mediainfo_json, ffprobe_json)
    audio_tracks = profile.build_audio_tracks(mediainfo_json, ffprobe_json, mkvmerge_json)
    subtitle_tracks = profile.build_subtitle_tracks(mediainfo_json, ffprobe_json, mkvmerge_json)
    name_tags = names.tag_all_tracks(audio_tracks)
    topology = profile.build_topology(audio_tracks, subtitle_tracks, container, name_tags)

    duration_s = video.get("duration_s") or _format_duration(ffprobe_json)
    file_info = profile.build_file_info(size_bytes, duration_s)
    normalization = profile.build_normalization(video, file_info, audio_tracks)

    media_profile = {
        "input": {"path": str(p), "extension": extension, "size_bytes": size_bytes, "duration_seconds": duration_s},
        "container": container, "video": video,
        "audio_tracks": audio_tracks, "subtitle_tracks": subtitle_tracks,
        "topology": topology, "file": file_info, "normalization": normalization,
    }

    # --- 3. Transcode signals (cheap, header-only) --------------------------
    transcode_signals = transcode.analyze_transcode_signals(video)

    # --- 4. Bitstream sampling — best-effort, whatever budget remains ------
    sample_result = None
    if budget.remaining() > 0.5:
        sample_result = sample_bitstream(str(p), fps=video.get("fps"), budget=budget)

    # --- 5. Evidence + scoring ----------------------------------------------
    all_evidence = evidence.collect_all_evidence(media_profile, transcode_signals, sample_result)
    result = scoring.score_candidates(all_evidence)
    explanation = scoring.build_explanation(all_evidence, result)
    contradictions = scoring.find_contradictions(all_evidence, result)

    duration_ms = int(budget.elapsed() * 1000)
    output = {
        "prediction": {
            "label": result.winner.label,
            "raw_score": round(result.winner.raw_score, 2),
            "confidence_score": round(result.winner.normalized_score, 4),
            "certainty": result.certainty,
            "runner_up": result.runner_up.label,
            "runner_up_score": round(result.runner_up.normalized_score, 4),
            "margin": round(result.margin_pp / 100.0, 4),
            "evidence_strength": round(result.evidence_strength, 2),
        },
        "performance": {
            "duration_ms": duration_ms,
            "timeout_ms": int(budget_s * 1000),
            "cache_hit": False,
            "sample_coverage": round(sample_result.coverage, 2) if sample_result else 0.0,
        },
        "ranking": [
            {"label": c.label, "raw_score": round(c.raw_score, 2),
             "normalized_score": round(c.normalized_score, 4), "rank": c.ranking_position}
            for c in result.ranking
        ],
        "media": media_profile,
        "features": {
            "transcode": {
                "video_transcode_probability": round(transcode_signals.video_transcode_probability, 2),
                "video_stream_untouched_probability": round(transcode_signals.video_stream_untouched_probability, 2),
                "screen_capture_probability": round(transcode_signals.screen_capture_probability, 2),
                "encoder_name": transcode_signals.encoder_name,
                "crf": transcode_signals.crf,
                "two_pass": transcode_signals.two_pass,
            },
        },
        "evidence": [
            {"feature": e.feature, "value": e.value, "strength": e.strength,
             "reliability": round(e.reliability, 2), "explanation": e.explanation,
             "contributions": {k: round(v, 2) for k, v in e.effective().items() if abs(v) >= 0.05}}
            for e in all_evidence
        ],
        "contradictions": contradictions,
        "explanation": explanation,
        "tools": {
            **tools.tool_versions(),
            "mediainfo": {**tools.tool_versions()["mediainfo"], "used": mediainfo_json is not None,
                          "error": None if mi_result.ok else mi_result.error},
            "ffprobe": {**tools.tool_versions()["ffprobe"], "used": ffprobe_json is not None,
                        "error": None if ff_result.ok else ff_result.error},
            "mkvmerge": {**tools.tool_versions()["mkvmerge"], "used": mkvmerge_json is not None,
                         "error": None if (mkv_result is None or mkv_result.ok) else mkv_result.error,
                         "applicable": is_mkv},
        },
        "engine_version": ENGINE_VERSION,
    }

    if use_cache:
        cache.put(path, output, conn=conn)
    return output


def _format_duration(ffprobe_json: Optional[dict]) -> Optional[float]:
    if not ffprobe_json:
        return None
    try:
        return float((ffprobe_json.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        return None


def _error_result(message: str) -> dict:
    """Even a total failure still returns the full 9-candidate shape (never
    `unknown`) — every candidate at the structural floor, SD arbitrarily
    first just to have a deterministic, harmless default; `certainty` is
    "bajo" and the message is front and center in `explanation`."""
    ranking = [
        {"label": c, "raw_score": -60.0, "normalized_score": round(1.0 / len(CANDIDATES), 4), "rank": i + 1}
        for i, c in enumerate(CANDIDATES)
    ]
    return {
        "prediction": {
            "label": CANDIDATES[0], "raw_score": -60.0, "confidence_score": round(1.0 / len(CANDIDATES), 4),
            "certainty": "bajo", "runner_up": CANDIDATES[1],
            "runner_up_score": round(1.0 / len(CANDIDATES), 4), "margin": 0.0, "evidence_strength": 0.0,
        },
        "performance": {"duration_ms": 0, "timeout_ms": int(DEFAULT_BUDGET_S * 1000), "cache_hit": False, "sample_coverage": 0.0},
        "ranking": ranking,
        "media": {}, "features": {}, "evidence": [], "contradictions": [],
        "explanation": {"winner": message, "winner_vs_runner_up": ""},
        "tools": tools.tool_versions(),
        "engine_version": ENGINE_VERSION,
        "error": message,
    }
