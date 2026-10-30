"""Tests for services/uploadrr_progress.py — the ported parser that reads
real progress from Uploadrr-EMU's own output (originally in legacy.py), the
mkvmerge --gui-mode parser, and the fixed-weight phase state builder."""
from __future__ import annotations

from emuwarez_uploadrr.services.uploadrr_progress import (
    PHASE_KEY_ALIASES,
    PHASES,
    RAW_SUBPHASE_WEIGHTS,
    RUNNING_DISPLAY_ORDER,
    RUNNING_SUB_PHASE_ORDER,
    build_phase_state,
    parse_mkvmerge_gui_progress,
    parse_uploadrr_progress,
    resolve_display_progress,
    with_phase_timestamps,
)


def test_phase_weights_sum_to_100():
    assert sum(weight for _key, _label, weight in PHASES) == 100


def test_running_display_order_keys_match_phases_table():
    # RUNNING_SUB_PHASE_ORDER holds raw (pre-merge) keys, several of which no
    # longer have their own PHASES row (see PHASE_KEY_ALIASES) — the merged/
    # displayed sequence is what must line up with PHASES.
    phase_keys = [key for key, _label, _weight in PHASES]
    for key in RUNNING_DISPLAY_ORDER:
        assert key in phase_keys


def test_raw_subphase_weights_cover_every_running_sub_phase():
    for key in RUNNING_SUB_PHASE_ORDER:
        assert key in RAW_SUBPHASE_WEIGHTS


def test_merged_group_raw_weights_sum_to_displayed_weight():
    # Each merged phase's own PHASES weight must equal the sum of its raw
    # members' weights — otherwise resolve_display_progress()'s interpolation
    # would change the job-wide global_pct total versus the old, unmerged
    # list. verificacion_presubida ("Inicio de Uploadrr") is the deliberate
    # exception: 10 of its 22 points are app-level integrity/preflight work
    # with no raw trigger at all — its raw members only ever need to sum to
    # THEIR OWN total (12), not the full displayed weight (see
    # resolve_display_progress's own docstring/uploadrr_progress.py's
    # RAW_SUBPHASE_WEIGHTS comment for why that's still correct).
    phase_weights = {key: weight for key, _label, weight in PHASES}
    groups: dict[str, list[str]] = {}
    for raw_key in RUNNING_SUB_PHASE_ORDER:
        display_key = PHASE_KEY_ALIASES.get(raw_key, raw_key)
        groups.setdefault(display_key, []).append(raw_key)
    for display_key, members in groups.items():
        if len(members) <= 1 or display_key == "verificacion_presubida":
            continue
        assert sum(RAW_SUBPHASE_WEIGHTS[m] for m in members) == phase_weights[display_key]


def test_resolve_display_progress_unmerged_passthrough():
    assert resolve_display_progress("uploading_emu", 0) == ("uploading_emu", 0)


def test_resolve_display_progress_verificacion_group():
    # queue_processing(2) + video_processing(2) + mediainfo_export(3) +
    # video_metadata(2) + duplicates(3) = 12 (NOT the phase's own full
    # PHASES weight of 22 — see test_merged_group_raw_weights_sum_to_
    # displayed_weight's docstring). Only the LAST member (duplicates)
    # reaching 100% closes the displayed phase at 100.
    assert resolve_display_progress("queue_processing", 100) == ("verificacion_presubida", 17)
    assert resolve_display_progress("video_processing", 100) == ("verificacion_presubida", 33)
    assert resolve_display_progress("mediainfo_export", 100) == ("verificacion_presubida", 58)
    assert resolve_display_progress("video_metadata", 100) == ("verificacion_presubida", 75)
    assert resolve_display_progress("duplicates", 50) == ("verificacion_presubida", 88)
    assert resolve_display_progress("duplicates", 100) == ("verificacion_presubida", 100)


def test_resolve_display_progress_screenshots_group():
    # screenshots_generate(10) + screenshots_upload(10) = 20, equal shares.
    assert resolve_display_progress("screenshots_generate", 0) == ("screenshots", 0)
    assert resolve_display_progress("screenshots_generate", 100) == ("screenshots", 50)
    assert resolve_display_progress("screenshots_upload", 0) == ("screenshots", 50)
    assert resolve_display_progress("screenshots_upload", 100) == ("screenshots", 100)


def test_resolve_display_progress_hash_torrent_group():
    # hashing(20) + torrent_create(8) = 28.
    assert resolve_display_progress("hashing", 0) == ("hash_torrent", 0)
    assert resolve_display_progress("hashing", 100) == ("hash_torrent", round(100 * 20 / 28))
    assert resolve_display_progress("torrent_create", 100) == ("hash_torrent", 100)


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


def test_parse_uploadrr_progress_screenshots_upload_real_colon_format():
    """Regression: Uploadrr-EMU's real output (src/progress.py's
    ProgressManager.screen_start/screen_up) is "Uploading screenshots: 0/3"
    — WITH a colon — which the parenthesized-count pattern didn't account
    for at all, so this phase was never recognized as running during a real
    upload (including the whole per-host retry storm when a host fails),
    falling back to the generic "En progreso" label instead of showing the
    phase + its counter."""
    phase, pct, ok = parse_uploadrr_progress("Uploading screenshots: 0/3")
    assert phase == "screenshots_upload"
    assert pct == 0
    assert ok is False

    phase2, pct2, ok2 = parse_uploadrr_progress("Uploading screenshots: 3/3")
    assert phase2 == "screenshots_upload"
    assert ok2 is True
    assert pct2 == 100


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


