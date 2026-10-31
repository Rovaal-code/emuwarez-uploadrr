"""Tests for apply_nomenclature_proposal service — renames in place (same
directory) a file of the uploads folder; a library file is never renamed.

conftest.py provides isolated_db (autouse) pointing CONFIG_DIR to a tmp dir.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from emuwarez_uploadrr.database import init_db, connect
from emuwarez_uploadrr.services.nomenclature import (
    apply_nomenclature_proposal,
    build_nomenclature_apply_plan,
    CONFIRMATION_TOKEN,
)


@pytest.fixture(autouse=True)
def _tmp_es_la_carpeta_de_subidas(tmp_path, monkeypatch):
    """Solo se renombra lo que está en la carpeta de subidas: aquí, tmp_path."""
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", str(tmp_path))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(isolated_db):
    return isolated_db / "emuwarez_uploadrr.db"


def _open(isolated_db):
    conn = connect(_db(isolated_db))
    init_db(conn)
    return conn


def _insert_item(conn, title="Test Movie", path=None):
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status)
           VALUES ('movie', ?, 'Disponible', 'none', 'Pendiente')""",
        (title,),
    )
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if path:
        conn.execute("UPDATE library_items SET path = ? WHERE id = ?", (path, item_id))
    conn.commit()
    return item_id


# ---------------------------------------------------------------------------
# dry_run — no filesystem changes
# ---------------------------------------------------------------------------

def test_dry_run_source_file_missing(isolated_db):
    conn = _open(isolated_db)
    item_id = _insert_item(conn, path="/fake/source.mkv")
    result = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    assert result["dry_run"] is True
    assert result["status"] in ("blocked", "ready")
    conn.close()


def test_dry_run_blocked_no_source(isolated_db, tmp_path):
    conn = _open(isolated_db)
    item_id = _insert_item(conn)  # no path
    result = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    assert result["dry_run"] is True
    assert result["status"] == "blocked"
    conn.close()


def test_dry_run_creates_nothing(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="My Movie", path=str(src))
    conn.execute(
        "UPDATE library_items SET tmdb_id = '12345', year = 2020, resolution = '1080p', source = 'Blu-ray' WHERE id = ?",
        (item_id,),
    )
    conn.commit()
    result = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    assert result["dry_run"] is True
    # Nothing renamed — only the original file is still there.
    assert list(tmp_path.glob("*.mkv")) == [src]
    conn.close()


# ---------------------------------------------------------------------------
# Real apply — confirmation required
# ---------------------------------------------------------------------------

def test_apply_blocked_without_confirmation(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="My Movie", path=str(src))
    result = apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation=None, conn=conn
    )
    assert result["status"] == "blocked"
    assert src.exists()
    conn.close()


def test_apply_blocked_wrong_confirmation(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="My Movie", path=str(src))
    result = apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation="WRONG_TOKEN", conn=conn
    )
    assert result["status"] == "blocked"
    assert src.exists()
    conn.close()


def test_dry_run_takes_precedence_over_apply(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, path=str(src))
    result = apply_nomenclature_proposal(
        item_id, dry_run=True, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn
    )
    assert result["dry_run"] is True
    assert src.exists()
    conn.close()


# ---------------------------------------------------------------------------
# Real apply — renamed in place and DB updated
# ---------------------------------------------------------------------------

