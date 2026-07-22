"""Tests for services/library.py::_lib_sync_guard() — the shared active/done
lifecycle around sync_all(). Before this, only start_library_sync_background()
(the manual "sincronizar biblioteca" button) ever set `active`, so a sync
triggered by the scheduled sync-library task or the setup wizard's blocking
/sync never showed up in the UI's sync banner, never blocked the manual
button, and nothing stopped them running concurrently.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import library, scheduler


@pytest.fixture(autouse=True)
def _reset_lib_sync_progress():
    """_LIB_SYNC_PROGRESS is a module-level singleton — reset it around every
    test so state from one test can never leak into the next."""
    with library._LIB_SYNC_LOCK:
        library._LIB_SYNC_PROGRESS.update(
            active=False, done=False, phase="", imported=0, missing=0,
            total=0, instance="", instance_type="", error=None,
        )
    yield
    with library._LIB_SYNC_LOCK:
        library._LIB_SYNC_PROGRESS.update(
            active=False, done=False, phase="", imported=0, missing=0,
            total=0, instance="", instance_type="", error=None,
        )


def test_guard_marks_active_during_and_done_after_success():
    seen_active_inside = None
    with library._lib_sync_guard():
        seen_active_inside = library.get_lib_sync_progress()["active"]
    after = library.get_lib_sync_progress()
    assert seen_active_inside is True
    assert after["active"] is False
    assert after["done"] is True


def test_guard_resets_active_and_records_error_on_failure():
    with pytest.raises(RuntimeError, match="boom"):
        with library._lib_sync_guard():
            raise RuntimeError("boom")
    after = library.get_lib_sync_progress()
    assert after["active"] is False
    assert after["done"] is True
    assert after["error"] == "boom"


def test_guard_refuses_a_second_overlapping_sync():
    with library._lib_sync_guard():
        with pytest.raises(library.SyncAlreadyRunning):
            with library._lib_sync_guard():
                pass
        # The outer (first) guard is still legitimately active.
        assert library.get_lib_sync_progress()["active"] is True
    # Released once the outer guard's `with` block exits.
    assert library.get_lib_sync_progress()["active"] is False


def test_scheduled_library_sync_skips_when_a_sync_is_already_running(isolated_db):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path())
    init_db(conn)
    with library._lib_sync_guard():
        status, summary = scheduler._run_library_sync(conn)
    assert status == "skipped"
    assert "en marcha" in summary.lower()
