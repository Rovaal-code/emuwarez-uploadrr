"""Unit tests for emuwarez_uploadrr/integrations/seerr.py (Phase 11B).

All HTTP calls are mocked — no real Overseerr/Jellyseerr traffic.
"""
from __future__ import annotations

from unittest.mock import patch

from emuwarez_uploadrr.integrations.arr_base import ArrAuthError, ArrConnectionError, ArrClientError
from emuwarez_uploadrr.integrations.seerr import seerr_test_connection


def _instance(url="http://seerr.local:5055", api_key="key123"):
    return {"url": url, "api_key": api_key}


def test_success_reads_username_and_version():
    def fake_arr_request(method, url, api_key):
        if url.endswith("/auth/me"):
            return {"displayName": "Alvaro", "id": 1}
        if url.endswith("/status"):
            return {"version": "1.33.2"}
        raise AssertionError(f"unexpected url {url}")

    with patch("emuwarez_uploadrr.integrations.seerr.arr_request", side_effect=fake_arr_request):
        result = seerr_test_connection(_instance())

    assert result["ok"] is True
    assert result["username"] == "Alvaro"
    assert result["version"] == "1.33.2"


def test_success_falls_back_to_username_or_email_fields():
    def fake_arr_request(method, url, api_key):
        if url.endswith("/auth/me"):
            return {"username": "alvaro87"}
        raise ArrClientError("status unavailable")

    with patch("emuwarez_uploadrr.integrations.seerr.arr_request", side_effect=fake_arr_request):
        result = seerr_test_connection(_instance())

    assert result["ok"] is True
    assert result["username"] == "alvaro87"
    assert result["version"] is None  # /status failed but auth/me already confirmed the key


def test_auth_error_invalid_key():
    with patch("emuwarez_uploadrr.integrations.seerr.arr_request", side_effect=ArrAuthError("bad key")):
        result = seerr_test_connection(_instance())
    assert result["ok"] is False
    assert "incorrecta" in result["error"].lower() or "permisos" in result["error"].lower()


def test_connection_error():
    with patch("emuwarez_uploadrr.integrations.seerr.arr_request", side_effect=ArrConnectionError("timeout")):
        result = seerr_test_connection(_instance())
    assert result["ok"] is False
    assert "no se pudo conectar" in result["error"].lower()


def test_never_calls_network_without_mock():
    with patch("emuwarez_uploadrr.integrations.seerr.arr_request") as mock_req:
        mock_req.return_value = {"displayName": "x"}
        seerr_test_connection(_instance())
        assert mock_req.called


def test_api_key_never_in_result():
    secret = "SUPER_SECRET_SEERR_KEY"
    with patch("emuwarez_uploadrr.integrations.seerr.arr_request", side_effect=ArrAuthError("bad key")):
        result = seerr_test_connection(_instance(api_key=secret))
    import json
    assert secret not in json.dumps(result)
