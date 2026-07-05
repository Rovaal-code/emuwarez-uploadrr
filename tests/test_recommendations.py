"""Tests for the recommendation engine (Phase 8A)."""
from __future__ import annotations

import pytest


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert_item(conn, **kwargs) -> int:
    defaults = {
        "item_type": "movie",
        "title": "Test",
        "local_status": "Disponible",
        "request_status": "Sin petición",
        "nomenclature_status": "N/A",
        "file_exists": None,
        "arr_queue_status": None,
        "arr_history_status": None,
        "arr_history_event_type": None,
        "arr_history_error": None,
        "arr_queue_error": None,
        "arr_queue_progress": None,
        "prepared_path": None,
    }
    defaults.update(kwargs)
    conn.execute(
        """
        INSERT INTO library_items
        (item_type, title, local_status, request_status, nomenclature_status,
         file_exists, arr_queue_status, arr_history_status, arr_history_event_type,
         arr_history_error, arr_queue_error, arr_queue_progress, prepared_path, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            defaults["item_type"], defaults["title"], defaults["local_status"],
            defaults["request_status"], defaults["nomenclature_status"],
            defaults["file_exists"], defaults["arr_queue_status"],
            defaults["arr_history_status"], defaults["arr_history_event_type"],
            defaults["arr_history_error"], defaults["arr_queue_error"],
            defaults["arr_queue_progress"], defaults["prepared_path"],
        ),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def test_available_file_exists_not_adapted_recommends_nomenclature(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Disponible",
        nomenclature_status="No adaptada",
        file_exists=1,
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "adapt_nomenclature"


def test_available_file_missing_recommends_fix_path(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Disponible",
        nomenclature_status="No adaptada",
        file_exists=0,
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "fix_path"


def test_downloading_recommends_view_progress(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Faltante",
        arr_queue_status="downloading",
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "view_progress"


def test_queued_recommends_wait_download(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Faltante",
        arr_queue_status="queued",
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "wait_download"


def test_import_error_recommends_review_arr(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Faltante",
        arr_queue_status="import_error",
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "review_arr"


def test_pending_import_recommends_review_arr(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Faltante",
        arr_queue_status="pending_import",
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "review_arr"


def test_missing_no_queue_recommends_review_arr(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Faltante",
        arr_queue_status=None,
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "review_arr"


def test_available_nomenclature_correct_no_prepared_recommends_preflight(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Disponible",
        nomenclature_status="Correcta",
        file_exists=1,
        prepared_path=None,
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "run_preflight"


def test_available_nomenclature_correct_with_prepared_recommends_upload(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Disponible",
        nomenclature_status="Correcta",
        file_exists=1,
        prepared_path="/tmp/prepared/movie.mkv",
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] == "upload"


def test_no_create_emu_request_when_in_queue(db_conn):
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(
        db_conn,
        local_status="Faltante",
        arr_queue_status="downloading",
        request_status="Sin petición",
    )
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["recommended_action"] != "create_emu_request"


def test_get_recommendation_for_item_not_found(db_conn):
    from emuwarez_uploadrr.services.recommendations import get_recommendation_for_item
    result = get_recommendation_for_item(99999, db_conn)
    assert result is None


def test_refresh_recommendations_returns_counts(db_conn):
    from emuwarez_uploadrr.services.recommendations import refresh_recommendations
    _insert_item(db_conn, local_status="Disponible", file_exists=1, nomenclature_status="No adaptada")
    _insert_item(db_conn, local_status="Faltante")

    result = refresh_recommendations(db_conn)

    assert result["ok"] is True
    assert result["items_updated"] == 2
    assert result["errors"] == 0


def test_build_recommendation_for_series_row_is_not_applicable(db_conn):
    """Series/season rollup rows have no file of their own — no per-file
    diagnostic should ever be computed/persisted for them."""
    from emuwarez_uploadrr.services.recommendations import build_recommendation_for_item
    item_id = _insert_item(db_conn, item_type="series", local_status="Parcial")
    result = build_recommendation_for_item(item_id, db_conn)
    assert result["ok"] is True
    assert result["diagnostic_status"] == "not_applicable"
    assert result["recommended_action"] == "none"

    row = db_conn.execute(
        "SELECT diagnostic_status, recommended_action FROM library_items WHERE id = ?", (item_id,)
    ).fetchone()
    assert row["diagnostic_status"] == "not_applicable"
    assert row["recommended_action"] == "none"


def test_refresh_recommendations_skips_series_and_season_rows(db_conn):
    from emuwarez_uploadrr.services.recommendations import refresh_recommendations
    _insert_item(db_conn, local_status="Disponible", file_exists=1, nomenclature_status="No adaptada")
    _insert_item(db_conn, item_type="series", local_status="Parcial")
    _insert_item(db_conn, item_type="season", local_status="Parcial")

    result = refresh_recommendations(db_conn)

    assert result["items_updated"] == 1
    for row in db_conn.execute("SELECT item_type, recommended_action FROM library_items").fetchall():
        if row["item_type"] in ("series", "season"):
            assert row["recommended_action"] is None
