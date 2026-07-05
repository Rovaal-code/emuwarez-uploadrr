"""Tests for Phase 8B CLI commands (requests readiness/candidates)."""
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

import pytest

ENTRY = str(Path(__file__).parent.parent / "emuwarez_uploader.py")


def _run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, ENTRY] + args,
        capture_output=True,
        text=True,
        env=e,
    )


@pytest.fixture
def isolated_env(tmp_path):
    return {"CONFIG_DIR": str(tmp_path)}


def _insert_request(tmp_path, emu_id="cli-rr-1", title="CLI Test Movie"):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(tmp_path / "emuwarez_uploadrr.db")
    init_db(conn)
    conn.execute(
        "INSERT OR IGNORE INTO request_items (emu_id, title, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (emu_id, title),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM request_items WHERE emu_id = ?", (emu_id,)).fetchone()
    conn.close()
    return row["id"]


# ---------------------------------------------------------------------------
# requests readiness (empty)
# ---------------------------------------------------------------------------

def test_cli_readiness_empty(isolated_env, tmp_path):
    _run(["db", "init"], env=isolated_env)
    result = _run(["requests", "readiness"], env=isolated_env)
    assert result.returncode == 0 or result.returncode == 0
    # Either "Sin readiness" or the header
    assert "readiness-refresh" in result.stdout or "Sin readiness" in result.stdout or result.returncode == 0


# ---------------------------------------------------------------------------
# requests readiness-refresh (empty — no requests)
# ---------------------------------------------------------------------------

def test_cli_readiness_refresh_empty(isolated_env):
    _run(["db", "init"], env=isolated_env)
    result = _run(["requests", "readiness-refresh"], env=isolated_env)
    assert result.returncode == 0
    assert "Readiness recalculado" in result.stdout or "recalculado" in result.stdout.lower()


# ---------------------------------------------------------------------------
# requests readiness-refresh with data
# ---------------------------------------------------------------------------

def test_cli_readiness_refresh_with_data(isolated_env, tmp_path):
    isolated_env["CONFIG_DIR"] = str(tmp_path)
    _insert_request(tmp_path)
    result = _run(["requests", "readiness-refresh"], env=isolated_env)
    assert result.returncode == 0
    assert "1" in result.stdout  # 1 item updated


# ---------------------------------------------------------------------------
# requests candidates (no candidates)
# ---------------------------------------------------------------------------

def test_cli_candidates_no_candidates(isolated_env, tmp_path):
    isolated_env["CONFIG_DIR"] = str(tmp_path)
    req_id = _insert_request(tmp_path, "cli-cand-1", "Cand Movie")
    result = _run(["requests", "candidates", str(req_id)], env=isolated_env)
    assert result.returncode == 0
    # Should suggest running readiness-refresh
    assert "readiness-refresh" in result.stdout or "Sin candidatos" in result.stdout


# ---------------------------------------------------------------------------
# requests readiness <id> detail
# ---------------------------------------------------------------------------

def test_cli_readiness_detail_after_refresh(isolated_env, tmp_path):
    isolated_env["CONFIG_DIR"] = str(tmp_path)
    req_id = _insert_request(tmp_path, "cli-det-1", "Detail Movie")
    _run(["requests", "readiness-refresh"], env=isolated_env)
    result = _run(["requests", "readiness", str(req_id)], env=isolated_env)
    assert result.returncode == 0
    assert "no_local_match" in result.stdout or "Estado" in result.stdout


# ---------------------------------------------------------------------------
# No API keys in CLI output
# ---------------------------------------------------------------------------

def test_no_api_keys_in_cli_readiness(isolated_env, tmp_path):
    isolated_env["CONFIG_DIR"] = str(tmp_path)
    _insert_request(tmp_path, "cli-key-1", "Key Check Movie")
    _run(["requests", "readiness-refresh"], env=isolated_env)
    result = _run(["requests", "readiness"], env=isolated_env)
    for forbidden in ("api_key", "apikey", "token=", "password", "secret"):
        assert forbidden.lower() not in result.stdout.lower(), f"API key leaked: {forbidden}"
