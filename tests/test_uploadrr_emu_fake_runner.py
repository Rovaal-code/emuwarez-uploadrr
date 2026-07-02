"""Tests for tests/fixtures/fake_uploadrr_emu.py — Phase 10F.

Verifies the fake Uploadrr-EMU CLI fixture behaves as a safe, deterministic
stand-in: accepts the real flag contract, never touches the network, and
supports simulated failure/slowness for exercising cancel/timeout paths.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "fake_uploadrr_emu.py"


def _run(args, env=None):
    return subprocess.run(
        [sys.executable, str(FIXTURE), *args],
        capture_output=True, text=True, timeout=15, env=env,
    )


def test_fixture_exists():
    assert FIXTURE.exists()


def test_accepts_real_emu_flags_and_succeeds(tmp_path):
    fake_file = tmp_path / "movie.mkv"
    fake_file.write_bytes(b"\x00")
    result = _run([
        str(fake_file), "-tk", "EMU", "-mt", "Test Movie 2024", "-tmdb", "12345",
        "-ua", "-c", "movie", "-res", "1080p",
    ])
    assert result.returncode == 0
    assert "[EMU] Preparando subida" in result.stdout
    assert "[EMU] Torrent creado correctamente" in result.stdout
    assert "URL:" in result.stdout


def test_accepts_tv_flags_with_season_episode(tmp_path):
    fake_file = tmp_path / "episode.mkv"
    fake_file.write_bytes(b"\x00")
    result = _run([
        str(fake_file), "-tk", "EMU", "-mt", "Test Show", "-tmdb", "999",
        "-ua", "-c", "tv", "-res", "1080p", "-season", "S01", "-episode", "E02",
    ])
    assert result.returncode == 0


def test_fake_fail_flag_exits_nonzero(tmp_path):
    fake_file = tmp_path / "movie.mkv"
    fake_file.write_bytes(b"\x00")
    result = _run([str(fake_file), "-tk", "EMU", "-mt", "T", "-ua", "-c", "movie", "--fake-fail"])
    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_fake_fail_via_env(tmp_path):
    import os
    fake_file = tmp_path / "movie.mkv"
    fake_file.write_bytes(b"\x00")
    env = dict(os.environ, FAKE_UPLOADRR_FAIL="1")
    result = _run([str(fake_file), "-tk", "EMU", "-mt", "T", "-ua", "-c", "movie"], env=env)
    assert result.returncode == 1


def test_fake_sleep_delays_output(tmp_path):
    fake_file = tmp_path / "movie.mkv"
    fake_file.write_bytes(b"\x00")
    start = time.monotonic()
    result = _run([str(fake_file), "-tk", "EMU", "-mt", "T", "-ua", "-c", "movie", "--fake-sleep", "0.2"])
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed >= 0.2


def test_never_imports_network_modules():
    content = FIXTURE.read_text()
    for forbidden in ("import urllib", "import requests", "import socket", "import http.client"):
        assert forbidden not in content, f"fake_uploadrr_emu.py must not use: {forbidden}"


def test_never_prints_a_plausible_secret(tmp_path):
    """The fixture never has a real secret to leak — sanity-check it doesn't
    echo any of its CLI args verbatim in a way that could carry one."""
    fake_file = tmp_path / "movie.mkv"
    fake_file.write_bytes(b"\x00")
    result = _run([str(fake_file), "-tk", "EMU", "-mt", "T", "-ua", "-c", "movie"])
    assert "api_key" not in result.stdout.lower()
    assert "config.yaml" not in result.stdout.lower()
