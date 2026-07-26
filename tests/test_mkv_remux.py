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


def _insert_library_item(conn, title="Movie", prepared_path=None, path=None):
    conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, prepared_path, path) VALUES (?,?,?,?,?)",
        (title, "movie", "downloaded", prepared_path, path),
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


def test_lang_priority_x_private_use_suffix_is_not_latin():
    """Regression found auditing a real 2802-file library: MAX/HBO Max tags
    some Spanish tracks 'es-x-01'..'es-x-09' (a private-use BCP47 subtag, not
    a region) — even on natively Castilian-Spanish content (e.g. a
    Spanish-produced sitcom). Must stay Castilian priority, not be demoted."""
    from emuwarez_uploadrr.services.mkv_remux import lang_priority, lang_display_name
    assert lang_priority("spa", lang_ietf="es-x-02") == 0
    assert lang_display_name("spa", lang_ietf="es-x-02") == "Español (Castellano)"
    # A real Latin American region code still works.
    assert lang_priority("spa", lang_ietf="es-MX") == 3


def test_lang_display_name():
    from emuwarez_uploadrr.services.mkv_remux import lang_display_name
    assert lang_display_name("spa") == "Español (Castellano)"
    assert lang_display_name("spa", lang_ietf="es-419") == "Español (Latinoamérica)"
    assert lang_display_name("cat") == "Català"
    assert lang_display_name("eng") == "Inglés"
    assert lang_display_name("und") == "Desconocido"
    assert lang_display_name(None) == "Desconocido"


def test_lang_display_name_covers_audit_gaps():
    """Norwegian Bokmål and Filipino, both found in a real-library audit and
    missing from the map at the time."""
    from emuwarez_uploadrr.services.mkv_remux import lang_display_name
    assert lang_display_name("nb") == "Noruego (Bokmål)"
    assert lang_display_name("nob") == "Noruego (Bokmål)"
    assert lang_display_name("fil") == "Filipino"


def test_audio_codec_label_recognizes_mlp():
    """MediaInfo/mkvmerge can report TrueHD's underlying codec as 'MLP FBA
    16-ch' with no 'TrueHD' substring at all — found on real files."""
    from emuwarez_uploadrr.services.mkv_remux import _audio_codec_label
    assert _audio_codec_label("MLP FBA 16-ch") == "MLP"
    assert _audio_codec_label("TrueHD Atmos") == "TrueHD"


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
    assert by_id[4]["new_name"] == "Español (Castellano) - Forzado"
    assert by_id[3]["new_name"] == "Inglés"


def test_build_track_plan_default_flags():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    by_id = {t["id"]: t for t in plan["ordered_tracks"]}

    assert by_id[2]["default_after"] is True    # first audio (Spanish)
    assert by_id[5]["default_after"] is False
    assert by_id[1]["default_after"] is False
    assert by_id[4]["default_after"] is True    # Español (Castellano), also happens to be forced
    assert by_id[3]["default_after"] is False


