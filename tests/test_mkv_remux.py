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


def _enable_reorder(conn):
    """Enciende el reordenado. Viene apagado de fábrica, y sin reordenar el
    aplicador usa mkvpropedit (edita la cabecera) en vez de mkvmerge: los
    tests del camino de mkvmerge necesitan que haya algo que reordenar."""
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('remux.reorder_tracks', 'true')")
    conn.commit()


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
    """El forzado solo adelanta DENTRO de su idioma: nunca salta por encima de
    un idioma de mayor prioridad. Con audio castellano el activado sería el
    castellano forzado, pero aquí no hay ninguno (el forzado es inglés), así
    que no se activa ninguno: ves la peli doblada y sin subtítulos."""
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
    sub_ids = [t["id"] for t in plan["ordered_tracks"] if t["type"] == "subtitles"]
    assert sub_ids == [3, 2]                    # Español antes que Inglés forzado
    assert by_id[3]["default_after"] is False   # hay doblaje castellano: nada activado
    assert by_id[2]["default_after"] is False   # y el forzado inglés tampoco


def test_build_track_plan_forced_track_loses_default_tie_to_regular_same_language():
    """Dos subtítulos del mismo idioma (castellano), uno normal y otro forzado.
    El forzado va primero en el orden, y como el fichero TIENE audio castellano
    es además el activado: ves el doblaje y se te traducen los carteles y los
    diálogos en otro idioma, que es justo para lo que existe un forzado."""
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
    assert sub_ids_in_order == [2, 3]           # forzado antes que normal
    assert by_id[2]["default_after"] is True    # el forzado, porque hay doblaje
    assert by_id[3]["default_after"] is False   # el completo no


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
    # Reordenar viene apagado de fábrica, así que el orden no cambia: lo que
    # se aplica son los nombres y las marcas de predeterminada.
    assert result["order_changed"] is False
    # status "ready" ya significa que hay algo que aplicar (los renombrados);
    # sería "warning" si no hubiera nada.
    assert len(result["ordered_tracks"]) == 6
    assert "command_preview" in result


def test_plan_reorders_when_the_setting_is_on(tmp_path):
    """Y con el ajuste encendido vuelve a reordenar, que es el comportamiento
    de siempre."""
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('remux.reorder_tracks', 'true')")
    conn.commit()

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read:
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
        result = build_remux_plan(item_id, conn=conn)

    assert result["order_changed"] is True


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
    _enable_reorder(conn)

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
    _enable_reorder(conn)

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


# ---------------------------------------------------------------------------
# Forced subtitles: container flag first, track name second
# ---------------------------------------------------------------------------

from emuwarez_uploadrr.services.mkv_remux import _is_forced


@pytest.mark.parametrize("name", [
    "Forced",
    "forced",
    "Spanish [ForcedNarrative]",       # the real-world case that was missed
    "Español - Forzados",
    "Subtítulos forzados",
    "Castellano (Forzada)",
    "[FORCED]",
])
def test_forced_detected_from_the_track_name(name):
    """Plenty of releases never set the container's forced bit and only say it
    in the name, which used to be ignored entirely."""
    assert _is_forced({"track_name": name, "forced_track": 0}) is True


@pytest.mark.parametrize("name", [
    "Español (Castellano)",
    "SDH",
    "Full",
    "Full, not forced",                # says the opposite, in so many words
    "NonForced",
    "Non-Forced",
    "no forzado",
    "unforced",
    "reinforced dialogue",             # contains "forced" inside another word
])
def test_not_forced_from_the_track_name(name):
    assert _is_forced({"track_name": name, "forced_track": 0}) is False


def test_container_flag_wins_over_a_name_that_disagrees():
    """The flag is what a player actually acts on, so a name saying otherwise
    doesn't get to override it."""
    assert _is_forced({"track_name": "Full, not forced", "forced_track": 1}) is True


def test_missing_name_and_flag_is_not_forced():
    assert _is_forced({}) is False
    assert _is_forced({"track_name": None, "forced_track": None}) is False


