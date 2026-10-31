"""Tests for mkv_title service (Phase 10A) — no real mkvpropedit execution."""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest


def _make_conn(tmp_path):
    from emuwarez_uploadrr.database import connect, init_db
    os.environ["CONFIG_DIR"] = str(tmp_path)
    conn = connect(str(tmp_path / "db.sqlite3"))
    init_db(conn)
    return conn


def _insert_library_item(conn, title="Movie", prepared_path=None):
    conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, prepared_path) VALUES (?,?,?,?)",
        (title, "movie", "downloaded", prepared_path),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]


def _insert_proposal(conn, item_id, torrent_name):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO nomenclature_proposals
           (library_item_id, status, proposed_filename, proposed_title, created_at, updated_at)
           VALUES (?,?,?,?,?,?)""",
        (item_id, "valid", torrent_name, "Movie", now, now),
    )
    conn.commit()


def test_mkv_confirmation_token_value():
    from emuwarez_uploadrr.services.mkv_title import MKV_CONFIRMATION_TOKEN
    assert MKV_CONFIRMATION_TOKEN == "APLICAR_TITULO_MKV"


def test_build_internal_mkv_title_basic():
    from emuwarez_uploadrr.services.mkv_title import build_internal_mkv_title
    result = build_internal_mkv_title("Dune 2021 1080p WEB-DL AMZN - EMUWAREZ")
    assert " " not in result
    assert result == "Dune.2021.1080p.WEB-DL.AMZN.-.EMUWAREZ"


def test_build_internal_mkv_title_already_dots():
    from emuwarez_uploadrr.services.mkv_title import build_internal_mkv_title
    result = build_internal_mkv_title("Dune.2021.1080p.BluRay-EMUWAREZ")
    assert result == "Dune.2021.1080p.BluRay-EMUWAREZ"


def test_preview_item_not_found(tmp_path):
    conn = _make_conn(tmp_path)
    from emuwarez_uploadrr.services.mkv_title import preview_internal_title_update
    result = preview_internal_title_update(9999, conn=conn)
    assert result.get("status") in ("blocked", "error")
    assert result.get("errors")


def test_preview_no_prepared_path(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=None)
    _insert_proposal(conn, item_id, "Film.2024.1080p.BluRay-EMUWAREZ")

    from emuwarez_uploadrr.services.mkv_title import preview_internal_title_update
    result = preview_internal_title_update(item_id, conn=conn)
    assert result.get("status") == "blocked"
    assert any("prepared_path" in e.lower() or "no" in e.lower() for e in result.get("errors", [result.get("status", "")]))


def test_preview_with_mkv_path(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")

    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=str(mkv_file))
    _insert_proposal(conn, item_id, "Film 2024 1080p BluRay - EMUWAREZ")

    with patch("emuwarez_uploadrr.services.mkv_title.check_mkvpropedit_available") as mock_chk:
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvpropedit"}
        from emuwarez_uploadrr.services.mkv_title import preview_internal_title_update
        result = preview_internal_title_update(item_id, conn=conn)

    assert result.get("status") != "error"
    assert result.get("internal_mkv_title") == "Film.2024.1080p.BluRay.-.EMUWAREZ"
    assert result.get("mkvpropedit_available") is True


def test_apply_without_confirmation_is_dry_run(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")

    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=str(mkv_file))
    _insert_proposal(conn, item_id, "Film 2024 1080p BluRay - EMUWAREZ")

    from emuwarez_uploadrr.services.mkv_title import apply_internal_title_update
    result = apply_internal_title_update(item_id, dry_run=True, apply=False, confirmation=None, conn=conn)
    assert result.get("status") in ("dry_run", "blocked", "ready", "warning")


def test_apply_with_wrong_confirmation_blocked(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")

    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=str(mkv_file))
    _insert_proposal(conn, item_id, "Film 2024 1080p BluRay - EMUWAREZ")

    from emuwarez_uploadrr.services.mkv_title import apply_internal_title_update
    result = apply_internal_title_update(
        item_id, dry_run=False, apply=True, confirmation="WRONG_TOKEN", conn=conn
    )
    assert result.get("status") in ("blocked", "error")


def test_apply_real_requires_token_not_called(tmp_path):
    """mkvpropedit must NOT be called without the correct confirmation token."""
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")

    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=str(mkv_file))
    _insert_proposal(conn, item_id, "Film 2024 1080p BluRay - EMUWAREZ")

    with patch("subprocess.run") as mock_run:
        from emuwarez_uploadrr.services.mkv_title import apply_internal_title_update, MKV_CONFIRMATION_TOKEN
        apply_internal_title_update(
            item_id, dry_run=False, apply=True, confirmation=None, conn=conn
        )
        mock_run.assert_not_called()


def test_apply_non_mkv_file_blocked(tmp_path):
    """Only .mkv files should be processed."""
    avi_file = tmp_path / "Film.2024.avi"
    avi_file.write_bytes(b"fake avi")

    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=str(avi_file))
    _insert_proposal(conn, item_id, "Film 2024 1080p BluRay - EMUWAREZ")

    from emuwarez_uploadrr.services.mkv_title import apply_internal_title_update, MKV_CONFIRMATION_TOKEN
    result = apply_internal_title_update(
        item_id, dry_run=False, apply=True, confirmation=MKV_CONFIRMATION_TOKEN, conn=conn
    )
    assert result.get("status") in ("blocked", "error")


def test_mkvpropedit_uses_shell_false(tmp_path):
    """subprocess.run must be called with shell=False."""
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")

    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=str(mkv_file))
    _insert_proposal(conn, item_id, "Film 2024 1080p BluRay - EMUWAREZ")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch("emuwarez_uploadrr.services.mkv_title.check_mkvpropedit_available",
               return_value={"available": True, "path": "/usr/bin/mkvpropedit"}):
        from emuwarez_uploadrr.services.mkv_title import apply_internal_title_update, MKV_CONFIRMATION_TOKEN
        apply_internal_title_update(
            item_id, dry_run=False, apply=True, confirmation=MKV_CONFIRMATION_TOKEN, conn=conn
        )
        if mock_run.called:
            _, kwargs = mock_run.call_args
            assert kwargs.get("shell") is False or not mock_run.call_args[1].get("shell", False)


@pytest.mark.parametrize("codigo,estado", [(1, "applied"), (2, "error")])
def test_el_error_de_mkvpropedit_dice_el_motivo(tmp_path, codigo, estado):
    """mkvpropedit escribe "Error: …" en stdout, no en stderr: antes el motivo
    se perdía, y un aviso (código 1) contaba como fallo."""
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Film", prepared_path=str(mkv_file))
    _insert_proposal(conn, item_id, "Film 2024 1080p BluRay - EMUWAREZ")
    salida = MagicMock(returncode=codigo, stdout="Error: The file could not be opened for writing.", stderr="")
    with patch("subprocess.run", return_value=salida), \
         patch("emuwarez_uploadrr.services.mkv_title.check_mkvpropedit_available",
               return_value={"available": True, "path": "/usr/bin/mkvpropedit"}):
        from emuwarez_uploadrr.services.mkv_title import apply_internal_title_update, MKV_CONFIRMATION_TOKEN
        result = apply_internal_title_update(
            item_id, dry_run=False, apply=True, confirmation=MKV_CONFIRMATION_TOKEN, conn=conn)
    assert result["status"] == estado
    if estado == "error":
        assert result["errors"] == ["Error: The file could not be opened for writing."]
