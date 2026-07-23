"""Unit tests for services/source_engine — pure functions, hand-built profile
dicts, no subprocess calls. Fast and hermetic by design; real-tool/pipeline
coverage lives in test_source_engine_realfiles.py.
"""
from __future__ import annotations

import math

from emuwarez_uploadrr.services.source_engine import profile
from emuwarez_uploadrr.services.source_engine.constants import CANDIDATES, certainty_label
from emuwarez_uploadrr.services.source_engine import evidence as ev
from emuwarez_uploadrr.services.source_engine import names, scoring, transcode


# ---------------------------------------------------------------------------
# profile.py
# ---------------------------------------------------------------------------

def test_build_video_prefers_mediainfo_over_ffprobe():
    mi = {"media": {"track": [
        {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080",
         "FrameRate": "23.976", "BitDepth": "8", "Encoded_Library": "x264 - core 165",
         "Encoded_Library_Settings": "crf=18.0 / keyint=250"},
    ]}}
    ff = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720}]}
    video = profile.build_video(mi, ff)
    assert video["codec"] == "AVC"
    assert video["width"] == 1920 and video["height"] == 1080
    assert video["encoder_settings"] == "crf=18.0 / keyint=250"


def test_build_video_falls_back_to_ffprobe_when_no_mediainfo():
    ff = {"streams": [{"codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160,
                        "avg_frame_rate": "24000/1001"}]}
    video = profile.build_video(None, ff)
    assert video["codec"] == "hevc"
    assert video["width"] == 3840
    assert abs(video["fps"] - 23.976) < 0.01


def test_lossless_audio_detected_via_compression_mode():
    mi = {"media": {"track": [
        {"@type": "Audio", "Format": "FLAC", "Compression_Mode": "Lossless"},
        {"@type": "Audio", "Format": "AC-3", "Compression_Mode": "Lossy"},
    ]}}
    tracks = profile.build_audio_tracks(mi, None, None)
    assert tracks[0]["lossless"] is True
    assert tracks[1]["lossless"] is False


def test_subtitle_kind_classification():
    mi = {"media": {"track": [
        {"@type": "Text", "Format": "PGS"},
        {"@type": "Text", "Format": "UTF-8"},
    ]}}
    subs = profile.build_subtitle_tracks(mi, None, None)
    assert subs[0]["kind"] == "bitmap"


def test_file_info_bitrate_calculation():
    info = profile.build_file_info(size_bytes=100_000_000, duration_s=100.0)
    assert info["total_bitrate_calculated_bps"] == 100_000_000 * 8 / 100.0


def test_file_info_handles_missing_duration():
    info = profile.build_file_info(size_bytes=100, duration_s=None)
    assert info["total_bitrate_calculated_bps"] is None


def test_normalization_bpppf_formula():
    video = {"width": 1920, "height": 1080, "fps": 24.0, "reported_bitrate_bps": 1920 * 1080 * 24 * 0.1}
    file_info = {"total_bitrate_calculated_bps": video["reported_bitrate_bps"]}
    norm = profile.build_normalization(video, file_info, audio_tracks=[])
    assert abs(norm["bits_per_pixel_per_frame"] - 0.1) < 1e-6


def test_normalization_none_when_missing_dimensions():
    norm = profile.build_normalization({"width": None, "height": None, "fps": None}, {}, [])
    assert norm["bits_per_pixel_per_frame"] is None


# ---------------------------------------------------------------------------
# names.py
# ---------------------------------------------------------------------------

def test_track_name_tags_commentary_multilanguage():
    assert names.tag_track_name("Director's Commentary")["commentary"] is True
    assert names.tag_track_name("Comentario del director")["commentary"] is True
    assert names.tag_track_name("Commentaire du réalisateur")["commentary"] is True
    assert names.tag_track_name("Español 5.1")["commentary"] is False


def test_track_name_tags_forced_and_sdh():
    assert names.tag_track_name("Forced")["forced"] is True
    assert names.tag_track_name("Forzados")["forced"] is True
    assert names.tag_track_name("English SDH")["hearing_impaired"] is True


def test_track_name_none_is_all_false():
    tags = names.tag_track_name(None)
    assert all(v is False for v in tags.values())


# ---------------------------------------------------------------------------
# transcode.py
# ---------------------------------------------------------------------------

def test_transcode_signals_detect_x264_fingerprint():
    video = {"encoder": "x264 - core 165", "encoder_settings": "crf=18.0 / pass=2 / keyint=250"}
    sig = transcode.analyze_transcode_signals(video)
    assert sig.has_encoder_fingerprint is True
    assert sig.crf == 18.0
    assert sig.two_pass is True
    assert sig.keyint == 250
    # Deliberately NOT > 0.8: a confirmed genuine Netflix WEB-DL reporting
    # rc=2pass proved two-pass isn't a reliable re-encode tell either (see
    # transcode.py's docstring) — it gets the same modest weight as a plain
    # single-pass fingerprint now, not extra confidence.
    assert 0.3 < sig.video_transcode_probability < 0.6