def test_forced_name_reaches_the_track_label_and_the_ordering():
    """La bandera no es solo cosmética: es el desempate que pone el forzado
    delante del normal dentro de su idioma."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    mkv_json = {"tracks": [
        {"id": 0, "type": "video", "codec": "AVC", "properties": {}},
        {"id": 1, "type": "audio", "codec": "AC-3",
         "properties": {"language": "spa", "audio_channels": 6}},
        # Forced only by NAME, and listed first on purpose.
        {"id": 2, "type": "subtitles", "codec": "SubRip",
         "properties": {"language": "spa", "track_name": "Spanish [ForcedNarrative]"}},
        {"id": 3, "type": "subtitles", "codec": "SubRip",
         "properties": {"language": "spa", "track_name": "Español (Castellano)"}},
    ]}
    plan = build_track_plan(mkv_json)
    subs = [t for t in plan["ordered_tracks"] if t["type"] == "subtitles"]
    by_id = {t["id"]: t for t in subs}
    assert by_id[2]["forced"] is True
    assert by_id[3]["forced"] is False
    assert by_id[2]["new_name"].endswith("- Forzado")
    # El forzado abre el grupo del castellano.
    assert [t["id"] for t in subs][:2] == [2, 3]


# ---------------------------------------------------------------------------
# Qué subtítulo queda activado: depende del audio, no del orden
# ---------------------------------------------------------------------------

def _plan_with(audio_langs, subs):
    """subs: lista de (lang, forced). Devuelve (orden de ids, id activado)."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    tracks = [{"id": 0, "type": "video", "codec": "AVC", "properties": {"pixel_dimensions": "1920x1080"}}]
    tid = 1
    for lang in audio_langs:
        tracks.append({"id": tid, "type": "audio", "codec": "AC-3",
                       "properties": {"language": lang, "audio_channels": 6}})
        tid += 1
    ids = {}
    for lang, forced in subs:
        tracks.append({"id": tid, "type": "subtitles", "codec": "SubRip",
                       "properties": {"language": lang, "forced_track": forced}})
        ids[(lang, forced)] = tid
        tid += 1
    plan = build_track_plan({"tracks": tracks})
    sub_tracks = [t for t in plan["ordered_tracks"] if t["type"] == "subtitles"]
    default = next((t["id"] for t in sub_tracks if t["default_after"]), None)
    return [t["id"] for t in sub_tracks], default, ids


def test_forced_order_is_per_language_never_across_languages():
    """Español Forzado, Español, Català Forzado, Català, Inglés Forzado, Inglés."""
    order, _, ids = _plan_with(
        ["jpn"],
        [("eng", False), ("cat", True), ("spa", False), ("eng", True), ("spa", True), ("cat", False)],
    )
    assert order == [
        ids[("spa", True)], ids[("spa", False)],
        ids[("cat", True)], ids[("cat", False)],
        ids[("eng", True)], ids[("eng", False)],
    ]


def test_with_castilian_audio_the_forced_castilian_sub_is_the_one_enabled():
    """Ves el doblaje, así que se activan los carteles y los diálogos en otro
    idioma que el doblaje no cubre — para eso existe un forzado."""
    _, default, ids = _plan_with(["spa", "eng"], [("spa", False), ("spa", True), ("eng", False)])
    assert default == ids[("spa", True)]


def test_with_castilian_audio_but_no_forced_sub_nothing_is_enabled():
    """Doblada y sin subtítulos: no hay nada que traducir por encima."""
    _, default, _ = _plan_with(["spa"], [("spa", False), ("eng", False)])
    assert default is None


def test_without_castilian_audio_the_full_castilian_sub_is_enabled():
    """Versión original: hacen falta TODOS los diálogos, no solo los carteles,
    así que se activa el completo y no el forzado."""
    _, default, ids = _plan_with(["jpn"], [("spa", True), ("spa", False)])
    assert default == ids[("spa", False)]


