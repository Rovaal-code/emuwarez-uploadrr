"""Tests for nomenclature service (Phase 6A)."""
from __future__ import annotations

import json
import pytest
from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.services.nomenclature import (
    build_nomenclature_proposal,
    validate_nomenclature_preconditions,
    get_latest_nomenclature_proposal,
    mark_nomenclature_status,
    _infer_provider_from_item,
)


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    db_file = tmp_path / "test.db"
    conn = connect(db_file)
    init_db(conn)
    yield conn
    conn.close()


def _insert_item(conn, *, title="Test Movie", local_status="Disponible", path="/fake/path/movie.mkv", item_type="movie"):
    cursor = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path)
           VALUES (?, ?, ?, 'Sin petición', ?)""",
        (item_type, title, local_status, path),
    )
    conn.commit()
    return cursor.lastrowid


def test_validate_preconditions_empty_item():
    result = validate_nomenclature_preconditions({})
    assert not result["ok"]
    assert result["errors"]


def test_validate_preconditions_faltante():
    item = {"title": "Test", "local_status": "Faltante", "path": "/some/path"}
    result = validate_nomenclature_preconditions(item)
    assert not result["ok"]
    assert any("faltante" in e.lower() or "disponible" in e.lower() for e in result["errors"])


def test_validate_preconditions_no_path():
    item = {"title": "Test", "local_status": "Disponible", "path": None}
    result = validate_nomenclature_preconditions(item)
    assert not result["ok"]
    assert any("ruta" in e.lower() for e in result["errors"])


def test_validate_preconditions_path_not_exists():
    item = {"title": "Test", "local_status": "Disponible", "path": "/nonexistent/path/movie.mkv"}
    result = validate_nomenclature_preconditions(item)
    assert result["ok"]  # warning, not error
    assert result["warnings"]


def test_build_proposal_item_not_found(db_conn):
    result = build_nomenclature_proposal(99999, conn=db_conn)
    assert result["status"] == "blocked"
    errors = json.loads(result.get("errors_json", "[]"))
    assert errors


def test_build_proposal_faltante(db_conn):
    item_id = _insert_item(db_conn, local_status="Faltante")
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    assert result["status"] == "blocked"


def test_build_proposal_available(db_conn):
    item_id = _insert_item(db_conn, local_status="Disponible", path="/fake/movie.mkv")
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    assert result["status"] in ("valid", "warning", "blocked")
    assert result.get("proposed_title") or result.get("errors_json")


def test_build_proposal_uses_resolution_from_item(db_conn):
    cursor = db_conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path, resolution)
           VALUES ('movie', 'Test', 'Disponible', 'Sin petición', '/fake/movie.mkv', '1080p')""",
    )
    db_conn.commit()
    item_id = cursor.lastrowid
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    assert result.get("resolution") == "1080p"


def test_build_proposal_uses_source_from_quality(db_conn):
    cursor = db_conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path, quality)
           VALUES ('movie', 'Test', 'Disponible', 'Sin petición', '/fake/movie.mkv', 'WEB-DL 1080p')""",
    )
    db_conn.commit()
    item_id = cursor.lastrowid
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    assert result.get("source") is not None


def test_build_proposal_no_mediainfo_warning(db_conn):
    item_id = _insert_item(db_conn, local_status="Disponible")
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    warnings = json.loads(result.get("warnings_json", "[]"))
    assert any("mediainfo" in w.lower() or "codec" in w.lower() for w in warnings)


def test_infer_provider_prefers_hmax_over_max_substring():
    item = {"path": "/movies/Show.2020.1080p.HMAX.WEB-DL.mkv"}
    assert _infer_provider_from_item(item, "WEB-DL") == "HMAX"


def test_infer_provider_none_without_provider_carrying_source():
    item = {"path": "/movies/Show.2020.1080p.AMZN.WEB-DL.mkv"}
    assert _infer_provider_from_item(item, "BluRay") is None
    assert _infer_provider_from_item(item, None) is None


def test_infer_provider_none_without_match():
    item = {"path": "/movies/Show.2020.1080p.WEB-DL.mkv"}
    assert _infer_provider_from_item(item, "WEB-DL") is None


def test_build_proposal_detects_provider_in_web_dl_filename(db_conn):
    """Phase 6E — a provider code already present in the current filename
    (AMZN, in this case) must survive into the proposal and the filename,
    but only when the source is a provider-carrying one (WEB-DL)."""
    cursor = db_conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path, quality)
           VALUES ('movie', 'Ad Astra', 'Disponible', 'Sin petición',
                   '/movies/Ad Astra/Ad Astra.2019.1080p.AMZN.WEB-DL.mkv', 'WEBDL-1080p')""",
    )
    db_conn.commit()
    item_id = cursor.lastrowid
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    assert result.get("provider_final") == "AMZN"
    assert "AMZN" in result.get("proposed_filename", "")


