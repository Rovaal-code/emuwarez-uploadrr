"""Tests for mkv_remux service (Phase 12A) — no real mkvmerge execution."""
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


_SAMPLE_MKV_JSON = {
    "tracks": [
        {"id": 0, "type": "video", "codec": "AVC/H.264/MPEG-4p10",
         "properties": {"pixel_dimensions": "1920x1080"}},
        {"id": 1, "type": "audio", "codec": "E-AC-3",
         "properties": {"language": "eng", "audio_channels": 6, "track_name": "English"}},
        {"id": 2, "type": "audio", "codec": "AC-3",
         "properties": {"language": "spa", "audio_channels": 6}},
        {"id": 3, "type": "subtitles", "codec": "SubRip/SRT", "properties": {"language": "eng"}},
        {"id": 4, "type": "subtitles", "codec": "SubRip/SRT",
         "properties": {"language": "spa", "forced_track": True}},
        {"id": 5, "type": "audio", "codec": "AC-3", "properties": {"language": "cat", "audio_channels": 2}},
    ]
}


# ---------------------------------------------------------------------------
# Pure functions: language display / priority
# ---------------------------------------------------------------------------

def test_lang_priority_castilian_first():
    from emuwarez_uploadrr.services.mkv_remux import lang_priority
    assert lang_priority("spa") == 0
    assert lang_priority("cat") == 1
    assert lang_priority("eng") == 2
    assert lang_priority("fre") == 3


def test_lang_priority_latin_spanish_is_not_castilian():
    from emuwarez_uploadrr.services.mkv_remux import lang_priority
    # Plain 639-2 "spa" has no regional variant — only language_ietf or an
    # existing track name can signal Latin American Spanish.
    assert lang_priority("spa", lang_ietf="es-419") == 3
    assert lang_priority("spa", existing_name="Español Latino") == 3
    assert lang_priority("spa", lang_ietf="es-ES") == 0


def test_lang_display_name():
    from emuwarez_uploadrr.services.mkv_remux import lang_display_name
    assert lang_display_name("spa") == "Español (Castellano)"
    assert lang_display_name("spa", lang_ietf="es-419") == "Español (Latinoamérica)"
    assert lang_display_name("cat") == "Català"
    assert lang_display_name("eng") == "Inglés"
    assert lang_display_name("und") == "Desconocido"
    assert lang_display_name(None) == "Desconocido"


# ---------------------------------------------------------------------------
# Pure function: build_track_plan
# ---------------------------------------------------------------------------

def test_build_track_plan_orders_audio_and_subs_by_priority():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan(_SAMPLE_MKV_JSON)

    audio_ids_in_order = [t["id"] for t in plan["ordered_tracks"] if t["type"] == "audio"]
    assert audio_ids_in_order == [2, 5, 1]  # spa, cat, eng

    sub_ids_in_order = [t["id"] for t in plan["ordered_tracks"] if t["type"] == "subtitles"]
    assert sub_ids_in_order == [4, 3]  # spa (forced), eng

    assert plan["new_order"] == [0, 2, 5, 1, 4, 3]
    assert plan["order_changed"] is True
    assert plan["any_changed"] is True


def test_build_track_plan_names_are_professional():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    by_id = {t["id"]: t for t in plan["ordered_tracks"]}

    assert by_id[0]["new_name"] == "1080p AVC"
    assert by_id[2]["new_name"] == "Español (Castellano) - DD 5.1"
    assert by_id[5]["new_name"] == "Català - DD 2.0"
    assert by_id[1]["new_name"] == "Inglés - DD+ 5.1"
    assert by_id[4]["new_name"] == "Español (Castellano) (Forzado)"
    assert by_id[3]["new_name"] == "Inglés"


def test_build_track_plan_default_flags():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    by_id = {t["id"]: t for t in plan["ordered_tracks"]}

    assert by_id[2]["default_after"] is True    # first audio (Spanish)
    assert by_id[5]["default_after"] is False
    assert by_id[1]["default_after"] is False
    assert by_id[4]["default_after"] is True    # forced subtitle stays default
    assert by_id[3]["default_after"] is False


def test_build_track_plan_no_change_when_already_ordered():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    already_ok = {
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC/H.264", "properties": {"pixel_dimensions": "1920x1080"}},
            {"id": 1, "type": "audio", "codec": "AC-3",
             "properties": {"language": "spa", "audio_channels": 2,
                             "track_name": "Español (Castellano) - DD 2.0", "default_track": True}},
        ]
    }
    plan = build_track_plan(already_ok)
    assert plan["order_changed"] is False
    # Video's own name still gets computed but the video default flag is
    # never touched, and nothing else differs, so nothing is "changed" — video
    # track name wasn't pre-set in the fixture, so it *does* change once; make
    # that explicit rather than asserting False across the board.
    audio = [t for t in plan["ordered_tracks"] if t["type"] == "audio"][0]
    assert audio["changed"] is False