def test_build_track_plan_subtitle_default_follows_language_priority_not_forced_flag():
    """Subtitle default_after must follow the SAME Español Castellano ->
    Català -> Inglés priority as audio — NOT the "forced" flag. A forced
    track in a lower-priority language must NOT become default just because
    it's forced; a non-forced Castellano track must."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    mkv_json = {
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC/H.264/MPEG-4p10",
             "properties": {"pixel_dimensions": "1920x1080"}},
            {"id": 1, "type": "audio", "codec": "AC-3", "properties": {"language": "spa", "audio_channels": 6}},
            # Forced, but English (lowest priority) — must NOT win default.
            {"id": 2, "type": "subtitles", "codec": "SubRip/SRT",
             "properties": {"language": "eng", "forced_track": True}},
            # Not forced, but Castellano (highest priority) — must win default.
            {"id": 3, "type": "subtitles", "codec": "SubRip/SRT", "properties": {"language": "spa"}},
        ]
    }
    plan = build_track_plan(mkv_json)
    by_id = {t["id"]: t for t in plan["ordered_tracks"]}
    assert by_id[3]["default_after"] is True    # Español (Castellano), not forced
    assert by_id[2]["default_after"] is False   # Inglés, forced — still not default


def test_build_track_plan_forced_track_loses_default_tie_to_regular_same_language():
    """Two subtitle tracks of the SAME language (both Español Castellano, top
    priority): one regular, one forced-only. They tie on language priority, so
    without a tiebreaker Python's stable sort keeps them in the file's own
    original order — if mkvmerge happened to list the forced track first, it
    would win the tie and become default by accident. The regular track must
    always win: a forced track only covers foreign-language lines, it's not
    meant to be the general default subtitle."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    mkv_json = {
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC/H.264/MPEG-4p10",
             "properties": {"pixel_dimensions": "1920x1080"}},
            {"id": 1, "type": "audio", "codec": "AC-3", "properties": {"language": "spa", "audio_channels": 6}},
            # Forced Spanish listed BEFORE the regular Spanish track in the
            # file's own order — the exact real-world case that used to win
            # the default flag by accident.
            {"id": 2, "type": "subtitles", "codec": "SubRip/SRT",
             "properties": {"language": "spa", "forced_track": True}},
            {"id": 3, "type": "subtitles", "codec": "SubRip/SRT", "properties": {"language": "spa"}},
        ]
    }
    plan = build_track_plan(mkv_json)
    by_id = {t["id"]: t for t in plan["ordered_tracks"]}
    sub_ids_in_order = [t["id"] for t in plan["ordered_tracks"] if t["type"] == "subtitles"]
    assert sub_ids_in_order == [3, 2]           # regular before forced
    assert by_id[3]["default_after"] is True    # regular Español (Castellano)
    assert by_id[2]["default_after"] is False   # forced Español (Castellano) — not default


def test_apply_track_overrides_name_and_default():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan, apply_track_overrides
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    overrides = {
        2: {"new_name": "Español (mi nombre a mano)"},
        1: {"default_after": True},  # user wants English as default instead
    }
    patched = apply_track_overrides(plan, overrides)
    by_id = {t["id"]: t for t in patched["ordered_tracks"]}
    assert by_id[2]["new_name"] == "Español (mi nombre a mano)"
    assert by_id[1]["default_after"] is True
    # untouched tracks keep the auto-computed values
    assert by_id[5]["new_name"] == "Català - DD 2.0"


def test_apply_track_overrides_ignores_video_default():
    """Video's default flag is never touched, even via override."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan, apply_track_overrides
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    patched = apply_track_overrides(plan, {0: {"default_after": True}})
    video = [t for t in patched["ordered_tracks"] if t["type"] == "video"][0]
    assert video["default_after"] is False  # untouched — the sample video track has no default_track set


def test_apply_track_overrides_blank_name_is_ignored():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan, apply_track_overrides
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    patched = apply_track_overrides(plan, {2: {"new_name": "   "}})
    by_id = {t["id"]: t for t in patched["ordered_tracks"]}
    assert by_id[2]["new_name"] == "Español (Castellano) - DD 5.1"  # auto-computed kept


def test_apply_track_overrides_none_is_noop():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan, apply_track_overrides
    plan = build_track_plan(_SAMPLE_MKV_JSON)
    assert apply_track_overrides(plan, None) is plan


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


def test_build_track_plan_prefers_known_resolution_over_pixel_height():
    """A cropped/letterboxed 2.40:1 encode can store fewer pixel rows than its
    nominal resolution (e.g. 1920x800 for an actual 1080p master, confirmed on
    a real file) — known_resolution (from Radarr/Sonarr) must win over the
    pixel-height heuristic."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    cropped = {
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC/H.264",
             "properties": {"pixel_dimensions": "1920x800"}},
        ]
    }
    without_hint = build_track_plan(cropped)
    assert without_hint["ordered_tracks"][0]["new_name"] == "720p AVC"  # the bug, unpatched

    with_hint = build_track_plan(cropped, known_resolution="1080p")
    assert with_hint["ordered_tracks"][0]["new_name"] == "1080p AVC"


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


