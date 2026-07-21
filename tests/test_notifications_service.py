"""Unit tests for emuwarez_uploadrr/services/notifications.py (Phase 11A).

All HTTP calls are mocked — no real Discord/Telegram traffic.
"""
from __future__ import annotations

import json
import socket
import urllib.error
from unittest.mock import MagicMock, patch

from emuwarez_uploadrr.services.notifications import send_discord, send_discord_test, send_telegram, send_telegram_test


def _mock_response(status: int = 204, body: bytes = b"") -> MagicMock:
    m = MagicMock()
    m.status = status
    m.read.return_value = body
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url="http://x", code=code, msg="err", hdrs=None, fp=None)  # type: ignore[arg-type]


def _url_error(reason: str) -> urllib.error.URLError:
    return urllib.error.URLError(reason=reason)


def _timeout_url_error() -> urllib.error.URLError:
    return urllib.error.URLError(reason=socket.timeout("timed out"))


class TestSendDiscordTest:
    def test_not_configured_no_url(self):
        result = send_discord_test(None)
        assert result["ok"] is False
        assert result["status"] == "not_configured"
        assert result["service"] == "discord"

    def test_not_configured_blank_url(self):
        result = send_discord_test("   ")
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    def test_invalid_url_scheme(self):
        result = send_discord_test("not-a-url")
        assert result["ok"] is False
        assert result["status"] == "invalid_url"

    def test_success_204(self):
        with patch("urllib.request.urlopen", return_value=_mock_response(204)):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is True
        assert result["status"] == "sent"

    def test_invalid_webhook_404(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    def test_timeout(self):
        with patch("urllib.request.urlopen", side_effect=_timeout_url_error()):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=_url_error("refused")):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_never_sends_real_network_request(self):
        """Guard: without mocking, this must fail fast (invalid host), never
        actually reach discord.com — belt-and-suspenders check that the
        service doesn't bypass urllib.request.urlopen."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            send_discord_test("https://discord.com/api/webhooks/123/abc")
            mock_urlopen.assert_called_once()


class TestSendTelegramTest:
    def test_not_configured_no_token(self):
        result = send_telegram_test(None, "123")
        assert result["ok"] is False
        assert result["status"] == "not_configured"
        assert result["service"] == "telegram"

    def test_not_configured_no_chat_id(self):
        result = send_telegram_test("token123", None)
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    def test_success(self):
        body = json.dumps({"ok": True, "result": {}}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_mock_response(200, body)):
            result = send_telegram_test("123456:ABC", "-100123")
        assert result["ok"] is True
        assert result["status"] == "sent"

    def test_telegram_api_returns_not_ok(self):
        body = json.dumps({"ok": False, "description": "chat not found"}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_mock_response(200, body)):
            result = send_telegram_test("123456:ABC", "-100123")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_invalid_bot_token_401(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            result = send_telegram_test("bad-token", "-100123")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    def test_invalid_chat_id_400(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(400)):
            result = send_telegram_test("123456:ABC", "not-a-chat")
        assert result["ok"] is False
        assert result["status"] == "invalid_chat_id"

    def test_timeout(self):
        with patch("urllib.request.urlopen", side_effect=_timeout_url_error()):
            result = send_telegram_test("123456:ABC", "-100123")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_never_sends_real_network_request(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            send_telegram_test("123456:ABC", "-100123")
            mock_urlopen.assert_called_once()

    def test_bot_token_never_in_result(self):
        """Defensive: the raw token must never leak into the result dict."""
        secret = "123456:SUPER_SECRET_TOKEN_ABC"
        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            result = send_telegram_test(secret, "-100123")
        assert secret not in json.dumps(result)


class TestSendDiscordPoster:
    def test_without_poster_no_embed(self):
        with patch("urllib.request.urlopen", return_value=_mock_response(204)) as mock_urlopen:
            send_discord("https://discord.com/api/webhooks/123/abc", "hola")
        sent = json.loads(mock_urlopen.call_args[0][0].data)
        assert sent == {"content": "hola"}

    def test_with_poster_adds_embed_image(self):
        with patch("urllib.request.urlopen", return_value=_mock_response(204)) as mock_urlopen:
            send_discord(
                "https://discord.com/api/webhooks/123/abc", "hola",
                poster_url="https://image.tmdb.org/t/p/w154/abc.jpg",
            )
        sent = json.loads(mock_urlopen.call_args[0][0].data)
        assert sent["content"] == "hola"
        # Resized to a normal/large size, not left at the small UI thumbnail size.
        assert sent["embeds"] == [{"image": {"url": "https://image.tmdb.org/t/p/w500/abc.jpg"}}]

    def test_poster_url_not_matching_tmdb_shape_passed_through(self):
        with patch("urllib.request.urlopen", return_value=_mock_response(204)) as mock_urlopen:
            send_discord(
                "https://discord.com/api/webhooks/123/abc", "hola",
                poster_url="https://example.com/poster.jpg",
            )
        sent = json.loads(mock_urlopen.call_args[0][0].data)
        assert sent["embeds"] == [{"image": {"url": "https://example.com/poster.jpg"}}]


class TestSendTelegramPoster:
    def test_without_poster_uses_sendmessage(self):
        body = json.dumps({"ok": True, "result": {}}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_mock_response(200, body)) as mock_urlopen:
            send_telegram("123456:ABC", "-100123", "hola")
        req = mock_urlopen.call_args[0][0]
        assert req.full_url.endswith("/sendMessage")
        sent = json.loads(req.data)
        assert sent == {"chat_id": "-100123", "text": "hola"}

    def test_with_poster_uses_sendphoto(self):
        body = json.dumps({"ok": True, "result": {}}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=_mock_response(200, body)) as mock_urlopen:
            send_telegram(
                "123456:ABC", "-100123", "hola",
                poster_url="https://image.tmdb.org/t/p/w154/abc.jpg",
            )
        req = mock_urlopen.call_args[0][0]
        assert req.full_url.endswith("/sendPhoto")
        sent = json.loads(req.data)
        assert sent["chat_id"] == "-100123"
        assert sent["photo"] == "https://image.tmdb.org/t/p/w500/abc.jpg"
        assert sent["caption"] == "hola"
