"""Tests for services/media_info_service.py (Phase 6B).

The `mediainfo` binary isn't installed in this dev/test sandbox (only the
Docker homelab image has it via apt) — every test here mocks
`mediainfo_available()`/`legacy.run_mediainfo_json()` rather than shelling
out for real.
"""
from __future__ import annotations

from unittest.mock import patch

from emuwarez_uploadrr.services import media_info_service as svc


def _fake_mediainfo_json():
    return {
        "media": {
            "track": [
                {"@type": "General"},
                {"@type": "Video", "Format": "HEVC", "Width": "1920", "Height": "1080"},
                {"@type": "Audio", "Format": "E-AC-3", "Language": "eng"},
                {"@type": "Audio", "Format": "E-AC-3", "Language": "spa"},
                {"@type": "Text", "Language": "eng"},
                {"@type": "Text", "Language": "spa"},
            ]
        }
    }


def test_mediainfo_available_reflects_shutil_which():
    with patch("shutil.which", return_value=None):
        assert svc.mediainfo_available() is False
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        assert svc.mediainfo_available() is True


def test_read_media_info_summary_returns_none_when_binary_missing(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with patch.object(svc, "mediainfo_available", return_value=False):
        assert svc.read_media_info_summary(str(f)) is None


def test_read_media_info_summary_returns_none_for_missing_file():
    with patch.object(svc, "mediainfo_available", return_value=True):
        assert svc.read_media_info_summary("/nonexistent/path/movie.mkv") is None


def test_read_media_info_summary_returns_none_for_empty_path():
    assert svc.read_media_info_summary("") is None
    assert svc.read_media_info_summary(None) is None


def test_read_media_info_summary_parses_real_tracks(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.legacy, "run_mediainfo_json", return_value=_fake_mediainfo_json()),
    ):
        result = svc.read_media_info_summary(str(f))
    assert result["video_codec"] == "HEVC"
    # legacy.audio_codec() maps the raw "E-AC-3" format string to its
    # commercial name (Dolby Digital Plus), not passed through verbatim.
    assert result["audio_codec"] == "DD+"
    assert result["audio_languages"] == "ING / ESP"
    assert result["subtitle_languages"] == "ING / ESP"


def test_read_media_info_summary_never_prompts_on_unknown_language(tmp_path):
    """The legacy CLI's map_audio_language() calls prompt()/input() on an
    unmapped language — unacceptable in a web request handler. This must
    fall back to a 3-letter code instead of blocking."""
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    info = {"media": {"track": [
        {"@type": "Video", "Format": "AVC"},
        {"@type": "Audio", "Format": "AAC", "Language": "xx-unknown"},
    ]}}
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.legacy, "run_mediainfo_json", return_value=info),
        patch("builtins.input", side_effect=AssertionError("must never prompt")),
    ):
        result = svc.read_media_info_summary(str(f))
    assert result["audio_languages"] == "XX-"


def test_read_media_info_summary_handles_subprocess_failure(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.legacy, "run_mediainfo_json", side_effect=RuntimeError("mediainfo falló")),
    ):
        assert svc.read_media_info_summary(str(f)) is None


# ---------------------------------------------------------------------------
# build_mediainfo_report — on-demand MediaInfo vs eMuwarez comparison table
# ---------------------------------------------------------------------------

def test_build_mediainfo_report_empty_path():
    r = svc.build_mediainfo_report("")
    assert r["available"] is False and r["rows"] == []


def test_build_mediainfo_report_binary_missing(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with patch.object(svc, "mediainfo_available", return_value=False):
        r = svc.build_mediainfo_report(str(f))
    assert r["available"] is False
    assert "mediainfo" in r["message"].lower()


def test_build_mediainfo_report_missing_file():
    with patch.object(svc, "mediainfo_available", return_value=True):
        r = svc.build_mediainfo_report("/nonexistent/movie.mkv")
    assert r["available"] is False and r["rows"] == []


def test_build_mediainfo_report_handles_subprocess_failure(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.legacy, "run_mediainfo_json", side_effect=RuntimeError("boom")),
    ):
        r = svc.build_mediainfo_report(str(f))
    assert r["available"] is False and "boom" in r["message"]


def test_build_mediainfo_report_rows_and_emu_mapping(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.legacy, "run_mediainfo_json", return_value=_fake_mediainfo_json()),
    ):
        r = svc.build_mediainfo_report(str(f))
    assert r["available"] is True
    by_field = {row["field"]: row for row in r["rows"]}
    # Two Spanish+English E-AC-3 tracks → DUAL DD+ in the eMuwarez segment.
    assert r["audio_summary"] and r["audio_summary"].startswith("DUAL DD+")
    # Each row exposes both the raw MediaInfo value and the eMuwarez value.
    assert "Subtítulos" in by_field
    assert by_field["Subtítulos"]["emu"] == "SUBS"


