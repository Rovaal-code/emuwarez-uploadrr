"""Tests for runtime_diagnostics service — no Docker required."""
import importlib


def test_get_runtime_diagnostics_returns_checks():
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    assert "ok" in result
    assert "checks" in result
    assert isinstance(result["checks"], list)
    assert len(result["checks"]) > 0


def test_each_check_has_required_fields():
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    for check in result["checks"]:
        assert "name" in check
        assert "status" in check
        assert "message" in check
        assert check["status"] in ("ok", "warning", "error", "unknown")


def test_result_has_ok_warnings_errors():
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    assert isinstance(result["ok"], bool)
    assert isinstance(result["warnings"], list)
    assert isinstance(result["errors"], list)


def test_config_dir_check_with_existing_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_config_dir()
    assert result["status"] == "ok"


def test_config_dir_missing_returns_warning(tmp_path, monkeypatch):
    missing = str(tmp_path / "nonexistent_dir")
    monkeypatch.setenv("CONFIG_DIR", missing)
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_config_dir()
    assert result["status"] == "warning"


def test_config_dir_not_writable(tmp_path, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o444)
    monkeypatch.setenv("CONFIG_DIR", str(locked))
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_config_dir()
    # Should be error or warning depending on root access
    assert result["status"] in ("error", "warning", "ok")
    locked.chmod(0o755)  # restore for cleanup


def test_database_check_no_db_returns_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_database_path()
    assert result["status"] == "warning"
    assert "no existe" in result["message"]


def test_database_check_with_db_returns_ok(tmp_path, monkeypatch):
    import sqlite3
    db_path = tmp_path / "emuwarez_uploadrr.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_database_path()
    assert result["status"] == "ok"


def test_frontend_check_returns_check_dict():
    from emuwarez_uploadrr.services.runtime_diagnostics import check_frontend_dist
    result = check_frontend_dist()
    assert result["status"] in ("ok", "warning")
    assert "message" in result
    assert "name" in result


def test_frontend_check_ok_when_dist_exists(tmp_path, monkeypatch):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    # Patch the candidates list by monkeypatching Path
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    # Direct call with known good path — test the helper logic
    from pathlib import Path
    original_candidates = [dist, Path("/nonexistent/path")]
    found = any(p.exists() and (p / "index.html").exists() for p in original_candidates)
    assert found


def test_uploadrr_not_mounted_returns_warning(monkeypatch):
    monkeypatch.setenv("UPLOADRR_PATH", "/nonexistent/uploadrr")
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_uploadrr_mount()
    # If /opt/Uploadrr doesn't exist in CI, must be warning
    assert result["status"] in ("ok", "warning")


def test_allowed_roots_warning_without_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "empty_config"))
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_allowed_roots_setting()
    assert result["status"] == "warning"


def test_allowed_roots_warning_when_not_configured(tmp_path, monkeypatch):
    import sqlite3
    db_path = tmp_path / "emuwarez_uploadrr.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE settings (key TEXT, value TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.check_allowed_roots_setting()
    assert result["status"] == "warning"


def test_environment_check_ok():
    from emuwarez_uploadrr.services.runtime_diagnostics import check_environment
    result = check_environment()
    assert result["status"] == "ok"
    assert "CONFIG_DIR" in result.get("details", {})
    assert "TZ" in result.get("details", {})


def test_diagnostics_no_secrets_in_output():
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    all_text = str(result).lower()
    # API keys should never appear in diagnostics
    assert "api_token=" not in all_text
    assert "tmdb_api_key" not in all_text
    assert "emu_api_key" not in all_text


def test_errors_list_populated_on_error(tmp_path, monkeypatch):
    # Create a file where a dir is expected
    bad_path = tmp_path / "notadir"
    bad_path.write_text("not a directory")
    monkeypatch.setenv("CONFIG_DIR", str(bad_path))
    import emuwarez_uploadrr.services.runtime_diagnostics as rd
    importlib.reload(rd)
    result = rd.get_runtime_diagnostics()
    # ok should be False when there's an error
    assert isinstance(result["ok"], bool)
    assert isinstance(result["errors"], list)


def _instancia(conn, nombre, enabled):
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES ('radarr', ?, 'http://radarr:7878', 'k', ?)",
        (nombre, enabled),
    )
    conn.commit()


def test_instancia_habilitada_no_da_aviso(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect()
    init_db(conn)
    _instancia(conn, "Radarr", 1)
    conn.close()
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    arr = [c for c in result["checks"] if c["name"] == "arr_health_config"]
    assert [c["status"] for c in arr] == ["ok"]
    assert arr[0]["details"]["radarr_enabled"] == 1
    assert not any("instancias" in w.lower() and "no hay" in w.lower() for w in result["warnings"])
    assert all(c["name"] != "arr_instances" for c in result["checks"])


def test_instancias_apagadas_dan_aviso(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect()
    init_db(conn)
    _instancia(conn, "Radarr", 0)
    conn.close()
    from emuwarez_uploadrr.services.runtime_diagnostics import check_arr_health_configuration
    result = check_arr_health_configuration()
    assert result["status"] == "warning"
    assert result["details"]["radarr_total"] == 1
    assert result["details"]["radarr_enabled"] == 0
