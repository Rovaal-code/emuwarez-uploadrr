"""Tests for the sidebar's system-stats endpoint/service."""
from __future__ import annotations

import io
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
    with connect(db_path()) as conn:
        init_db(conn)
        path = system_stats._library_disk_path(conn)
    assert path == str(CONFIG_DIR)


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


def test_cgroup_mem_stats_v2_unlimited_falls_back():
    files = {
        "/sys/fs/cgroup/memory.current": "2147483648\n",
        "/sys/fs/cgroup/memory.max": "max\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_mem_stats() is None


def test_cgroup_mem_stats_v1_used_when_v2_absent():
    files = {
        "/sys/fs/cgroup/memory/memory.usage_in_bytes": "1073741824\n",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes": "2147483648\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        result = system_stats._cgroup_mem_stats()
    assert result == (1073741824, 2147483648)


def test_cgroup_mem_stats_v1_unlimited_sentinel_falls_back():
    files = {
        "/sys/fs/cgroup/memory/memory.usage_in_bytes": "1073741824\n",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes": "9223372036854771712\n",
    }
    with patch("builtins.open", side_effect=_fake_open(files)):
        assert system_stats._cgroup_mem_stats() is None


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


def test_cgroup_cpu_percent_none_without_quota():
    with patch("builtins.open", side_effect=_fake_open({})):
        assert system_stats._cgroup_cpu_percent() is None


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
