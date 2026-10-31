"""Source detection: name first, then a MediaInfo heuristic as a fallback."""
from __future__ import annotations

from pathlib import Path

from emuwarez_uploadrr.services.media_probe import (
    _detect_source_by_name, heuristic_source,
    estimate_source_from_bitrate, detect_video_codec,
)


def test_name_wins_when_present():
    assert _detect_source_by_name(Path("Peli 2020 1080p WEB-DL x264.mkv")) == "WEB-DL"
    assert _detect_source_by_name(Path("Peli 2020 1080p BluRay x264.mkv")) == "BluRay"
    assert _detect_source_by_name(Path("Peli 2020 1080p x264.mkv")) is None


def test_heuristic_lossless_is_disc():
    assert heuristic_source(["DTS-HD MA", "DD"], size_gb=30, resolution="1080p") == "BDRemux"
    assert heuristic_source(["TrueHD"], size_gb=12, resolution="1080p") == "BluRay"
    assert heuristic_source(["PCM"], size_gb=50, resolution="2160p") == "BDRemux"


def test_heuristic_ddplus_is_webdl():
    assert heuristic_source(["DD+", "DD+"], size_gb=5, resolution="1080p") == "WEB-DL"
    assert heuristic_source(["E-AC-3"], size_gb=4, resolution="1080p") == "WEB-DL"


def test_detect_video_codec_ignores_filename_uses_real_encoder_fields():
    # Regression: the filename used to be checked alongside the real
    # WritingLibrary/Encoded_Library MediaInfo fields, in a single combined
    # string — a file whose (possibly already-renamed) name merely contains
    # the substring "x264" kept reporting codec=x264 forever, even once
    # MediaInfo's own Format/encoder fields showed plain, untouched AVC with
    # no encoder fingerprint at all.
    video_plain_avc = {"Format": "AVC"}
    path_with_x264_in_name = Path("Movie 2017 1080p BDRemux x264-GRP.mkv")
    assert detect_video_codec(video_plain_avc, path_with_x264_in_name) == "AVC"

    video_real_x264 = {"Format": "AVC", "Encoded_Library": "x264 - core 165"}
    assert detect_video_codec(video_real_x264, Path("Movie 2017 1080p BluRay.mkv")) == "x264"


def test_detect_video_codec_prefers_hevc_over_generic_format_string():
    video = {"Format": "HEVC", "Encoded_Library": "x265 - 3.4"}
    assert detect_video_codec(video, Path("Movie.mkv")) == "x265"


def test_detect_video_codec_reads_writing_library_key_with_underscore():
    # Regression: this used to look up "WritingLibrary" (no underscore),
    # which never matches MediaInfo's real JSON key ("Writing_library") —
    # detection silently depended on Encoded_Library alone. Real case: One
    # Piece S23E01 reports the encoder only under Writing_library.
    video = {"Format": "AVC", "Writing_library": "x264 core 164"}
    assert detect_video_codec(video, Path("One Piece - S23E01 [1080p].mkv")) == "x264"


def test_heuristic_ambiguous_returns_none():
    assert heuristic_source(["DD", "AAC"], size_gb=4, resolution="1080p") is None


def test_bitrate_reencoded_lossy_never_returns_webdl():
    # WEB-DL means "untouched platform rip" by definition — a re-encoded
    # stream (x264 fingerprint present) can never genuinely be one, no
    # matter the bitrate.
    reencoded_video = {"Encoded_Library_Settings": "cabac=1 ref=3 ..."}
    # ~16.3 Mbps at 1080p: a real case (Geostorm, AC3+DTS audio, 12.93 GB /
    # ~109 min) that a naive "reencoded + above the WEB-DL floor" check used
    # to mislabel WEB-DL, even though that bitrate sits solidly in BluRay
    # tier (>= the 9 Mbps threshold) — regressed to MHD, the disc-encode tier.
    size_bytes = int(12.93 * 1024 ** 3)
    duration_s = 109 * 60
    assert estimate_source_from_bitrate(
        size_bytes, duration_s, ["AC-3"], "1080p", video=reencoded_video,
    ) == "MHD"

    # Same re-encode fingerprint, but mid bitrate (between the WEB-DL floor
    # and the BluRay threshold) → still WEBRip/HDTV by bitrate, same as before.
    mid_size_bytes = int(6.0 * duration_s * 1_000_000 / 8)  # ~6 Mbps
    assert estimate_source_from_bitrate(
        mid_size_bytes, duration_s, ["AC-3"], "1080p", video=reencoded_video,
    ) == "WEBRip"
    very_low_size_bytes = int(0.3 * 1024 ** 3)
    assert estimate_source_from_bitrate(
        very_low_size_bytes, duration_s, ["AC-3"], "1080p", video=reencoded_video,
    ) == "HDTV"

    # NOT re-encoded (no fingerprint) → still confidently WEB-DL regardless
    # of bitrate, unaffected by this fix.
    assert estimate_source_from_bitrate(
        size_bytes, duration_s, ["AC-3"], "1080p", video={},
    ) == "WEB-DL"
