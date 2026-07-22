"""Tests for services/emu_catalog.get_item_comparison — the detail-card
"Comparación con eMuwarez" panel. Before this, an install that had NEVER
synced the eMuwarez catalog (an empty emu_catalog table) was indistinguishable
from one that HAD synced and genuinely found no match — both produced
`matches: []`, so every single item confidently showed "No está en eMuwarez ·
Contenido único" even though nothing had ever really been compared.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import set_state
from emuwarez_uploadrr.services.emu_catalog import (
    SYNC_COMPLETED_STATE_KEY,
    SYNC_STATE_KEY,
    get_item_comparison,
)


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _movie(conn, title, tmdb_id, **extra):
    fields = {
        "resolution": "1080p", "source": "WEB-DL", "video_codec": "H.264",
        "audio_languages": None, "size_bytes": 1_000_000_000,
    }
    fields.update(extra)
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            tmdb_id, resolution, source, video_codec, audio_languages, size_bytes, updated_at)
           VALUES ('movie', ?, 'Disponible', 'Sin petición', 'N/A', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (title, str(tmdb_id), fields["resolution"], fields["source"], fields["video_codec"],
         fields["audio_languages"], fields["size_bytes"]),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _catalog_movie(conn, tmdb_id, name="Movie 1080p WEB-DL"):
    conn.execute(
        """INSERT INTO emu_catalog
           (torrent_id, category, tmdb_id, resolution, source, codec, has_spanish, size, name)
           VALUES (?, 'Peliculas', ?, '1080p', 'WEB-DL', 'H.264', 1, 1000000000, ?)""",
        (f"t{tmdb_id}", str(tmdb_id), name),
    )
    conn.commit()


def test_never_synced_reports_unavailable_not_unique(db_conn):
    """The exact bug: an empty emu_catalog table (never synced) must NOT be
    read as "genuinely not in eMuwarez" — it must say so isn't comparable yet."""
    item_id = _movie(db_conn, "Some Movie", tmdb_id=555)
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is False
    assert "sincroniza" in result["message"].lower()
    assert result["matches"] == []


def test_synced_and_genuinely_not_in_catalog(db_conn):
    item_id = _movie(db_conn, "Unique Movie", tmdb_id=556)
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is True
    assert result["in_catalog"] == 0
    assert result["matches"] == []


def test_synced_and_match_found(db_conn):
    item_id = _movie(db_conn, "Matched Movie", tmdb_id=557)
    _catalog_movie(db_conn, tmdb_id=557)
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is True
    assert result["in_catalog"] == 1
    assert len(result["matches"]) == 1
    assert result["matches"][0]["name"] == "Movie 1080p WEB-DL"


def test_started_but_never_finished_reports_unavailable_not_unique(db_conn):
    """The exact real-world bug: a sync that STARTS (stamping the throttle
    marker immediately, before downloading anything) but then stalls/crashes
    mid-download must NOT be read as "synced" just because SYNC_STATE_KEY is
    set — that key only means "an attempt began", not "one finished". Every
    item must keep showing "not yet compared", not a false "contenido único"
    against a catalog table that's still empty."""
    item_id = _movie(db_conn, "Some Movie", tmdb_id=558)
    set_state(db_conn, SYNC_STATE_KEY, "2026-01-01T00:00:00Z")  # attempt started...
    db_conn.commit()                                             # ...but never finished
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is False
    assert "sincroniza" in result["message"].lower()
    assert result["matches"] == []
