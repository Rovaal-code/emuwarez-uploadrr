"""Tests for the eMuwarez catalog comparison rollup
(services/emu_catalog._compute_and_store_item_status): every movie/season is
marked present (1) or not (0) on eMuwarez, and a series rolls up to
0 = no seasons, 1 = all seasons, 2 = partial (some on, some off). Specials
(season 0/None) are excluded from the partial calculation.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.emu_catalog import _compute_and_store_item_status


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _series(conn, title, tvdb_id):
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status, tvdb_id, updated_at)
           VALUES ('series', ?, 'Disponible', 'Sin petición', 'N/A', ?, CURRENT_TIMESTAMP)""",
        (title, str(tvdb_id)),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _season(conn, parent_id, tvdb_id, season_number):
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            parent_id, tvdb_id, season_number, updated_at)
           VALUES ('season', ?, 'Disponible', 'Sin petición', 'N/A', ?, ?, ?, CURRENT_TIMESTAMP)""",
        (f"S{season_number}", parent_id, str(tvdb_id), season_number),
    )
    conn.commit()


def _catalog_series(conn, tvdb_id, season_number, name="Show S0X 1080p WEB-DL"):
    conn.execute(
        """INSERT INTO emu_catalog
           (torrent_id, category, tvdb_id, season_number, resolution, source, codec, has_spanish, size, name)
           VALUES (?, 'Series', ?, ?, '1080p', 'WEB-DL', NULL, NULL, 1, ?)""",
        (f"t{tvdb_id}-{season_number}", str(tvdb_id), season_number, name),
    )
    conn.commit()


def test_series_all_seasons_present_is_si(db_conn):
    sid = _series(db_conn, "Fully There", tvdb_id=100)
    _season(db_conn, sid, 100, 1)
    _season(db_conn, sid, 100, 2)
    _catalog_series(db_conn, 100, 1)
    _catalog_series(db_conn, 100, 2)

    _compute_and_store_item_status(db_conn)
    assert db_conn.execute("SELECT emu_in_catalog FROM library_items WHERE id=?", (sid,)).fetchone()[0] == 1


def test_series_no_seasons_present_is_no(db_conn):
    sid = _series(db_conn, "Not There", tvdb_id=200)
    _season(db_conn, sid, 200, 1)
    _season(db_conn, sid, 200, 2)
    # no catalog rows for tvdb 200

    _compute_and_store_item_status(db_conn)
    assert db_conn.execute("SELECT emu_in_catalog FROM library_items WHERE id=?", (sid,)).fetchone()[0] == 0


def test_series_mixed_seasons_is_partial(db_conn):
    sid = _series(db_conn, "Half There", tvdb_id=300)
    _season(db_conn, sid, 300, 1)
    _season(db_conn, sid, 300, 2)
    _season(db_conn, sid, 300, 3)
    _catalog_series(db_conn, 300, 1)  # only S1 on eMuwarez

    _compute_and_store_item_status(db_conn)
    assert db_conn.execute("SELECT emu_in_catalog FROM library_items WHERE id=?", (sid,)).fetchone()[0] == 2
    # the individual seasons still carry their own state
    rows = {
        r["season_number"]: r["emu_in_catalog"]
        for r in db_conn.execute(
            "SELECT season_number, emu_in_catalog FROM library_items WHERE parent_id=? AND item_type='season'", (sid,)
        )
    }
    assert rows == {1: 1, 2: 0, 3: 0}


def test_missing_specials_ignored_when_setting_on(db_conn):
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    set_setting(db_conn, "series.ignore_specials", "true")
    sid = _series(db_conn, "Complete But Specials", tvdb_id=400)
    _season(db_conn, sid, 400, 0)  # specials, not on eMuwarez
    _season(db_conn, sid, 400, 1)
    _season(db_conn, sid, 400, 2)
    _catalog_series(db_conn, 400, 1)
    _catalog_series(db_conn, 400, 2)

    _compute_and_store_item_status(db_conn)
    # with "Ignorar especiales" ON, all *real* seasons present → Sí
    assert db_conn.execute("SELECT emu_in_catalog FROM library_items WHERE id=?", (sid,)).fetchone()[0] == 1
    # ...but the specials season itself is still marked "No" (uploadable)
    special = db_conn.execute(
        "SELECT emu_in_catalog FROM library_items WHERE parent_id=? AND season_number=0", (sid,)
    ).fetchone()[0]
    assert special == 0


def test_missing_specials_count_when_setting_off(db_conn):
    # With "Ignorar especiales" explicitly OFF, a missing special counts, so a
    # series complete except its specials is Partial (consistent with
    # Estado/Nomenclatura). Default is ON, so we set it off here.
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    set_setting(db_conn, "series.ignore_specials", "false")
    sid = _series(db_conn, "Complete But Specials Off", tvdb_id=410)
    _season(db_conn, sid, 410, 0)  # specials, not on eMuwarez
    _season(db_conn, sid, 410, 1)
    _catalog_series(db_conn, 410, 1)

    _compute_and_store_item_status(db_conn)
    assert db_conn.execute("SELECT emu_in_catalog FROM library_items WHERE id=?", (sid,)).fetchone()[0] == 2
