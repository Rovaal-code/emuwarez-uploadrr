"""Tests for Phase 9B — docker-e2e-demo.sh and fake_uploadrr fixture.

These tests do NOT require Docker or a running container.
They validate the scripts are well-formed and safe.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
E2E_SCRIPT = REPO_ROOT / "scripts" / "docker-e2e-demo.sh"
FAKE_UPLOADRR = REPO_ROOT / "tests" / "fixtures" / "fake_uploadrr.py"


# ---------------------------------------------------------------------------
# docker-e2e-demo.sh — existence and well-formedness
# ---------------------------------------------------------------------------

def test_e2e_script_exists():
    assert E2E_SCRIPT.exists(), f"Script not found: {E2E_SCRIPT}"


def test_e2e_script_is_executable():
    assert os.access(E2E_SCRIPT, os.X_OK), f"Script not executable: {E2E_SCRIPT}"


def test_e2e_script_has_strict_mode():
    content = E2E_SCRIPT.read_text()
    assert "set -euo pipefail" in content, "Script must use 'set -euo pipefail'"


def test_e2e_script_uses_mktemp():
    content = E2E_SCRIPT.read_text()
    assert "mktemp -d" in content, "Script must create a tmpdir with 'mktemp -d'"


def test_e2e_script_has_cleanup_trap():
    content = E2E_SCRIPT.read_text()
    assert "trap" in content, "Script must use 'trap' for cleanup"
    assert "cleanup" in content


def test_e2e_script_has_keep_container():
    content = E2E_SCRIPT.read_text()
    assert "KEEP_CONTAINER" in content, "Script must support KEEP_CONTAINER variable"


def test_e2e_script_has_configurable_port():
    content = E2E_SCRIPT.read_text()
    assert "PORT" in content, "Script must support PORT variable"


def test_e2e_script_demo_seed_command():
    content = E2E_SCRIPT.read_text()
    assert "demo seed" in content, "Script must call 'demo seed'"
    assert "DEMO_SEED" in content, "Script must pass DEMO_SEED confirmation token"


def test_e2e_script_no_real_api_keys():
    content = E2E_SCRIPT.read_text()
    for suspicious in ["api_key=", "API_KEY=", "TMDb_KEY", "EMU_KEY"]:
        assert suspicious not in content, f"Script must not contain real API key: {suspicious}"


def test_e2e_script_validates_uploadrr_not_in_image():
    content = E2E_SCRIPT.read_text()
    assert "Uploadrr" in content, "Script must check that Uploadrr/ is not inside the image"


def test_e2e_script_checks_health_endpoint():
    content = E2E_SCRIPT.read_text()
    assert "/api/health" in content, "Script must poll /api/health"


def test_e2e_script_runs_queue_commands():
    content = E2E_SCRIPT.read_text()
    assert "queue refresh" in content
    assert "queue list" in content
    assert "action-plan" in content


def test_e2e_script_runs_nomenclature_preview():
    content = E2E_SCRIPT.read_text()
    assert "nomenclature preview" in content


def test_e2e_script_runs_upload_preflight():
    content = E2E_SCRIPT.read_text()
    assert "upload preflight" in content


# ---------------------------------------------------------------------------
# fake_uploadrr.py — existence and output safety
# ---------------------------------------------------------------------------

def test_fake_uploadrr_exists():
    assert FAKE_UPLOADRR.exists(), f"Fixture not found: {FAKE_UPLOADRR}"


def test_fake_uploadrr_output():
    result = subprocess.run(
        [sys.executable, str(FAKE_UPLOADRR), "--dry-run", "/some/path.mkv"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "Upload completed" in result.stdout
    assert "Torrent URL" in result.stdout
    assert "Torrent ID" in result.stdout


def test_fake_uploadrr_no_secrets_in_output():
    result = subprocess.run(
        [sys.executable, str(FAKE_UPLOADRR)],
        capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    for secret_pattern in ["api_key", "api_token", "password", "token=", "Bearer "]:
        assert secret_pattern not in output.lower(), (
            f"fake_uploadrr output must not contain secrets: found '{secret_pattern}'"
        )


def test_fake_uploadrr_accepts_any_args():
    result = subprocess.run(
        [sys.executable, str(FAKE_UPLOADRR), "--title", "Test Movie", "--tmdb", "12345", "--source", "webdl"],
        capture_output=True, text=True
    )
    assert result.returncode == 0


def test_fake_uploadrr_no_network():
    content = FAKE_UPLOADRR.read_text()
    assert "import urllib" not in content, "fake_uploadrr must not import urllib"
    assert "import requests" not in content, "fake_uploadrr must not import requests library"
    assert "socket" not in content, "fake_uploadrr must not use socket"
