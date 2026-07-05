"""Tests for Phase 9A — CLI queue action subcommands."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def patched_db(isolated_db, monkeypatch):
    from emuwarez_uploadrr.database import connect, init_db
    db_path = isolated_db / "emuwarez_uploadrr.db"
    conn = connect(db_path)
    init_db(conn)
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('api_token', 'clitoken')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("EMUWAREZ_DB", str(db_path))
    return db_path


def _run(args: list[str]) -> int:
    from emuwarez_uploadrr.cli import modern_main
    return modern_main(args)


def _insert_queue_item(patched_db, action="upload", title="CLI Test") -> int:
    from emuwarez_uploadrr.database import connect
    conn = connect(patched_db)
    conn.execute(
        """INSERT INTO operational_queue_items
           (queue_key, item_type, entity_type, entity_id, title, status, action,
            blockers_json, reasons_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
        (f"key-cli-{action}", "upload_ready", "library", 1, title, "ready", action,
         "[]", "[]"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM operational_queue_items ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["id"]


def test_actions_missing_item_exits_nonzero(capsys, patched_db):
    rc = _run(["queue", "actions", "99999"])
    assert rc != 0


def test_actions_lists_primary_action(capsys, patched_db):
    iid = _insert_queue_item(patched_db, action="upload", title="Upload Item")
    rc = _run(["queue", "actions", str(iid)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "upload" in out.lower()


def test_action_plan_missing_item(capsys, patched_db):
    rc = _run(["queue", "action-plan", "99999"])
    assert rc != 0


def test_action_plan_shows_flow(capsys, patched_db):
    iid = _insert_queue_item(patched_db, action="adapt_nomenclature", title="Nom Test")
    rc = _run(["queue", "action-plan", str(iid)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "nomenclature" in out.lower() or "library" in out.lower()


def test_execute_safe_blocked_shows_guidance(capsys, patched_db):
    iid = _insert_queue_item(patched_db, action="upload", title="Upload Block")
    rc = _run(["queue", "execute-safe", str(iid), "--action", "upload"])
    assert rc != 0
    out = capsys.readouterr().out
    assert "bloqueada" in out.lower() or "guiado" in out.lower() or "blocked" in out.lower()


def test_execute_safe_view_plan_ok(capsys, patched_db):
    iid = _insert_queue_item(patched_db, action="upload", title="View Plan")
    rc = _run(["queue", "execute-safe", str(iid), "--action", "view_plan"])
    assert rc == 0


def test_events_empty(capsys, patched_db):
    iid = _insert_queue_item(patched_db, action="upload", title="Events Test")
    rc = _run(["queue", "events", str(iid)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "sin eventos" in out.lower() or "no hay" in out.lower() or "event" in out.lower()


def test_events_limit_option(capsys, patched_db):
    iid = _insert_queue_item(patched_db, action="upload", title="Events Limit")
    rc = _run(["queue", "events", str(iid), "--limit", "5"])
    assert rc == 0
