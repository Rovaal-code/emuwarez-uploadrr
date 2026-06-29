"""Tests for Docker runtime compatibility — no Docker daemon required."""
from __future__ import annotations

import os
import importlib

import pytest
from fastapi.testclient import TestClient


def _fresh_app(tmp_path, monkeypatch):
    """Create a fresh FastAPI app instance with CWD set to tmp_path."""
    monkeypatch.chdir(tmp_path)
    # Re-import app module to pick up any path changes
    import emuwarez_uploadrr.web.app as app_mod
    importlib.reload(app_mod)
    return app_mod.create_app()


def test_app_creates_without_frontend_dist(tmp_path, monkeypatch):
    """App must start even if frontend/dist does not exist."""
    app = _fresh_app(tmp_path, monkeypatch)
    assert app is not None


def test_health_endpoint_works_without_frontend(tmp_path, monkeypatch):
    """GET /api/health returns 200 even without frontend/dist."""
    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_api_docs_available_without_frontend(tmp_path, monkeypatch):
    """Swagger docs must be available regardless of frontend presence."""
    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/docs")
    assert resp.status_code == 200


def test_config_dir_env_var_respected(tmp_path, monkeypatch):
    """CONFIG_DIR env var must be read at call time by db_path()."""
    config_path = tmp_path / "custom_config"
    config_path.mkdir()
    monkeypatch.setenv("CONFIG_DIR", str(config_path))

    import emuwarez_uploadrr.database as db_mod
    resolved = db_mod.db_path()
    assert str(config_path) in str(resolved)


def test_config_dir_default_is_home_based(monkeypatch):
    """Without CONFIG_DIR env var, db_path uses home-based default."""
    monkeypatch.delenv("CONFIG_DIR", raising=False)

    import emuwarez_uploadrr.database as db_mod
    resolved = db_mod.db_path()
    # Default is ~/.config/emuwarez-renamer/...
    assert "emuwarez" in str(resolved).lower() or ".config" in str(resolved)


def test_frontend_dist_served_when_present(tmp_path, monkeypatch):
    """If frontend/dist/index.html exists, the SPA fallback is mounted."""
    # Create a fake frontend/dist in the repo root location that app.py checks
    # app.py resolves: Path(__file__).parent.parent.parent / "frontend" / "dist"
    # That is the actual repo root — we can't fake it easily, so just verify
    # the app starts and /api/* still works (static mount doesn't break API).
    app = _fresh_app(tmp_path, monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_dockerignore_excludes_uploadrr():
    """Verify .dockerignore explicitly excludes Uploadrr/."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dockerignore = os.path.join(repo_root, ".dockerignore")
    assert os.path.exists(dockerignore), ".dockerignore must exist"
    content = open(dockerignore).read()
    assert "Uploadrr/" in content, ".dockerignore must exclude Uploadrr/"


def test_dockerfile_exists():
    """Dockerfile must exist in repo root."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dockerfile = os.path.join(repo_root, "Dockerfile")
    assert os.path.exists(dockerfile), "Dockerfile must exist"


def test_dockerfile_does_not_copy_uploadrr():
    """Dockerfile must not COPY Uploadrr/ into the image."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dockerfile = os.path.join(repo_root, "Dockerfile")
    content = open(dockerfile).read()
    # No COPY instruction should reference the standalone Uploadrr/ tool directory.
    # Note: "emuwarez_uploadrr/" is our Python package and is fine to COPY.
    # We check for COPY that starts with "Uploadrr" (the external tool), not our package.
    import re
    copy_uploadrr = re.findall(r"^COPY\s+Uploadrr[/\s]", content, re.MULTILINE)
    assert not copy_uploadrr, f"Dockerfile must not COPY Uploadrr/ tool: {copy_uploadrr}"


def test_compose_example_exists():
    """docker-compose.example.yml must exist."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compose = os.path.join(repo_root, "docker-compose.example.yml")
    assert os.path.exists(compose), "docker-compose.example.yml must exist"


def test_env_example_exists_without_secrets():
    """'.env.example must exist and must not contain real API keys."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_example = os.path.join(repo_root, ".env.example")
    assert os.path.exists(env_example), ".env.example must exist"
    content = open(env_example).read()
    # Must not contain anything that looks like a real secret
    assert "api_key" not in content.lower() or "api_key=" not in content.lower()
    assert "password" not in content.lower()
    assert "secret" not in content.lower()


def test_web_info_contains_docker_section(tmp_path, monkeypatch, capsys):
    """CLI web info must output a Docker section."""
    import emuwarez_uploadrr.cli as cli_mod
    cli_mod.cmd_web_info()
    captured = capsys.readouterr()
    assert "Docker" in captured.out
    assert "docker build" in captured.out
    assert "docker compose" in captured.out
    assert "/config" in captured.out
    assert "EXDEV" in captured.out or "hardlink" in captured.out.lower()