def test_build_mediainfo_report_codec_row_shows_encoder_fingerprint_alongside_format(tmp_path):
    """Regression: the raw MediaInfo column used to show bare "AVC" next to
    an eMuwarez "x264" value with no visible connection between the two —
    confusing, since both are true at once (generic Format vs. the specific
    hand encoder that produced it). Real case: One Piece S23E01, Format=AVC,
    Writing_library="x264 core 164"."""
    f = tmp_path / "One Piece - S23E01 [1080p].mkv"
    f.write_text("fake")
    info = {"media": {"track": [
        {"@type": "General"},
        {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080",
         "Writing_library": "x264 core 164",
         "Encoded_Library_Settings": "cabac=1 / ref=4 / rc=2pass / bitrate=8000"},
        {"@type": "Audio", "Format": "AAC", "Language": "ja"},
    ]}}
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.legacy, "run_mediainfo_json", return_value=info),
    ):
        r = svc.build_mediainfo_report(str(f))
    by_field = {row["field"]: row for row in r["rows"]}
    assert by_field["Códec de vídeo"]["mediainfo"] == "AVC (x264)"
    assert by_field["Códec de vídeo"]["emu"] == "x264"


# ---------------------------------------------------------------------------
# One entry per real audio track, in track order
# ---------------------------------------------------------------------------

def _mediainfo_with_audio(tracks: list[dict]):
    return {"media": {"track": [
        {"@type": "General"},
        {"@type": "Video", "Format": "HEVC", "Width": "1920", "Height": "1080"},
        *[{"@type": "Audio", **t} for t in tracks],
        {"@type": "Text", "Language": "spa"},
    ]}}


def _summary(tmp_path, tracks):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.legacy, "run_mediainfo_json", return_value=_mediainfo_with_audio(tracks)),
    ):
        return svc.build_mediainfo_report(str(f))["audio_summary"]


def test_repeated_language_with_different_codecs_keeps_every_track(tmp_path):
    """The regression: languages were de-duplicated (the DUAL/MULTI rules need
    distinct ones) but codecs/channels were not, and the three lists were then
    zipped together. Every entry after a repeated language landed on the wrong
    codec and the last track vanished: this file came out as
    "JAP TrueHD 5.1 CAT DD 5.1 ESP DD+ 2.0" — Catalan wearing the second
    Japanese track's codec, and the fourth track gone."""
    summary = _summary(tmp_path, [
        # A real TrueHD track: MediaInfo reports the raw format as "MLP FBA"
        # and the commercial name separately, which is what audio_codec reads.
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "ja", "Channels": "6"},
        {"Format": "AC-3", "Language": "ja", "Channels": "6"},
        {"Format": "E-AC-3", "Language": "ca", "Channels": "2"},
        {"Format": "E-AC-3", "Language": "es", "Channels": "2"},
    ])
    # Two Japanese tracks on different codecs stay apart; Catalan and Spanish
    # share a codec AND channel count, so they are ONE entry.
    assert summary == "JAP TrueHD 5.1 JAP DD 5.1 ESP-CAT DD+ 2.0"


def test_languages_sharing_a_codec_join_with_a_hyphen(tmp_path):
    """Straight out of the guide: "…BDRemux AVC ESP-CAT TrueHD 5.1…". Listing
    them separately would claim two audio tracks where the release states one
    shared one."""
    summary = _summary(tmp_path, [
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "ca", "Channels": "6"},
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "es", "Channels": "6"},
    ])
    # Spanish leads regardless of track order, same as _split_languages sorts it.
    assert summary == "ESP-CAT TrueHD 5.1"


def test_same_language_different_channels_stays_apart(tmp_path):
    """Same codec but a different channel layout is a different entry: the
    grouping keys on both."""
    summary = _summary(tmp_path, [
        {"Format": "AC-3", "Language": "es", "Channels": "6"},
        {"Format": "AC-3", "Language": "es", "Channels": "2"},
    ])
    assert summary == "ESP DD 5.1 ESP DD 2.0"


def test_every_track_keeps_its_own_codec(tmp_path):
    summary = _summary(tmp_path, [
        {"Format": "DTS", "Language": "es", "Channels": "6"},
        {"Format": "AC-3", "Language": "en", "Channels": "2"},
    ])
    assert summary == "ESP DTS 5.1 ING DD 2.0"


def test_identical_tracks_are_not_listed_twice(tmp_path):
    """Same language AND codec AND channels twice adds nothing to the name."""
    summary = _summary(tmp_path, [
        {"Format": "AC-3", "Language": "es", "Channels": "6"},
        {"Format": "AC-3", "Language": "es", "Channels": "6"},
    ])
    assert summary == "ESP DD 5.1"


def test_dual_applies_per_entry_not_to_the_whole_file(tmp_path):
    """DUAL describes ONE audio entry, so a file whose tracks don't all share a
    codec still gets it on the entry that does."""
    summary = _summary(tmp_path, [
        {"Format": "DTS", "Language": "ja", "Channels": "6"},
        {"Format": "E-AC-3", "Language": "es", "Channels": "2"},
        {"Format": "E-AC-3", "Language": "en", "Channels": "2"},
    ])
    assert summary == "JAP DTS 5.1 DUAL DD+ 2.0"


def test_dual_shortcut_still_applies(tmp_path):
    """Spanish + English on the same codec/channels stays "DUAL", it doesn't
    become two spelled-out entries."""
    summary = _summary(tmp_path, [
        {"Format": "E-AC-3", "Language": "es", "Channels": "6"},
        {"Format": "E-AC-3", "Language": "en", "Channels": "6"},
    ])
    assert summary == "DUAL DD+ 5.1"


def test_multi_shortcut_still_applies(tmp_path):
    summary = _summary(tmp_path, [
        {"Format": "AC-3", "Language": lang, "Channels": "6"}
        for lang in ("es", "en", "fr", "de")
    ])
    assert summary == "MULTI DD 5.1"
