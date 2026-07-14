"""Source detection: name first, then a MediaInfo heuristic as a fallback."""
from __future__ import annotations

from pathlib import Path

from emuwarez_uploadrr.legacy import (
    _detect_source_by_name, detect_source, heuristic_source, detect_source_smart,
)


def test_name_wins_when_present():
    assert _detect_source_by_name(Path("Peli 2020 1080p WEB-DL x264.mkv")) == "WEB-DL"
    assert _detect_source_by_name(Path("Peli 2020 1080p BluRay x264.mkv")) == "BluRay"
    assert _detect_source_by_name(Path("Peli 2020 1080p x264.mkv")) is None


def test_detect_source_defaults_bluray():
    assert detect_source(Path("Peli 2020 1080p x264.mkv")) == "BluRay"


def test_heuristic_lossless_is_disc():
    assert heuristic_source(["DTS-HD MA", "DD"], size_gb=30, resolution="1080p") == "BDRemux"
    assert heuristic_source(["TrueHD"], size_gb=12, resolution="1080p") == "BluRay"
    assert heuristic_source(["PCM"], size_gb=50, resolution="2160p") == "BDRemux"


def test_heuristic_ddplus_is_webdl():
    assert heuristic_source(["DD+", "DD+"], size_gb=5, resolution="1080p") == "WEB-DL"
    assert heuristic_source(["E-AC-3"], size_gb=4, resolution="1080p") == "WEB-DL"


def test_heuristic_ambiguous_returns_none():
    assert heuristic_source(["DD", "AAC"], size_gb=4, resolution="1080p") is None


def test_smart_flags_guess(tmp_path):
    # Name has a keyword → not a guess.
    named = tmp_path / "Peli 2020 1080p WEB-DL x264.mkv"
    named.write_bytes(b"x")
    assert detect_source_smart(named, ["DD+"], "1080p") == ("WEB-DL", False)

    # No keyword + DD+ audio → guessed WEB-DL.
    plain = tmp_path / "Peli 2020 1080p x264.mkv"
    plain.write_bytes(b"x")
    src, guess = detect_source_smart(plain, ["DD+"], "1080p")
    assert src == "WEB-DL" and guess is True

    # No keyword + ambiguous audio → last-resort BluRay, still a guess.
    src2, guess2 = detect_source_smart(plain, ["AAC"], "1080p")
    assert src2 == "BluRay" and guess2 is True
