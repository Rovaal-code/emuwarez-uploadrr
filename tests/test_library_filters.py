"""Tests for list_library()/count_library() filter parity (Phase 4A of the
12-part batch) — count_library() used to silently ignore request/
nomenclature/origin/instance_id, so `total` went out of sync with the
actual filtered `items` list as soon as any of those filters were used."""
from __future__ import annotations

import pytest


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert(conn, title, **kwargs):
    defaults = {
        "item_type": "movie", "local_status": "Disponible",
        "request_status": "Sin petición", "nomenclature_status": "N/A",
        "instance_type": "radarr", "instance_id": None,
    }
    defaults.update(kwargs)
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            instance_type, instance_id, updated_at)
           VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (defaults["item_type"], title, defaults["local_status"],
         defaults["request_status"], defaults["nomenclature_status"],
         defaults["instance_type"], defaults["instance_id"]),
    )
    conn.commit()


def test_count_matches_list_length_with_nomenclature_filter(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library
    _insert(db_conn, "Adapted", nomenclature_status="Correcta")
    _insert(db_conn, "Not adapted", nomenclature_status="No adaptada")
    _insert(db_conn, "Also not adapted", nomenclature_status="No adaptada")

    items = list_library(db_conn, nomenclature="No adaptada")
    total = count_library(db_conn, nomenclature="No adaptada")
    assert len(items) == 2
    assert total == 2


def test_count_matches_list_length_with_request_filter(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library
    _insert(db_conn, "Has request", request_status="Compatible")
    _insert(db_conn, "No request", request_status="Sin petición")

    items = list_library(db_conn, request="Compatible")
    total = count_library(db_conn, request="Compatible")
    assert len(items) == 1
    assert total == 1


def test_count_matches_list_length_with_origin_filter(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library
    _insert(db_conn, "Radarr item", instance_type="radarr")
    _insert(db_conn, "Sonarr item 1", instance_type="sonarr")
    _insert(db_conn, "Sonarr item 2", instance_type="sonarr")

    items = list_library(db_conn, origin="sonarr")
    total = count_library(db_conn, origin="sonarr")
    assert len(items) == 2
    assert total == 2


def test_count_matches_list_length_with_instance_id_filter(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library
    _insert(db_conn, "Instance 1 item", instance_id=1)
    _insert(db_conn, "Instance 2 item A", instance_id=2)
    _insert(db_conn, "Instance 2 item B", instance_id=2)

    items = list_library(db_conn, instance_id=2)
    total = count_library(db_conn, instance_id=2)
    assert len(items) == 2
    assert total == 2


def test_not_available_sentinel_matches_all_missing_statuses(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library, NOT_AVAILABLE_STATUS_FILTER
    _insert(db_conn, "Available", local_status="Disponible")
    _insert(db_conn, "Missing", local_status="Faltante")
    _insert(db_conn, "Queued", local_status="En cola")
    _insert(db_conn, "Pending import", local_status="Pendiente de importar")
    _insert(db_conn, "Search error", local_status="Error de búsqueda")

    items = list_library(db_conn, status=NOT_AVAILABLE_STATUS_FILTER)
    total = count_library(db_conn, status=NOT_AVAILABLE_STATUS_FILTER)
    assert len(items) == 4
    assert total == 4
    assert all(i["title"] != "Available" for i in items)


def test_count_matches_list_length_with_combined_filters(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library
    _insert(db_conn, "Match", item_type="movie", nomenclature_status="No adaptada", instance_type="radarr")
    _insert(db_conn, "Wrong type", item_type="series", nomenclature_status="No adaptada", instance_type="radarr")
    _insert(db_conn, "Wrong nomenclature", item_type="movie", nomenclature_status="Correcta", instance_type="radarr")

    items = list_library(db_conn, item_type="movie", nomenclature="No adaptada", origin="radarr")
    total = count_library(db_conn, item_type="movie", nomenclature="No adaptada", origin="radarr")
    assert len(items) == 1
    assert total == 1


def _insert_with_parent(conn, title, item_type, parent_id=None):
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status, parent_id, updated_at)
           VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (item_type, title, "Disponible", "Sin petición", "N/A", parent_id),
    )
    conn.commit()
    return cur.lastrowid


def test_parent_id_top_level_sentinel_excludes_children(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library, TOP_LEVEL_PARENT_FILTER
    _insert_with_parent(db_conn, "Movie", "movie")
    series_id = _insert_with_parent(db_conn, "Series", "series")
    _insert_with_parent(db_conn, "Season 1", "season", parent_id=series_id)

    items = list_library(db_conn, parent_id=TOP_LEVEL_PARENT_FILTER)
    total = count_library(db_conn, parent_id=TOP_LEVEL_PARENT_FILTER)
    titles = {i["title"] for i in items}
    assert titles == {"Movie", "Series"}
    assert total == 2


def test_parent_id_zero_sentinel_is_not_treated_as_no_filter(db_conn):
    """Regression guard: parent_id=0 must mean 'top level only', never
    'no filter at all' (which a bare `if parent_id:` check would wrongly
    do, since 0 is falsy in Python)."""
    from emuwarez_uploadrr.services.library import count_library, TOP_LEVEL_PARENT_FILTER
    _insert_with_parent(db_conn, "Movie", "movie")
    series_id = _insert_with_parent(db_conn, "Series", "series")
    _insert_with_parent(db_conn, "Season 1", "season", parent_id=series_id)

    total_no_filter = count_library(db_conn)
    total_top_level = count_library(db_conn, parent_id=TOP_LEVEL_PARENT_FILTER)
    assert total_no_filter == 3
    assert total_top_level == 2


def test_parent_id_filter_returns_only_children(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library
    series_id = _insert_with_parent(db_conn, "Series", "series")
    season_id = _insert_with_parent(db_conn, "Season 1", "season", parent_id=series_id)
    _insert_with_parent(db_conn, "Episode 1", "episode", parent_id=season_id)
    _insert_with_parent(db_conn, "Episode 2", "episode", parent_id=season_id)

    seasons = list_library(db_conn, parent_id=series_id)
    episodes = list_library(db_conn, parent_id=season_id)
    assert len(seasons) == 1 and seasons[0]["title"] == "Season 1"
    assert len(episodes) == 2
    assert count_library(db_conn, parent_id=season_id) == 2
