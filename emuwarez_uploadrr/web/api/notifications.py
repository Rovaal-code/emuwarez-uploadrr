"""Notification test-send endpoints (Phase 11A).

POST /api/notifications/test/discord   — send a test message to a Discord webhook
POST /api/notifications/test/telegram  — send a test message via a Telegram bot

Safety guarantees (see services/notifications.py):
- Only sends when explicitly requested (this endpoint).
- Never stores credentials — this endpoint only sends a test message.
- Never returns the full webhook URL / bot token.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_auth
from ..runtime import _db_path
from ..schemas import IntegrationTestResult, TestDiscordRequest, TestTelegramRequest

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


@router.post("/test/discord", response_model=IntegrationTestResult)
def test_discord(
    body: TestDiscordRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    from emuwarez_uploadrr.database import get_setting_canonical
    from emuwarez_uploadrr.services.notifications import send_discord_test

    webhook_url = body.webhook_url
    if not webhook_url:
        with _get_conn() as conn:
            webhook_url = get_setting_canonical(conn, "notify.discord.webhook_url")

    result = send_discord_test(webhook_url)
    return IntegrationTestResult(**result)


@router.post("/test/telegram", response_model=IntegrationTestResult)
def test_telegram(
    body: TestTelegramRequest,
    current_user: dict = Depends(require_auth),
) -> IntegrationTestResult:
    from emuwarez_uploadrr.database import get_setting_canonical
    from emuwarez_uploadrr.services.notifications import send_telegram_test

    bot_token = body.bot_token
    chat_id = body.chat_id
    if not bot_token or not chat_id:
        with _get_conn() as conn:
            if not bot_token:
                bot_token = get_setting_canonical(conn, "notify.telegram.bot_token")
            if not chat_id:
                chat_id = get_setting_canonical(conn, "notify.telegram.chat_id")

    result = send_telegram_test(bot_token, chat_id)
    return IntegrationTestResult(**result)