def test_transcode_signals_detect_real_x264_twopass_format():
    """x264 reports its own rate-control mode as "rc=2pass"/"rc=1pass" — NOT
    "pass=2". The original regex only matched the latter (never seen in a
    real x264 dump) and so never actually detected two-pass at all."""
    video = {"encoder": "x264 - core 164", "encoder_settings": "rc=2pass / bitrate=8000 / keyint=96"}
    sig = transcode.analyze_transcode_signals(video)
    assert sig.two_pass is True

    video_1pass = {"encoder": "x264", "encoder_settings": "rc=1pass / crf=18.0"}
    sig_1pass = transcode.analyze_transcode_signals(video_1pass)
    assert sig_1pass.two_pass is False


def test_transcode_signals_no_fingerprint_favors_untouched():
    video = {"encoder": "", "encoder_settings": ""}
    sig = transcode.analyze_transcode_signals(video)
    assert sig.has_encoder_fingerprint is False
    assert sig.video_transcode_probability < 0.3
    assert sig.video_stream_untouched_probability > 0.6


def test_transcode_never_reaches_100_percent_certainty():
    video = {"encoder": "x264", "encoder_settings": "crf=16.0"}
    sig = transcode.analyze_transcode_signals(video)
    assert sig.video_stream_untouched_probability >= 0.05
    video2 = {}
    sig2 = transcode.analyze_transcode_signals(video2)
    assert sig2.video_transcode_probability > 0.0


def test_resize_evidence_ignores_standard_macroblock_padding():
    video = {"coded_width": 1920, "coded_height": 1088, "width": 1920, "height": 1080}
    sig = transcode.analyze_transcode_signals(video)
    assert sig.resize_evidence is False


def test_resize_evidence_flags_real_resize():
    video = {"coded_width": 1920, "coded_height": 1080, "width": 1280, "height": 720}
    sig = transcode.analyze_transcode_signals(video)
    assert sig.resize_evidence is True


# ---------------------------------------------------------------------------
# evidence.py
# ---------------------------------------------------------------------------

def _base_profile(**overrides) -> dict:
    base = {
        "container": {"format": "Matroska", "is_fragmented": False, "chapter_count": 0, "attachment_count": 0},
        "video": {"width": 1920, "height": 1080, "fps": 24.0, "scan_type": "Progressive",
                   "hdr": False, "dolby_vision": False, "codec": "AVC",
                   "encoder_settings": None, "coded_width": 1920, "coded_height": 1080},
        "audio_tracks": [],
        "subtitle_tracks": [],
        "topology": {"chapter_count": 0, "pgs_count": 0, "vobsub_count": 0, "text_subtitle_count": 0},
        "normalization": {"bits_per_pixel_per_frame": None, "video_share_of_file": None},
    }
    base.update(overrides)
    return base


def test_structural_single_file_always_penalizes_fbd_fdvd():
    result = ev.structural_single_file(_base_profile())
    assert len(result) == 1
    contrib = result[0].contributions
    assert contrib["FBD"] < -50 and contrib["FDVD"] < -50
    for other in CANDIDATES:
        if other not in ("FBD", "FDVD"):
            assert contrib[other] == 0.0


def test_bitrate_normalization_favors_bdremux_at_high_bpppf():
    profile_dict = _base_profile(normalization={"bits_per_pixel_per_frame": 0.30, "video_share_of_file": 0.9})
    result = ev.bitrate_normalization_signal(profile_dict)
    contrib = result[0].contributions
    assert contrib["BDRemux"] > contrib["SD"]
    assert contrib["BDRemux"] > contrib["HDTV"]


def test_bitrate_normalization_favors_webrip_over_bdremux_at_low_bpppf():
    profile_dict = _base_profile(normalization={"bits_per_pixel_per_frame": 0.06, "video_share_of_file": 0.8})
    result = ev.bitrate_normalization_signal(profile_dict)
    contrib = result[0].contributions
    assert contrib["WEBRIP"] > contrib["BDRemux"]


def test_bitrate_normalization_never_favors_sd():
    """SD is deliberately absent from _BPPF_RANGES — MPEG-2 (DVD-era codec)
    is inefficient enough that a genuine DVD rip commonly lands at a
    moderate-to-high bpppf despite its low absolute Mbps once normalized for
    resolution/fps, so a low-bpppf reading is NOT evidence of SD. SD
    detection is left to resolution_signal/video_codec_signal instead."""
    for bpppf in (0.02, 0.1, 0.3, 0.5):
        profile_dict = _base_profile(normalization={"bits_per_pixel_per_frame": bpppf, "video_share_of_file": 0.8})
        result = ev.bitrate_normalization_signal(profile_dict)
        assert result[0].contributions["SD"] == 0.0


