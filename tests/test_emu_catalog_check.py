"""Tests for the eMuwarez catalog duplicate-check (emu_search_existing wired
into match_all_requests / match_single_request), added to reduce false
negatives where the internal library-vs-request matcher has no candidate or
classifies "No compatible" even though eMuwarez's own torrent catalog
already has a match for the request's tmdb_id.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.base import build_url


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert_request(conn, **kwargs) -> int:
    defaults = {
        "emu_id": "emu-1",
        "title": "Test Movie",
        "category": "Pelicula",
        "requested_resolution": None,
        "requested_source": None,
        "emu_status": "open",
        "tmdb_id": None,
        "imdb_id": None,
    }
    defaults.update(kwargs)
    conn.execute(
        """
        INSERT INTO request_items
        (emu_id, title, category, requested_resolution, requested_source,
         emu_status, tmdb_id, imdb_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            defaults["emu_id"], defaults["title"], defaults["category"],
            defaults["requested_resolution"], defaults["requested_source"],
            defaults["emu_status"], defaults["tmdb_id"], defaults["imdb_id"],
        ),
    )
    conn.commit()
    return conn.execute("SELECT id FROM request_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


# ---------------------------------------------------------------------------
# emu_search_existing — URL construction with tmdbId
# ---------------------------------------------------------------------------

def test_emu_search_existing_builds_tmdb_id_query(monkeypatch):
    captured = {}

    def fake_request_json(method, url, **kwargs):
        captured["url"] = url
        return {"data": []}

    monkeypatch.setattr(emu, "request_json", fake_request_json)
    emu.emu_search_existing("KEY123", tmdb_id="603")

    assert "tmdbId=603" in captured["url"]
    assert "api_token=KEY123" in captured["url"]
    # No free-text name should be sent when tmdb_id is given and query is None.
    assert "name=" not in captured["url"]


def test_emu_search_existing_falls_back_to_name(monkeypatch):
    captured = {}

    def fake_request_json(method, url, **kwargs):
        captured["url"] = url
        return {"data": []}

    monkeypatch.setattr(emu, "request_json", fake_request_json)
    emu.emu_search_existing("KEY123", query="The Matrix")

    assert "tmdbId=" not in captured["url"]
    assert "name=The" in captured["url"] or "name=The+Matrix" in captured["url"]


def test_emu_search_existing_prefers_tmdb_over_name_when_both_given(monkeypatch):
    captured = {}

    def fake_request_json(method, url, **kwargs):
        captured["url"] = url
        return {"data": []}

    monkeypatch.setattr(emu, "request_json", fake_request_json)
    emu.emu_search_existing("KEY123", query="The Matrix", tmdb_id="603")

    assert "tmdbId=603" in captured["url"]
    # Both may be sent — tmdbId is just required to be present and authoritative.


# ---------------------------------------------------------------------------
# match_all_requests — only checks eMuwarez catalog for no-candidate / "No
# compatible" cases, never for already-good matches.
# ---------------------------------------------------------------------------

def test_match_all_requests_checks_catalog_when_no_candidate(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.requests import match_all_requests

    req_id = _insert_request(db_conn, title="Completely Unmatched Thing", tmdb_id="999")

    calls = []

    def fake_search(api_key, query=None, base_url=None, tmdb_id=None, category=None):
        calls.append(tmdb_id)
        return {"data": [{"id": 1, "name": "Completely Unmatched Thing"}]}

    monkeypatch.setattr(emu, "emu_search_existing", fake_search)

    match_all_requests(db_conn, emu_api_key="FAKEKEY")

    assert calls == ["999"]
    row = db_conn.execute(
        "SELECT emu_catalog_result, emu_catalog_checked_at FROM request_items WHERE id = ?",
        (req_id,),
    ).fetchone()
    assert row["emu_catalog_result"] == "found"
    assert row["emu_catalog_checked_at"] is not None


def test_match_all_requests_skips_catalog_check_without_tmdb_id(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.requests import match_all_requests

    _insert_request(db_conn, title="No TMDb ID Here", tmdb_id=None)

    calls = []
    monkeypatch.setattr(
        emu, "emu_search_existing",
        lambda *a, **kw: calls.append(1) or {"data": []},
    )

    match_all_requests(db_conn, emu_api_key="FAKEKEY")

    assert calls == []  # never called — no tmdb_id means no authoritative check


def test_match_all_requests_does_not_check_catalog_for_compatible_match(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.requests import match_all_requests

    _insert_request(db_conn, title="Matched Movie", tmdb_id="603", requested_resolution=None, requested_source=None)
    db_conn.execute(
        """
        INSERT INTO library_items
        (item_type, title, local_status, request_status, nomenclature_status,
         tmdb_id, file_exists, updated_at)
        VALUES ('movie', 'Matched Movie', 'Disponible', 'Sin peticion', 'N/A', '603', 1, CURRENT_TIMESTAMP)
        """
    )
    db_conn.commit()

    calls = []
    monkeypatch.setattr(
        emu, "emu_search_existing",
        lambda *a, **kw: calls.append(1) or {"data": []},
    )

    match_all_requests(db_conn, emu_api_key="FAKEKEY")

    assert calls == []  # already Compatible via TMDb ID match — no need to hit the API


def test_match_all_requests_no_emu_api_key_skips_network_entirely(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.requests import match_all_requests

    _insert_request(db_conn, title="Unmatched", tmdb_id="42")

    calls = []
    monkeypatch.setattr(
        emu, "emu_search_existing",
        lambda *a, **kw: calls.append(1) or {"data": []},
    )

    match_all_requests(db_conn, emu_api_key=None)

    assert calls == []


# ---------------------------------------------------------------------------
# Caching / TTL
# ---------------------------------------------------------------------------

def test_match_all_requests_respects_ttl_cache(db_conn, monkeypatch):
    import datetime as dt
    from emuwarez_uploadrr.services.requests import match_all_requests

    req_id = _insert_request(db_conn, title="Unmatched", tmdb_id="42")
    recent = dt.datetime.now(dt.timezone.utc).isoformat()
    db_conn.execute(
        "UPDATE request_items SET emu_catalog_checked_at = ?, emu_catalog_result = ? WHERE id = ?",
        (recent, "not_found", req_id),
    )
    db_conn.commit()

    calls = []
    monkeypatch.setattr(
        emu, "emu_search_existing",
        lambda *a, **kw: calls.append(1) or {"data": []},
    )

    match_all_requests(db_conn, emu_api_key="FAKEKEY")

    assert calls == []  # cached within TTL — should not re-query


def test_match_all_requests_rechecks_after_ttl_expired(db_conn, monkeypatch):
    import datetime as dt
    from emuwarez_uploadrr.services.requests import match_all_requests, EMU_CATALOG_CHECK_TTL_SECONDS

    req_id = _insert_request(db_conn, title="Unmatched", tmdb_id="42")
    stale = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=EMU_CATALOG_CHECK_TTL_SECONDS + 60)
    ).isoformat()
    db_conn.execute(
        "UPDATE request_items SET emu_catalog_checked_at = ?, emu_catalog_result = ? WHERE id = ?",
        (stale, "not_found", req_id),
    )
    db_conn.commit()

    calls = []
    monkeypatch.setattr(
        emu, "emu_search_existing",
        lambda *a, **kw: calls.append(1) or {"data": []},
    )

    match_all_requests(db_conn, emu_api_key="FAKEKEY")

    assert calls == [1]  # TTL expired — should re-query


# ---------------------------------------------------------------------------
# Network failure must not break the rest of the sync/match run.
# ---------------------------------------------------------------------------

def test_match_all_requests_survives_emu_search_failure(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.requests import match_all_requests

    req_id = _insert_request(db_conn, title="Unmatched", tmdb_id="42")

    def boom(*a, **kw):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(emu, "emu_search_existing", boom)

    # Must not raise.
    updated = match_all_requests(db_conn, emu_api_key="FAKEKEY")
    assert updated == 0  # no library candidate either way

    row = db_conn.execute(
        "SELECT emu_catalog_result FROM request_items WHERE id = ?", (req_id,)
    ).fetchone()
    assert row["emu_catalog_result"] == "error"


def test_match_single_request_no_candidate_checks_catalog(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.requests import match_single_request

    req_id = _insert_request(db_conn, title="Totally Unmatched", tmdb_id="777")

    calls = []

    def fake_search(api_key, query=None, base_url=None, tmdb_id=None, category=None):
        calls.append(tmdb_id)
        return {"data": []}

    monkeypatch.setattr(emu, "emu_search_existing", fake_search)

    result = match_single_request(db_conn, req_id, emu_api_key="FAKEKEY")

    assert result is None  # still no library match, contract unchanged
    assert calls == ["777"]
    row = db_conn.execute(
        "SELECT emu_catalog_result FROM request_items WHERE id = ?", (req_id,)
    ).fetchone()
    assert row["emu_catalog_result"] == "not_found"
