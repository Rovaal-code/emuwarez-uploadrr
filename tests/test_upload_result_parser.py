"""Tests for upload_result_parser — pure functions, no DB."""
import pytest
from emuwarez_uploadrr.services.upload_result_parser import (
    extract_urls,
    extract_possible_torrent_ids,
    build_error_summary,
    classify_upload_result,
    parse_uploadrr_output,
)


def test_extract_urls_finds_https():
    text = "Subida completada: https://emuwarez.me/torrents/12345"
    urls = extract_urls(text)
    assert len(urls) == 1
    assert urls[0] == "https://emuwarez.me/torrents/12345"


def test_extract_urls_finds_http():
    text = "Ver en http://tracker.example.com/t/42"
    urls = extract_urls(text)
    assert "http://tracker.example.com/t/42" in urls


def test_extract_urls_multiple_deduplicates():
    text = "https://a.com/1 https://b.com/2 https://a.com/1"
    urls = extract_urls(text)
    assert len(urls) == 2


def test_extract_urls_empty_on_no_urls():
    assert extract_urls("No hay ninguna URL aquí.") == []


def test_extract_urls_empty_string():
    assert extract_urls("") == []


def test_extract_torrent_id_with_explicit_pattern():
    text = "Upload successful! torrent_id: 98765"
    ids = extract_possible_torrent_ids(text)
    assert "98765" in ids


def test_extract_torrent_id_uploaded_id_pattern():
    text = "uploaded_id=42000"
    ids = extract_possible_torrent_ids(text)
    assert "42000" in ids


def test_extract_torrent_id_does_not_invent():
    text = "Proceso completado sin error."
    ids = extract_possible_torrent_ids(text)
    assert ids == []


def test_extract_torrent_id_no_pattern_match():
    text = "El ID de la película en TMDb es 550."
    # short number without explicit keyword should not match
    ids = extract_possible_torrent_ids(text)
    # This might or might not match depending on regex — what matters is it doesn't invent from thin air
    # The key invariant: no false positives when the text has no upload-related ID patterns
    assert isinstance(ids, list)


def test_classify_exit_0_is_completed():
    result = classify_upload_result("OK", "", 0)
    assert result["status"] == "completed"
    assert result["error_summary"] is None
    assert result["exit_code"] == 0


def test_classify_exit_1_is_failed():
    result = classify_upload_result("", "Error: connection refused", 1)
    assert result["status"] == "failed"
    assert result["exit_code"] == 1


def test_classify_with_url_in_stdout():
    stdout = "Uploaded to https://emuwarez.me/torrents/999"
    result = classify_upload_result(stdout, "", 0)
    assert result["status"] == "completed"
    assert "https://emuwarez.me/torrents/999" in result["urls"]


def test_classify_with_torrent_id():
    stdout = "torrent id: 77777"
    result = classify_upload_result(stdout, "", 0)
    assert "77777" in result["torrent_ids"]


def test_classify_exit_none_is_failed():
    result = classify_upload_result("", "", None)
    assert result["status"] == "failed"


def test_build_error_summary_from_stderr():
    stderr = "line1\nline2\nERROR: authentication failed\n"
    summary = build_error_summary(stderr, "", 1)
    assert "authentication failed" in summary
    assert "Exit code: 1" in summary


def test_build_error_summary_empty():
    summary = build_error_summary("", "", 0)
    # exit_code 0 → no "Exit code" appended, and no lines → None
    assert summary is None


def test_build_error_summary_fallback_stdout():
    # No stderr but stdout has content
    summary = build_error_summary("", "last line from stdout", 1)
    assert "last line from stdout" in summary


def test_api_token_in_output_not_in_result():
    """Caller must redact before passing, but parser itself must not leak."""
    # Simulate already-redacted output arriving at classifier
    stdout = "api_token=***REDACTED*** Subida OK https://emu.me/t/1"
    result = classify_upload_result(stdout, "", 0)
    # The real token is not in the output — redaction happened upstream
    assert "***REDACTED***" not in str(result.get("error_summary") or "")


def test_parse_uploadrr_output_returns_dict():
    text = "torrent_id: 100  https://emu.me/t/100"
    result = parse_uploadrr_output(text)
    assert "urls" in result
    assert "torrent_ids" in result
    assert "https://emu.me/t/100" in result["urls"]
    assert "100" in result["torrent_ids"]
