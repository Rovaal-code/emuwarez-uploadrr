"""Tests for the sidebar's system-stats endpoint/service."""
from __future__ import annotations

from unittest.mock import patch

from emuwarez_uploadrr.services import system_stats


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