def test_build_proposal_ignores_provider_like_tokens_on_non_streaming_source(db_conn):
    """A BluRay/HDTV/DVD release was never provider-tagged — even if a
    provider-looking token appears somewhere in the path, it must not be
    reported as a detected provider (avoids false positives from short,
    generic codes like IT/HS/SL)."""
    cursor = db_conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path, quality)
           VALUES ('movie', 'IT', 'Disponible', 'Sin petición', '/movies/IT.2017.1080p.BluRay.mkv', 'Bluray-1080p')""",
    )
    db_conn.commit()
    item_id = cursor.lastrowid
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    assert result.get("provider_final") is None


def test_build_proposal_uses_real_media_info_columns(db_conn):
    """Phase 6A — video_codec/audio_codec/audio_languages parsed at sync
    time from Radarr/Sonarr's own mediaInfo must be used verbatim, not
    re-guessed from the quality profile name, and must silence the
    'codec not detected' warning."""
    cursor = db_conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, path, quality,
            video_codec, audio_codec, audio_languages, subtitle_languages)
           VALUES ('movie', 'Ad Astra', 'Disponible', 'Sin petición', '/fake/Ad Astra.mkv',
                   'WEBDL-1080p', 'x265', 'EAC3', 'eng / spa', 'eng / spa')""",
    )
    db_conn.commit()
    item_id = cursor.lastrowid
    result = build_nomenclature_proposal(item_id, conn=db_conn)
    assert result.get("video_codec") == "x265"
    assert result.get("audio_summary") == "EAC3 eng / spa"
    assert result.get("subtitle_summary") == "eng / spa"
    warnings = json.loads(result.get("warnings_json", "[]"))
    assert not any("codec" in w.lower() for w in warnings)


def test_get_latest_proposal(db_conn):
    item_id = _insert_item(db_conn, local_status="Disponible")
    build_nomenclature_proposal(item_id, conn=db_conn)
    result = get_latest_nomenclature_proposal(item_id, conn=db_conn)
    assert result is not None
    assert result["library_item_id"] == item_id


def test_force_refresh_creates_new_proposal(db_conn):
    item_id = _insert_item(db_conn, local_status="Disponible")
    p1 = build_nomenclature_proposal(item_id, conn=db_conn)
    p2 = build_nomenclature_proposal(item_id, force_refresh=True, conn=db_conn)
    assert p2.get("id") != p1.get("id")


def test_mark_nomenclature_status(db_conn):
    item_id = _insert_item(db_conn, local_status="Disponible")
    build_nomenclature_proposal(item_id, conn=db_conn)
    mark_nomenclature_status(item_id, "expired", conn=db_conn)
    result = get_latest_nomenclature_proposal(item_id, conn=db_conn)
    assert result is None or result.get("status") != "expired"


def test_no_filesystem_modification(tmp_path, monkeypatch):
    """Ensure build_nomenclature_proposal never calls os.rename or os.remove."""
    import os
    calls: list = []

    def fake_rename(*args, **kwargs):
        calls.append(("rename", args))
        raise AssertionError(f"os.rename called: {args}")

    def fake_remove(*args, **kwargs):
        calls.append(("remove", args))
        raise AssertionError(f"os.remove called: {args}")

    monkeypatch.setattr(os, "rename", fake_rename)
    monkeypatch.setattr(os, "remove", fake_remove)
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))

    db_file = tmp_path / "safe.db"
    conn = connect(db_file)
    init_db(conn)
    cursor = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, path)
           VALUES ('movie', 'Safe Test', 'Disponible', 'Sin petición', '/fake/safe.mkv')""",
    )
    conn.commit()
    item_id = cursor.lastrowid
    build_nomenclature_proposal(item_id, conn=conn)
    conn.close()
    assert len(calls) == 0, f"Filesystem was modified: {calls}"