def test_latin_spanish_audio_does_not_count_as_castilian():
    """El latino no es castellano (lang_priority ya lo separa), así que se
    trata como si no hubiera doblaje: manda el subtítulo completo."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan({"tracks": [
        {"id": 0, "type": "video", "codec": "AVC", "properties": {"pixel_dimensions": "1920x1080"}},
        {"id": 1, "type": "audio", "codec": "AC-3",
         "properties": {"language": "spa", "language_ietf": "es-419", "audio_channels": 6}},
        {"id": 2, "type": "subtitles", "codec": "SubRip", "properties": {"language": "spa", "forced_track": True}},
        {"id": 3, "type": "subtitles", "codec": "SubRip", "properties": {"language": "spa"}},
    ]})
    by_id = {t["id"]: t for t in plan["ordered_tracks"]}
    assert by_id[3]["default_after"] is True
    assert by_id[2]["default_after"] is False


def test_no_castilian_anywhere_falls_back_to_the_first_subtitle():
    """Japonesa subtitulada solo en inglés: mejor el primero activado que el
    fichero entero con todos los subtítulos apagados."""
    order, default, _ = _plan_with(["jpn"], [("eng", False), ("fre", False)])
    assert default == order[0]


def test_a_file_with_no_subtitles_at_all_has_no_default():
    _, default, _ = _plan_with(["spa"], [])
    assert default is None


# ---------------------------------------------------------------------------
# Reordenar es opcional: apagado, solo se renombra y se marca
# ---------------------------------------------------------------------------

_MIXED = {"tracks": [
    {"id": 0, "type": "video", "codec": "AVC", "properties": {"pixel_dimensions": "1920x1080"}},
    # Inglés antes que castellano a propósito: con reordenado, el castellano
    # sube; sin él, se queda donde está pero igualmente marcado.
    {"id": 1, "type": "audio", "codec": "AC-3", "properties": {"language": "eng", "audio_channels": 6}},
    {"id": 2, "type": "audio", "codec": "AC-3", "properties": {"language": "spa", "audio_channels": 6}},
    {"id": 3, "type": "subtitles", "codec": "SubRip", "properties": {"language": "eng"}},
    {"id": 4, "type": "subtitles", "codec": "SubRip", "properties": {"language": "spa"}},
]}


def test_reorder_on_moves_castilian_first():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan(_MIXED, reorder=True)
    assert plan["new_order"] == [0, 2, 1, 4, 3]
    assert plan["order_changed"] is True


def test_reorder_off_keeps_the_file_order_but_still_renames_and_marks():
    """Sin reordenar, las pistas se quedan donde están. Pero el nombre y la
    marca de predeterminada se deciden igual, porque son reglas de IDIOMA y no
    de posición: el castellano sigue siendo el marcado aunque vaya el segundo."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan(_MIXED, reorder=False)
    assert plan["new_order"] == [0, 1, 2, 3, 4]
    assert plan["order_changed"] is False

    by_id = {t["id"]: t for t in plan["ordered_tracks"]}
    # El castellano queda marcado, esté donde esté.
    assert by_id[2]["default_after"] is True     # audio ESP
    assert by_id[1]["default_after"] is False    # audio ING
    # Con doblaje castellano no se activa ningún subtítulo (no hay forzado).
    assert by_id[4]["default_after"] is False
    assert by_id[3]["default_after"] is False
    # Y los nombres se aplican igual que con reordenado.
    assert by_id[2]["new_name"] == "Español (Castellano) - DD 5.1"
    assert by_id[4]["new_name"] == "Español (Castellano)"


def test_reorder_off_still_reports_the_renames_as_a_change():
    """order_changed=False no puede significar "no hay nada que hacer": los
    nombres y las marcas siguen cambiando y hay que aplicarlos."""
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan(_MIXED, reorder=False)
    assert plan["any_changed"] is True


# ---------------------------------------------------------------------------
# Sin reordenar: se edita la cabecera, no se reescribe el contenedor
# ---------------------------------------------------------------------------

def test_mkvpropedit_args_select_tracks_by_uid():
    """Por UID y no por posición: es estable aunque el fichero se lea de otra
    manera. Sin UID se cae a la posición, que mkvpropedit numera desde 1."""
    from emuwarez_uploadrr.services.mkv_remux import build_mkvpropedit_args
    plan = {"ordered_tracks": [
        {"id": 0, "type": "video", "uid": 111, "new_name": "1080p x264", "default_after": True},
        {"id": 1, "type": "audio", "uid": 222, "new_name": "Español (Castellano) - DD 5.1", "default_after": True},
        {"id": 2, "type": "subtitles", "uid": None, "new_name": "Español (Castellano)", "default_after": False},
    ]}
    args = build_mkvpropedit_args("/data/peli.mkv", plan)
    assert args[:2] == ["mkvpropedit", "/data/peli.mkv"]
    assert "track:=111" in args and "track:=222" in args
    assert "track:3" in args                       # sin uid: posición 1-based
    # El vídeo no lleva bandera de predeterminada; audio y subtítulos sí.
    assert args.count("flag-default=1") == 1
    assert args.count("flag-default=0") == 1


