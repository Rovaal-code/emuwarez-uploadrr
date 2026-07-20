"""Tests for trailer_check service — post-upload trailer verification."""
from __future__ import annotations

from emuwarez_uploadrr.services.trailer_check import (
    check_trailer_for_job,
    extract_youtube_trailer_url,
    find_emu_description_file,
)


def _make_desc(tmp_path, folder_name: str, text: str):
    folder = tmp_path / "tmp" / folder_name
    folder.mkdir(parents=True)
    desc = folder / "[EMU]DESCRIPTION.txt"
    desc.write_text(text, encoding="utf-8")
    return desc


def test_find_emu_description_file_exact_candidate_match(tmp_path):
    _make_desc(tmp_path, "Movie.2024.1080p.WEB-DL-EMUWAREZ", "[center][youtube]abc123[/youtube][/center]")
    found = find_emu_description_file(str(tmp_path), ["Movie.2024.1080p.WEB-DL-EMUWAREZ"])
    assert found is not None
    assert found.parent.name == "Movie.2024.1080p.WEB-DL-EMUWAREZ"


def test_find_emu_description_file_falls_back_to_most_recent(tmp_path):
    # Neither candidate name matches any real folder — falls back to
    # scanning tmp/ for the most recently modified [EMU]DESCRIPTION.txt.
    _make_desc(tmp_path, "SomeOtherFolder", "no trailer here")
    found = find_emu_description_file(str(tmp_path), ["Nonexistent.Name"])
    assert found is not None
    assert found.parent.name == "SomeOtherFolder"


def test_find_emu_description_file_missing_tmp_dir(tmp_path):
    assert find_emu_description_file(str(tmp_path / "does-not-exist"), ["X"]) is None


def test_find_emu_description_file_no_uploadrr_path():
    assert find_emu_description_file("", ["X"]) is None
    assert find_emu_description_file(None, ["X"]) is None


def test_extract_youtube_trailer_url_found(tmp_path):
    desc = _make_desc(tmp_path, "X", "[center][youtube]dQw4w9WgXcQ[/youtube][/center]")
    assert extract_youtube_trailer_url(desc) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_extract_youtube_trailer_url_not_found(tmp_path):
    desc = _make_desc(tmp_path, "X", "[center][img]https://example.com/logo.png[/img][/center]")
    assert extract_youtube_trailer_url(desc) is None


def test_check_trailer_for_job_found(tmp_path):
    _make_desc(tmp_path, "Movie.2024-EMUWAREZ", "[youtube]abc123[/youtube]")
    result = check_trailer_for_job(str(tmp_path), ["Movie.2024-EMUWAREZ"])
    assert result == {"checked": True, "found": True, "url": "https://www.youtube.com/watch?v=abc123"}


def test_check_trailer_for_job_checked_but_not_found(tmp_path):
    _make_desc(tmp_path, "Movie.2024-EMUWAREZ", "sin trailer aqui")
    result = check_trailer_for_job(str(tmp_path), ["Movie.2024-EMUWAREZ"])
    assert result == {"checked": True, "found": False, "url": None}


def test_check_trailer_for_job_inconclusive_when_file_missing(tmp_path):
    result = check_trailer_for_job(str(tmp_path), ["Nothing.Here"])
    assert result == {"checked": False, "found": False, "url": None}
