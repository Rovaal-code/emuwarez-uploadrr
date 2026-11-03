"""In-app notification feed + fan-out to Discord/Telegram.

One `emit()` call:
  1. stores a row in the `notifications` table (backs the topbar bell), and
  2. best-effort forwards it to Discord/Telegram, but only to the channels
     that have that event type enabled (Ajustes → Notificaciones).

Dispatch is deliberately non-fatal: a webhook being down must never break the
upload/sync/request flow that triggered the notification, so every outbound
call is wrapped and failures are swallowed (they're logged instead).
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from .settings import get_setting_canonical, get_setting_raw
from .notifications import send_discord, send_telegram
from .eventos import EVENTO_NOTIFICACION, publicar

_log = logging.getLogger("emuwarez.notifications")

# --- Event catalog -----------------------------------------------------------
# code -> human label (shown in the Settings checkbox matrix and used as the
# default enabled set).
#
# La matriz de Ajustes se pinta con lo que devuelve esta tabla
# (`notify_event_types` en la respuesta de ajustes), así que añadir un evento
# aquí ya lo hace aparecer sola. Lo que SÍ hay que tocar a mano es
# NotificationBell.tsx, que elige icono y disposición comparando el código con
# seis literales: un evento nuevo sale sin icono.
#
# (Aquí ponía "Keep in sync with the frontend EVENT_TYPES list". Esa lista
# dejó de existir cuando los tipos pasaron a venir del backend, y el
# comentario mandaba mantener algo que no se puede encontrar.)
EVENT_TYPES: dict[str, str] = {
    "request_published": "Petición publicada",
    "upload_completed": "Subida completada",
    "upload_failed": "Subida fallida",
    "request_match_found": "Contenido compatible",
    "request_new_ready": "Petición nueva lista para subir",
    "content_missing_new": "Contenido nuevo faltante",
    "content_unique_changed": "Nuevo contenido único",
    "version_available": "Versión nueva disponible",
}

# Eventos que NO se mandan a Discord/Telegram salvo que se pidan a mano.
#
# Que haya una versión nueva es cosa de quien administra esto, no algo que
# valga la pena empujar a un chat: no hay nada que hacer al respecto desde el
# móvil y se repetiría en cada actualización. En la campana sí aparece por
# defecto, que es donde se mira el estado de la aplicación.
SOLO_UI_POR_DEFECTO: frozenset[str] = frozenset({"version_available"})

# When a channel has never been configured, default to forwarding every event
# (so enabling Discord/Telegram "just works" without extra clicks).
_ALL_EVENTS = set(EVENT_TYPES)


# --- Channel preferences -----------------------------------------------------

def _channel_enabled(conn: sqlite3.Connection, channel: str) -> bool:
    return (get_setting_canonical(conn, f"notify.{channel}.enabled") or "") == "true"


def ui_enabled(conn: sqlite3.Connection) -> bool:
    """The in-app bell channel is ON by default (unlike Discord/Telegram, which
    must be opted into with credentials). Only an explicit "false" disables it."""
    return (get_setting_canonical(conn, "notify.ui.enabled") or "true") != "false"


def _ui_stores(conn: sqlite3.Connection, event_type: str) -> bool:
    """Whether this event should be stored in the bell feed. Known events honour
    the UI channel's checkbox selection; unknown/system events are always kept."""
    if not ui_enabled(conn):
        return False
    if event_type not in EVENT_TYPES:
        return True
    return event_type in channel_events(conn, "ui")


def channel_events(conn: sqlite3.Connection, channel: str) -> set[str]:
    """Tipos de evento activos en un canal.

    Sin configurar, la campana recibe todo y los canales externos todo menos
    los de SOLO_UI_POR_DEFECTO. Configurado, se respeta exactamente lo que el
    usuario guardó: si desmarcó algo, desmarcado se queda, y una selección vacía
    guardada ("") es un canal sin eventos, no uno sin configurar."""
    raw = get_setting_raw(conn, f"notify.{channel}.events")
    if raw is None:
        return set(_ALL_EVENTS) if channel == "ui" else set(_ALL_EVENTS - SOLO_UI_POR_DEFECTO)
    return {c.strip() for c in raw.split(",") if c.strip() and c.strip() in EVENT_TYPES}


# --- Store -------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "event_type": row["event_type"],
        "title": row["title"],
        "body": row["body"],
        "link": row["link"],
        "level": row["level"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "poster_url": row["poster_url"],
        "content_title": row["content_title"],
        "created_at": row["created_at"],
        "read_at": row["read_at"],
        "read": row["read_at"] is not None,
    }