def test_plan_no_file_at_all(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=None, path=None)
    from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
    result = build_remux_plan(item_id, conn=conn)
    assert result["status"] == "blocked"
    assert result["using_prepared_copy"] is False
    assert result["errors"]


def test_plan_falls_back_to_source_path_without_nomenclature(tmp_path):
    """Track reorder/rename must work BEFORE nomenclature has ever run — it
    should fall back to the item's own file when there's no prepared_path."""
    mkv_file = tmp_path / "Original.File.mkv"
    mkv_file.write_bytes(b"fake mkv")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=None, path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read:
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
        result = build_remux_plan(item_id, conn=conn)

    assert result["status"] == "ready"
    assert result["prepared_path"] == str(mkv_file)
    assert result["using_prepared_copy"] is False


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


def test_apply_skips_mkvmerge_when_no_changes(tmp_path):
    """Tracks already in the right order with the right names — apply_remux
    must not run mkvmerge at all (a full rewrite of the file for nothing,
    same runtime as a real remux), just mark it applied instantly."""
    mkv_file = tmp_path / "Film.2024.mkv"
    original_bytes = b"fake mkv original, never touched"
    mkv_file.write_bytes(original_bytes)
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    already_ok = {
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC/H.264",
             "properties": {"pixel_dimensions": "1920x1080", "track_name": "1080p AVC"}},
            {"id": 1, "type": "audio", "codec": "AC-3",
             "properties": {"language": "spa", "audio_channels": 2,
                             "track_name": "Español (Castellano) - DD 2.0", "default_track": True}},
        ]
    }

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read, \
         patch("emuwarez_uploadrr.services.mkv_remux.subprocess.Popen") as mock_popen:
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": already_ok}
        from emuwarez_uploadrr.services.mkv_remux import apply_remux, REMUX_CONFIRMATION_TOKEN
        progress_calls: list[int] = []
        result = apply_remux(
            item_id, dry_run=False, apply=True, confirmation=REMUX_CONFIRMATION_TOKEN, conn=conn,
            on_progress=progress_calls.append,
        )

    mock_popen.assert_not_called()
    assert result["status"] == "applied"
    assert mkv_file.read_bytes() == original_bytes  # untouched
    assert progress_calls == [100]
    row = conn.execute("SELECT track_remux_status FROM library_items WHERE id=?", (item_id,)).fetchone()
    assert row["track_remux_status"] == "aplicado"


def test_apply_success_replaces_file(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv original")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    class _FakePopen:
        def __init__(self, args, **kwargs):
            # Simulate mkvmerge actually writing the -o target, and streaming
            # --gui-mode progress lines on stdout.
            out_idx = args.index("-o") + 1
            with open(args[out_idx], "wb") as fh:
                fh.write(b"fake mkv remuxed")
            self.stdout = iter(["#GUI#progress 50%\n", "#GUI#progress 100%\n"])

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read, \
         patch("emuwarez_uploadrr.services.mkv_remux.subprocess.Popen", side_effect=_FakePopen):
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        from emuwarez_uploadrr.services.mkv_remux import apply_remux, REMUX_CONFIRMATION_TOKEN
        progress_calls: list[int] = []
        result = apply_remux(
            item_id, dry_run=False, apply=True, confirmation=REMUX_CONFIRMATION_TOKEN, conn=conn,
            on_progress=progress_calls.append,
        )

    assert result["status"] == "applied"
    assert mkv_file.read_bytes() == b"fake mkv remuxed"
    assert 50 in progress_calls
    assert progress_calls[-1] == 100
    row = conn.execute("SELECT track_remux_status FROM library_items WHERE id=?", (item_id,)).fetchone()
    assert row["track_remux_status"] == "aplicado"


def test_apply_failure_leaves_original_untouched(tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv original")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))

    class _FakePopen:
        def __init__(self, args, **kwargs):
            # mkvmerge hard failure, no output produced
            self.stdout = iter(["error: something broke\n"])

        def wait(self, timeout=None):
            return 2

        def kill(self):
            pass

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read, \
         patch("emuwarez_uploadrr.services.mkv_remux.subprocess.Popen", side_effect=_FakePopen):
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
