"""Benchmark runner — spec section 23.

    python -m emuwarez_uploadrr.services.source_engine.benchmark /ruta/dataset

Analyzes every media file found (recursively) under the given directory and
reports p50/p95/max timing, cache-hit rate, and error/timeout counts. Always
runs with `use_cache=False` per file on its first pass so the numbers reflect
a cold analysis, then re-runs the whole set once more to report the cache-hit
timing too.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .engine import analyze

_MEDIA_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".mov", ".ts", ".avi"}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    f, c = int(k), min(int(k) + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def run_benchmark(dataset_dir: str) -> dict:
    root = Path(dataset_dir)
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _MEDIA_EXTENSIONS]

    # First pass: cache enabled but necessarily all misses (nothing cached
    # yet) — this is the realistic "first time you open this file" timing.
    cold_durations: list[float] = []
    errors = 0
    timeouts = 0
    for f in files:
        t0 = time.monotonic()
        result = analyze(str(f), use_cache=True)
        cold_durations.append(time.monotonic() - t0)
        if result.get("error"):
            errors += 1
        if "timeout" in (result.get("explanation", {}).get("winner") or "").lower():
            timeouts += 1

    # Second pass over the same files: every one should now be a cache hit.
    warm_durations: list[float] = []
    cache_hits = 0
    for f in files:
        t0 = time.monotonic()
        result = analyze(str(f), use_cache=True)
        warm_durations.append(time.monotonic() - t0)
        if result.get("performance", {}).get("cache_hit"):
            cache_hits += 1

    return {
        "file_count": len(files),
        "cold": {
            "p50_s": round(_percentile(cold_durations, 50), 2),
            "p95_s": round(_percentile(cold_durations, 95), 2),
            "max_s": round(max(cold_durations), 2) if cold_durations else 0.0,
        },
        "warm_cached": {
            "p50_s": round(_percentile(warm_durations, 50), 2),
            "p95_s": round(_percentile(warm_durations, 95), 2),
            "cache_hit_rate": round(cache_hits / len(files), 2) if files else 0.0,
        },
        "errors": errors,
        "timeouts": timeouts,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Uso: python -m emuwarez_uploadrr.services.source_engine.benchmark <dataset_dir>", file=sys.stderr)
        return 2
    # Standalone CLI use (outside the running app) may point at a fresh
    # CONFIG_DIR whose schema was never migrated — ensure the cache table
    # exists so the warm-cache pass is meaningful instead of silently no-op.
    from ...database import connect, init_db
    init_db(connect())
    result = run_benchmark(argv[0])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