def list_notifications(conn: sqlite3.Connection, *, limit: int = 30, unread_only: bool = False) -> list[dict]:
    where = "WHERE read_at IS NULL" if unread_only else ""
    rows = conn.execute(
        f"SELECT * FROM notifications {where} ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def unread_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM notifications WHERE read_at IS NULL").fetchone()
    return int(row["n"]) if row else 0


def mark_read(conn: sqlite3.Connection, notification_id: int) -> None:
    conn.execute(
        "UPDATE notifications SET read_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id = ? AND read_at IS NULL",
        (notification_id,),
    )


def mark_all_read(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE notifications SET read_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE read_at IS NULL"
    )


def delete_notification(conn: sqlite3.Connection, notification_id: int) -> None:
    conn.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))


def delete_all_notifications(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM notifications")


# --- Emit --------------------------------------------------------------------

def _format_message(title: str, body: Optional[str], link: Optional[str], content_title: Optional[str] = None) -> str:
    parts = [f"📢 {title}"]
    if content_title:
        parts.append(f"«{content_title}»")
    if body:
        parts.append(body)
    if link:
        parts.append(link)
    return "\n".join(parts)


def _dispatch(conn: sqlite3.Connection, event_type: str, message: str, poster_url: Optional[str] = None) -> None:
    """Best-effort fan-out to Discord/Telegram. Never raises."""
    try:
        if _channel_enabled(conn, "discord") and event_type in channel_events(conn, "discord"):
            webhook = get_setting_canonical(conn, "notify.discord.webhook_url")
            res = send_discord(webhook, message, poster_url=poster_url)
            if not res.get("ok"):
                _log.warning("Discord notify falló (%s): %s", event_type, res.get("message"))
    except Exception:
        _log.exception("Error enviando notificación a Discord")

    try:
        if _channel_enabled(conn, "telegram") and event_type in channel_events(conn, "telegram"):
            token = get_setting_canonical(conn, "notify.telegram.bot_token")
            chat = get_setting_canonical(conn, "notify.telegram.chat_id")
            res = send_telegram(token, chat, message, poster_url=poster_url)
            if not res.get("ok"):
                _log.warning("Telegram notify falló (%s): %s", event_type, res.get("message"))
    except Exception:
        _log.exception("Error enviando notificación a Telegram")


def emit(
    conn: sqlite3.Connection,
    event_type: str,
    title: str,
    body: Optional[str] = None,
    *,
    link: Optional[str] = None,
    level: str = "info",
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    poster_url: Optional[str] = None,
    content_title: Optional[str] = None,
    dispatch: bool = True,
    commit: bool = True,
) -> int:
    """Store an in-app notification and (optionally) forward it to the enabled
    external channels. Returns the new notification id.

    `poster_url` is the content's poster (a fully-qualified, publicly loadable
    URL — Radarr/Sonarr's own `remoteUrl`), shown as a small thumbnail in the
    bell and at full size in Discord/Telegram. `content_title` is the plain
    item name (e.g. "Dune: Parte Dos (2024)") shown next to that poster — pair
    it with a `body` that's just the reason/action ("Se ha subido a eMuwarez
    correctamente."), not the item name again. Omit both for notifications
    with no single associated item (e.g. an aggregate summary) — the bell
    falls back to its plain title/body layout for those.

    `commit=True` commits the insert immediately so the bell reflects it even
    when the caller's own transaction is long-lived; pass False to fold it into
    the caller's transaction.
    """
    # The bell is now a configurable channel ("UI" card in Ajustes →
    # Notificaciones): only store the event if that channel keeps it enabled.
    notif_id = 0
    if _ui_stores(conn, event_type):
        cur = conn.execute(
            """
            INSERT INTO notifications (event_type, title, body, link, level, entity_type, entity_id, poster_url, content_title)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_type, title, body, link, level, entity_type, entity_id, poster_url, content_title),
        )
        notif_id = int(cur.lastrowid)
        if commit:
            conn.commit()
        # La campana sondeaba cada 30 segundos, así que una notificación podía
        # tardar medio minuto en aparecer. Solo se avisa si de verdad se
        # guardó: si el canal UI está desactivado no hay nada que enseñar.
        publicar(EVENTO_NOTIFICACION, {"event_type": event_type, "level": level})
    # Discord/Telegram fan-out is independent of the bell (each has its own
    # enabled flag + event selection).
    if dispatch:
        _dispatch(conn, event_type, _format_message(title, body, link, content_title), poster_url=poster_url)
    return notif_id


__all__ = [
    "EVENT_TYPES", "SOLO_UI_POR_DEFECTO",
    "channel_events",
    "ui_enabled",
    "list_notifications",
    "unread_count",
    "mark_read",
    "mark_all_read",
    "emit",
]
