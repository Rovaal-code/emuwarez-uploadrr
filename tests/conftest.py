"""Shared pytest fixtures.

Every test gets its own temp directory as CONFIG_DIR so the database is
isolated from the real ~/.config/emuwarez-renamer/ path.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FAKE_UPLOADRR_EMU_SCRIPT = Path(__file__).parent / "fixtures" / "fake_uploadrr_emu.py"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point CONFIG_DIR to a per-test temp dir so each test starts with a fresh DB."""
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture
def client(isolated_db):
    """TestClient with a freshly created app (DB is already isolated)."""
    from emuwarez_uploadrr.web.app import create_app
    return TestClient(create_app())


@pytest.fixture
def admin_token(client):
    """Create admin user and return a valid session token."""
    resp = client.post("/api/setup/admin", json={
        "username": "testadmin",
        "password": "TestPass1!secret",
    })
    assert resp.status_code == 201, resp.text
    resp = client.post("/api/auth/login", json={
        "username": "testadmin",
        "password": "TestPass1!secret",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture
def auth_headers(admin_token):
    """Authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def fake_uploadrr_emu_dir(tmp_path):
    """A fake Uploadrr-EMU install directory for real-subprocess tests.

    <dir>/upload.py is a copy of tests/fixtures/fake_uploadrr_emu.py — a
    test-only CLI that accepts the real Uploadrr-EMU flags, never touches
    the network, and never uploads anything real (see that file's docstring).
    <dir>/data/config.yaml is a minimal placeholder config so config-staging
    tests (Phase 10F) have something to back up/stage/restore.

    Never points at a real Uploadrr-EMU installation.
    """
    uploadrr_dir = tmp_path / "FakeUploadrrEMU"
    uploadrr_dir.mkdir()
    shutil.copy(FAKE_UPLOADRR_EMU_SCRIPT, uploadrr_dir / "upload.py")
    data_dir = uploadrr_dir / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        "DEFAULT:\n"
        "  tmdb: PLACEHOLDER_TMDB_KEY\n"
        "  default_torrent_client: qbit\n"
        "\n"
        "TRACKERS:\n"
        "  EMU:\n"
        "    api_key: PLACEHOLDER_EMU_KEY\n"
        "    anon: false\n",
        encoding="utf-8",
    )
    return uploadrr_dir


@pytest.fixture
def fake_uploadrr_python_path():
    """python_path to use with fake_uploadrr_emu_dir — the current interpreter."""
    return sys.executable
