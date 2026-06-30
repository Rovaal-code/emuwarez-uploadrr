"""Tests for Phase 8C — CLI 'queue' command group."""
from __future__ import annotations

import sys
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


# ---------------------------------------------------------------------------
# summary — empty
# ---------------------------------------------------------------------------

def test_queue_summary_empty(capsys):
    rc = _run(["queue", "summary"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "total" in out.lower() or "0" in out


# ---------------------------------------------------------------------------
# refresh — empty sources
# ---------------------------------------------------------------------------

def test_queue_refresh_empty(capsys):
    rc = _run(["queue", "refresh"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ok" in out.lower() or "refresh" in out.lower() or "cola" in out.lower()


# ---------------------------------------------------------------------------
# list — empty
# ---------------------------------------------------------------------------

def test_queue_list_empty(capsys):
    rc = _run(["queue", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "sin" in out.lower() or "vacía" in out.lower() or "empty" in out.lower() or "0" in out


# ---------------------------------------------------------------------------
# show — unknown ID
# ---------------------------------------------------------------------------

def test_queue_show_unknown(capsys):
    rc = _run(["queue", "show", "99999"])
    assert rc != 0 or "no encontrado" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# resolve — unknown ID
# ---------------------------------------------------------------------------

def test_queue_resolve_unknown(capsys):
    rc = _run(["queue", "resolve", "99999"])
    assert rc != 0 or "no encontrado" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# ignore — unknown ID
# ---------------------------------------------------------------------------

def test_queue_ignore_unknown(capsys):
    rc = _run(["queue", "ignore", "99999"])
    assert rc != 0 or "no encontrado" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# No API keys in CLI output
# ---------------------------------------------------------------------------

def test_no_api_keys_in_cli_output(capsys):
    _run(["queue", "refresh"])
    _run(["queue", "summary"])
    _run(["queue", "list"])
    out = capsys.readouterr().out
    for forbidden in ("api_key", "apikey", "password", "secret"):
        assert forbidden.lower() not in out.lower(), f"Sensitive key '{forbidden}' found in CLI output"
