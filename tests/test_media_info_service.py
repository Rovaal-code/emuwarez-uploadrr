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
