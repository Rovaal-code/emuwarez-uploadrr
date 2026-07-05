"""Tests for Phase 9A — operational_actions service."""
from __future__ import annotations

import json
import pytest


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert_library(conn, title="Test Movie", file_exists=1) -> int:
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            file_exists, updated_at)
           VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        ("movie", title, "Disponible", "Sin petición", "N/A", file_exists),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _insert_queue_item(conn, action="upload", status="ready",
                       library_item_id=None, upload_job_id=None,
                       request_item_id=None, title="Test Item") -> int:
    conn.execute(
        """INSERT INTO operational_queue_items
           (queue_key, item_type, entity_type, entity_id, title, status, action,
            blockers_json, reasons_json,
            library_item_id, upload_job_id, request_item_id, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
        (f"key-{action}-{title}", "upload_ready", "library", 1, title, status, action,
         "[]", '["Listo para subir"]',
         library_item_id, upload_job_id, request_item_id),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM operational_queue_items ORDER BY id DESC LIMIT 1"
    ).fetchone()["id"]


# ---------------------------------------------------------------------------
# get_queue_action_plan
# ---------------------------------------------------------------------------

def test_plan_not_found(db_conn):
    from emuwarez_uploadrr.services.operational_actions import get_queue_action_plan
    result = get_queue_action_plan(9999, db_conn)
    assert result["ok"] is False
    assert "9999" in result["error"]


def test_plan_upload_action(db_conn):
    from emuwarez_uploadrr.services.operational_actions import get_queue_action_plan
    iid = _insert_queue_item(db_conn, action="upload", title="Upload Movie")
    result = get_queue_action_plan(iid, db_conn)
    assert result["ok"] is True
    plan = result["plan"]
    assert plan["action"] == "upload"
    assert plan["flow"] == "upload_execution"
    assert plan["requires_confirmation"] is True
    assert plan["confirmation_token"] == "INICIAR_UPLOADRR"
    assert plan["safe_to_execute_inline"] is False
    assert plan["ui"]["route"] == "/uploads"


def test_plan_adapt_nomenclature(db_conn):
    from emuwarez_uploadrr.services.operational_actions import get_queue_action_plan
    iid = _insert_queue_item(db_conn, action="adapt_nomenclature")
    result = get_queue_action_plan(iid, db_conn)
    plan = result["plan"]
    assert plan["flow"] == "nomenclature"
    assert plan["ui"]["route"] == "/library"
    assert plan["confirmation_token"] == "APLICAR_NOMENCLATURA"


def test_plan_verify_file_safe(db_conn):
    from emuwarez_uploadrr.services.operational_actions import get_queue_action_plan
    iid = _insert_queue_item(db_conn, action="verify_file")
    result = get_queue_action_plan(iid, db_conn)
    plan = result["plan"]
    assert plan["safe_to_execute_inline"] is True
    assert plan["requires_confirmation"] is False


def test_plan_target_includes_library_item_id(db_conn):
    from emuwarez_uploadrr.services.operational_actions import get_queue_action_plan
    lib_id = _insert_library(db_conn)
    iid = _insert_queue_item(db_conn, action="adapt_nomenclature", library_item_id=lib_id)
    plan = get_queue_action_plan(iid, db_conn)["plan"]
    assert plan["target"].get("library_item_id") == lib_id


# ---------------------------------------------------------------------------
# list_available_queue_actions
# ---------------------------------------------------------------------------

def test_list_actions_not_found(db_conn):
    from emuwarez_uploadrr.services.operational_actions import list_available_queue_actions
    actions = list_available_queue_actions(9999, db_conn)
    assert actions == []


def test_list_actions_upload_includes_primary_and_view_plan(db_conn):
    from emuwarez_uploadrr.services.operational_actions import list_available_queue_actions
    iid = _insert_queue_item(db_conn, action="upload")
    actions = list_available_queue_actions(iid, db_conn)
    action_names = [a["action"] for a in actions]
    assert "upload" in action_names
    assert "view_plan" in action_names
    primary = next(a for a in actions if a["action"] == "upload")
    assert primary["primary"] is True


def test_list_actions_verify_file_added_when_library_item_present(db_conn):
    from emuwarez_uploadrr.services.operational_actions import list_available_queue_actions
    lib_id = _insert_library(db_conn)
    iid = _insert_queue_item(db_conn, action="upload", library_item_id=lib_id)
    actions = list_available_queue_actions(iid, db_conn)
    action_names = [a["action"] for a in actions]
    assert "verify_file" in action_names


def test_list_actions_verify_file_not_duplicated(db_conn):
    from emuwarez_uploadrr.services.operational_actions import list_available_queue_actions
    lib_id = _insert_library(db_conn)
    iid = _insert_queue_item(db_conn, action="verify_file", library_item_id=lib_id)
    actions = list_available_queue_actions(iid, db_conn)
    count = sum(1 for a in actions if a["action"] == "verify_file")
    assert count == 1


# ---------------------------------------------------------------------------
# execute_safe_queue_action
# ---------------------------------------------------------------------------

def test_execute_blocked_upload(db_conn):
    from emuwarez_uploadrr.services.operational_actions import execute_safe_queue_action
    iid = _insert_queue_item(db_conn, action="upload")
    result = execute_safe_queue_action(iid, db_conn, action="upload")
    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["guided_flow"] == "upload_execution"
    assert result["ui_route"] == "/uploads"
    assert result["confirmation_token"] == "INICIAR_UPLOADRR"


def test_execute_blocked_adapt_nomenclature(db_conn):
    from emuwarez_uploadrr.services.operational_actions import execute_safe_queue_action
    iid = _insert_queue_item(db_conn, action="adapt_nomenclature")
    result = execute_safe_queue_action(iid, db_conn, action="adapt_nomenclature")
    assert result["blocked"] is True
    assert result["guided_flow"] == "nomenclature"


def test_execute_view_plan_ok(db_conn):
    from emuwarez_uploadrr.services.operational_actions import execute_safe_queue_action
    iid = _insert_queue_item(db_conn, action="upload")
    result = execute_safe_queue_action(iid, db_conn, action="view_plan")
    assert result["ok"] is True
    assert result.get("blocked") is not True
    assert result.get("plan") is not None


def test_execute_not_found(db_conn):
    from emuwarez_uploadrr.services.operational_actions import execute_safe_queue_action
    result = execute_safe_queue_action(9999, db_conn)
    assert result["ok"] is False
    assert result.get("blocked") is not True


def test_execute_blocked_records_event(db_conn):
    from emuwarez_uploadrr.services.operational_actions import (
        execute_safe_queue_action, get_queue_action_events,
    )
    iid = _insert_queue_item(db_conn, action="retry_upload")
    execute_safe_queue_action(iid, db_conn, action="retry_upload")
    events = get_queue_action_events(iid, db_conn)
    assert len(events) > 0
    assert any(e["event_type"] == "blocked" for e in events)


def test_execute_view_plan_records_event(db_conn):
    from emuwarez_uploadrr.services.operational_actions import (
        execute_safe_queue_action, get_queue_action_events,
    )
    iid = _insert_queue_item(db_conn, action="upload")
    execute_safe_queue_action(iid, db_conn, action="view_plan")
    events = get_queue_action_events(iid, db_conn)
    assert len(events) > 0
    assert any("plan" in (e.get("action") or "") or "plan" in (e.get("event_type") or "") for e in events)


# ---------------------------------------------------------------------------
# get_queue_action_events
# ---------------------------------------------------------------------------

def test_events_empty_initially(db_conn):
    from emuwarez_uploadrr.services.operational_actions import get_queue_action_events
    iid = _insert_queue_item(db_conn, action="upload")
    events = get_queue_action_events(iid, db_conn)
    assert isinstance(events, list)
    assert len(events) == 0


def test_events_newest_first(db_conn):
    from emuwarez_uploadrr.services.operational_actions import (
        record_queue_action_event, get_queue_action_events,
    )
    iid = _insert_queue_item(db_conn, action="upload")
    record_queue_action_event(iid, "execute", "ok", "first", {}, db_conn)
    record_queue_action_event(iid, "execute", "ok", "second", {}, db_conn)
    events = get_queue_action_events(iid, db_conn)
    assert events[0]["message"] == "second"
    assert events[1]["message"] == "first"


def test_record_event_sanitizes_api_key(db_conn):
    from emuwarez_uploadrr.services.operational_actions import (
        record_queue_action_event, get_queue_action_events,
    )
    iid = _insert_queue_item(db_conn, action="upload")
    record_queue_action_event(
        iid, "execute", "ok", "test",
        {"api_key": "secret123", "data": "safe"},
        db_conn,
    )
    events = get_queue_action_events(iid, db_conn)
    details = json.loads(events[0]["details_json"] or "{}")
    assert "api_key" not in details
    assert details.get("data") == "safe"