def test_parse_uploadrr_progress_qbittorrent_bad_login():
    # clients.py's _add_to_qbittorrent prints this and returns without
    # raising on a bad login — pct stays 0 (not 100) so it's never mistaken
    # for a completed phase by advance_running_phase.
    phase, pct, ok = parse_uploadrr_progress("INCORRECT QBIT LOGIN CREDENTIALS")
    assert phase == "qbittorrent_add"
    assert pct == 0
    assert ok is False


def test_parse_uploadrr_progress_client_add_failed():
    line = "Torrent client add failed: Failed to connect to qBittorrent. Connection refused"
    assert parse_uploadrr_progress(line) == ("qbittorrent_add", 0, False)


def test_parse_uploadrr_progress_torrent_redownload_failed():
    # UNIT3D.py's follow-up GET for the tracker-signed .torrent 403'd — the
    # eMuwarez upload itself still succeeded, but no [tracker]{name}.torrent
    # file exists for add_to_client() to hand to qBittorrent.
    phase, pct, ok = parse_uploadrr_progress(
        "Torrent upload succeeded, but failed to download the torrent file: 403 Forbidden"
    )
    assert phase == "qbittorrent_add"
    assert pct == 0
    assert ok is False


def test_parse_mkvmerge_gui_progress():
    assert parse_mkvmerge_gui_progress("#GUI#progress 42%") == 42
    assert parse_mkvmerge_gui_progress("#GUI#progress 100%") == 100
    assert parse_mkvmerge_gui_progress("some other mkvmerge output") is None


def test_build_phase_state_all_pending():
    state = build_phase_state([])
    assert state["global_pct"] == 0
    assert all(p["status"] == "pending" for p in state["phases"])


def test_build_phase_state_partial_progress():
    state = build_phase_state(["verificacion_presubida", "nomenclature"], current="remux", current_pct=50)
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["verificacion_presubida"]["status"] == "done" and by_key["verificacion_presubida"]["pct"] == 100
    assert by_key["nomenclature"]["status"] == "done"
    assert by_key["remux"]["status"] == "running" and by_key["remux"]["pct"] == 50
    assert by_key["screenshots"]["status"] == "pending"
    # 22 + 5 + (15 * 0.5) = 34.5 -> banker's rounding -> 34
    assert state["global_pct"] == 34


def test_build_phase_state_running_sub_phase_advances():
    # nomenclatura/remux already done, "Inicio de Uploadrr"
    # (verificacion_presubida) in progress at 50%:
    # (5+15) + 22*0.5 = 20 + 11 = 31
    state = build_phase_state(
        ["nomenclature", "remux"],
        current="verificacion_presubida", current_pct=50,
    )
    assert state["global_pct"] == 31
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["verificacion_presubida"]["status"] == "running"
    assert by_key["screenshots"]["status"] == "pending"


def test_build_phase_state_all_done():
    all_keys = [key for key, _label, _weight in PHASES]
    state = build_phase_state(all_keys)
    assert state["global_pct"] == 100
    assert all(p["status"] == "done" and p["pct"] == 100 for p in state["phases"])


# ---------------------------------------------------------------------------
# with_phase_timestamps
# ---------------------------------------------------------------------------

def test_with_phase_timestamps_stamps_running_and_done():
    state = build_phase_state([], current="verificacion_presubida", current_pct=0)
    stamped = with_phase_timestamps(state, None, now="2026-01-01T00:00:00+00:00")
    by_key = {p["key"]: p for p in stamped["phases"]}
    assert by_key["verificacion_presubida"]["started_at"] == "2026-01-01T00:00:00+00:00"
    assert by_key["verificacion_presubida"]["finished_at"] is None
    assert by_key["nomenclature"]["started_at"] is None


def test_with_phase_timestamps_carries_forward_started_at():
    # First call: verificación presubida starts.
    state1 = build_phase_state([], current="verificacion_presubida", current_pct=0)
    stamped1 = with_phase_timestamps(state1, None, now="2026-01-01T00:00:00+00:00")

    # Later call: it's now done — started_at must be preserved from the
    # first call, not overwritten to the second call's "now".
    state2 = build_phase_state(["verificacion_presubida"])
    stamped2 = with_phase_timestamps(state2, stamped1["phases"], now="2026-01-01T00:00:10+00:00")

    by_key = {p["key"]: p for p in stamped2["phases"]}
    assert by_key["verificacion_presubida"]["started_at"] == "2026-01-01T00:00:00+00:00"
    assert by_key["verificacion_presubida"]["finished_at"] == "2026-01-01T00:00:10+00:00"


def test_with_phase_timestamps_pending_phase_has_no_timestamps():
    state = build_phase_state([], current="verificacion_presubida", current_pct=0)
    stamped = with_phase_timestamps(state, None, now="2026-01-01T00:00:00+00:00")
    by_key = {p["key"]: p for p in stamped["phases"]}
    assert by_key["hash_torrent"]["started_at"] is None
    assert by_key["hash_torrent"]["finished_at"] is None
