"""Tests for sync_emu_catalog()'s pre-flight connectivity check: before this,
a full/incremental sync went straight into the paginated download with no
check that eMuwarez was even reachable, so a down/unreachable tracker only
surfaced (if at all) deep inside the fetch loop instead of failing fast with
a clear error.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import emu_catalog
from emuwarez_uploadrr.services.settings import set_setting


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    set_setting(conn, "emu.api_key", "FAKEKEY")
    conn.commit()
    return conn


def test_unreachable_emu_fails_fast_without_fetching_catalog(db_conn, monkeypatch):
    calls = {"test_connection": 0, "fetch_all": 0}

    def fake_test_connection(api_key, base_url=None, **kw):
        calls["test_connection"] += 1
        raise IntegrationError("Connection refused")

    def fake_fetch_all_torrents(*args, **kwargs):
        calls["fetch_all"] += 1
        return []

    monkeypatch.setattr(emu_catalog.emu, "emu_test_connection", fake_test_connection)
    monkeypatch.setattr(emu_catalog.emu, "emu_fetch_all_torrents", fake_fetch_all_torrents)

    with pytest.raises(IntegrationError):
        emu_catalog.sync_emu_catalog(db_conn, force=True, mode="full")

    assert calls["test_connection"] == 1
    # The expensive paginated download must never start if eMuwarez isn't reachable.
    assert calls["fetch_all"] == 0


def test_reachable_emu_proceeds_to_fetch_catalog(db_conn, monkeypatch):
    calls = {"test_connection": 0, "fetch_all": 0}

    def fake_test_connection(api_key, base_url=None, **kw):
        calls["test_connection"] += 1
        return {"data": []}

    def fake_fetch_all_torrents(*args, **kwargs):
        calls["fetch_all"] += 1
        return []

    monkeypatch.setattr(emu_catalog.emu, "emu_test_connection", fake_test_connection)
    monkeypatch.setattr(emu_catalog.emu, "emu_fetch_all_torrents", fake_fetch_all_torrents)

    result = emu_catalog.sync_emu_catalog(db_conn, force=True, mode="full")

    assert calls["test_connection"] == 1
    assert calls["fetch_all"] == 1
    assert result["status"] == "ok"
    # The completed marker must be set once a sync genuinely finishes.
    from emuwarez_uploadrr.database import get_state
    assert get_state(db_conn, emu_catalog.SYNC_COMPLETED_STATE_KEY)