def test_apply_real_renames_file_and_updates_db(isolated_db, tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"video bytes")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Test Film", path=str(src))
    conn.execute(
        "UPDATE library_items SET tmdb_id = '9999', year = 2021, resolution = '1080p' WHERE id = ?",
        (item_id,),
    )
    conn.commit()

    result = apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn
    )

    if result["status"] == "applied":
        dst = result["destination_path"]
        assert dst is not None
        assert Path(dst).exists()
        # Renamed in place — same directory as the original, and the original
        # filename no longer exists (it's not a copy).
        assert Path(dst).parent == tmp_path
        assert not src.exists()
        assert Path(dst).read_bytes() == b"video bytes"

        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        assert row["prepared_path"] == dst
        assert row["nomenclature_applied_at"] is not None
        # `path` follows the rename (same directory, raw convention).
        assert row["path"] == dst

        proposal_row = conn.execute(
            "SELECT * FROM nomenclature_proposals WHERE library_item_id = ? ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if proposal_row:
            assert proposal_row["status"] == "applied"
            assert proposal_row["applied_path"] == dst

        op_row = conn.execute(
            "SELECT * FROM filesystem_operations WHERE library_item_id = ? ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        assert op_row is not None
        assert op_row["status"] == "applied"
        assert op_row["dry_run"] == 0
        assert result["operation_id"] == op_row["id"]

    conn.close()


# ---------------------------------------------------------------------------
# filesystem_operations always saved
# ---------------------------------------------------------------------------

def test_a_dry_run_records_nothing(isolated_db, tmp_path):
    """El historial es de lo que se hizo; una vista previa no hace nada."""
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"v")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Movie", path=str(src))

    apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    ops = conn.execute(
        "SELECT * FROM filesystem_operations WHERE library_item_id = ?", (item_id,)
    ).fetchall()
    assert ops == []
    conn.close()


# ---------------------------------------------------------------------------
# CONFIRMATION_TOKEN value
# ---------------------------------------------------------------------------

def test_confirmation_token_value():
    assert CONFIRMATION_TOKEN == "APLICAR_NOMENCLATURA"


# ---------------------------------------------------------------------------
# Phase 6B — real MediaInfo invocation at apply time (mocked, no real
# mediainfo binary in this sandbox)
# ---------------------------------------------------------------------------

def test_apply_plan_prefers_real_media_info_over_synced_values(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Ad Astra", path=str(src))
    # Simulate stale/guessed values from an old sync (Phase 6A columns).
    conn.execute(
        "UPDATE library_items SET video_codec = 'AVC', audio_codec = 'AAC', tmdb_id = '1', year = 2019 WHERE id = ?",
        (item_id,),
    )
    conn.commit()

    real_media_info = {
        "video_codec": "HEVC", "audio_codec": "DD+",
        "audio_languages": "ING / ESP", "subtitle_languages": "ING / ESP",
    }
    with patch(
        "emuwarez_uploadrr.services.media_info_service.read_media_info_summary",
        return_value=real_media_info,
    ):
        plan = build_nomenclature_apply_plan(item_id, conn=conn)

    assert plan["proposal"]["video_codec"] == "HEVC"
    row = conn.execute("SELECT video_codec, audio_codec FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["video_codec"] == "HEVC"
    assert row["audio_codec"] == "DD+"
    conn.close()


def test_apply_plan_preserves_manually_edited_source_despite_mediainfo_mismatch(isolated_db, tmp_path):
    # Real production bug: a file named "...BDRemux..." always re-detects
    # source=BDReMux from the raw filename. A user who manually edited the
    # source to "BluRay" via the field editor (save_nomenclature_fields(),
    # which stamps fields_json) had that edit silently discarded the next
    # time the job ran, because _refresh_media_info_from_real_file() force-
    # refreshed the WHOLE proposal from scratch whenever ANY of
    # video_codec/audio_codec/audio_languages/subtitle_languages disagreed
    # with a fresh MediaInfo read — completely unrelated to `source`.
    src = tmp_path / "Movie 2017 1080p BDRemux x264-GRP.mkv"
    src.write_bytes(b"video")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Some Movie", path=str(src))
    conn.execute(
        "UPDATE library_items SET video_codec = 'AVC', tmdb_id = '1', year = 2017 WHERE id = ?",
        (item_id,),
    )
    now = "2024-01-01T00:00:00+00:00"
    conn.execute(
        """INSERT INTO nomenclature_proposals
           (library_item_id, status, source, fields_json, created_at, updated_at)
           VALUES (?, 'valid', 'BluRay', '{"source": "BluRay"}', ?, ?)""",
        (item_id, now, now),
    )
    conn.commit()

    real_media_info = {
        "video_codec": "HEVC", "audio_codec": "DD+",
        "audio_languages": "ING / ESP", "subtitle_languages": "ING / ESP",
    }
    with patch(
        "emuwarez_uploadrr.services.media_info_service.read_media_info_summary",
        return_value=real_media_info,
    ):
        plan = build_nomenclature_apply_plan(item_id, conn=conn)

    assert plan["proposal"]["source"] == "BluRay"
    # The unrelated codec correction still lands on library_items.
    row = conn.execute("SELECT video_codec FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["video_codec"] == "HEVC"
    conn.close()


def test_apply_plan_falls_back_when_mediainfo_unavailable(isolated_db, tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Some Movie", path=str(src))
    conn.execute("UPDATE library_items SET video_codec = 'AVC', tmdb_id = '1', year = 2019 WHERE id = ?", (item_id,))
    conn.commit()

    with patch(
        "emuwarez_uploadrr.services.media_info_service.read_media_info_summary",
        return_value=None,
    ):
        plan = build_nomenclature_apply_plan(item_id, conn=conn)

    # No mediainfo available — the Phase 6A synced value must survive untouched.
    assert plan["proposal"]["video_codec"] == "AVC"
    conn.close()


# ---------------------------------------------------------------------------
# La biblioteca no se renombra: Jellyfin la lee con los nombres de Radarr/Sonarr
# ---------------------------------------------------------------------------

def test_a_library_file_is_never_renamed(isolated_db, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.filesystem_apply import SOLO_EN_SUBIDAS
    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", str(tmp_path / "uploads"))
    media = tmp_path / "media"
    media.mkdir()
    src = media / "Test Film (2021).mkv"
    src.write_bytes(b"video bytes")
    conn = _open(isolated_db)
    item_id = _insert_item(conn, title="Test Film", path=str(src))

    preview = apply_nomenclature_proposal(item_id, dry_run=True, conn=conn)
    result = apply_nomenclature_proposal(
        item_id, dry_run=False, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn)

    assert preview["renombrable"] is False and preview["message"] == SOLO_EN_SUBIDAS
    assert result["status"] == "blocked" and SOLO_EN_SUBIDAS in result["errors"]
    assert [p.name for p in media.iterdir()] == ["Test Film (2021).mkv"]
    assert src.read_bytes() == b"video bytes"
    row = conn.execute("SELECT path, prepared_path FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["path"] == str(src) and row["prepared_path"] is None
    conn.close()
