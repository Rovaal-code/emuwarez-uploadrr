"""Unit tests for emuwarez_uploadrr/services/notifications.py (Phase 11A).

All HTTP calls are mocked — no real Discord/Telegram traffic.
"""
from __future__ import annotations

import json

from emuwarez_uploadrr.services.notifications import send_discord, send_discord_test, send_telegram, send_telegram_test
from tests.http_falso import falla_conexion, respuesta, servidor_falso, tiempo_agotado


def _mock_response(status: int = 204, body: bytes = b""):
    return respuesta(status, cuerpo=body)


def _http_error(code: int):
    return respuesta(code)


def _url_error(reason: str):
    return falla_conexion(reason)


def _timeout_url_error():
    return tiempo_agotado()


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
        with servidor_falso(_mock_response(204)):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is True
        assert result["status"] == "sent"

    def test_invalid_webhook_404(self):
        with servidor_falso(_http_error(404)):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    def test_timeout(self):
        with servidor_falso(_timeout_url_error()):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_connection_error(self):
        with servidor_falso(_url_error("refused")):
            result = send_discord_test("https://discord.com/api/webhooks/123/abc")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_never_sends_real_network_request(self):
        """Guard: without mocking, this must fail fast (invalid host), never
        actually reach discord.com — belt-and-suspenders check that the
        service doesn't bypass http_cliente.pedir."""
        with servidor_falso() as servidor:
            send_discord_test("https://discord.com/api/webhooks/123/abc")
            assert len(servidor.peticiones) == 1


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
        with servidor_falso(_mock_response(200, body)):
            result = send_telegram_test("123456:ABC", "-100123")
        assert result["ok"] is True
        assert result["status"] == "sent"

    def test_telegram_api_returns_not_ok(self):
        body = json.dumps({"ok": False, "description": "chat not found"}).encode("utf-8")
        with servidor_falso(_mock_response(200, body)):
            result = send_telegram_test("123456:ABC", "-100123")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_invalid_bot_token_401(self):
        with servidor_falso(_http_error(401)):
            result = send_telegram_test("bad-token", "-100123")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    def test_invalid_chat_id_400(self):
        with servidor_falso(_http_error(400)):
            result = send_telegram_test("123456:ABC", "not-a-chat")
        assert result["ok"] is False
        assert result["status"] == "invalid_chat_id"

    def test_timeout(self):
        with servidor_falso(_timeout_url_error()):
            result = send_telegram_test("123456:ABC", "-100123")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_never_sends_real_network_request(self):
        with servidor_falso() as servidor:
            send_telegram_test("123456:ABC", "-100123")
            assert len(servidor.peticiones) == 1

    def test_bot_token_never_in_result(self):
        """Defensive: the raw token must never leak into the result dict."""
        secret = "123456:SUPER_SECRET_TOKEN_ABC"
        with servidor_falso(_http_error(401)):
            result = send_telegram_test(secret, "-100123")
        assert secret not in json.dumps(result)


class TestSendDiscordPoster:
    def test_without_poster_no_embed(self):
        with servidor_falso(_mock_response(204)) as servidor:
            send_discord("https://discord.com/api/webhooks/123/abc", "hola")
        sent = json.loads(servidor.ultima.content)
        assert sent == {"content": "hola"}

    def test_with_poster_adds_embed_image(self):
        with servidor_falso(_mock_response(204)) as servidor:
            send_discord(
                "https://discord.com/api/webhooks/123/abc", "hola",
                poster_url="https://image.tmdb.org/t/p/w154/abc.jpg",
            )
        sent = json.loads(servidor.ultima.content)
        assert sent["content"] == "hola"
        # Resized to a normal/large size, not left at the small UI thumbnail size.
        assert sent["embeds"] == [{"image": {"url": "https://image.tmdb.org/t/p/w500/abc.jpg"}}]

    def test_poster_url_not_matching_tmdb_shape_passed_through(self):
        with servidor_falso(_mock_response(204)) as servidor:
            send_discord(
                "https://discord.com/api/webhooks/123/abc", "hola",
                poster_url="https://example.com/poster.jpg",
            )
        sent = json.loads(servidor.ultima.content)
        assert sent["embeds"] == [{"image": {"url": "https://example.com/poster.jpg"}}]


class TestSendTelegramPoster:
    def test_without_poster_uses_sendmessage(self):
        body = json.dumps({"ok": True, "result": {}}).encode("utf-8")
        with servidor_falso(_mock_response(200, body)) as servidor:
            send_telegram("123456:ABC", "-100123", "hola")
        req = servidor.ultima
        assert str(req.url).endswith("/sendMessage")
        sent = json.loads(req.content)
        assert sent == {"chat_id": "-100123", "text": "hola"}

    def test_with_poster_uses_sendphoto(self):
        body = json.dumps({"ok": True, "result": {}}).encode("utf-8")
        with servidor_falso(_mock_response(200, body)) as servidor:
            send_telegram(
                "123456:ABC", "-100123", "hola",
                poster_url="https://image.tmdb.org/t/p/w154/abc.jpg",
            )
        req = servidor.ultima
        assert str(req.url).endswith("/sendPhoto")
        sent = json.loads(req.content)
        assert sent["chat_id"] == "-100123"
        assert sent["photo"] == "https://image.tmdb.org/t/p/w500/abc.jpg"
        assert sent["caption"] == "hola"


def test_las_peticiones_salen_igual_que_con_urllib():
    """Mismo cuerpo byte a byte (json.dumps), mismas cabeceras, y el token de Telegram solo en la ruta."""
    with servidor_falso(_mock_response(204)) as servidor:
        send_discord("https://discord.com/api/webhooks/123/abc", "hola ñ")
    p = servidor.ultima
    assert p.method == "POST" and str(p.url) == "https://discord.com/api/webhooks/123/abc"
    assert p.content == json.dumps({"content": "hola ñ"}).encode("utf-8")
    assert p.headers["Content-Type"] == "application/json"
    assert p.headers["User-Agent"] == "emuwarez-uploadrr/3"
    assert p.extensions["timeout"]["connect"] == 10

    with servidor_falso(_mock_response(200, b'{"ok": true}')) as servidor:
        send_telegram("123456:ABC", "-100123", "hola")
    assert str(servidor.ultima.url) == "https://api.telegram.org/bot123456:ABC/sendMessage"
    assert servidor.ultima.content == json.dumps({"chat_id": "-100123", "text": "hola"}).encode("utf-8")


def test_el_motivo_de_un_fallo_de_red_llega_al_mensaje():
    with servidor_falso(_url_error("[Errno 111] Connection refused")):
        r = send_discord("https://discord.com/api/webhooks/123/abc", "hola")
    assert r["message"] == "No se pudo conectar con Discord: [Errno 111] Connection refused"
