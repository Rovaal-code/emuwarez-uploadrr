"""Tests for ARR diagnostics CLI commands (Phase 8A)."""
from __future__ import annotations

from unittest.mock import patch


def _run_cli(args_list, isolated_db):
    import os
    os.environ["CONFIG_DIR"] = str(isolated_db)
    from emuwarez_uploadrr.cli import modern_main
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    conn.close()
    return modern_main(["--db", str(isolated_db / "emuwarez_uploadrr.db")] + args_list)


def test_arr_health_no_instances(isolated_db, capsys):
    rc = _run_cli(["arr", "health"], isolated_db)
    assert rc == 0
    captured = capsys.readouterr()
    assert "instancias" in captured.out.lower()


def test_arr_health_with_mocked_instance(isolated_db, capsys):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES ('radarr', 'Radarr Local', 'http://radarr:7878', 'testkey', 1)"
    )
    conn.commit()
    conn.close()

    with patch("emuwarez_uploadrr.services.arr_health.radarr_test_connection") as mock_test, \
         patch("emuwarez_uploadrr.services.arr_health.radarr_get_system_status") as mock_status:
        mock_test.return_value = {"ok": True, "version": "5.0.0"}
        mock_status.return_value = {"version": "5.0.0", "appName": "Radarr"}
        rc = _run_cli(["arr", "health"], isolated_db)

    assert rc == 0
    captured = capsys.readouterr()
    assert "Radarr" in captured.out or "radarr" in captured.out.lower()


def test_arr_refresh_health_no_instances(isolated_db, capsys):
    rc = _run_cli(["arr", "refresh-health"], isolated_db)
    assert rc == 0


def test_library_verify_files_empty(isolated_db, capsys):
    rc = _run_cli(["library", "verify-files"], isolated_db)
    assert rc == 0
    captured = capsys.readouterr()
    assert "Verificados" in captured.out


def test_library_recommendations_empty(isolated_db, capsys):
    rc = _run_cli(["library", "recommendations"], isolated_db)
    assert rc == 0
    captured = capsys.readouterr()
    assert "recalculadas" in captured.out.lower()


def test_library_diagnostics_empty(isolated_db, capsys):
    rc = _run_cli(["library", "diagnostics"], isolated_db)
    assert rc == 0


def test_missing_diagnostics_empty(isolated_db, capsys):
    rc = _run_cli(["missing", "diagnostics"], isolated_db)
    assert rc == 0
    captured = capsys.readouterr()
    assert "faltantes" in captured.out.lower() or len(captured.out) > 0


def test_cli_no_api_keys_in_arr_health_output(isolated_db, capsys):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES ('radarr', 'Test', 'http://radarr', 'SECRET_KEY_123', 1)"
    )
    conn.commit()
    conn.close()

    with patch("emuwarez_uploadrr.services.arr_health.radarr_test_connection") as mock_test, \
         patch("emuwarez_uploadrr.services.arr_health.radarr_get_system_status") as mock_status:
        mock_test.return_value = {"ok": True}
        mock_status.return_value = {"version": "5.0"}
        rc = _run_cli(["arr", "health"], isolated_db)

    captured = capsys.readouterr()
    assert "SECRET_KEY_123" not in captured.out
    assert rc == 0
