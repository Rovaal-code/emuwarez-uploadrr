"""Unit tests for emuwarez_uploadrr/services/integration_tests.py (Phase 10C).

All HTTP calls are mocked — no real internet traffic.
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from emuwarez_uploadrr.services.integration_tests import (
    test_arr_connection as svc_test_arr,
    test_emuwarez_connection as svc_test_emu,
    test_tmdb_connection as svc_test_tmdb,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status: int = 200) -> MagicMock:
    m = MagicMock()
    m.status = status
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url="http://x", code=code, msg="err", hdrs=None, fp=None)  # type: ignore[arg-type]


def _url_error(reason: str) -> urllib.error.URLError:
    return urllib.error.URLError(reason=reason)


def _timeout_url_error() -> urllib.error.URLError:
    exc = urllib.error.URLError(reason=socket.timeout("timed out"))
    return exc


# ---------------------------------------------------------------------------
# svc_test_tmdb
# ---------------------------------------------------------------------------

class TestTmdbConnection:
    def test_not_configured_no_key(self):
        result = svc_test_tmdb(api_key=None)
        assert result["ok"] is False
        assert result["status"] == "not_configured"
        assert result["service"] == "tmdb"

    def test_not_configured_empty_key(self):
        result = svc_test_tmdb(api_key="   ")
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    @patch("urllib.request.urlopen")
    def test_success(self, mock_open):
        mock_open.return_value = _mock_response(200)
        result = svc_test_tmdb(api_key="validkey123")
        assert result["ok"] is True
        assert result["status"] == "connected"
        assert result["service"] == "tmdb"

    @patch("urllib.request.urlopen")
    def test_invalid_key_401(self, mock_open):
        mock_open.side_effect = _http_error(401)
        result = svc_test_tmdb(api_key="badkey")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    @patch("urllib.request.urlopen")
    def test_invalid_key_403(self, mock_open):
        mock_open.side_effect = _http_error(403)
        result = svc_test_tmdb(api_key="badkey")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    @patch("urllib.request.urlopen")
    def test_connection_error_other_http(self, mock_open):
        mock_open.side_effect = _http_error(500)
        result = svc_test_tmdb(api_key="anykey")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    @patch("urllib.request.urlopen")
    def test_timeout(self, mock_open):
        mock_open.side_effect = _timeout_url_error()
        result = svc_test_tmdb(api_key="anykey")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    @patch("urllib.request.urlopen")
    def test_url_error_network(self, mock_open):
        mock_open.side_effect = _url_error("Name or service not known")
        result = svc_test_tmdb(api_key="anykey")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_reads_key_from_db_when_none(self, tmp_path):
        """api_key=None → reads from DB (settings key 'tmdb.api_key')."""
        from emuwarez_uploadrr.database import connect, init_db
        conn = connect(tmp_path / "test.db")
        init_db(conn)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('tmdb.api_key', '')")
        conn.commit()
        result = svc_test_tmdb(api_key=None, conn=conn)
        assert result["status"] == "not_configured"

    def test_full_key_never_in_response(self):
        """Full API key must not appear in the result dict."""
        import json
        secret = "supersecret_tmdb_key_99999"
        result = svc_test_tmdb(api_key=secret)
        serialised = json.dumps(result)
        assert secret not in serialised


# ---------------------------------------------------------------------------
# svc_test_emu
# ---------------------------------------------------------------------------

class TestEmuwarezConnection:
    def test_not_configured_no_key(self):
        result = svc_test_emu(api_key=None)
        assert result["ok"] is False
        assert result["status"] == "not_configured"
        assert result["service"] == "emuwarez"

    def test_invalid_url(self):
        result = svc_test_emu(api_key="key123", base_url="not-a-url")
        assert result["ok"] is False
        assert result["status"] == "invalid_url"

    @patch("urllib.request.urlopen")
    def test_success(self, mock_open):
        mock_open.return_value = _mock_response(200)
        result = svc_test_emu(api_key="key123", base_url="https://emuwarez.com")
        assert result["ok"] is True
        assert result["status"] == "connected"

    @patch("urllib.request.urlopen")
    def test_invalid_key_401(self, mock_open):
        mock_open.side_effect = _http_error(401)
        result = svc_test_emu(api_key="badkey", base_url="https://emuwarez.com")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    @patch("urllib.request.urlopen")
    def test_timeout(self, mock_open):
        mock_open.side_effect = _timeout_url_error()
        result = svc_test_emu(api_key="key", base_url="https://emuwarez.com")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    @patch("urllib.request.urlopen")
    def test_connection_error(self, mock_open):
        mock_open.side_effect = _url_error("Connection refused")
        result = svc_test_emu(api_key="key", base_url="https://emuwarez.com")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_defaults_to_emuwarez_base_url(self):
        """base_url defaults to https://emuwarez.com when not provided."""
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_response(200)
            result = svc_test_emu(api_key="key123")
            assert result["ok"] is True
            called_url = mock_open.call_args[0][0].full_url
            assert "emuwarez.com" in called_url

    def test_full_key_never_in_response(self):
        import json
        secret = "emuwarez_secret_key_00000"
        result = svc_test_emu(api_key=secret, base_url="badurl")
        serialised = json.dumps(result)
        assert secret not in serialised


