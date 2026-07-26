"""Tests for the sidebar's system-stats endpoint/service."""
from __future__ import annotations

import io
import threading
import time
from unittest.mock import patch

from emuwarez_uploadrr.services import system_stats


def _fake_open(files: dict[str, str]):
    """Returns a stand-in for builtins.open: paths in `files` yield their
    string content, everything else raises FileNotFoundError — same as a
    real filesystem where only some cgroup files exist."""
    def _opener(path, *args, **kwargs):
        if path in files:
            return io.StringIO(files[path])
        raise FileNotFoundError(path)
    return _opener


def test_get_system_stats_shape(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    with connect(db_path()) as conn:
        init_db(conn)
        stats = system_stats.get_system_stats(conn)
    assert 0 <= stats["cpu_percent"] <= 100
    assert stats["cpu_name"]
    assert 0 <= stats["ram_percent"] <= 100
    assert stats["ram_total_gb"] > 0
    assert stats["net_down_bps"] >= 0
    assert stats["net_up_bps"] >= 0
    assert "gpu" in stats  # dict or None, either is fine


def test_library_disk_path_falls_back_when_empty(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    from emuwarez_uploadrr.constants import CONFIG_DIR
    system_stats._disk_path_cache = None
    with connect(db_path()) as conn:
        init_db(conn)
        path = system_stats._library_disk_path(conn)
    assert path == str(CONFIG_DIR)


class _ExplodingConn:
    def execute(self, *a, **k):
        raise AssertionError("should not re-query the DB while the cache is still fresh")


def test_library_disk_path_single_flights_concurrent_cold_calls(isolated_db):
    """Several requests landing while the cache is cold (the sidebar polls
    every 4s without waiting for the previous call) must not each redo the
    expensive filesystem walk — only the first should, the rest wait on it."""
    from emuwarez_uploadrr.database import connect, init_db, db_path
    system_stats._disk_path_cache = None
    call_count = 0

    def _slow_resolve(conn):
        nonlocal call_count
        call_count += 1
        time.sleep(0.2)
        return "/some/resolved/path"

    with connect(db_path()) as conn:
        init_db(conn)
        with patch.object(system_stats, "_resolve_library_disk_path", side_effect=_slow_resolve):
            results = []
            threads = [
                threading.Thread(target=lambda: results.append(system_stats._library_disk_path(conn)))
                for _ in range(5)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

    assert call_count == 1
    assert results == ["/some/resolved/path"] * 5


def test_library_disk_path_is_cached_across_calls(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    system_stats._disk_path_cache = None
    with connect(db_path()) as conn:
        init_db(conn)
        first = system_stats._library_disk_path(conn)
    # A second call within the TTL must serve the cached value without
    # touching the connection at all — a broken/closed conn would still work.
    second = system_stats._library_disk_path(_ExplodingConn())
    assert first == second


def test_gpu_stats_none_when_nvidia_smi_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        assert system_stats._gpu_stats() is None


def test_gpu_stats_parses_nvidia_smi_output():
    class FakeResult:
        returncode = 0
        stdout = "NVIDIA GeForce RTX 4090, 12, 1024, 16384\n"
    with patch("subprocess.run", return_value=FakeResult()):
        gpu = system_stats._gpu_stats()
    assert gpu is not None
    assert gpu["name"] == "NVIDIA GeForce RTX 4090"
    assert gpu["percent"] == 12.0
    assert round(gpu["vram_used_gb"], 2) == 1.0
    assert round(gpu["vram_total_gb"], 2) == 16.0
    assert 5 < gpu["vram_percent"] < 10


def test_net_rates_first_call_is_zero():
    system_stats._net_prev = None
    down, up = system_stats._net_rates()
    assert (down, up) == (0.0, 0.0)
    assert system_stats._net_prev is not None


def test_system_stats_endpoint_requires_auth(client):
    resp = client.get("/api/system/stats")
    assert resp.status_code == 401


def test_system_stats_endpoint_authenticated(client, auth_headers):
    resp = client.get("/api/system/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "cpu_percent" in data
    assert "ram_percent" in data
    assert "disk_percent" in data


# ---------------------------------------------------------------------------
# Container-aware CPU/RAM (cgroup v1/v2, with graceful host-wide fallback)
# ---------------------------------------------------------------------------

def test_cgroup_mem_stats_v2():
    files = {
        "/sys/fs/cgroup/memory.current": "2147483648\n",
        "/sys/fs/cgroup/memory.max": "4294967296\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        result = system_stats._cgroup_mem_stats()
    assert result == (2147483648, 4294967296)


def test_cgroup_mem_stats_v2_unlimited_still_reports_usage():
    """No real cap (plain docker run/compose, no mem_limit) — still returns
    THIS cgroup's actual usage, just with limit=None so the caller falls
    back to the host's total as the denominator instead of hiding the
    container's own number behind a full host-wide reading."""
    files = {
        "/sys/fs/cgroup/memory.current": "2147483648\n",
        "/sys/fs/cgroup/memory.max": "max\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_mem_stats() == (2147483648, None)


def test_cgroup_mem_stats_v1_used_when_v2_absent():
    files = {
        "/sys/fs/cgroup/memory/memory.usage_in_bytes": "1073741824\n",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes": "2147483648\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        result = system_stats._cgroup_mem_stats()
    assert result == (1073741824, 2147483648)


def test_cgroup_mem_stats_v1_unlimited_sentinel_still_reports_usage():
    files = {
        "/sys/fs/cgroup/memory/memory.usage_in_bytes": "1073741824\n",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes": "9223372036854771712\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_mem_stats() == (1073741824, None)


def test_cgroup_mem_stats_none_when_no_cgroup_files():
    with patch("builtins.open", side_effect=_fake_open({})):
        assert system_stats._cgroup_mem_stats() is None


def test_cgroup_cpu_quota_cores_v2_two_cores():
    files = {"/sys/fs/cgroup/cpu.max": "200000 100000\n"}
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_cpu_quota_cores() == 2.0


def test_cgroup_cpu_quota_cores_v2_unlimited_is_none():
    files = {"/sys/fs/cgroup/cpu.max": "max 100000\n"}
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_cpu_quota_cores() is None


def test_cgroup_cpu_quota_cores_v1_half_core():
    files = {
        "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "50000\n",
        "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_cpu_quota_cores() == 0.5


def test_cgroup_cpu_quota_cores_v1_unlimited_is_none():
    files = {
        "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1\n",
        "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_cpu_quota_cores() is None


def test_cgroup_cpu_percent_none_without_any_cgroup():
    """No cgroup CPU controller readable at all (bare host, outside any
    container) — nothing to report, caller falls back to psutil's own
    host-wide reading."""
    with patch("builtins.open", side_effect=_fake_open({})):
        assert system_stats._cgroup_cpu_percent() is None


def test_cgroup_cpu_percent_uncapped_falls_back_to_host_core_count():
    """A cgroup with usage_usec but no quota (--cpus not set) still reports
    THIS cgroup's own usage — just measured against every host core, since
    there's no smaller allocation to compare against."""
    system_stats._cgroup_cpu_prev = None
    files = {"/sys/fs/cgroup/cpu.stat": "usage_usec 1000000\nuser_usec 900000\n"}
    with patch("builtins.open", side_effect=_fake_open(files)), \
         patch("os.cpu_count", return_value=4), \
         patch("time.monotonic", return_value=1000.0):
        first = system_stats._cgroup_cpu_percent()
    assert first == 0.0

    # 1 second later, this cgroup burned 2 full core-seconds — with 4 host
    # cores as the denominator that's 50%, not 200% (which dividing by a
    # missing/zero quota would have produced).
    files["/sys/fs/cgroup/cpu.stat"] = "usage_usec 3000000\nuser_usec 2700000\n"
    with patch("builtins.open", side_effect=_fake_open(files)), \
         patch("os.cpu_count", return_value=4), \
         patch("time.monotonic", return_value=1001.0):
        second = system_stats._cgroup_cpu_percent()
    assert second == 50.0


def test_cgroup_cpu_percent_computes_rate_against_quota():
    system_stats._cgroup_cpu_prev = None
    files = {
        "/sys/fs/cgroup/cpu.max": "100000 100000\n",  # 1 whole core allowed
        "/sys/fs/cgroup/cpu.stat": "usage_usec 1000000\nuser_usec 900000\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)), \
         patch("time.monotonic", return_value=1000.0):
        first = system_stats._cgroup_cpu_percent()
    assert first == 0.0  # nothing to diff against yet

    # 1 second later, this 1-core container burned 0.5s of CPU time = 50%.
    files["/sys/fs/cgroup/cpu.stat"] = "usage_usec 1500000\nuser_usec 1350000\n"
    with patch("builtins.open", side_effect=_fake_open(files)), \
         patch("time.monotonic", return_value=1001.0):
        second = system_stats._cgroup_cpu_percent()
    assert second == 50.0


def test_get_system_stats_uses_cgroup_values_when_available(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    with patch.object(system_stats, "_cgroup_mem_stats", return_value=(1_000_000_000, 2_000_000_000)), \
         patch.object(system_stats, "_cgroup_cpu_percent", return_value=42.0):
        with connect(db_path()) as conn:
            init_db(conn)
            stats = system_stats.get_system_stats(conn)
    assert stats["cpu_percent"] == 42.0
    assert stats["ram_percent"] == 50.0
    assert round(stats["ram_used_gb"], 2) == round(1_000_000_000 / 1024**3, 2)


def test_get_system_stats_uncapped_cgroup_uses_own_usage_over_host_total(isolated_db):
    """An uncapped container/cgroup (no mem_limit/--cpus set — the common
    case for a plain `docker run`/compose service) must still show ITS OWN
    memory usage as "used", just measured against the host's total as the
    denominator — not the host's own used/total, which would count every
    other process too."""
    from emuwarez_uploadrr.database import connect, init_db, db_path
    with patch.object(system_stats, "_cgroup_mem_stats", return_value=(1_000_000_000, None)), \
         patch.object(system_stats, "_cgroup_cpu_percent", return_value=3.5), \
         patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value.used = 20_000_000_000
        mock_vm.return_value.total = 4_000_000_000
        with connect(db_path()) as conn:
            init_db(conn)
            stats = system_stats.get_system_stats(conn)
    assert stats["cpu_percent"] == 3.5
    # used = the cgroup's own 1GB, NOT the host's 20GB.
    assert round(stats["ram_used_gb"], 2) == round(1_000_000_000 / 1024**3, 2)
    # total = the host's 4GB (no cgroup limit to use instead).
    assert round(stats["ram_total_gb"], 2) == round(4_000_000_000 / 1024**3, 2)
    assert stats["ram_percent"] == 25.0


def test_get_system_stats_falls_back_to_host_without_cgroup(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    with patch.object(system_stats, "_cgroup_mem_stats", return_value=None), \
         patch.object(system_stats, "_cgroup_cpu_percent", return_value=None):
        with connect(db_path()) as conn:
            init_db(conn)
            stats = system_stats.get_system_stats(conn)
    # Host-wide values, same shape as before — no container detected.
    assert 0 <= stats["cpu_percent"] <= 100
    assert 0 <= stats["ram_percent"] <= 100


# ---------------------------------------------------------------------------
# estimate_max_concurrent_uploads — "Subidas en paralelo" Test button
# ---------------------------------------------------------------------------

def test_estimate_concurrent_uploads_shape():
    result = system_stats.estimate_max_concurrent_uploads()
    assert result["recommended"] >= 1
    assert result["ram_limited_to"] >= 1
    assert result["cpu_limited_to"] >= 1
    assert result["available_ram_gb"] >= 0
    assert result["cpu_cores"] >= 1
    assert result["recommended"] == min(result["ram_limited_to"], result["cpu_limited_to"])


def test_estimate_concurrent_uploads_ram_limited():
    with patch.object(system_stats, "_cgroup_mem_stats", return_value=None), \
         patch.object(system_stats, "_cgroup_cpu_quota_cores", return_value=None), \
         patch("psutil.virtual_memory") as mock_vm, \
         patch("os.cpu_count", return_value=64):
        mock_vm.return_value.available = int(2.5 * 1024 ** 3)  # 2.5 GB free
        result = system_stats.estimate_max_concurrent_uploads()
    # floor(2.5 / 0.8) = 3 slots by RAM, way more than that by CPU (63 cores).
    assert result["ram_limited_to"] == 3
    assert result["cpu_limited_to"] == 10  # capped at the setting's own max
    assert result["recommended"] == 3


def test_estimate_concurrent_uploads_cpu_limited():
    with patch.object(system_stats, "_cgroup_mem_stats", return_value=None), \
         patch.object(system_stats, "_cgroup_cpu_quota_cores", return_value=None), \
         patch("psutil.virtual_memory") as mock_vm, \
         patch("os.cpu_count", return_value=3):
        mock_vm.return_value.available = 64 * 1024 ** 3  # plenty of RAM
        result = system_stats.estimate_max_concurrent_uploads()
    # 3 cores - 1 reserved for the host/web server = 2.
    assert result["cpu_limited_to"] == 2
    assert result["recommended"] == 2


def test_estimate_concurrent_uploads_never_below_one():
    """Even on a tiny single-core box with almost no free RAM, the estimate
    must still recommend at least 1 — never 0 (that means "sin límite",
    the opposite of what a resource-constrained host needs)."""
    with patch.object(system_stats, "_cgroup_mem_stats", return_value=None), \
         patch.object(system_stats, "_cgroup_cpu_quota_cores", return_value=None), \
         patch("psutil.virtual_memory") as mock_vm, \
         patch("os.cpu_count", return_value=1):
        mock_vm.return_value.available = 100 * 1024 ** 2  # 100 MB free
        result = system_stats.estimate_max_concurrent_uploads()
    assert result["recommended"] == 1
    assert result["ram_limited_to"] == 1
    assert result["cpu_limited_to"] == 1


def test_estimate_concurrent_uploads_uses_cgroup_limits_when_present():
    """Inside a capped container, the estimate must respect ITS OWN quota
    (e.g. `docker run --cpus=2 --memory=3g`), not the host's full capacity —
    same "cgroup-aware" principle get_system_stats already applies."""
    with patch.object(system_stats, "_cgroup_mem_stats", return_value=(1 * 1024 ** 3, 3 * 1024 ** 3)), \
         patch.object(system_stats, "_cgroup_cpu_quota_cores", return_value=2.0), \
         patch("os.cpu_count", return_value=64):
        result = system_stats.estimate_max_concurrent_uploads()
    # 2 GB available (3 GB limit - 1 GB used) / 0.8 GB per slot = 2 slots by RAM.
    assert result["ram_limited_to"] == 2
    # 2 quota cores - 1 reserved = 1 by CPU.
    assert result["cpu_limited_to"] == 1
    assert result["recommended"] == 1


def test_upload_concurrency_estimate_endpoint_requires_auth(client):
    resp = client.get("/api/system/upload-concurrency-estimate")
    assert resp.status_code == 401


def test_upload_concurrency_estimate_endpoint_authenticated(client, auth_headers):
    resp = client.get("/api/system/upload-concurrency-estimate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "recommended" in data
    assert "ram_limited_to" in data
    assert "cpu_limited_to" in data
