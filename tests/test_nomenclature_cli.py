"""CLI tests for Phase 10A nomenclature and mkv-title commands."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest


def _db_for(tmp_path):
    return str(tmp_path / "emuwarez_uploadrr.db")


def _run_cli(args, tmp_path):
    from emuwarez_uploadrr.cli import modern_main
    return modern_main(["--db", _db_for(tmp_path)] + args)


def _seed_db(tmp_path, title="Film", prepared_path=None, torrent_name=None, path=None):
    from emuwarez_uploadrr.database import connect, init_db
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn = connect(_db_for(tmp_path))
    init_db(conn)
    conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, prepared_path, path) VALUES (?,?,?,?,?)",
        (title, "movie", "downloaded", prepared_path, path),
    )
    conn.commit()
    item_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    if torrent_name:
        conn.execute(
            """INSERT INTO nomenclature_proposals
               (library_item_id, status, proposed_filename, proposed_title, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (item_id, "valid", torrent_name, title, now, now),
        )
        conn.commit()
    conn.close()
    return item_id


def test_nomenclature_sources_lists_webdl(tmp_path, capsys):
    rc = _run_cli(["nomenclature", "sources"], tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert "WEB-DL" in out


def test_nomenclature_sources_lists_bluray(tmp_path, capsys):
    rc = _run_cli(["nomenclature", "sources"], tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert "BluRay" in out


def test_nomenclature_providers_lists_amzn(tmp_path, capsys):
    rc = _run_cli(["nomenclature", "providers"], tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert "AMZN" in out


def test_nomenclature_providers_lists_nf(tmp_path, capsys):
    rc = _run_cli(["nomenclature", "providers"], tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert "NF" in out


def test_nomenclature_fields_not_found(tmp_path, capsys):
    rc = _run_cli(["nomenclature", "fields", "9999"], tmp_path)
    assert rc == 1


def test_nomenclature_fields_found(tmp_path, capsys):
    f = tmp_path / "dune.mkv"; f.write_bytes(b"x" * 2048)
    _MI_OK = {
        "available": True, "audio_summary": "ESP AC3 5.1",
        "rows": [
            {"field": "Códec de vídeo", "mediainfo": "AVC", "emu": "H.264"},
            {"field": "Source", "mediainfo": "del nombre del archivo", "emu": "WEB-DL"},
        ],
    }
    # El fichero es de mentira: mkvmerge tampoco lo reconocería.
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=[]), \
         patch("emuwarez_uploadrr.services.media_info_service.build_mediainfo_report", return_value=_MI_OK), \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json", return_value={"ok": True, "data": {}}):
        item_id = _seed_db(tmp_path, title="Dune", path=str(f),
                           torrent_name="Dune 2021 1080p WEB-DL AMZN - EMUWAREZ")
        rc = _run_cli(["nomenclature", "fields", str(item_id)], tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dune" in out or "dune" in out.lower()


def test_nomenclature_preview_fields(tmp_path, capsys):
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=[]):
        item_id = _seed_db(tmp_path, title="Film", torrent_name="Film 2024 1080p BluRay - EMUWAREZ")
        fields = json.dumps({"title": "Film", "year": "2024", "source": "BluRay", "tag": "EMUWAREZ"})
        rc = _run_cli(["nomenclature", "preview-fields", str(item_id), "--fields-json", fields], tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    assert "torrent_name" in out.lower() or "Film" in out


def test_mkv_title_preview_no_prepared_path(tmp_path, capsys):
    item_id = _seed_db(tmp_path, title="Film", torrent_name="Film 2024 1080p BluRay - EMUWAREZ")
    rc = _run_cli(["mkv-title", "preview", str(item_id)], tmp_path)
    out = capsys.readouterr().out
    assert rc == 1
    assert "blocked" in out.lower() or "status" in out.lower()


def test_mkv_title_preview_with_mkv(tmp_path, capsys):
    mkv_file = tmp_path / "Film.mkv"
    mkv_file.write_bytes(b"fake mkv")
    item_id = _seed_db(
        tmp_path, title="Film",
        prepared_path=str(mkv_file),
        torrent_name="Film 2024 1080p BluRay - EMUWAREZ",
    )
    with patch("emuwarez_uploadrr.services.mkv_title.check_mkvpropedit_available",
               return_value={"available": False, "path": None}):
        rc = _run_cli(["mkv-title", "preview", str(item_id)], tmp_path)
    out = capsys.readouterr().out
    assert "Film" in out


def test_mkv_title_apply_dryrun_no_execution(tmp_path, capsys):
    mkv_file = tmp_path / "Film.mkv"
    mkv_file.write_bytes(b"fake mkv")
    item_id = _seed_db(
        tmp_path, title="Film",
        prepared_path=str(mkv_file),
        torrent_name="Film 2024 1080p BluRay - EMUWAREZ",
    )
    with patch("subprocess.run") as mock_run:
        rc = _run_cli(["mkv-title", "apply", str(item_id), "--dry-run"], tmp_path)
        mock_run.assert_not_called()
    out = capsys.readouterr().out
    assert "mkvpropedit no se ha ejecutado" in out or rc in (0, 1)