# ---------------------------------------------------------------------------
# svc_test_arr
# ---------------------------------------------------------------------------

class TestArrConnection:
    def test_invalid_kind(self):
        result = svc_test_arr(kind="jellyfin", base_url="http://x", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "invalid_kind"

    def test_invalid_kind_none(self):
        result = svc_test_arr(kind=None, base_url="http://x", api_key="k")  # type: ignore[arg-type]
        assert result["ok"] is False
        assert result["status"] == "invalid_kind"

    def test_not_configured_missing_url(self):
        result = svc_test_arr(kind="radarr", base_url="", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    def test_not_configured_missing_key(self):
        result = svc_test_arr(kind="sonarr", base_url="http://localhost:8989", api_key="  ")
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_success_radarr(self, mock_req):
        mock_req.return_value = {"version": "5.3.6", "appName": "Radarr"}
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="abc123")
        assert result["ok"] is True
        assert result["status"] == "connected"
        assert result["service"] == "radarr"
        assert result["details"]["version"] == "5.3.6"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_success_sonarr(self, mock_req):
        mock_req.return_value = {"version": "4.0.1"}
        result = svc_test_arr(kind="sonarr", base_url="http://localhost:8989", api_key="xyz")
        assert result["ok"] is True
        assert result["service"] == "sonarr"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_invalid_key(self, mock_req):
        from emuwarez_uploadrr.integrations.arr_base import ArrAuthError
        mock_req.side_effect = ArrAuthError("Autenticación fallida")
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="wrong")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_connection_error(self, mock_req):
        from emuwarez_uploadrr.integrations.arr_base import ArrConnectionError
        mock_req.side_effect = ArrConnectionError("No se pudo conectar")
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_timeout_detected(self, mock_req):
        from emuwarez_uploadrr.integrations.arr_base import ArrConnectionError
        mock_req.side_effect = ArrConnectionError("Timeout conectando con http://x")
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_prepends_http_if_missing_scheme(self):
        """URLs without scheme get http:// prepended before making the call."""
        with patch("emuwarez_uploadrr.integrations.arr_base.arr_request") as mock_req:
            mock_req.return_value = {"version": "5.0"}
            result = svc_test_arr(kind="radarr", base_url="192.168.1.10:7878", api_key="k")
            assert result["ok"] is True
            called_url = mock_req.call_args[0][1]
            assert called_url.startswith("http://")

    def test_full_key_never_in_response(self):
        import json
        secret = "radarr_secret_api_key_xyz"
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key=secret)
        # Will be a failure (no real server) but key must not appear in result
        serialised = json.dumps(result)
        assert secret not in serialised
