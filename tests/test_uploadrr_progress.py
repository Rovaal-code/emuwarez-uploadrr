"""Tests for services/uploadrr_progress.py — the ported parser that reads
real progress from Uploadrr-EMU's own output (originally in legacy.py), the
mkvmerge --gui-mode parser, and the fixed-weight phase state builder."""
from __future__ import annotations

from emuwarez_uploadrr.services.uploadrr_progress import (
    PHASES,
    RUNNING_SUB_PHASE_ORDER,
    build_phase_state,
    parse_mkvmerge_gui_progress,
    parse_uploadrr_progress,
    with_phase_timestamps,
)


def test_phase_weights_sum_to_100():
    assert sum(weight for _key, _label, weight in PHASES) == 100


def test_running_sub_phases_match_phases_table():
    phase_keys = [key for key, _label, _weight in PHASES]
    for key in RUNNING_SUB_PHASE_ORDER:
        assert key in phase_keys


def test_parse_uploadrr_progress_ignores_unrelated_text():
    assert parse_uploadrr_progress("") is None
    assert parse_uploadrr_progress("some random log line") is None


def test_parse_uploadrr_progress_queue_and_mediainfo():
    assert parse_uploadrr_progress("Starting queue processing") == ("queue_processing", 100, True)
    phase, pct, ok = parse_uploadrr_progress("Exporting MediaInfo for file.mkv")
    assert phase == "mediainfo_export" and ok is None
    phase2, pct2, ok2 = parse_uploadrr_progress("MediaInfo JSON Exported")
    assert phase2 == "mediainfo_export" and ok2 is True and pct2 == 100


def test_parse_uploadrr_progress_video_metadata_and_dupes():
    assert parse_uploadrr_progress("Processing video metadata") == ("video_metadata", 100, None)
    assert parse_uploadrr_progress("Searching for existing torrents") == ("duplicates", 50, None)
    assert parse_uploadrr_progress("No dupes found") == ("duplicates", 100, True)


def test_parse_uploadrr_progress_screenshots_with_counter():
    phase, pct, ok = parse_uploadrr_progress("Generating screenshots (2/8)")
    assert phase == "screenshots_generate"
    assert ok is False
    phase2, pct2, ok2 = parse_uploadrr_progress("Generating screenshots (8/8)")
    assert phase2 == "screenshots_generate"
    assert ok2 is True
    assert pct2 > pct

    phase3, _pct3, ok3 = parse_uploadrr_progress("Uploading screenshots (3/8)")
    assert phase3 == "screenshots_upload"
    assert ok3 is False


def test_parse_uploadrr_progress_hashing_and_torrent():
    phase, pct, ok = parse_uploadrr_progress("Hashing: 50.0%")
    assert phase == "hashing"
    assert pct == 50
    assert ok is None

    phase2, pct2, ok2 = parse_uploadrr_progress("Creating torrent: 30%")
    assert phase2 == "torrent_create"
    assert pct2 == 30


def test_parse_uploadrr_progress_uploading_to_emu():
    assert parse_uploadrr_progress("Uploading to EMU") == ("uploading_emu", 0, None)


def test_parse_uploadrr_progress_success_and_failure():
    assert parse_uploadrr_progress("Torrent uploaded successfully") == ("uploading_emu", 100, True)
    assert parse_uploadrr_progress('{"success":false}') == ("uploading_emu", 100, False)


def test_parse_mkvmerge_gui_progress():
    assert parse_mkvmerge_gui_progress("#GUI#progress 42%") == 42
    assert parse_mkvmerge_gui_progress("#GUI#progress 100%") == 100
    assert parse_mkvmerge_gui_progress("some other mkvmerge output") is None


def test_build_phase_state_all_pending():
    state = build_phase_state([])
    assert state["global_pct"] == 0
    assert all(p["status"] == "pending" for p in state["phases"])


def test_build_phase_state_partial_progress():
    state = build_phase_state(["integrity", "nomenclature"], current="remux", current_pct=50)
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["integrity"]["status"] == "done" and by_key["integrity"]["pct"] == 100
    assert by_key["nomenclature"]["status"] == "done"
    assert by_key["remux"]["status"] == "running" and by_key["remux"]["pct"] == 50
    assert by_key["preflight"]["status"] == "pending" and by_key["preflight"]["pct"] == 0
    assert by_key["queue_processing"]["status"] == "pending"
    # 5 + 5 + (15 * 0.5) = 17.5 -> rounds to 18
    assert state["global_pct"] == 18


def test_build_phase_state_running_sub_phase_advances():
    # queue_processing/video_processing/mediainfo_export already done, hashing
    # in progress at 50%: (5+5+15+5) wrapper phases + (2+2+3) earlier running
    # sub-phases + 20*0.5 hashing = 30 + 7 + 10 = 47
    state = build_phase_state(
        ["integrity", "nomenclature", "remux", "preflight", "queue_processing", "video_processing", "mediainfo_export"],
        current="hashing", current_pct=50,
    )
    assert state["global_pct"] == 47
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["hashing"]["status"] == "running"
    assert by_key["torrent_create"]["status"] == "pending"


def test_build_phase_state_all_done():
    all_keys = [key for key, _label, _weight in PHASES]
    state = build_phase_state(all_keys)
    assert state["global_pct"] == 100
    assert all(p["status"] == "done" and p["pct"] == 100 for p in state["phases"])


# ---------------------------------------------------------------------------
# with_phase_timestamps
# ---------------------------------------------------------------------------

def test_with_phase_timestamps_stamps_running_and_done():
    state = build_phase_state([], current="integrity", current_pct=0)
    stamped = with_phase_timestamps(state, None, now="2026-01-01T00:00:00+00:00")
    by_key = {p["key"]: p for p in stamped["phases"]}
    assert by_key["integrity"]["started_at"] == "2026-01-01T00:00:00+00:00"
    assert by_key["integrity"]["finished_at"] is None
    assert by_key["nomenclature"]["started_at"] is None


def test_with_phase_timestamps_carries_forward_started_at():
    # First call: integrity starts.
    state1 = build_phase_state([], current="integrity", current_pct=0)
    stamped1 = with_phase_timestamps(state1, None, now="2026-01-01T00:00:00+00:00")

    # Later call: integrity is now done — started_at must be preserved from
    # the first call, not overwritten to the second call's "now".
    state2 = build_phase_state(["integrity"])
    stamped2 = with_phase_timestamps(state2, stamped1["phases"], now="2026-01-01T00:00:10+00:00")

    by_key = {p["key"]: p for p in stamped2["phases"]}
    assert by_key["integrity"]["started_at"] == "2026-01-01T00:00:00+00:00"
    assert by_key["integrity"]["finished_at"] == "2026-01-01T00:00:10+00:00"


def test_with_phase_timestamps_pending_phase_has_no_timestamps():
    state = build_phase_state([], current="integrity", current_pct=0)
    stamped = with_phase_timestamps(state, None, now="2026-01-01T00:00:00+00:00")
    by_key = {p["key"]: p for p in stamped["phases"]}
    assert by_key["hashing"]["started_at"] is None
    assert by_key["hashing"]["finished_at"] is None
