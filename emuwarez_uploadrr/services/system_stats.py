"""Live host resource usage for the sidebar's "System Status" gauges
(CPU/RAM/disk/network, plus GPU/VRAM when an NVIDIA GPU is present).

Everything here is best-effort: a missing GPU, an unreadable disk path or a
psutil hiccup must never break the sidebar — every helper degrades to a safe
default instead of raising.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time

import psutil

from ..constants import CONFIG_DIR

# psutil.cpu_percent() with no interval returns 0.0 (or the since-boot
# average) on its very first call, then the real delta on every call after
# that — priming it once at import time means the *first* request already
# gets a meaningful number instead of a misleading 0%.
psutil.cpu_percent(interval=None)

# Network counters are cumulative since boot — rates need a delta between two
# samples. Kept as module state (one process, one set of counters) rather
# than per-request, since a single sample can't produce a rate at all.
_net_prev: tuple[float, int, int] | None = None


def _net_rates() -> tuple[float, float]:
    """(download bytes/sec, upload bytes/sec) since the previous call. The
    very first call after startup has nothing to diff against, so it
    reports 0/0 — the next call (a few seconds later, from the frontend's
    own poll interval) gives the real rate."""
    global _net_prev
    try:
        counters = psutil.net_io_counters()
    except Exception:
        return 0.0, 0.0
    now = time.monotonic()
    if _net_prev is None:
        _net_prev = (now, counters.bytes_recv, counters.bytes_sent)
        return 0.0, 0.0
    prev_t, prev_recv, prev_sent = _net_prev
    dt = max(now - prev_t, 0.001)
    down = max(0.0, (counters.bytes_recv - prev_recv) / dt)
    up = max(0.0, (counters.bytes_sent - prev_sent) / dt)
    _net_prev = (now, counters.bytes_recv, counters.bytes_sent)
    return down, up


def _gpu_stats() -> dict | None:
    """First NVIDIA GPU's utilization/VRAM via `nvidia-smi`, or None when
    there's no NVIDIA GPU / no driver installed — no GPU is a normal,
    expected case, not an error."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=2,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        name, util, mem_used, mem_total = [p.strip() for p in result.stdout.strip().splitlines()[0].split(",")]
        mem_used_mb, mem_total_mb = float(mem_used), float(mem_total)
        return {
            "name": name,
            "percent": float(util),
            "vram_used_gb": round(mem_used_mb / 1024, 2),
            "vram_total_gb": round(mem_total_mb / 1024, 2),
            "vram_percent": round(mem_used_mb / mem_total_mb * 100, 1) if mem_total_mb else 0.0,
        }
    except Exception:
        return None


def _library_disk_path(conn) -> str:
    """Directory of some real, currently-reachable library file — measuring
    disk usage there answers "how full is the disk the library lives on",
    which can be a completely different filesystem than the app's own
    CONFIG_DIR (e.g. a media library mounted over SSHFS/NFS). Falls back to
    CONFIG_DIR when the library is empty or nothing is reachable yet."""
    from .path_mapping import resolve_local_path
    try:
        rows = conn.execute(
            "SELECT prepared_path, path FROM library_items "
            "WHERE prepared_path IS NOT NULL OR path IS NOT NULL LIMIT 200"
        ).fetchall()
    except Exception:
        rows = []
    for row in rows:
        raw = row["prepared_path"] or row["path"]
        local = resolve_local_path(raw, conn)
        if not local:
            continue
        p = os.path.dirname(local)
        # Walk up to the nearest existing ancestor — the file itself may
        # have moved/been deleted since the last sync, but its mount point
        # almost certainly still exists.
        while p and p not in ("/", ""):
            if os.path.exists(p):
                return p
            p = os.path.dirname(p)
    return str(CONFIG_DIR)


def get_system_stats(conn) -> dict:
    vm = psutil.virtual_memory()
    disk_path = _library_disk_path(conn)
    try:
        du = shutil.disk_usage(disk_path)
        disk_total, disk_used = du.total, du.used
    except Exception:
        disk_total, disk_used = 0, 0
    down, up = _net_rates()
    gpu = _gpu_stats()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_percent": vm.percent,
        "ram_used_gb": round(vm.used / (1024 ** 3), 2),
        "ram_total_gb": round(vm.total / (1024 ** 3), 2),
        "disk_path": disk_path,
        "disk_used_gb": round(disk_used / (1024 ** 3), 2),
        "disk_total_gb": round(disk_total / (1024 ** 3), 2),
        "disk_percent": round(disk_used / disk_total * 100, 1) if disk_total else 0.0,
        "net_down_bps": round(down, 1),
        "net_up_bps": round(up, 1),
        "gpu": gpu,
    }
