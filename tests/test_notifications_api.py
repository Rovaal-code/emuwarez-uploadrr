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


# ---------------------------------------------------------------------------
# In-app notification feed (topbar bell)
# ---------------------------------------------------------------------------

def test_feed_requires_auth(client):
    assert client.get("/api/notifications").status_code == 401


def test_feed_empty_by_default(client, auth_headers):
    resp = client.get("/api/notifications", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["notifications"] == []
    assert data["unread_count"] == 0


def _emit(event_type="upload_completed", title="Subida completada", body="x"):
    """Store a notification directly via the service (no external dispatch)."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.web.runtime import _db_path
    from emuwarez_uploadrr.services import notification_center as nc
    conn = connect(_db_path())
    init_db(conn)
    try:
        return nc.emit(conn, event_type, title, body, dispatch=False)
    finally:
        conn.close()


def test_feed_lists_and_marks_read(client, auth_headers):
    nid = _emit()
    resp = client.get("/api/notifications", headers=auth_headers)
    data = resp.json()
    assert data["unread_count"] == 1
    assert data["notifications"][0]["title"] == "Subida completada"
    assert data["notifications"][0]["read"] is False

    r2 = client.post(f"/api/notifications/{nid}/read", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["unread_count"] == 0

    assert client.get("/api/notifications", headers=auth_headers).json()["unread_count"] == 0


def test_feed_mark_all_read(client, auth_headers):
    _emit()
    _emit(title="Otra")
    assert client.get("/api/notifications", headers=auth_headers).json()["unread_count"] == 2
    r = client.post("/api/notifications/read-all", headers=auth_headers)
    assert r.status_code == 200 and r.json()["unread_count"] == 0


def test_settings_expose_event_types_and_default_all_enabled(client, auth_headers):
    from emuwarez_uploadrr.services.notification_center import SOLO_UI_POR_DEFECTO

    s = client.get("/api/settings", headers=auth_headers).json()
    codes = {e["code"] for e in s["notify_event_types"]}
    assert {"upload_completed", "request_match_found"} <= codes

    # Sin configurar, los canales externos reciben todo MENOS los eventos que
    # son opt-in a propósito: que haya una versión nueva es cosa de quien
    # administra esto, no algo que empujar a un chat.
    esperado_bots = codes - set(SOLO_UI_POR_DEFECTO)
    assert set(s["notify_discord_events"]) == esperado_bots
    assert set(s["notify_telegram_events"]) == esperado_bots
    assert SOLO_UI_POR_DEFECTO, "si no hay eventos solo-UI, esta prueba no comprueba nada"


def test_el_aviso_de_version_llega_a_la_campana_pero_no_a_los_bots(client, auth_headers):
    """Lo pedido: activado por defecto en la interfaz, no en los bots."""
    from emuwarez_uploadrr.services.notification_center import channel_events
    from emuwarez_uploadrr.database import connect, db_path

    conn = connect(db_path())
    try:
        assert "version_available" in channel_events(conn, "ui")
        assert "version_available" not in channel_events(conn, "discord")
        assert "version_available" not in channel_events(conn, "telegram")
    finally:
        conn.close()


def test_settings_save_event_selection(client, auth_headers):
    client.put("/api/settings", json={"notify_discord_events": ["upload_completed", "bogus"]}, headers=auth_headers)
    s = client.get("/api/settings", headers=auth_headers).json()
    # bogus dropped, only the known code kept.
    assert s["notify_discord_events"] == ["upload_completed"]