def test_apply_without_reordering_edits_in_place(tmp_path):
    """Lo que esto evita: reescribir 20 GB para cambiar unas cadenas de la
    cabecera, y sustituir el fichero por uno nuevo, que rompe el hardlink
    compartido con el cliente de torrent."""
    from emuwarez_uploadrr.services.mkv_remux import apply_remux, REMUX_CONFIRMATION_TOKEN
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"contenido original")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=str(mkv_file))     # reordenado APAGADO

    llamadas = []

    def _fake_run(args, **kwargs):
        llamadas.append(args)
        class _R:
            returncode = 0
            stdout = "Realizado."
            stderr = ""
        return _R()

    inodo_antes = mkv_file.stat().st_ino
    with (
        patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available",
              return_value={"available": True, "path": "/usr/bin/mkvmerge"}),
        patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json",
              return_value={"ok": True, "data": _SAMPLE_MKV_JSON}),
        patch("emuwarez_uploadrr.services.mkv_remux.subprocess.run", _fake_run),
    ):
        result = apply_remux(item_id, conn=conn, dry_run=False, apply=True,
                             confirmation=REMUX_CONFIRMATION_TOKEN)

    assert result["status"] == "applied"
    assert llamadas and llamadas[0][0] == "mkvpropedit", llamadas
    # Ni "-o" ni fichero temporal: no se escribe una copia.
    assert "-o" not in llamadas[0]
    # Y lo que de verdad importa: el fichero es el MISMO.
    assert mkv_file.stat().st_ino == inodo_antes
    assert mkv_file.read_bytes() == b"contenido original"
    conn.close()


# ---------------------------------------------------------------------------
# El plan dice si la ordenación está activada, para que la tabla pueda avisar
# ---------------------------------------------------------------------------

def _plan_con_reorden(tmp_path, activado: bool) -> dict:
    mkv_file = tmp_path / "Peli.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, prepared_path=None, path=str(mkv_file))
    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available") as mock_chk, \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json") as mock_read, \
         patch("emuwarez_uploadrr.services.mkv_remux.reorder_tracks_enabled") as mock_reorder:
        mock_chk.return_value = {"available": True, "path": "/usr/bin/mkvmerge"}
        mock_read.return_value = {"ok": True, "data": _SAMPLE_MKV_JSON}
        mock_reorder.return_value = activado
        from emuwarez_uploadrr.services.mkv_remux import build_remux_plan
        return build_remux_plan(item_id, conn=conn)


@pytest.mark.parametrize("activado", [True, False])
def test_el_plan_dice_si_la_ordenacion_esta_activada(tmp_path, activado):
    """La tabla de "Ver Pistas" enseña el orden que va a quedar, así que con la
    ordenación apagada enseña el ACTUAL — y sin este dato nada distingue "ya
    estaban bien" de "no se van a mover". La interfaz lo usa para avisar."""
    assert _plan_con_reorden(tmp_path, activado)["reorder_enabled"] is activado


def test_apagada_el_plan_conserva_el_orden_del_archivo(tmp_path):
    """Que el aviso diga la verdad: apagada, las pistas se quedan donde están.

    Es lo que hace que el aviso valga la pena — el castellano NO sube al primer
    puesto, aunque la tabla siga llamándose "Ordenación y Nombre de las Pistas".
    """
    plan = _plan_con_reorden(tmp_path, False)
    assert plan["order_changed"] is False
    assert [t["id"] for t in plan["ordered_tracks"]] == [t["id"] for t in plan["tracks"]]


def test_activada_el_plan_si_reordena(tmp_path):
    """Y el contraste: con ella puesta el orden sí cambia, así que no hay nada
    que avisar. Si este test y el de arriba dieran lo mismo, el aviso sobraría
    o mentiría."""
    plan = _plan_con_reorden(tmp_path, True)
    assert plan["order_changed"] is True
