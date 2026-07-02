"""API tests for POST /api/notifications/test/* (Phase 11A).

All external HTTP calls are mocked at the service layer — no real
Discord/Telegram traffic.
"""
from __future__ import annotations

from unittest.mock import patch


def test_discord_test_requires_auth(client):
    resp = client.post("/api/notifications/test/discord", json={})
    assert resp.status_code == 401


def test_telegram_test_requires_auth(client):
    resp = client.post("/api/notifications/test/telegram", json={})
    assert resp.status_code == 401


def test_discord_not_configured(client, auth_headers):
    with patch("emuwarez_uploadrr.services.notifications.send_discord_test") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "discord", "status": "not_configured", "message": "No webhook", "details": {}}
        resp = client.post("/api/notifications/test/discord", json={}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["status"] == "not_configured"


def test_discord_uses_body_webhook_when_provided(client, auth_headers):
    with patch("emuwarez_uploadrr.services.notifications.send_discord_test") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "discord", "status": "sent", "message": "OK", "details": {}}
        resp = client.post(
            "/api/notifications/test/discord",
            json={"webhook_url": "https://discord.com/api/webhooks/1/abc"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    mock_svc.assert_called_once_with("https://discord.com/api/webhooks/1/abc")


def test_discord_falls_back_to_stored_webhook(client, auth_headers):
    client.put("/api/settings", json={"notify_discord_webhook_url": "https://discord.com/api/webhooks/2/xyz"}, headers=auth_headers)
    with patch("emuwarez_uploadrr.services.notifications.send_discord_test") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "discord", "status": "sent", "message": "OK", "details": {}}
        resp = client.post("/api/notifications/test/discord", json={}, headers=auth_headers)
    assert resp.status_code == 200
    mock_svc.assert_called_once_with("https://discord.com/api/webhooks/2/xyz")


def test_telegram_not_configured(client, auth_headers):
    with patch("emuwarez_uploadrr.services.notifications.send_telegram_test") as mock_svc:
        mock_svc.return_value = {"ok": False, "service": "telegram", "status": "not_configured", "message": "No token", "details": {}}
        resp = client.post("/api/notifications/test/telegram", json={}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_configured"


def test_telegram_uses_body_values_when_provided(client, auth_headers):
    with patch("emuwarez_uploadrr.services.notifications.send_telegram_test") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "telegram", "status": "sent", "message": "OK", "details": {}}
        resp = client.post(
            "/api/notifications/test/telegram",
            json={"bot_token": "123:ABC", "chat_id": "-100999"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    mock_svc.assert_called_once_with("123:ABC", "-100999")


def test_telegram_falls_back_to_stored_values(client, auth_headers):
    client.put(
        "/api/settings",
        json={"notify_telegram_bot_token": "999:STORED", "notify_telegram_chat_id": "-100111"},
        headers=auth_headers,
    )
    with patch("emuwarez_uploadrr.services.notifications.send_telegram_test") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "telegram", "status": "sent", "message": "OK", "details": {}}
        resp = client.post("/api/notifications/test/telegram", json={}, headers=auth_headers)
    assert resp.status_code == 200
    mock_svc.assert_called_once_with("999:STORED", "-100111")


def test_discord_response_never_contains_full_secret(client, auth_headers):
    with patch("emuwarez_uploadrr.services.notifications.send_discord_test") as mock_svc:
        mock_svc.return_value = {"ok": True, "service": "discord", "status": "sent", "message": "OK", "details": {}}
        resp = client.post(
            "/api/notifications/test/discord",
            json={"webhook_url": "https://discord.com/api/webhooks/1/SUPER_SECRET_PART"},
            headers=auth_headers,
        )
    assert "SUPER_SECRET_PART" not in resp.text