def test_build_mkvmerge_args_shape():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan, build_mkvmerge_args
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    args = build_mkvmerge_args("/tmp/out.mkv", "/tmp/in.mkv", plan)
    assert args[0] == "mkvmerge"
    assert "-o" in args and "/tmp/out.mkv" in args
    assert args[-1] == "/tmp/in.mkv"
    assert "--track-order" in args
    order_idx = args.index("--track-order")
    assert args[order_idx + 1] == "0:0,0:2,0:5,0:1,0:4,0:3"


# ---------------------------------------------------------------------------
# Orchestration: build_remux_plan / apply_remux (mocked subprocess)
# ---------------------------------------------------------------------------

def test_remux_confirmation_token_value():
    from emuwarez_uploadrr.services.mkv_remux import REMUX_CONFIRMATION_TOKEN
    assert REMUX_CONFIRMATION_TOKEN == "REORDENAR_PISTAS"


def test_plan_item_not_found(tmp_path):
    conn = _make_conn(tmp_path)
    from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
    result = build_remux_plan(9999, conn=conn)
    assert result["status"] == "blocked"
    assert result["errors"]


def test_plan_no_prepared_path(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=None)
    from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
    result = build_remux_plan(item_id, conn=conn)
    assert result["status"] == "blocked"
    assert any("prepared_path" in e.lower() for e in result["errors"])


def test_plan_mkvmerge_unavailable(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk:
        mock_chk.return_value = {"available": False, "path": None}
        from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
        result = build_remux_plan(item_id, conn=conn)

    assert result["status"] == "blocked"
    assert any("mkvmerge" in e.lower() for e in result["errors"])


def test_plan_ready_with_mocked_mkvmerge(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read:
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
        result = build_remux_plan(item_id, conn=conn)

    assert result["status"] == "ready"
    assert result["order_changed"] is True
    assert len(result["ordered_tracks"]) == 6
    assert "command_preview" in result


def test_apply_requires_confirmation(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read:
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        from emuwarez_uploadrr.services.mkv_remux import apply_remux
        result = apply_remux(item_id, dry_run=False, apply=True, confirmation="wrong", conn=conn)

    assert result["status"] == "blocked"
    assert any("confirmar" in e.lower() for e in result["errors"])


def test_apply_success_replaces_file(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv original")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    def _fake_run(args, **kwargs):
        # Simulate mkvmerge actually writing the -o target.
        out_idx = args.index("-o") + 1
        with open(args[out_idx], "wb") as fh:
            fh.write(b"fake mkv remuxed")
        m = MagicMock()
        m.returncode = 0
        m.stdout = "ok"
        m.stderr = ""
        return m

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read, \
         patch("emuwarez_uploadrr.services.mkv_remux.subprocess.run", side_effect=_fake_run):
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        from emuwarez_uploadrr.services.mkv_remux import apply_remux, REMUX_CONFIRMATION_TOKEN
        result = apply_remux(
            item_id, dry_run=False, apply=True, confirmation=REMUX_CONFIRMATION_TOKEN, conn=conn,
        )

    assert result["status"] == "applied"
    assert mkv_file.read_bytes() == b"fake mkv remuxed"
    row = conn.execute("SELECT track_remux_status FROM library_items WHERE id=?", (item_id,)).fetchone()
    assert row["track_remux_status"] == "aplicado"


def test_apply_failure_leaves_original_untouched(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv original")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    def _fake_run(args, **kwargs):
        m = MagicMock()
        m.returncode = 2  # mkvmerge hard failure, no output produced
        m.stdout = ""
        m.stderr = "error: something broke"
        return m

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read, \
         patch("emuwarez_uploadrr.services.mkv_remux.subprocess.run", side_effect=_fake_run):
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        from emuwarez_uploadrr.services.mkv_remux import apply_remux, REMUX_CONFIRMATION_TOKEN
        result = apply_remux(
            item_id, dry_run=False, apply=True, confirmation=REMUX_CONFIRMATION_TOKEN, conn=conn,
        )

    assert result["status"] == "error"
    assert mkv_file.read_bytes() == b"fake mkv original"  # untouched
    row = conn.execute("SELECT track_remux_status FROM library_items WHERE id=?", (item_id,)).fetchone()
    assert row["track_remux_status"] == "error"
