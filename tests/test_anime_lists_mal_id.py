"""Tests for services/anime_lists.get_mal_id and its wiring into
upsert_library_item — no network involved: ensure_anime_id_map() only
downloads when the local anime_id_map mirror is empty, so seeding it directly
(as if a previous sync had already populated it) exercises the exact same
lookup path without ever calling the real Fribb/anime-lists download."""
from __future__ import annotations

import time

import pytest

from emuwarez_uploadrr.database import set_state
from emuwarez_uploadrr.services.anime_lists import get_mal_id
from emuwarez_uploadrr.services.library import upsert_library_item
from emuwarez_uploadrr.models import LibraryItem


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _seed(conn, *, tvdb_id=None, season_number=None, tmdb_movie_id=None, mal_id="12345"):
    conn.execute(
        "INSERT INTO anime_id_map (tvdb_id, season_number, tmdb_movie_id, mal_id) VALUES (?, ?, ?, ?)",
        (tvdb_id, season_number, tmdb_movie_id, mal_id),
    )
    # Real _download_and_store() always stamps this alongside the rows it
    # inserts — stamping it here too keeps ensure_anime_id_map() from seeing
    # a "stale" table and attempting a real download in these tests.
    set_state(conn, "last_anime_id_map_sync_utc", str(int(time.time())))
    conn.commit()


def test_get_mal_id_movie_matches_by_tmdb(db_conn):
    _seed(db_conn, tmdb_movie_id="128", mal_id="164")
    assert get_mal_id(db_conn, item_type="movie", tvdb_id=None, tmdb_id="128", season_number=None) == "164"


def test_get_mal_id_movie_no_match_returns_none(db_conn):
    _seed(db_conn, tmdb_movie_id="128", mal_id="164")
    assert get_mal_id(db_conn, item_type="movie", tvdb_id=None, tmdb_id="999999", season_number=None) is None


def test_get_mal_id_series_prefers_exact_season_match(db_conn):
    # Same tvdb_id, two different anidb/MAL entries for season 1 vs season 2 —
    # a real pattern for long-running anime the tracker splits by cour/season.
    _seed(db_conn, tvdb_id="79099", season_number=1, mal_id="3269")
    _seed(db_conn, tvdb_id="79099", season_number=2, mal_id="9999")
    assert get_mal_id(db_conn, item_type="season", tvdb_id="79099", tmdb_id=None, season_number=2) == "9999"
    assert get_mal_id(db_conn, item_type="season", tvdb_id="79099", tmdb_id=None, season_number=1) == "3269"


def test_get_mal_id_series_falls_back_without_season_number(db_conn):
    _seed(db_conn, tvdb_id="72025", season_number=1, mal_id="290")
    assert get_mal_id(db_conn, item_type="series", tvdb_id="72025", tmdb_id=None, season_number=None) == "290"


def test_get_mal_id_no_tvdb_id_returns_none(db_conn):
    assert get_mal_id(db_conn, item_type="series", tvdb_id=None, tmdb_id=None, season_number=None) is None


def test_upsert_library_item_resolves_mal_id_for_movie(db_conn):
    _seed(db_conn, tmdb_movie_id="128", mal_id="164")
    item = LibraryItem(
        id=None, item_type="movie", title="Princess Mononoke",
        instance_id=1, instance_type="radarr", instance_name="Radarr",
        external_id="1", tmdb_id="128",
    )
    item_id = upsert_library_item(db_conn, item, notify_missing=False)
    row = db_conn.execute("SELECT mal_id FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["mal_id"] == "164"


def test_upsert_library_item_no_relevant_id_skips_lookup(db_conn):
    """A movie with no tmdb_id can't be matched at all — mal_id stays None
    without even touching anime_id_map (nothing to look up against)."""
    item = LibraryItem(
        id=None, item_type="movie", title="Sin TMDb",
        instance_id=1, instance_type="radarr", instance_name="Radarr",
        external_id="2", tmdb_id=None,
    )
    item_id = upsert_library_item(db_conn, item, notify_missing=False)
    row = db_conn.execute("SELECT mal_id FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["mal_id"] is None


def test_upsert_library_item_self_corrects_when_entry_removed(db_conn, monkeypatch):
    """mal_id isn't sticky — if a later anime_id_map refresh no longer has a
    match (entry corrected/removed upstream), the next sync clears it back to
    None instead of leaving a stale value forever."""
    _seed(db_conn, tmdb_movie_id="128", mal_id="164")
    item = LibraryItem(
        id=None, item_type="movie", title="Princess Mononoke",
        instance_id=1, instance_type="radarr", instance_name="Radarr",
        external_id="1", tmdb_id="128",
    )
    item_id = upsert_library_item(db_conn, item, notify_missing=False)
    assert db_conn.execute("SELECT mal_id FROM library_items WHERE id = ?", (item_id,)).fetchone()["mal_id"] == "164"

    db_conn.execute("DELETE FROM anime_id_map")
    db_conn.commit()
    # The table is now empty, so ensure_anime_id_map() would try a real
    # download on the next upsert — force that attempt to fail (best-effort,
    # never raises) instead of hitting the real network in a test.
    import emuwarez_uploadrr.services.anime_lists as anime_lists
    monkeypatch.setattr(anime_lists, "request_json", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no network in tests")))
    upsert_library_item(db_conn, item, notify_missing=False)
    row = db_conn.execute("SELECT mal_id FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["mal_id"] is None


def test_una_lista_vacia_o_recortada_no_borra_la_tabla(db_conn, monkeypatch):
    """Si GitHub devuelve una lista vacía o a medias, la tabla que había se queda."""
    from emuwarez_uploadrr.services import anime_lists
    for i in range(10):
        _seed(db_conn, tmdb_movie_id=str(i), mal_id=str(100 + i))
    for respuesta in ([], [{"mal_id": 1, "themoviedb_id": {"movie": [1]}}]):
        monkeypatch.setattr(anime_lists, "request_json", lambda *a, _r=respuesta, **k: _r)
        anime_lists.ensure_anime_id_map(db_conn, force=True)
        assert db_conn.execute("SELECT COUNT(*) FROM anime_id_map").fetchone()[0] == 10
