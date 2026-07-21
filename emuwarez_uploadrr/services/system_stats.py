"""Live host resource usage for the sidebar's "System Status" gauges
(CPU/RAM/disk/network, plus GPU/VRAM when an NVIDIA GPU is present).

Everything here is best-effort: a missing GPU, an unreadable disk path or a
psutil hiccup must never break the sidebar — every helper degrades to a safe
default instead of raising.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time

import psutil

from ..constants import CONFIG_DIR

_cpu_name_cache: str | None = None


def _cpu_name() -> str:
    """Best-effort CPU model name — cached, since it never changes for the
    life of the process and /proc/cpuinfo is a bit of a waste to re-read on
    every poll."""
    global _cpu_name_cache
    if _cpu_name_cache is not None:
        return _cpu_name_cache
    name = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    name = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass
    if not name:
        name = platform.processor() or platform.machine() or "CPU"
    _cpu_name_cache = name
    return name

# psutil.cpu_percent() with no interval returns 0.0 (or the since-boot
# average) on its very first call, then the real delta on every call after
# that — priming it once at import time means the *first* request already
# gets a meaningful number instead of a misleading 0%.
psutil.cpu_percent(interval=None)


# ---------------------------------------------------------------------------
# Container-aware CPU/RAM — psutil's cpu_percent()/virtual_memory() read
# host-wide /proc data. That's correct on bare metal, but wrong once this
# runs inside a Docker/Podman/Kubernetes container with its own cgroup
# limits: the host might show 8% RAM used while the container is at 90% of
# what it was actually granted. When a real (finite) cgroup limit is
# present, prefer it; when there's no limit (or no cgroup at all — the dev/
# bare-host case), the host-wide view *is* the right answer, since the
# process could use up to the whole host anyway.
# ---------------------------------------------------------------------------

def _cgroup_mem_stats() -> tuple[int, int] | None:
    """(used_bytes, limit_bytes) from the cgroup memory controller, cgroup
    v2 first then v1. None when unavailable or unlimited."""
    try:
        with open("/sys/fs/cgroup/memory.current") as f:
            used = int(f.read().strip())
        with open("/sys/fs/cgroup/memory.max") as f:
            raw = f.read().strip()
        if raw != "max":
            limit = int(raw)
            if 0 < limit < (1 << 62):
                return used, limit
    except Exception:
        pass
    try:
        with open("/sys/fs/cgroup/memory/memory.usage_in_bytes") as f:
            used = int(f.read().strip())
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            limit = int(f.read().strip())
        # v1's "no limit" sentinel is an astronomically large number, not a
        # real GB-scale value — same finite-and-plausible check as v2.
        if 0 < limit < (1 << 62):
            return used, limit
    except Exception:
        pass
    return None


def _cgroup_cpu_quota_cores() -> float | None:
    """How many CPU cores this cgroup is actually allowed to use (may be
    fractional, e.g. `docker run --cpus=1.5`). None when unlimited/absent —
    the container can use every host core, so psutil's host-wide percentage
    is already the correct number."""
    try:
        with open("/sys/fs/cgroup/cpu.max") as f:
            quota_str, period_str = f.read().split()
        if quota_str != "max":
            return int(quota_str) / int(period_str)
    except Exception:
        pass
    try:
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as f:
            quota = int(f.read().strip())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as f:
            period = int(f.read().strip())
        if quota > 0:
            return quota / period
    except Exception:
        pass
    return None


def _cgroup_cpu_usage_usec() -> int | None:
    try:
        with open("/sys/fs/cgroup/cpu.stat") as f:
            for line in f:
                if line.startswith("usage_usec"):
                    return int(line.split()[1])
    except Exception:
        pass
    try:
        with open("/sys/fs/cgroup/cpuacct/cpuacct.usage") as f:
            return int(f.read().strip()) // 1000  # ns -> µs
    except Exception:
        pass
    return None


# Cumulative-since-boot counter — same delta-over-time pattern as the
# network rate below; a single sample can't produce a percentage.
_cgroup_cpu_prev: tuple[float, int] | None = None


def _cgroup_cpu_percent() -> float | None:
    """Percent of THIS CONTAINER's own CPU allocation in use (100% =
    saturating every core it was granted). None when there's no real quota
    to measure against, so the caller falls back to psutil's host-wide
    figure."""
    quota_cores = _cgroup_cpu_quota_cores()
    if not quota_cores:
        return None
    usage_usec = _cgroup_cpu_usage_usec()
    if usage_usec is None:
        return None
    global _cgroup_cpu_prev
    now = time.monotonic()
    if _cgroup_cpu_prev is None:
        _cgroup_cpu_prev = (now, usage_usec)
        return 0.0
    prev_t, prev_usage = _cgroup_cpu_prev
    dt_usec = max((now - prev_t) * 1_000_000, 1.0)
    delta_usage = max(usage_usec - prev_usage, 0)
    _cgroup_cpu_prev = (now, usage_usec)
    return min(100.0, round(delta_usage / dt_usec / quota_cores * 100, 1))

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


# Resolving this walks stale library rows' paths up to an existing ancestor
# directory — each os.path.exists() on a dead prefix under a network mount
# (SSHFS/NFS) can cost seconds, not milliseconds, since a negative lookup
# still needs a full round trip. Which filesystem the library lives on
# essentially never changes mid-session, so the result is cached instead of
# re-walked on every 4s sidebar poll (see SystemStatusPanel.tsx's POLL_MS).
_disk_path_cache: tuple[float, str] | None = None
_DISK_PATH_CACHE_TTL = 300.0  # 5 minutes
# The sidebar polls every 4s without waiting for the previous request to
# finish (SystemStatusPanel.tsx), so several requests can land while the
# cache is still cold right after it expires. Without this lock every one of
# them would independently re-run the same multi-second filesystem walk;
# with it, only the first pays the cost and the rest just wait for its result.
_disk_path_lock = threading.Lock()


def _library_disk_path(conn) -> str:
    """Directory of some real, currently-reachable library file — measuring
    disk usage there answers "how full is the disk the library lives on",
    which can be a completely different filesystem than the app's own
    CONFIG_DIR (e.g. a media library mounted over SSHFS/NFS). Falls back to
    CONFIG_DIR when the library is empty or nothing is reachable yet."""
    global _disk_path_cache
    now = time.monotonic()
    if _disk_path_cache is not None:
        resolved_at, cached_path = _disk_path_cache
        if now - resolved_at < _DISK_PATH_CACHE_TTL:
            return cached_path

    with _disk_path_lock:
        # Another thread may have already finished the walk while we were
        # waiting for the lock — re-check before redoing the expensive work.
        now = time.monotonic()
        if _disk_path_cache is not None:
            resolved_at, cached_path = _disk_path_cache
            if now - resolved_at < _DISK_PATH_CACHE_TTL:
                return cached_path
        path = _resolve_library_disk_path(conn)
        _disk_path_cache = (now, path)
        return path


def _resolve_library_disk_path(conn) -> str:
    from .path_mapping import resolve_local_path
    try:
        rows = conn.execute(
            "SELECT prepared_path, path FROM library_items "
            "WHERE prepared_path IS NOT NULL OR path IS NOT NULL LIMIT 200"
        ).fetchall()
    except Exception:
        rows = []
    path = str(CONFIG_DIR)
    for row in rows:
        raw = row["prepared_path"] or row["path"]
        local = resolve_local_path(raw, conn)
        if not local:
            continue
        p = os.path.dirname(local)
        # Walk up to the nearest existing ancestor — the file itself may
        # have moved/been deleted since the last sync, but its mount point
        # almost certainly still exists.
        found = False
        while p and p not in ("/", ""):
            if os.path.exists(p):
                path = p
                found = True
                break
            p = os.path.dirname(p)
        if found:
            break
    return path


def get_system_stats(conn) -> dict:
    vm = psutil.virtual_memory()
    host_cpu_percent = psutil.cpu_percent(interval=None)

    cgroup_mem = _cgroup_mem_stats()
    ram_used, ram_total = cgroup_mem if cgroup_mem else (vm.used, vm.total)
    ram_percent = round(ram_used / ram_total * 100, 1) if ram_total else 0.0

    cgroup_cpu_percent = _cgroup_cpu_percent()
    cpu_percent = cgroup_cpu_percent if cgroup_cpu_percent is not None else host_cpu_percent

    disk_path = _library_disk_path(conn)
    try:
        du = shutil.disk_usage(disk_path)
        disk_total, disk_used = du.total, du.used
    except Exception:
        disk_total, disk_used = 0, 0
    down, up = _net_rates()
    gpu = _gpu_stats()
    return {
        "cpu_percent": cpu_percent,
        "cpu_name": _cpu_name(),
        "ram_percent": ram_percent,
        "ram_used_gb": round(ram_used / (1024 ** 3), 2),
        "ram_total_gb": round(ram_total / (1024 ** 3), 2),
        "disk_path": disk_path,
        "disk_used_gb": round(disk_used / (1024 ** 3), 2),
        "disk_total_gb": round(disk_total / (1024 ** 3), 2),
        "disk_percent": round(disk_used / disk_total * 100, 1) if disk_total else 0.0,
        "net_down_bps": round(down, 1),
        "net_up_bps": round(up, 1),
        "gpu": gpu,
    }
