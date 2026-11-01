"""Tests for Uploadrr runtime settings API and connection test — Phase 10F."""
from __future__ import annotations



def test_get_settings_returns_uploadrr_defaults(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["uploadrr_runtime_type"] == "uploadrr_emu"
    assert data["uploadrr_timeout"] == 7200
    assert data["uploadrr_allowed_roots"] == ["/data"]
    assert data["uploadrr_path"] is None


def test_put_settings_saves_uploadrr_path(client, auth_headers):
    resp = client.put("/api/settings", json={"uploadrr_path": "/opt/Uploadrr"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["uploadrr_path"] == "/opt/Uploadrr"

    resp2 = client.get("/api/settings", headers=auth_headers)
    assert resp2.json()["uploadrr_path"] == "/opt/Uploadrr"


def test_put_settings_saves_runtime_type(client, auth_headers):
    resp = client.put("/api/settings", json={"uploadrr_runtime_type": "uploadrr_generic"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["uploadrr_runtime_type"] == "uploadrr_generic"


def test_put_settings_invalid_runtime_type_returns_422(client, auth_headers):
    resp = client.put("/api/settings", json={"uploadrr_runtime_type": "not_a_real_runtime"}, headers=auth_headers)
    assert resp.status_code == 422


def test_put_settings_saves_python_path(client, auth_headers):
    resp = client.put("/api/settings", json={"uploadrr_python_path": "/usr/local/bin/python"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["uploadrr_python_path"] == "/usr/local/bin/python"


def test_put_settings_saves_timeout(client, auth_headers):
    resp = client.put("/api/settings", json={"uploadrr_timeout": 3600}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["uploadrr_timeout"] == 3600


def test_put_settings_invalid_timeout_zero_returns_422(client, auth_headers):
    resp = client.put("/api/settings", json={"uploadrr_timeout": 0}, headers=auth_headers)
    assert resp.status_code == 422


def test_put_settings_invalid_timeout_negative_returns_422(client, auth_headers):
    resp = client.put("/api/settings", json={"uploadrr_timeout": -5}, headers=auth_headers)
    assert resp.status_code == 422


def test_put_settings_allowed_roots_as_csv_string_normalized(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"uploadrr_allowed_roots": "/data/uploads/emu, /data/media ,"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["uploadrr_allowed_roots"] == ["/data/uploads/emu", "/data/media"]


def test_put_settings_allowed_roots_as_list_normalized(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"uploadrr_allowed_roots": ["/data/a", " /data/b ", ""]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["uploadrr_allowed_roots"] == ["/data/a", "/data/b"]


def test_put_settings_uploadrr_fields_do_not_clobber_other_settings(client, auth_headers):
    client.put("/api/settings", json={"default_release_tag": "MYTAG"}, headers=auth_headers)
    resp = client.put("/api/settings", json={"uploadrr_timeout": 1800}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["default_release_tag"] == "MYTAG"
    assert resp.json()["uploadrr_timeout"] == 1800


# ---------------------------------------------------------------------------
# POST /api/integrations/test/uploadrr — filesystem-only check
# ---------------------------------------------------------------------------

def test_integration_test_uploadrr_not_configured(client, auth_headers):
    resp = client.post("/api/integrations/test/uploadrr", json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["status"] == "not_configured"


def test_integration_test_uploadrr_path_not_found(client, auth_headers):
    resp = client.post(
        "/api/integrations/test/uploadrr",
        json={"path": "/this/path/does/not/exist/anywhere"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert resp.json()["status"] == "not_found"


def test_integration_test_uploadrr_ok_with_script_and_config(client, auth_headers, tmp_path):
    import sys
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# stub")
    data_dir = uploadrr_dir / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text("DEFAULT:\n  tmdb: x\n")

    resp = client.post(
        "/api/integrations/test/uploadrr",
        json={"path": str(uploadrr_dir), "python_path": sys.executable},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["details"]["config_yaml_found"] is True


def test_integration_test_uploadrr_ok_without_config_yaml(client, auth_headers, tmp_path):
    import sys
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# stub")

    resp = client.post(
        "/api/integrations/test/uploadrr",
        json={"path": str(uploadrr_dir), "python_path": sys.executable},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "connected_no_config"


def test_integration_test_uploadrr_python_path_missing_reported(client, auth_headers, tmp_path):
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("# stub")

    resp = client.post(
        "/api/integrations/test/uploadrr",
        json={"path": str(uploadrr_dir), "python_path": "/does/not/exist/python"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["status"] == "python_missing"


def test_integration_test_uploadrr_never_executes_upload_py(client, auth_headers, tmp_path, monkeypatch):
    """upload.py raises if ever executed — the test endpoint must never run it."""
    import sys
    uploadrr_dir = tmp_path / "Uploadrr"
    uploadrr_dir.mkdir()
    (uploadrr_dir / "upload.py").write_text("raise SystemExit('should never run')\n")

    resp = client.post(
        "/api/integrations/test/uploadrr",
        json={"path": str(uploadrr_dir), "python_path": sys.executable},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_integration_test_uploadrr_requires_auth(client):
    resp = client.post("/api/integrations/test/uploadrr", json={})
    assert resp.status_code == 401
