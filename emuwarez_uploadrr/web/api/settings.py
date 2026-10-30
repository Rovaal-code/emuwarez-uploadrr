"""Settings API — read and update editable application settings.

GET  /api/settings  — return editable settings (no raw secrets)
PUT  /api/settings  — update one or more settings
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import re

logger = logging.getLogger("emuwarez.settings")

from pydantic import BaseModel, field_validator

from ..dependencies import require_auth
from ..runtime import _db_path
from ...services.settings import get_setting_canonical, mask_secret, set_setting
from ...services.uploadrr_contract import RUNTIME_EMU, RUNTIME_GENERIC, DEFAULT_TIMEOUT_SECONDS, DEFAULT_ALLOWED_ROOTS
from ...services.source_assistant import EMU_PROVIDERS
from ...services.notification_center import EVENT_TYPES, channel_events, ui_enabled
from ...services.mkv_remux import MODOS_PISTAS, modo_pistas, reordena
from ...services.upload_execution import (
    UPLOAD_MAX_CONCURRENT_SETTING_KEY, UPLOAD_MAX_CONCURRENT_CHOICES, get_upload_max_concurrent,
)
from ...services.integration_tests import test_tmdb_connection, test_emuwarez_connection
from ...database import get_setting_canonical

router = APIRouter(tags=["settings"])

_VALID_RUNTIME_TYPES: frozenset[str] = frozenset({RUNTIME_EMU, RUNTIME_GENERIC})

# Provider codes that are valid in provider_priority_order. Derived from the
# single canonical list (services/source_assistant.EMU_PROVIDERS) so the setup
# wizard, the upload wizard and this validation never drift apart.
_VALID_PROVIDER_CODES: frozenset[str] = frozenset(p["code"] for p in EMU_PROVIDERS)

_DEFAULT_PRIORITY: list[str] = ["AMZN", "NF", "DSNP", "MAX", "ATVP"]
_DEFAULT_REGION = "ES"
_DEFAULT_TAG = "EMUWAREZ"


class SettingsResponse(BaseModel):
    default_release_tag: str
    # Todos los grupos de subida, el de por defecto el primero.
    upload_tags: list[str] = []
    provider_priority_order: list[str]
    tmdb_watch_region: str
    tmdb_localize_series_titles: bool = True
    tmdb_api_key_configured: bool
    tmdb_api_key_masked: Optional[str] = None
    # Phase 11A: Emuwarez API key, editable from Settings (not just setup wizard).
    emu_api_key_configured: bool = False
    emu_api_key_masked: Optional[str] = None
    # qBittorrent (torrent client used by Uploadrr)
    qbit_url: Optional[str] = None
    qbit_tag: Optional[str] = None
    qbit_username: Optional[str] = None
    qbit_password_configured: bool = False
    # El proxy de qui no se devuelve: lleva su clave dentro.
    qbit_qui_configured: bool = False
    qbit_configured: bool = False
    # Image hosts (screenshots)
    image_hosts_available: list = []          # [{id, label, needs_key, url, favicon}]
    image_hosts_enabled: list[str] = []       # enabled ids, in fallback order
    image_host_keys_configured: list[str] = []  # ids that have a key set
    # Phase 5 (12-part batch): the user's own eMuwarez username, used by the
    # Dashboard's "Mis peticiones" card to filter request_items.author.
    emu_username: Optional[str] = None
    # Phase 10F: Uploadrr runtime settings (no secrets involved here).
    uploadrr_path: Optional[str] = None
    uploadrr_runtime_type: str = RUNTIME_EMU
    uploadrr_python_path: Optional[str] = None
    uploadrr_timeout: int = DEFAULT_TIMEOUT_SECONDS
    uploadrr_allowed_roots: list[str] = []
    # Phase 11A: notification providers (Discord webhook / Telegram bot).
    notify_discord_enabled: bool = False
    notify_discord_webhook_configured: bool = False
    notify_discord_webhook_masked: Optional[str] = None
    notify_telegram_enabled: bool = False
    notify_telegram_bot_token_configured: bool = False
    notify_telegram_bot_token_masked: Optional[str] = None
    notify_telegram_chat_id: Optional[str] = None
    # Per-channel event-type selection + the catalog of available event types.
    notify_ui_enabled: bool = True
    notify_event_types: list[dict] = []
    notify_ui_events: list[str] = []
    notify_discord_events: list[str] = []
    notify_telegram_events: list[str] = []
    # "Otros"
    series_ignore_specials: bool = True
    # Internal Source Tool (services/source_engine). Apagada por defecto.
    source_engine_enabled: bool = False
    # El logo del contenido en la descripción. Se sube por defecto.
    emu_add_logo: bool = True
    # Capturas de todos los capítulos de un pack. Por defecto, solo del primero.
    emu_per_episode_screens: bool = False
    # Qué se le hace a las pistas: uno de mkv_remux.MODOS_PISTAS. De fábrica
    # solo se renombran, que es lo barato (ver mkv_remux.MODO_PISTAS_POR_DEFECTO).
    remux_track_mode: str = "solo_renombrar"
    recent_activity_limit: int = 100
    upload_max_concurrent: int = 1
    # Remote path mappings: [{"from": "/data/media", "to": "/mnt/emu-media"}]
    path_mappings: list[dict] = []


class SettingsUpdateRequest(BaseModel):
    default_release_tag: Optional[str] = None
    upload_tags: Optional[list[str]] = None
    provider_priority_order: Optional[list[str]] = None
    tmdb_watch_region: Optional[str] = None
    tmdb_localize_series_titles: Optional[bool] = None
    tmdb_api_key: Optional[str] = None
    # Phase 11A
    emu_api_key: Optional[str] = None
    # qBittorrent
    qbit_url: Optional[str] = None
    qbit_tag: Optional[str] = None
    qbit_username: Optional[str] = None
    qbit_password: Optional[str] = None
    # Vacío deja el que haya, como la contraseña; quitarlo es qbit_qui_proxy_clear.
    qbit_qui_proxy_url: Optional[str] = None
    qbit_qui_proxy_clear: Optional[bool] = None
    # Image hosts
    image_hosts_enabled: Optional[list[str]] = None
    image_host_keys: Optional[dict] = None  # {host_id: api_key}
    emu_username: Optional[str] = None
    # Phase 10F
    uploadrr_path: Optional[str] = None
    uploadrr_runtime_type: Optional[str] = None
    uploadrr_python_path: Optional[str] = None
    uploadrr_timeout: Optional[int] = None
    # Accepts either a list of strings or a single CSV string (frontend may
    # submit either a textarea/CSV field or a parsed list).
    uploadrr_allowed_roots: Optional[list[str] | str] = None
    # Phase 11A: notifications
    notify_discord_enabled: Optional[bool] = None
    notify_discord_webhook_url: Optional[str] = None
    notify_telegram_enabled: Optional[bool] = None
    notify_telegram_bot_token: Optional[str] = None
    notify_telegram_chat_id: Optional[str] = None
    notify_ui_enabled: Optional[bool] = None
    notify_ui_events: Optional[list[str]] = None
    notify_discord_events: Optional[list[str]] = None
    notify_telegram_events: Optional[list[str]] = None
    series_ignore_specials: Optional[bool] = None
    source_engine_enabled: Optional[bool] = None
    emu_add_logo: Optional[bool] = None
    emu_per_episode_screens: Optional[bool] = None
    remux_track_mode: Optional[str] = None
    recent_activity_limit: Optional[int] = None
    upload_max_concurrent: Optional[int] = None
    path_mappings: Optional[list[dict]] = None

    @field_validator("qbit_url", "qbit_qui_proxy_url")
    @classmethod
    def valid_qbit_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        # Empty clears the config; otherwise require a real http(s) URL (like
        # Radarr/Sonarr instances).
        if v and not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("La URL de qBittorrent debe empezar por http:// o https:// e incluir un host válido")
        return v


def _normalize_allowed_roots(value: list[str] | str) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = value
    return [p.strip() for p in parts if p and p.strip()]


_RECENT_ACTIVITY_CHOICES = (0, 50, 100, 150, 200, 250, 300)  # 0 = sin límite


def _read_recent_activity_limit(conn) -> int:
    raw = get_setting_canonical(conn, "dashboard.recent_activity_limit")
    try:
        val = int(raw) if raw else 100
    except (TypeError, ValueError):
        return 100
    return val if val in _RECENT_ACTIVITY_CHOICES else 100


def _read_path_mappings(conn) -> list[dict]:
    from emuwarez_uploadrr.services.path_mapping import get_path_mappings
    return get_path_mappings(conn)


def _clean_path_mappings(raw: list[dict]) -> list[dict]:
    """Keep only well-formed {from, to} entries with absolute paths, trimmed."""
    out: list[dict] = []
    for m in raw or []:
        if not isinstance(m, dict):
            continue
        frm = str(m.get("from") or "").strip()
        to = str(m.get("to") or "").strip()
        if frm and to:
            out.append({"from": frm, "to": to})
    return out


def _clean_event_csv(codes: list[str]) -> str:
    """Keep only known event codes, dedup, and store as a CSV. An empty
    selection is stored as "" (i.e. the channel receives no events) — which is
    distinct from the setting never having been saved (→ all events)."""
    seen = [c for c in dict.fromkeys(codes) if c in EVENT_TYPES]
    return ",".join(seen)


def _read_upload_tags(conn) -> list[str]:
    """Los grupos de subida guardados, con el de por defecto el primero."""
    default = get_setting_canonical(conn, "default_release_tag") or _DEFAULT_TAG
    try:
        saved = json.loads(get_setting_canonical(conn, "upload_tags") or "[]")
    except ValueError:
        saved = []
    return list(dict.fromkeys([default, *saved]))


def _get_conn():
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(_db_path())
    init_db(conn)
    return conn


def _build_response(conn) -> SettingsResponse:
    raw_priority = get_setting_canonical(conn, "provider_priority_order")
    try:
        priority = json.loads(raw_priority) if raw_priority else _DEFAULT_PRIORITY
    except Exception:
        priority = _DEFAULT_PRIORITY

    tmdb_key = get_setting_canonical(conn, "tmdb.api_key")
    configured = bool(tmdb_key and tmdb_key.strip())
    masked = mask_secret(tmdb_key) if configured else None

    emu_key = get_setting_canonical(conn, "emu.api_key")
    emu_configured = bool(emu_key and emu_key.strip())
    emu_masked = mask_secret(emu_key) if emu_configured else None

    qbit_url = get_setting_canonical(conn, "qbit.url")
    qbit_pass = get_setting_canonical(conn, "qbit.password")
    qbit_pass_configured = bool(qbit_pass and qbit_pass.strip())
    qbit_qui = get_setting_canonical(conn, "qbit.qui_proxy_url")
    qbit_qui_configured = bool(qbit_qui and qbit_qui.strip())
    # qBittorrent is "configured" once a host is set (login is optional), o con el proxy de qui.
    qbit_configured = bool(qbit_url and qbit_url.strip()) or qbit_qui_configured

    from emuwarez_uploadrr.services.image_hosts import IMAGE_HOSTS, get_enabled_hosts, get_host_key
    img_available = [{"id": h["id"], "label": h["label"], "needs_key": h["needs_key"], "url": h["url"], "favicon": h.get("favicon")} for h in IMAGE_HOSTS]
    img_enabled = get_enabled_hosts(conn)
    img_keys_configured = [h["id"] for h in IMAGE_HOSTS if (get_host_key(conn, h["id"]) or "").strip()]

    discord_webhook = get_setting_canonical(conn, "notify.discord.webhook_url")
    discord_webhook_configured = bool(discord_webhook and discord_webhook.strip())
    telegram_token = get_setting_canonical(conn, "notify.telegram.bot_token")
    telegram_token_configured = bool(telegram_token and telegram_token.strip())

    raw_roots = get_setting_canonical(conn, "uploadrr.allowed_roots")
    if raw_roots is None:
        # Never configured — same default get_allowed_roots() enforces, so
        # what the user sees here always matches what real uploads use.
        allowed_roots = list(DEFAULT_ALLOWED_ROOTS)
    else:
        try:
            allowed_roots = json.loads(raw_roots) if raw_roots else []
            if not isinstance(allowed_roots, list):
                allowed_roots = []
        except Exception:
            allowed_roots = []

    raw_timeout = get_setting_canonical(conn, "uploadrr.timeout")
    try:
        timeout = int(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS

    return SettingsResponse(
        default_release_tag=get_setting_canonical(conn, "default_release_tag") or _DEFAULT_TAG,
        upload_tags=_read_upload_tags(conn),
        provider_priority_order=priority,
        tmdb_watch_region=get_setting_canonical(conn, "tmdb_watch_region") or _DEFAULT_REGION,
        tmdb_localize_series_titles=(get_setting_canonical(conn, "tmdb.localize_series_titles") or "true") != "false",
        tmdb_api_key_configured=configured,
        tmdb_api_key_masked=masked,
        uploadrr_path=get_setting_canonical(conn, "uploadrr.path"),
        uploadrr_runtime_type=get_setting_canonical(conn, "uploadrr.runtime_type") or RUNTIME_EMU,
        uploadrr_python_path=get_setting_canonical(conn, "uploadrr.python_path"),
        uploadrr_timeout=timeout,
        uploadrr_allowed_roots=allowed_roots,
        emu_api_key_configured=emu_configured,
        emu_api_key_masked=emu_masked,
        emu_username=get_setting_canonical(conn, "emu.username"),
        qbit_url=qbit_url,
        qbit_tag=get_setting_canonical(conn, "qbit.tag"),
        qbit_username=get_setting_canonical(conn, "qbit.username"),
        qbit_password_configured=qbit_pass_configured,
        qbit_qui_configured=qbit_qui_configured,
        qbit_configured=qbit_configured,
        image_hosts_available=img_available,
        image_hosts_enabled=img_enabled,
        image_host_keys_configured=img_keys_configured,
        notify_discord_enabled=(get_setting_canonical(conn, "notify.discord.enabled") or "") == "true",
        notify_discord_webhook_configured=discord_webhook_configured,
        notify_discord_webhook_masked=mask_secret(discord_webhook) if discord_webhook_configured else None,
        notify_telegram_enabled=(get_setting_canonical(conn, "notify.telegram.enabled") or "") == "true",
        notify_telegram_bot_token_configured=telegram_token_configured,
        notify_telegram_bot_token_masked=mask_secret(telegram_token) if telegram_token_configured else None,
        notify_telegram_chat_id=get_setting_canonical(conn, "notify.telegram.chat_id"),
        notify_ui_enabled=ui_enabled(conn),
        notify_event_types=[{"code": c, "label": l} for c, l in EVENT_TYPES.items()],
        notify_ui_events=sorted(channel_events(conn, "ui")),
        notify_discord_events=sorted(channel_events(conn, "discord")),
        notify_telegram_events=sorted(channel_events(conn, "telegram")),
        series_ignore_specials=(get_setting_canonical(conn, "series.ignore_specials") or "true") != "false",
        source_engine_enabled=get_setting_canonical(conn, "source_engine.enabled") == "true",
        emu_add_logo=get_setting_canonical(conn, "emu.add_logo") != "false",
        emu_per_episode_screens=get_setting_canonical(conn, "emu.per_episode_screens") == "true",
        remux_track_mode=modo_pistas(conn),
        recent_activity_limit=_read_recent_activity_limit(conn),
        upload_max_concurrent=get_upload_max_concurrent(conn),
        path_mappings=_read_path_mappings(conn),
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings(current_user: dict = Depends(require_auth)) -> SettingsResponse:
    with _get_conn() as conn:
        return _build_response(conn)


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    body: SettingsUpdateRequest,
    current_user: dict = Depends(require_auth),
) -> SettingsResponse:
    errors: list[str] = []

    if body.default_release_tag is not None:
        tag = body.default_release_tag.strip()
        if not tag:
            errors.append("default_release_tag no puede estar vacío")
        elif any(c in tag for c in "/\\"):
            errors.append("default_release_tag no puede tener / ni \\")

    if body.upload_tags is not None:
        if not all(t.strip() for t in body.upload_tags):
            errors.append("upload_tags no puede tener tags vacíos")
        # El tag acaba en el nombre del fichero: con una barra sería otra carpeta.
        if any(c in t for t in body.upload_tags for c in "/\\"):
            errors.append("upload_tags no puede tener / ni \\")

    if body.provider_priority_order is not None:
        codes = [c.strip() for c in body.provider_priority_order]
        invalid = [c for c in codes if c not in _VALID_PROVIDER_CODES]
        if invalid:
            errors.append(f"Códigos de provider inválidos: {', '.join(invalid)}")
        if len(codes) != len(set(codes)):
            errors.append("provider_priority_order contiene duplicados")

    if body.uploadrr_runtime_type is not None and body.uploadrr_runtime_type not in _VALID_RUNTIME_TYPES:
        errors.append(
            f"uploadrr_runtime_type inválido: '{body.uploadrr_runtime_type}'. "
            f"Debe ser uno de: {', '.join(sorted(_VALID_RUNTIME_TYPES))}"
        )

    if body.uploadrr_timeout is not None and body.uploadrr_timeout <= 0:
        errors.append("uploadrr_timeout debe ser un entero positivo")

    # TMDb y eMuwarez son integraciones obligatorias: si se manda el campo,
    # no puede quedar vacío (borrar la key sin poner una nueva no está permitido).
    if body.tmdb_api_key is not None and not body.tmdb_api_key.strip():
        errors.append("La API key de TMDb es obligatoria: no se puede guardar vacía")

    if body.emu_api_key is not None and not body.emu_api_key.strip():
        errors.append("La API key de eMuwarez es obligatoria: no se puede guardar vacía")

    if errors:
        raise HTTPException(
            status_code=422,
            detail="; ".join(errors),
        )

    with _get_conn() as conn:
        # Live-validate any new TMDb/eMuwarez key BEFORE writing anything else —
        # an invalid key must abort the whole save, not just that field.
        key_errors: list[str] = []

        tmdb_candidate = body.tmdb_api_key.strip() if body.tmdb_api_key else None
        if tmdb_candidate:
            result = test_tmdb_connection(api_key=tmdb_candidate, conn=conn)
            if not result.get("ok"):
                key_errors.append(f"API key de TMDb inválida: {result.get('message')}")

        emu_candidate = body.emu_api_key.strip() if body.emu_api_key else None
        if emu_candidate:
            # enforce_rate_limit=False: this is a save precondition, not the
            # "Probar conexión" button — it must not collide with its throttle.
            result = test_emuwarez_connection(api_key=emu_candidate, conn=conn, enforce_rate_limit=False)
            if not result.get("ok"):
                key_errors.append(f"API key de eMuwarez inválida: {result.get('message')}")

        if key_errors:
            raise HTTPException(
                status_code=422,
                detail="; ".join(key_errors),
            )

        if body.default_release_tag is not None:
            set_setting(conn, "default_release_tag", body.default_release_tag.strip())

        if body.upload_tags is not None:
            tags = list(dict.fromkeys(t.strip() for t in body.upload_tags))
            set_setting(conn, "upload_tags", json.dumps(tags, ensure_ascii=False))

        if body.provider_priority_order is not None:
            codes = [c.strip() for c in body.provider_priority_order]
            set_setting(conn, "provider_priority_order", json.dumps(codes, ensure_ascii=False))

        if body.tmdb_watch_region is not None:
            set_setting(conn, "tmdb_watch_region", body.tmdb_watch_region.strip())

        if body.tmdb_localize_series_titles is not None:
            set_setting(conn, "tmdb.localize_series_titles",
                        "true" if body.tmdb_localize_series_titles else "false")

        if tmdb_candidate:
            set_setting(conn, "tmdb.api_key", tmdb_candidate)

        if emu_candidate:
            set_setting(conn, "emu.api_key", emu_candidate)

        if body.emu_username is not None:
            set_setting(conn, "emu.username", body.emu_username.strip())

        if body.qbit_url is not None:
            set_setting(conn, "qbit.url", body.qbit_url.strip())
        if body.qbit_tag is not None:
            set_setting(conn, "qbit.tag", body.qbit_tag.strip())
        if body.qbit_username is not None:
            set_setting(conn, "qbit.username", body.qbit_username.strip())
        # Blank password left untouched (keeps the stored one), same as api keys.
        if body.qbit_password is not None and body.qbit_password.strip():
            set_setting(conn, "qbit.password", body.qbit_password.strip())
        if body.qbit_qui_proxy_clear:
            set_setting(conn, "qbit.qui_proxy_url", "")
        elif body.qbit_qui_proxy_url:
            set_setting(conn, "qbit.qui_proxy_url", body.qbit_qui_proxy_url)

        if body.image_hosts_enabled is not None or body.image_host_keys is not None:
            from emuwarez_uploadrr.services.image_hosts import set_config, get_enabled_hosts
            enabled = body.image_hosts_enabled if body.image_hosts_enabled is not None else get_enabled_hosts(conn)
            set_config(conn, enabled, body.image_host_keys or {})

        if body.uploadrr_path is not None:
            set_setting(conn, "uploadrr.path", body.uploadrr_path.strip())

        if body.uploadrr_runtime_type is not None:
            set_setting(conn, "uploadrr.runtime_type", body.uploadrr_runtime_type)

        if body.uploadrr_python_path is not None:
            set_setting(conn, "uploadrr.python_path", body.uploadrr_python_path.strip())

        if body.uploadrr_timeout is not None:
            set_setting(conn, "uploadrr.timeout", str(body.uploadrr_timeout))

        if body.uploadrr_allowed_roots is not None:
            normalized = _normalize_allowed_roots(body.uploadrr_allowed_roots)
            set_setting(conn, "uploadrr.allowed_roots", json.dumps(normalized, ensure_ascii=False))

        if body.notify_discord_enabled is not None:
            set_setting(conn, "notify.discord.enabled", "true" if body.notify_discord_enabled else "false")

        if body.notify_discord_webhook_url is not None and body.notify_discord_webhook_url.strip():
            set_setting(conn, "notify.discord.webhook_url", body.notify_discord_webhook_url.strip())

        if body.notify_telegram_enabled is not None:
            set_setting(conn, "notify.telegram.enabled", "true" if body.notify_telegram_enabled else "false")

        if body.notify_telegram_bot_token is not None and body.notify_telegram_bot_token.strip():
            set_setting(conn, "notify.telegram.bot_token", body.notify_telegram_bot_token.strip())

        if body.notify_telegram_chat_id is not None:
            set_setting(conn, "notify.telegram.chat_id", body.notify_telegram_chat_id.strip())

        if body.notify_ui_enabled is not None:
            set_setting(conn, "notify.ui.enabled", "true" if body.notify_ui_enabled else "false")

        if body.notify_ui_events is not None:
            set_setting(conn, "notify.ui.events", _clean_event_csv(body.notify_ui_events))

        if body.notify_discord_events is not None:
            set_setting(conn, "notify.discord.events", _clean_event_csv(body.notify_discord_events))

        if body.notify_telegram_events is not None:
            set_setting(conn, "notify.telegram.events", _clean_event_csv(body.notify_telegram_events))

        if body.series_ignore_specials is not None:
            set_setting(conn, "series.ignore_specials", "true" if body.series_ignore_specials else "false")
        if body.source_engine_enabled is not None:
            set_setting(conn, "source_engine.enabled", "true" if body.source_engine_enabled else "false")
        if body.emu_add_logo is not None:
            set_setting(conn, "emu.add_logo", "true" if body.emu_add_logo else "false")
        if body.emu_per_episode_screens is not None:
            set_setting(conn, "emu.per_episode_screens", "true" if body.emu_per_episode_screens else "false")
        if body.remux_track_mode is not None:
            if body.remux_track_mode not in MODOS_PISTAS:
                raise HTTPException(
                    status_code=422,
                    detail=f"remux_track_mode debe ser uno de {list(MODOS_PISTAS)}")
            set_setting(conn, "remux.track_mode", body.remux_track_mode)
            # El ajuste viejo de sí/no se deja escrito y a la par. modo_pistas()
            # ya no lo mira cuando existe el nuevo, pero sigue siendo lo que lee
            # cualquier instalación que se vuelva atrás a una versión anterior,
            # y encontrárselo congelado en el valor de antes sería peor que
            # traducirlo.
            set_setting(conn, "remux.reorder_tracks",
                        "true" if reordena(body.remux_track_mode) else "false")

        if body.recent_activity_limit is not None:
            if body.recent_activity_limit not in _RECENT_ACTIVITY_CHOICES:
                raise HTTPException(status_code=422, detail=f"recent_activity_limit debe ser uno de {_RECENT_ACTIVITY_CHOICES}")
            set_setting(conn, "dashboard.recent_activity_limit", str(body.recent_activity_limit))

        if body.upload_max_concurrent is not None:
            if body.upload_max_concurrent not in UPLOAD_MAX_CONCURRENT_CHOICES:
                raise HTTPException(status_code=422, detail=f"upload_max_concurrent debe ser uno de {UPLOAD_MAX_CONCURRENT_CHOICES}")
            set_setting(conn, UPLOAD_MAX_CONCURRENT_SETTING_KEY, str(body.upload_max_concurrent))

        if body.path_mappings is not None:
            import json as _json
            set_setting(conn, "library.path_mappings", _json.dumps(_clean_path_mappings(body.path_mappings), ensure_ascii=False))

        conn.commit()
        # Log WHICH settings changed (names only — never values, some are secrets).
        changed = sorted(body.model_dump(exclude_none=True).keys())
        if changed:
            logger.info("Ajustes guardados: %s", ", ".join(changed))
        return _build_response(conn)
