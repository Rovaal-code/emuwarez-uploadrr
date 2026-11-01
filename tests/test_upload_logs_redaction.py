"""Tests for secrets redaction in upload execution logs."""
from __future__ import annotations

from emuwarez_uploadrr.services.upload_execution import redact_secrets


def test_redact_api_token_param():
    result = redact_secrets("api_token=abc123xyz", [])
    assert "abc123xyz" not in result
    assert "***REDACTED***" in result


def test_redact_api_key_param():
    result = redact_secrets("api_key=xyz789secret", [])
    assert "xyz789secret" not in result
    assert "***REDACTED***" in result


def test_no_change_without_secrets():
    text = "This is a normal log line with no secrets."
    result = redact_secrets(text, [])
    assert result == text


def test_known_secret_value_redacted():
    secret = "supersecretapikey1234"
    text = f"Connecting to tracker with {secret} as auth"
    result = redact_secrets(text, [secret])
    assert secret not in result
    assert "***REDACTED***" in result


def test_multiple_secrets_in_same_string():
    s1 = "emu_api_key_value"
    s2 = "tmdb_key_value"
    text = f"emu={s1} tmdb={s2}"
    result = redact_secrets(text, [s1, s2])
    assert s1 not in result
    assert s2 not in result
    assert result.count("***REDACTED***") == 2


def test_empty_secrets_list_no_change():
    text = "log line: path=/mnt/storage/movie.mkv"
    result = redact_secrets(text, [])
    assert result == text


def test_short_secret_not_redacted():
    # Secrets shorter than 4 chars are skipped to avoid over-matching
    text = "value=abc"
    result = redact_secrets(text, ["abc"])
    # short secret (3 chars) is not redacted
    assert "abc" in result


def test_api_token_url_param():
    text = "GET /api/requests?api_token=topsecrettoken123"
    result = redact_secrets(text, [])
    assert "topsecrettoken123" not in result
    assert "***REDACTED***" in result


def test_token_equals_pattern():
    text = "token=myverylongsecrettoken"
    result = redact_secrets(text, [])
    assert "myverylongsecrettoken" not in result
    assert "***REDACTED***" in result


def test_redact_preserves_rest_of_string():
    text = "Uploading file.mkv with api_key=secret123 to EMU tracker"
    result = redact_secrets(text, [])
    assert "Uploading file.mkv with" in result
    assert "to EMU tracker" in result
    assert "secret123" not in result
