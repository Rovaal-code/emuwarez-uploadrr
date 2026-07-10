"""Notification providers (Discord webhook / Telegram bot) — Phase 11A.

Safety rules:
- Only sends an explicit test message when the user clicks "Probar" — never
  triggered automatically by settings changes.
- Never logs or returns the full webhook URL / bot token (same masking
  convention as web/services/settings_service.py::mask_secret).
- Read-only with respect to the app's own data — this module only makes an
  outbound HTTP call to Discord/Telegram, it never reads library/upload data.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Optional

_TIMEOUT = 10  # seconds — short timeout, matches services/integration_tests.py

_TEST_MESSAGE = "eMuwarez Uploadrr — notificación de prueba. Si ves esto, la configuración es correcta."


def _ok(service: str, message: str = "Notificación enviada correctamente") -> dict:
    return {"ok": True, "service": service, "status": "sent", "message": message, "details": {}}


def _fail(service: str, status: str, message: str) -> dict:
    return {"ok": False, "service": service, "status": status, "message": message, "details": {}}


def send_discord(webhook_url: Optional[str], message: str) -> dict:
    """Send an arbitrary message to a Discord webhook. Read-only w.r.t. app
    data — the caller supplies the already-formatted text."""
    if not webhook_url or not webhook_url.strip():
        return _fail("discord", "not_configured", "Webhook de Discord no configurado")

    url = webhook_url.strip()
    if not url.startswith(("http://", "https://")):
        return _fail("discord", "invalid_url", "URL de webhook de Discord inválida")

    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "emuwarez-uploadrr/3"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status in (200, 204):
                return _ok("discord")
            return _fail("discord", "connection_error", f"Discord respondió HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            return _fail("discord", "invalid_key", "Webhook de Discord inválido o eliminado")
        return _fail("discord", "connection_error", f"Error HTTP {exc.code} al enviar a Discord")
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower() or isinstance(exc.reason, socket.timeout):
            return _fail("discord", "timeout", "Timeout al conectar con Discord")
        return _fail("discord", "connection_error", f"No se pudo conectar con Discord: {reason}")
    except Exception as exc:
        return _fail("discord", "unexpected_error", f"Error inesperado: {type(exc).__name__}")


def send_telegram(bot_token: Optional[str], chat_id: Optional[str], message: str) -> dict:
    """Send an arbitrary message via a Telegram bot. Read-only w.r.t. app data."""
    if not bot_token or not bot_token.strip():
        return _fail("telegram", "not_configured", "Bot token de Telegram no configurado")
    if not chat_id or not chat_id.strip():
        return _fail("telegram", "not_configured", "Chat ID de Telegram no configurado")

    token = bot_token.strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id.strip(), "text": message}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "emuwarez-uploadrr/3"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                return _ok("telegram")
            return _fail("telegram", "connection_error", body.get("description", "Error desconocido de Telegram"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return _fail("telegram", "invalid_key", "Bot token de Telegram inválido")
        if exc.code == 400:
            return _fail("telegram", "invalid_chat_id", "Chat ID de Telegram inválido o el bot no tiene acceso")
        return _fail("telegram", "connection_error", f"Error HTTP {exc.code} al conectar con Telegram")
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower() or isinstance(exc.reason, socket.timeout):
            return _fail("telegram", "timeout", "Timeout al conectar con Telegram")
        return _fail("telegram", "connection_error", f"No se pudo conectar con Telegram: {reason}")
    except Exception as exc:
        return _fail("telegram", "unexpected_error", f"Error inesperado: {type(exc).__name__}")


def send_discord_test(webhook_url: Optional[str]) -> dict:
    """Send the fixed test message to a Discord webhook (Ajustes → Probar)."""
    return send_discord(webhook_url, _TEST_MESSAGE)


def send_telegram_test(bot_token: Optional[str], chat_id: Optional[str]) -> dict:
    """Send the fixed test message via a Telegram bot (Ajustes → Probar)."""
    return send_telegram(bot_token, chat_id, _TEST_MESSAGE)


__all__ = [
    "send_discord", "send_telegram",
    "send_discord_test", "send_telegram_test",
]
