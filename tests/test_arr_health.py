"""Tests for ARR health service (Phase 8A)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def db_with_instances(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES ('radarr', 'Test Radarr', 'http://radarr:7878', 'testkey', 1)"
    )
    conn.commit()
    return conn


@pytest.fixture
def db_with_movie_item(db_with_instances):
    conn = db_with_instances
    inst_id = conn.execute("SELECT id FROM instances WHERE type='radarr' LIMIT 1").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO library_items
        (item_type, title, local_status, request_status, nomenclature_status, external_id, instance_id, instance_type, updated_at)
        VALUES ('movie', 'Test Movie', 'Faltante', 'Sin petición', 'N/A', '42', ?, 'radarr', CURRENT_TIMESTAMP)
        """,
        (inst_id,),
    )
    conn.commit()
    item_id = conn.execute("SELECT id FROM library_items LIMIT 1").fetchone()["id"]
    return conn, item_id, inst_id


def test_collect_arr_health_no_instances(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.arr_health import collect_arr_health
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)

    result = collect_arr_health(conn)

    assert "instances" in result
    assert "summary" in result
    assert result["instances"] == []


def test_collect_arr_health_with_instance(db_with_instances):
    from emuwarez_uploadrr.services.arr_health import collect_arr_health
    conn = db_with_instances

    with patch("emuwarez_uploadrr.services.arr_health.radarr_test_connection") as mock_test, \
         patch("emuwarez_uploadrr.services.arr_health.radarr_get_system_status") as mock_status:
        mock_test.return_value = {"ok": True, "version": "5.0.0"}
        mock_status.return_value = {"version": "5.0.0", "appName": "Radarr"}

        result = collect_arr_health(conn)

    assert len(result["instances"]) == 1
    assert result["instances"][0]["health_status"] == "ok"
    assert result["summary"]["radarr"] == 1


def test_collect_arr_health_connection_error(db_with_instances):
    from emuwarez_uploadrr.services.arr_health import collect_arr_health
    conn = db_with_instances

    with patch("emuwarez_uploadrr.services.arr_health.radarr_test_connection") as mock_test:
        mock_test.return_value = {"ok": False, "error": "Connection refused"}

        result = collect_arr_health(conn)

    assert result["instances"][0]["health_status"] == "error"
    assert result["summary"]["error"] == 1


def test_radarr_queue_maps_to_movie_item(db_with_movie_item):
    from emuwarez_uploadrr.services.arr_health import refresh_arr_queue_diagnostics
    conn, item_id, inst_id = db_with_movie_item

    fake_queue = [{"movieId": 42, "status": "downloading", "title": "Test Movie", "size": 1000, "sizeleft": 500, "statusMessages": []}]
    with patch("emuwarez_uploadrr.services.arr_health.radarr_get_queue") as mock_queue:
        mock_queue.return_value = fake_queue
        result = refresh_arr_queue_diagnostics(conn)

    assert result["library_items_updated"] == 1
    row = conn.execute("SELECT arr_queue_status FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["arr_queue_status"] == "downloading"


def test_radarr_history_import_error_saved(db_with_movie_item):
    from emuwarez_uploadrr.services.arr_health import refresh_arr_history_diagnostics
    conn, item_id, inst_id = db_with_movie_item

    fake_history = [{"movieId": 42, "eventType": "downloadFailed", "sourceTitle": "Test.Movie.mkv", "data": {"message": "Import failed"}}]
    with patch("emuwarez_uploadrr.services.arr_health.radarr_get_history") as mock_hist:
        mock_hist.return_value = fake_history
        result = refresh_arr_history_diagnostics(conn)

    assert result["library_items_updated"] == 1
    row = conn.execute("SELECT arr_history_status, arr_history_error FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["arr_history_status"] == "error"
    assert row["arr_history_error"] is not None


def test_no_api_keys_exposed_in_health(db_with_instances):
    from emuwarez_uploadrr.services.arr_health import collect_arr_health
    conn = db_with_instances

    with patch("emuwarez_uploadrr.services.arr_health.radarr_test_connection") as mock_test, \
         patch("emuwarez_uploadrr.services.arr_health.radarr_get_system_status") as mock_status:
        mock_test.return_value = {"ok": True}
        mock_status.return_value = {"version": "5.0"}

        result = collect_arr_health(conn)

    import json
    result_str = json.dumps(result)
    assert "testkey" not in result_str
