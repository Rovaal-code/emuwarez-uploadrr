"""Tests for Phase 8C — Unified operational queue service."""
from __future__ import annotations

import pytest


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert_request(conn, emu_id="emu-q1", title="Queue Movie", **kwargs) -> int:
    defaults = {"tmdb_id": None, "imdb_id": None, "category": "Pelicula"}
    defaults.update(kwargs)
    conn.execute(
        "INSERT OR IGNORE INTO request_items (emu_id, title, category, tmdb_id, imdb_id, updated_at) VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)",
        (emu_id, title, defaults["category"], defaults["tmdb_id"], defaults["imdb_id"]),
    )
    conn.commit()
    return conn.execute("SELECT id FROM request_items WHERE emu_id = ?", (emu_id,)).fetchone()["id"]


def _insert_library(conn, title="Queue Movie", **kwargs) -> int:
    defaults = {
        "item_type": "movie", "local_status": "Disponible", "request_status": "Sin petición",
        "nomenclature_status": "N/A", "file_exists": 1, "tmdb_id": None,
        "recommended_action": None, "arr_queue_status": None, "arr_history_status": None,
    }
    defaults.update(kwargs)
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            file_exists, tmdb_id, recommended_action, arr_queue_status, arr_history_status,
            updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (defaults["item_type"], title, defaults["local_status"], defaults["request_status"],
         defaults["nomenclature_status"], defaults["file_exists"], defaults["tmdb_id"],
         defaults["recommended_action"], defaults["arr_queue_status"], defaults["arr_history_status"]),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _insert_upload_job(conn, title="Upload Movie", status="ready") -> int:
    conn.execute(
        "INSERT INTO upload_jobs (title, path, status) VALUES (?,?,?)",
        (title, "/data/movie.mkv", status),
    )
    conn.commit()
    return conn.execute("SELECT id FROM upload_jobs ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _seed_request_readiness(conn, req_id, status="no_local_match", bucket="low", score=10):
    conn.execute(
        """INSERT OR REPLACE INTO request_readiness
           (request_item_id, status, recommended_action, priority_score, priority_bucket,
            last_evaluated_at, created_at, updated_at)
           VALUES (?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
        (req_id, status, "review_arr", score, bucket),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# refresh creates items from request_readiness
# ---------------------------------------------------------------------------

def test_refresh_creates_items_from_request_readiness(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue, list_operational_queue
    req_id = _insert_request(db_conn, "emu-rr", "Readiness Movie")
    _seed_request_readiness(db_conn, req_id, status="ready_to_upload", bucket="high", score=80)
    result = refresh_operational_queue(db_conn)
    assert result["ok"] is True
    assert result["items_built"] >= 1
    items = list_operational_queue(db_conn)
    keys = [i["queue_key"] for i in items]
    assert f"request:{req_id}:readiness" in keys


# ---------------------------------------------------------------------------
# refresh creates items from library recommendations
# ---------------------------------------------------------------------------

def test_refresh_creates_items_from_library_recommendations(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue, list_operational_queue
    _insert_library(db_conn, "Rec Movie", recommended_action="adapt_nomenclature")
    result = refresh_operational_queue(db_conn)
    assert result["ok"] is True
    items = list_operational_queue(db_conn)
    types = [i["item_type"] for i in items]
    assert "library_recommendation" in types


# ---------------------------------------------------------------------------
# refresh creates items from upload jobs
# ---------------------------------------------------------------------------

def test_refresh_creates_items_from_upload_jobs(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue, list_operational_queue
    job_id = _insert_upload_job(db_conn, status="ready")
    result = refresh_operational_queue(db_conn)
    assert result["ok"] is True
    items = list_operational_queue(db_conn)
    keys = [i["queue_key"] for i in items]
    assert f"upload:{job_id}:status" in keys


# ---------------------------------------------------------------------------
# refresh creates items from ARR diagnostics
# ---------------------------------------------------------------------------

def test_refresh_creates_items_from_arr_diagnostics(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue, list_operational_queue
    lib_id = _insert_library(db_conn, "ARR Error Movie", arr_queue_status="import_error")
    result = refresh_operational_queue(db_conn)
    assert result["ok"] is True
    items = list_operational_queue(db_conn)
    types = [i["item_type"] for i in items]
    assert "arr_issue" in types


# ---------------------------------------------------------------------------
# Refresh does NOT duplicate items
# ---------------------------------------------------------------------------

def test_no_duplicates_on_repeated_refresh(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue, list_operational_queue
    req_id = _insert_request(db_conn, "emu-dup", "Dup Movie")
    _seed_request_readiness(db_conn, req_id, status="no_local_match")
    refresh_operational_queue(db_conn)
    refresh_operational_queue(db_conn)
    items = list_operational_queue(db_conn)
    keys = [i["queue_key"] for i in items]
    assert keys.count(f"request:{req_id}:readiness") == 1


# ---------------------------------------------------------------------------
# Disappeared item gets resolved
# ---------------------------------------------------------------------------

def test_disappeared_item_gets_resolved(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue
    # insert a request with readiness
    req_id = _insert_request(db_conn, "emu-gone", "Gone Movie")
    _seed_request_readiness(db_conn, req_id, status="downloading")
    refresh_operational_queue(db_conn)
    # remove readiness row (simulates item disappearing)
    db_conn.execute("DELETE FROM request_readiness WHERE request_item_id = ?", (req_id,))
    db_conn.execute("DELETE FROM request_items WHERE id = ?", (req_id,))
    db_conn.commit()
    refresh_operational_queue(db_conn)
    row = db_conn.execute(
        "SELECT status FROM operational_queue_items WHERE queue_key = ?",
        (f"request:{req_id}:readiness",),
    ).fetchone()
    assert row is not None
    assert row["status"] == "resolved"


# ---------------------------------------------------------------------------
# queue_key is deterministic
# ---------------------------------------------------------------------------

def test_queue_key_is_deterministic(db_conn):
    from emuwarez_uploadrr.services.operational_queue import upsert_queue_item
    item = {
        "queue_key": "request:99:readiness",
        "item_type": "request_readiness",
        "entity_type": "request",
        "status": "open",
        "action": "review_arr",
    }
    r1 = upsert_queue_item(item, db_conn)
    r2 = upsert_queue_item(item, db_conn)
    assert r1["id"] == r2["id"]
    assert r1["queue_key"] == r2["queue_key"]


# ---------------------------------------------------------------------------
# Priority buckets correct
# ---------------------------------------------------------------------------

def test_priority_buckets_correct(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue, list_operational_queue
    req_id = _insert_request(db_conn, "emu-critical", "Critical Movie")
    _seed_request_readiness(db_conn, req_id, status="ready_to_upload", bucket="high", score=95)
    refresh_operational_queue(db_conn)
    items = list_operational_queue(db_conn)
    rr_items = [i for i in items if i["queue_key"] == f"request:{req_id}:readiness"]
    assert len(rr_items) == 1
    # score >= 90 → critical
    assert rr_items[0]["priority_bucket"] == "critical"


# ---------------------------------------------------------------------------
# Summary counts correctly
# ---------------------------------------------------------------------------

def test_summary_counts(db_conn):
    from emuwarez_uploadrr.services.operational_queue import upsert_queue_item, get_operational_queue_summary
    upsert_queue_item({"queue_key": "test:1", "item_type": "x", "entity_type": "y", "status": "ready", "action": "upload"}, db_conn)
    upsert_queue_item({"queue_key": "test:2", "item_type": "x", "entity_type": "y", "status": "waiting", "action": "wait_download"}, db_conn)
    upsert_queue_item({"queue_key": "test:3", "item_type": "x", "entity_type": "y", "status": "blocked", "action": "review_arr"}, db_conn)
    db_conn.commit()
    summary = get_operational_queue_summary(db_conn)
    assert summary["ready"] >= 1
    assert summary["waiting"] >= 1
    assert summary["blocked"] >= 1


# ---------------------------------------------------------------------------
# resolve marks resolved_at
# ---------------------------------------------------------------------------

def test_resolve_marks_resolved_at(db_conn):
    from emuwarez_uploadrr.services.operational_queue import upsert_queue_item, mark_queue_item_resolved
    item = upsert_queue_item({"queue_key": "resolve:1", "item_type": "x", "entity_type": "y", "status": "open", "action": "none"}, db_conn)
    db_conn.commit()
    result = mark_queue_item_resolved(item["id"], db_conn, reason="done")
    assert result["ok"] is True
    row = db_conn.execute("SELECT status, resolved_at FROM operational_queue_items WHERE id = ?", (item["id"],)).fetchone()
    assert row["status"] == "resolved"
    assert row["resolved_at"] is not None


# ---------------------------------------------------------------------------
# ignore marks ignored
# ---------------------------------------------------------------------------

def test_ignore_marks_ignored(db_conn):
    from emuwarez_uploadrr.services.operational_queue import upsert_queue_item, ignore_queue_item
    item = upsert_queue_item({"queue_key": "ignore:1", "item_type": "x", "entity_type": "y", "status": "open", "action": "none"}, db_conn)
    db_conn.commit()
    result = ignore_queue_item(item["id"], db_conn, reason="not needed")
    assert result["ok"] is True
    row = db_conn.execute("SELECT status FROM operational_queue_items WHERE id = ?", (item["id"],)).fetchone()
    assert row["status"] == "ignored"


# ---------------------------------------------------------------------------
# No API keys exposed
# ---------------------------------------------------------------------------

def test_no_api_keys_in_queue_output(db_conn):
    from emuwarez_uploadrr.services.operational_queue import refresh_operational_queue, list_operational_queue
    result = refresh_operational_queue(db_conn)
    result_str = str(result)
    items = list_operational_queue(db_conn)
    items_str = str(items)
    for forbidden in ("api_key", "apikey", "token", "password", "secret"):
        assert forbidden.lower() not in result_str.lower()
        assert forbidden.lower() not in items_str.lower()