def test_no_evidence_when_bpppf_missing():
    assert ev.bitrate_normalization_signal(_base_profile()) == []


def test_resolution_signal_penalizes_disc_tiers_at_sd():
    result = ev.resolution_signal(_base_profile(video={"width": 720, "height": 480}))
    contrib = result[0].contributions
    assert contrib["SD"] > 0
    assert contrib["BDRemux"] < 0
    assert contrib["MHD"] < 0


def test_pgs_alone_does_not_dominate_bdremux():
    """Spec section 27: PGS alone must not decide BDRemux — its contribution
    has to be small enough that other evidence can easily outweigh it."""
    profile_dict = _base_profile(
        subtitle_tracks=[{"kind": "bitmap", "codec": "PGS"}],
        topology={"chapter_count": 0, "pgs_count": 1, "vobsub_count": 0, "text_subtitle_count": 0},
    )
    result = ev.subtitle_profile_signal(profile_dict)
    contrib = result[0].contributions["BDRemux"]
    # A single medium-strength, moderate-reliability signal should stay well
    # under the weight of a strong/very_strong one (e.g. structural, ~90+).
    assert 0 < contrib < 15


def test_video_codec_mpeg2_favors_sd_hdtv():
    result = ev.video_codec_signal(_base_profile(video={"codec": "MPEG-2 Video"}))
    contrib = result[0].contributions
    assert contrib["SD"] > 0 and contrib["HDTV"] > 0
    assert contrib["BDRemux"] < 0


def test_bluray_compat_flag_detected():
    profile_dict = _base_profile(video={"encoder_settings": "cabac=1 / bluray_compat=1 / crf=18.0"})
    result = ev.bluray_compat_flag(profile_dict)
    assert len(result) == 1
    assert result[0].contributions["BluRay"] > 0


def test_bluray_compat_flag_absent_when_zero():
    profile_dict = _base_profile(video={"encoder_settings": "cabac=1 / bluray_compat=0"})
    assert ev.bluray_compat_flag(profile_dict) == []


# ---------------------------------------------------------------------------
# scoring.py — the mandatory invariants (spec sections 17-19)
# ---------------------------------------------------------------------------

def _mk_evidence(**per_candidate: float) -> ev.Evidence:
    contrib = {c: 0.0 for c in CANDIDATES}
    contrib.update(per_candidate)
    return ev.Evidence(feature="test", value=None, contributions=contrib,
                        strength="strong", reliability=1.0, explanation="test evidence")


def test_scoring_always_returns_all_nine_candidates():
    result = scoring.score_candidates([_mk_evidence(BluRay=10)])
    assert len(result.ranking) == len(CANDIDATES)
    assert {c.label for c in result.ranking} == set(CANDIDATES)


def test_scoring_normalized_scores_sum_to_one():
    result = scoring.score_candidates([_mk_evidence(BluRay=10, HDTV=-5)])
    total = sum(c.normalized_score for c in result.ranking)
    assert abs(total - 1.0) < 1e-6


def test_scoring_never_returns_unknown_even_with_no_evidence():
    result = scoring.score_candidates([])
    assert result.winner.label in CANDIDATES
    assert result.winner.label != "unknown"


def test_scoring_winner_has_highest_raw_score():
    result = scoring.score_candidates([_mk_evidence(BDRemux=50, SD=-10)])
    assert result.winner.label == "BDRemux"
    assert result.winner.raw_score == max(c.raw_score for c in result.ranking)


def test_scoring_margin_shrinks_as_scores_converge():
    close = scoring.score_candidates([_mk_evidence(BluRay=10.1, MHD=10.0)])
    far = scoring.score_candidates([_mk_evidence(BluRay=50.0, MHD=-10.0)])
    assert close.margin_pp < far.margin_pp


def test_certainty_label_thresholds():
    assert certainty_label(50) == "alto"
    assert certainty_label(20) == "medio"
    assert certainty_label(5) == "bajo"


def test_scoring_deterministic():
    evidence_list = [_mk_evidence(BluRay=12, HDTV=-3), _mk_evidence(MHD=4)]
    r1 = scoring.score_candidates(evidence_list)
    r2 = scoring.score_candidates(evidence_list)
    assert [c.raw_score for c in r1.ranking] == [c.raw_score for c in r2.ranking]
    assert [c.label for c in r1.ranking] == [c.label for c in r2.ranking]


def test_explanation_mentions_winner_and_runner_up():
    result = scoring.score_candidates([_mk_evidence(WEBRIP=20, HDTV=15)])
    explanation = scoring.build_explanation([_mk_evidence(WEBRIP=20, HDTV=15)], result)
    assert result.winner.label in explanation["winner"]
    assert "winner_vs_runner_up" in explanation


def test_evidence_strength_within_bounds():
    result = scoring.score_candidates([_mk_evidence(BluRay=5) for _ in range(20)])
    assert 0.0 <= result.evidence_strength <= 1.0
