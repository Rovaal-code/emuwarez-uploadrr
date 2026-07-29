"""Tests for the "content_unique_changed" notification
(services/emu_catalog._notify_if_unique_content_changed) — fires after an
eMuwarez catalog sync with the {movies, seasons, episodes} "contenido único"
totals (same numbers as the Dashboard's get_dashboard_summary), but only when
they changed since the last time, so a resync with no changes doesn't spam.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.emu_catalog import _notify_if_unique_content_changed
from emuwarez_uploadrr.services.notification_center import list_notifications


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


# has_spanish_ok=1 by default: "contenido único" only counts what could
# actually be uploaded, and since the Castilian rule reaches films too
# (services/upload_checks.py) a film with neither Castilian audio nor Castilian
# subtitles isn't uploadable and doesn't belong in that count. These tests are
# about the notification, not about the language rule, so their films are
# ordinary uploadable ones. `spanish_ok=0` covers the opposite case.
def _movie(conn, title, emu_in_catalog, *, spanish_ok: int | None = 1):
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status, emu_in_catalog,
            has_spanish_ok, updated_at)
           VALUES ('movie', ?, 'Disponible', 'Sin petición', 'N/A', ?, ?, CURRENT_TIMESTAMP)""",
        (title, emu_in_catalog, spanish_ok),
    )
    conn.commit()


def test_first_computation_notifies(db_conn):
    _movie(db_conn, "Unique Movie", emu_in_catalog=0)
    _notify_if_unique_content_changed(db_conn)

    notes = list_notifications(db_conn)
    assert len(notes) == 1
    assert notes[0]["event_type"] == "content_unique_changed"
    assert "1 películas" in notes[0]["body"]


def test_unchanged_counts_do_not_renotify(db_conn):
    _movie(db_conn, "Unique Movie", emu_in_catalog=0)
    _notify_if_unique_content_changed(db_conn)
    assert len(list_notifications(db_conn)) == 1

    # Same counts again — no new notification.
    _notify_if_unique_content_changed(db_conn)
    assert len(list_notifications(db_conn)) == 1


def test_changed_counts_notify_again(db_conn):
    _movie(db_conn, "Unique Movie", emu_in_catalog=0)
    _notify_if_unique_content_changed(db_conn)
    assert len(list_notifications(db_conn)) == 1

    _movie(db_conn, "Another Unique Movie", emu_in_catalog=0)
    _notify_if_unique_content_changed(db_conn)
    notes = list_notifications(db_conn)
    assert len(notes) == 2
    assert "2 películas" in notes[0]["body"]


def test_zero_unique_content_does_not_notify_on_first_run(db_conn):
    """Nothing unique at all (e.g. a fresh library with everything already on
    eMuwarez) — baseline is {0,0,0} vs the stored default (also None/{}), and
    since there's nothing noteworthy to report, still notifies once so the
    user gets a real zero baseline... but a SECOND identical zero-run must not."""
    _movie(db_conn, "Already On eMuwarez", emu_in_catalog=1)
    _notify_if_unique_content_changed(db_conn)
    _notify_if_unique_content_changed(db_conn)
    # However many times it fired on the very first computation, a second
    # identical (zero) run must not add another.
    first_count = len(list_notifications(db_conn))
    _notify_if_unique_content_changed(db_conn)
    assert len(list_notifications(db_conn)) == first_count
