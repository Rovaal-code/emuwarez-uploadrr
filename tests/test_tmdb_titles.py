"""Tests for TMDb series-title localization (services/tmdb_titles)."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import tmdb_titles


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def test_localized_default_on_and_toggle(db_conn):
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    assert tmdb_titles.series_titles_localized(db_conn) is True  # default ON
    set_setting(db_conn, "tmdb.localize_series_titles", "false")
    assert tmdb_titles.series_titles_localized(db_conn) is False


def test_resolve_uses_tmdb_and_caches(db_conn, monkeypatch):
    calls = []
    def fake_get_tv_title(tmdb_id, *, language="es-ES", api_key=None, conn=None):
        calls.append(tmdb_id)
        return "Los Serrano"
    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title", fake_get_tv_title)

    assert tmdb_titles.resolve_series_title(db_conn, 7283, "The Serrano") == "Los Serrano"
    # second call is served from cache — TMDb not hit again
    assert tmdb_titles.resolve_series_title(db_conn, 7283, "The Serrano") == "Los Serrano"
    assert calls == [7283]
    assert db_conn.execute("SELECT COUNT(*) FROM tmdb_title_cache").fetchone()[0] == 1


def test_resolve_falls_back_on_error(db_conn, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network")
    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title", boom)
    # error → keep the Sonarr title, and don't cache the failure
    assert tmdb_titles.resolve_series_title(db_conn, 999, "Fallback Title") == "Fallback Title"
    assert db_conn.execute("SELECT COUNT(*) FROM tmdb_title_cache").fetchone()[0] == 0


def test_resolve_without_tmdb_id_returns_fallback(db_conn):
    assert tmdb_titles.resolve_series_title(db_conn, None, "Fallback") == "Fallback"


def test_tmdb_returning_nothing_is_cached_as_fallback(db_conn, monkeypatch):
    calls = []
    def none_title(tmdb_id, *, language="es-ES", api_key=None, conn=None):
        calls.append(tmdb_id)
        return None
    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title", none_title)
    assert tmdb_titles.resolve_series_title(db_conn, 555, "Keep Me") == "Keep Me"
    # cached (as NULL) so we don't re-hit TMDb for a series it has no title for
    assert tmdb_titles.resolve_series_title(db_conn, 555, "Keep Me") == "Keep Me"
    assert calls == [555]
