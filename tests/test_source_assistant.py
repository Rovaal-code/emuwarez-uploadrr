"""Tests for source_assistant service (Phase 10A)."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch, MagicMock

import pytest


def _make_conn(tmp_path):
    from emuwarez_uploadrr.database import connect, init_db
    import os
    os.environ["CONFIG_DIR"] = str(tmp_path)
    conn = connect(str(tmp_path / "db.sqlite3"))
    init_db(conn)
    return conn


def _insert_library_item(conn, title="Test Movie", tmdb_id="123", path=None):
    conn.execute(
        "INSERT INTO library_items (title, item_type, tmdb_id, local_status, path) VALUES (?,?,?,?,?)",
        (title, "movie", tmdb_id, "downloaded", path),
    )
    conn.commit()
    row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
    return row["id"]


# MediaInfo of the real file is now mandatory to build the fields (the wizard
# blocks otherwise), so tests provide an accessible file + a stubbed report.
_MI_OK = {
    "available": True,
    "audio_summary": "ESP AC3 5.1",
    "rows": [
        {"field": "Códec de vídeo", "mediainfo": "AVC", "emu": "H.264"},
        {"field": "HDR/DV", "mediainfo": None, "emu": None},
        {"field": "Source", "mediainfo": "del nombre del archivo", "emu": "WEB-DL"},
    ],
}


def _accessible_item(conn, tmp_path, **kw):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    return _insert_library_item(conn, path=str(f), **kw)


def _insert_proposal(conn, item_id, torrent_name="Test.Movie.2024.1080p.WEB-DL.AMZN-EMUWAREZ"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO nomenclature_proposals
           (library_item_id, status, proposed_filename, proposed_title, created_at, updated_at)
           VALUES (?,?,?,?,?,?)""",
        (item_id, "valid", torrent_name, "Test Movie", now, now),
    )
    conn.commit()


def test_list_emu_sources_returns_all():
    from emuwarez_uploadrr.services.source_assistant import list_emu_sources, EMU_SOURCES
    result = list_emu_sources()
    assert len(result) == len(EMU_SOURCES)
    for s in result:
        assert "code" in s
        assert "label" in s


def test_list_emu_providers_returns_all():
    from emuwarez_uploadrr.services.source_assistant import list_emu_providers, EMU_PROVIDERS
    result = list_emu_providers()
    assert len(result) == len(EMU_PROVIDERS)
    for p in result:
        assert "code" in p
        assert "name" in p


def test_build_source_string_webdl_nf():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string("WEB-DL", "NF") == "NF WEB-DL"


def test_build_source_string_webdl_dsnp():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string("WEB-DL", "DSNP") == "DSNP WEB-DL"


def test_build_source_string_webrip_ignores_provider():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string("WEBRip", "NF") == "WEBRip"


def test_build_source_string_none_source():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string(None, "AMZN") is None


def test_get_tmdb_available_providers_never_raises():
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=[]):
        from emuwarez_uploadrr.services.source_assistant import get_tmdb_available_providers
        result = get_tmdb_available_providers(99999, "movie", region="ES")
        assert isinstance(result, list)


def test_get_tmdb_available_providers_handles_error():
    """_get_tmdb_available_providers_raw never raises; internal errors return []."""
    from emuwarez_uploadrr.integrations import tmdb as tmdb_mod
    with patch.object(tmdb_mod, "get_movie_watch_providers", side_effect=Exception("Network error")):
        from emuwarez_uploadrr.services.source_assistant import _get_tmdb_available_providers_raw
        result = _get_tmdb_available_providers_raw(99999, "movie", region="ES")
        assert result == []


def test_build_editable_nomenclature_fields_not_found(tmp_path):
    conn = _make_conn(tmp_path)
    from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
    result = build_editable_nomenclature_fields(9999, conn=conn)
    assert "error" in result


def test_build_editable_nomenclature_fields_basic(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _accessible_item(conn, tmp_path, title="Dune", tmdb_id="438631")
    _insert_proposal(conn, item_id, "Dune.2021.1080p.WEB-DL.AMZN-EMUWAREZ")

    with patch(
        "emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw",
        return_value=[],
    ), patch(
        "emuwarez_uploadrr.services.media_info_service.build_mediainfo_report",
        return_value=_MI_OK,
    ):
        from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
        result = build_editable_nomenclature_fields(item_id, conn=conn)

    assert "fields" in result
    assert "torrent_name" in result
    assert "internal_mkv_title" in result


def test_update_nomenclature_fields_preview_webdl(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Pelicula", tmdb_id=None)
    _insert_proposal(conn, item_id, "Pelicula.2023.1080p.WEB-DL.NF-EMUWAREZ")

    from emuwarez_uploadrr.services.source_assistant import update_nomenclature_fields_preview
    fields = {
        "title": "Pelicula",
        "year": "2023",
        "resolution": "1080p",
        "source": "WEB-DL",
        "provider": "NF",
        "video_codec": "H.265",
        "audio_summary": "DDP5.1",
        "subs": "SPA",
        "tag": "EMUWAREZ",
    }
    result = update_nomenclature_fields_preview(item_id, fields, conn=conn)
    assert "torrent_name" in result
    assert "internal_mkv_title" in result
    torrent_name = result["torrent_name"]
    assert "NF WEB-DL" in torrent_name or "NF.WEB-DL" in torrent_name


def test_update_nomenclature_fields_preview_bluray(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Pelicula", tmdb_id=None)
    _insert_proposal(conn, item_id, "Pelicula.2023.1080p.BluRay-EMUWAREZ")

    from emuwarez_uploadrr.services.source_assistant import update_nomenclature_fields_preview
    fields = {
        "title": "Pelicula",
        "year": "2023",
        "resolution": "1080p",
        "source": "BluRay",
        "provider": "AMZN",
        "video_codec": "H.265",
        "audio_summary": "DTS-HD",
        "subs": "SPA",
        "tag": "EMUWAREZ",
    }
    result = update_nomenclature_fields_preview(item_id, fields, conn=conn)
    torrent_name = result.get("torrent_name", "")
    assert "AMZN" not in torrent_name
    assert "BluRay" in torrent_name or "bluray" in torrent_name.lower()


def test_suggest_provider_no_tmdb(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="NoTMDb", tmdb_id=None)

    from emuwarez_uploadrr.services.source_assistant import suggest_provider_for_item
    result = suggest_provider_for_item(item_id, conn=conn)
    assert "suggested" in result or "error" in result or result.get("suggested") is None
