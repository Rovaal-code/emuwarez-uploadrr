"""API tests for the Phase 11A additions to GET/PUT /api/settings:
Emuwarez API key section and Discord/Telegram notification settings.
"""
from __future__ import annotations

import json


def _mock_emu_ok(monkeypatch):
    """emu_api_key is mandatory and live-tested before being saved in
    PUT /settings (emuwarez_uploadrr/web/api/settings.py imports the probe
    at module load time, so patch it there, not just in integration_tests)."""
    ok = lambda *a, **k: {"ok": True, "service": "emuwarez", "status": "connected", "message": "Conexión correcta"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection", ok)
    monkeypatch.setattr("emuwarez_uploadrr.web.api.settings.test_emuwarez_connection", ok)


# ---------------------------------------------------------------------------
# Emuwarez API key
# ---------------------------------------------------------------------------

def test_get_settings_emu_defaults(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["emu_api_key_configured"] is False
    assert data["emu_api_key_masked"] is None


def test_put_settings_saves_emu_api_key(client, auth_headers, monkeypatch):
    _mock_emu_ok(monkeypatch)
    resp = client.put("/api/settings", json={"emu_api_key": "emu_secret_key_1234567890"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["emu_api_key_configured"] is True
    assert data["emu_api_key_masked"] is not None
    assert "emu_secret_key_1234567890" not in json.dumps(data)


def test_put_settings_blank_emu_api_key_is_rejected(client, auth_headers, monkeypatch):
    # eMuwarez is mandatory: an explicit empty key must be rejected outright,
    # not silently ignored, and must not touch the existing key.
    _mock_emu_ok(monkeypatch)
    client.put("/api/settings", json={"emu_api_key": "emu_secret_key_1234567890"}, headers=auth_headers)
    resp = client.put("/api/settings", json={"emu_api_key": ""}, headers=auth_headers)
    assert resp.status_code == 422

    get_resp = client.get("/api/settings", headers=auth_headers)
    assert get_resp.json()["emu_api_key_configured"] is True


# ---------------------------------------------------------------------------
# Notifications settings
# ---------------------------------------------------------------------------

def test_get_settings_notifications_defaults(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["notify_discord_enabled"] is False
    assert data["notify_discord_webhook_configured"] is False
    assert data["notify_telegram_enabled"] is False
    assert data["notify_telegram_bot_token_configured"] is False
    assert data["notify_telegram_chat_id"] is None


def test_put_settings_enables_discord_and_saves_webhook(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"notify_discord_enabled": True, "notify_discord_webhook_url": "https://discord.com/api/webhooks/1/abcdefghi"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["notify_discord_enabled"] is True
    assert data["notify_discord_webhook_configured"] is True
    assert "abcdefghi" not in json.dumps(data)


def test_put_settings_saves_telegram_fields(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={
            "notify_telegram_enabled": True,
            "notify_telegram_bot_token": "123456:SECRETTOKEN",
            "notify_telegram_chat_id": "-100987654321",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["notify_telegram_enabled"] is True
    assert data["notify_telegram_bot_token_configured"] is True
    assert data["notify_telegram_chat_id"] == "-100987654321"
    assert "SECRETTOKEN" not in json.dumps(data)


def test_put_settings_can_disable_notifications_without_clearing_secret(client, auth_headers):
    client.put(
        "/api/settings",
        json={"notify_discord_enabled": True, "notify_discord_webhook_url": "https://discord.com/api/webhooks/1/keepme"},
        headers=auth_headers,
    )
    resp = client.put("/api/settings", json={"notify_discord_enabled": False}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["notify_discord_enabled"] is False
    # Disabling must not wipe the stored webhook — re-enabling later should keep it.
    assert data["notify_discord_webhook_configured"] is True


# ---------------------------------------------------------------------------
# provider_priority_order round-trips as a plain list (checkbox+drag UI backing field)
# ---------------------------------------------------------------------------

def test_put_settings_provider_priority_order_as_list(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"provider_priority_order": ["NF", "AMZN", "DSNP"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["provider_priority_order"] == ["NF", "AMZN", "DSNP"]


def test_put_settings_provider_priority_order_empty_list_allowed(client, auth_headers):
    resp = client.put("/api/settings", json={"provider_priority_order": []}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["provider_priority_order"] == []
