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
from ...services.settings import escribir_ajuste, estado_secreto, leer_ajuste, set_setting
from ...services.ajustes_registro import AJUSTES, SECRET, error_de, error_de_url_publica
from ...services.uploadrr_contract import DEFAULT_ALLOWED_ROOTS
from ...services.source_assistant import EMU_PROVIDERS
from ...services.notification_center import EVENT_TYPES, channel_events
from ...services.mkv_remux import modo_pistas, reordena
from ...services.integration_tests import test_tmdb_connection, test_emuwarez_connection
from ...database import get_setting_canonical

router = APIRouter(tags=["settings"])

# Los ajustes sencillos (sí/no, número, uno de una lista, texto, secreto) están
# declarados en services/ajustes_registro.py: de allí salen su clave, su valor
# por defecto, su conversión, su validación y, si es un secreto, el enmascarado.
# Los campos de los modelos de abajo que NO salen de allí son estos: listas y
# estructuras guardadas como JSON con su propio código, lo que se calcula a
# partir de otros ajustes y las órdenes de un PUT. Lo comprueba
# tests/test_ajustes_registro.py.
FUERA_DEL_REGISTRO: frozenset[str] = frozenset({
    "upload_tags", "provider_priority_order", "uploadrr_allowed_roots", "path_mappings",
    "image_hosts_available", "image_hosts_enabled", "image_host_keys_configured", "image_host_keys",
    "notify_event_types", "notify_ui_events", "notify_discord_events", "notify_telegram_events",
    # Calculado: hay host de qBittorrent o proxy de qui.
    "qbit_configured",
    # Órdenes del PUT, no ajustes.
    "clear", "qbit_qui_proxy_clear",
})

# Provider codes that are valid in provider_priority_order. Derived from the
# single canonical list (services/source_assistant.EMU_PROVIDERS) so the setup
# wizard, the upload wizard and this validation never drift apart.
_VALID_PROVIDER_CODES: frozenset[str] = frozenset(p["code"] for p in EMU_PROVIDERS)

_DEFAULT_PRIORITY: list[str] = ["AMZN", "NF", "DSNP", "MAX", "ATVP"]


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
    # Dónde abre el usuario la WebUI en su navegador (opcional): solo para el enlace «Abrir en qBittorrent».
    qbit_public_url: Optional[str] = None
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
    uploadrr_runtime_type: str = AJUSTES["uploadrr_runtime_type"].defecto
    uploadrr_python_path: Optional[str] = None
    uploadrr_timeout: int = AJUSTES["uploadrr_timeout"].defecto
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
    # Las subidas de un lote: una notificación por subida o una sola al terminar el lote.
    notify_lote_modo: str = AJUSTES["notify_lote_modo"].defecto
    # "Otros"
    series_ignore_specials: bool = True
    # Sincronizar una instancia de Radarr/Sonarr en cuanto vuelve a responder tras estar caída.
    sincronizar_al_volver_instancia: bool = True
    # Internal Source Tool (services/source_engine). Apagada por defecto.
    source_engine_enabled: bool = False
    # El logo del contenido en la descripción. Se sube por defecto.
    emu_add_logo: bool = True
    # Capturas de todos los capítulos de un pack. Por defecto, solo del primero.
    emu_per_episode_screens: bool = False
    # Qué se le hace a las pistas: uno de mkv_remux.MODOS_PISTAS. De fábrica
    # solo se renombran, que es lo barato (ver mkv_remux.MODO_PISTAS_POR_DEFECTO).
    remux_track_mode: str = AJUSTES["remux_track_mode"].defecto
    # Nunca copiar por reflink un fichero compartido: sus ediciones se omiten. Apagado por defecto.
    remux_no_reflink_copies: bool = False
    recent_activity_limit: int = AJUSTES["recent_activity_limit"].defecto
    upload_max_concurrent: int = AJUSTES["upload_max_concurrent"].defecto
    # Remote path mappings: [{"from": "/data/media", "to": "/mnt/emu-media"}]
    path_mappings: list[dict] = []


class SettingsUpdateRequest(BaseModel):
    # Secretos que se quitan: un valor vacío deja el que haya, así que borrar uno
    # se pide aparte. Valores: _CLAVES_BORRABLES, o "image_host_key:<id>".
    clear: Optional[list[str]] = None
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
    qbit_public_url: Optional[str] = None
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
    notify_lote_modo: Optional[str] = None
    series_ignore_specials: Optional[bool] = None
    sincronizar_al_volver_instancia: Optional[bool] = None
    source_engine_enabled: Optional[bool] = None
    emu_add_logo: Optional[bool] = None
    emu_per_episode_screens: Optional[bool] = None
    remux_track_mode: Optional[str] = None
    remux_no_reflink_copies: Optional[bool] = None
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


# Los secretos que un PUT /settings con `clear` puede quitar, y el ajuste de cada uno.
_CLAVES_BORRABLES = {a.campo: a.clave for a in AJUSTES.values() if a.borrable}
_PREFIJO_CLAVE_IMAGENES = "image_host_key:"


def _ajuste_a_borrar(nombre: str) -> Optional[str]:
    """El ajuste que quita un nombre de `clear`, o None si no es borrable."""
    if nombre in _CLAVES_BORRABLES:
        return _CLAVES_BORRABLES[nombre]
    if nombre.startswith(_PREFIJO_CLAVE_IMAGENES):
        from emuwarez_uploadrr.services.image_hosts import IMAGE_HOSTS
        host_id = nombre[len(_PREFIJO_CLAVE_IMAGENES):]
        if any(h["id"] == host_id for h in IMAGE_HOSTS):
            return f"imghost.key.{host_id}"
    return None


def _normalize_allowed_roots(value: list[str] | str) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = value
    return [p.strip() for p in parts if p and p.strip()]


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
    default = leer_ajuste(conn, "default_release_tag")
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

    # Los del registro: los sencillos ya convertidos y con su valor por
    # defecto; de cada secreto, si está puesto y (si se enseña) enmascarado.
    simples: dict = {}
    for campo, ajuste in AJUSTES.items():
        if ajuste.tipo == SECRET:
            puesto, enmascarado = estado_secreto(conn, campo)
            simples[f"{ajuste.campo_estado}_configured"] = puesto
            if ajuste.enmascara:
                simples[f"{ajuste.campo_estado}_masked"] = enmascarado
        else:
            simples[campo] = leer_ajuste(conn, campo)
    # El modo de pistas traduce el ajuste viejo de sí/no si el nuevo no está.
    simples["remux_track_mode"] = modo_pistas(conn)

    qbit_url = simples["qbit_url"]
    # qBittorrent is "configured" once a host is set (login is optional), o con el proxy de qui.
    qbit_configured = bool(qbit_url and qbit_url.strip()) or simples["qbit_qui_configured"]

    from emuwarez_uploadrr.services.image_hosts import IMAGE_HOSTS, get_enabled_hosts, get_host_key
    img_available = [{"id": h["id"], "label": h["label"], "needs_key": h["needs_key"], "url": h["url"], "favicon": h.get("favicon")} for h in IMAGE_HOSTS]
    img_enabled = get_enabled_hosts(conn)
    img_keys_configured = [h["id"] for h in IMAGE_HOSTS if (get_host_key(conn, h["id"]) or "").strip()]

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

    return SettingsResponse(
        **simples,
        upload_tags=_read_upload_tags(conn),
        provider_priority_order=priority,
        uploadrr_allowed_roots=allowed_roots,
        qbit_configured=qbit_configured,
        image_hosts_available=img_available,
        image_hosts_enabled=img_enabled,
        image_host_keys_configured=img_keys_configured,
        notify_event_types=[{"code": c, "label": l} for c, l in EVENT_TYPES.items()],
        notify_ui_events=sorted(channel_events(conn, "ui")),
        notify_discord_events=sorted(channel_events(conn, "discord")),
        notify_telegram_events=sorted(channel_events(conn, "telegram")),
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

    # Los valores que admite cada ajuste del registro (opciones, mínimo).
    for campo, ajuste in AJUSTES.items():
        valor = getattr(body, campo)
        if valor is not None and ajuste.tipo != SECRET:
            error = error_de(ajuste, valor)
            if error:
                errors.append(error)

    # Aquí y no en un validador de pydantic: su 422 devuelve el valor recibido (`input`) y esta URL no debe volver
    # con una clave dentro.
    if body.qbit_public_url is not None:
        error = error_de_url_publica(body.qbit_public_url)
        if error:
            errors.append(error)

    # TMDb y eMuwarez son integraciones obligatorias: si se manda el campo,
    # no puede quedar vacío (borrar la key sin poner una nueva no está permitido).
    if body.tmdb_api_key is not None and not body.tmdb_api_key.strip():
        errors.append("La API key de TMDb es obligatoria: no se puede guardar vacía")

    if body.emu_api_key is not None and not body.emu_api_key.strip():
        errors.append("La API key de eMuwarez es obligatoria: no se puede guardar vacía")

    desconocidos = [n for n in body.clear or [] if _ajuste_a_borrar(n) is None]
    if desconocidos:
        errors.append(f"No se puede quitar: {', '.join(desconocidos)}")

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

        # Antes que las escrituras: si llega a la vez un valor nuevo, gana ese.
        for nombre in body.clear or []:
            set_setting(conn, _ajuste_a_borrar(nombre), "")

        # Los del registro, ya validados. Un secreto vacío deja el que haya
        # (quitarlo es `clear`); los de TMDb y eMuwarez ni llegan aquí vacíos.
        for campo, ajuste in AJUSTES.items():
            valor = getattr(body, campo)
            if valor is None or (ajuste.tipo == SECRET and not valor.strip()):
                continue
            escribir_ajuste(conn, campo, valor)

        # Después de escribir el proxy de qui: si llegan los dos, gana quitarlo.
        if body.qbit_qui_proxy_clear:
            set_setting(conn, "qbit.qui_proxy_url", "")

        if body.remux_track_mode is not None:
            # El ajuste viejo de sí/no se deja escrito y a la par. modo_pistas()
            # ya no lo mira cuando existe el nuevo, pero sigue siendo lo que lee
            # cualquier instalación que se vuelva atrás a una versión anterior,
            # y encontrárselo congelado en el valor de antes sería peor que
            # traducirlo.
            set_setting(conn, "remux.reorder_tracks",
                        "true" if reordena(body.remux_track_mode) else "false")

        if body.upload_tags is not None:
            tags = list(dict.fromkeys(t.strip() for t in body.upload_tags))
            set_setting(conn, "upload_tags", json.dumps(tags, ensure_ascii=False))

        if body.provider_priority_order is not None:
            codes = [c.strip() for c in body.provider_priority_order]
            set_setting(conn, "provider_priority_order", json.dumps(codes, ensure_ascii=False))

        if body.image_hosts_enabled is not None or body.image_host_keys is not None:
            from emuwarez_uploadrr.services.image_hosts import set_config, get_enabled_hosts
            enabled = body.image_hosts_enabled if body.image_hosts_enabled is not None else get_enabled_hosts(conn)
            set_config(conn, enabled, body.image_host_keys or {})

        if body.uploadrr_allowed_roots is not None:
            normalized = _normalize_allowed_roots(body.uploadrr_allowed_roots)
            set_setting(conn, "uploadrr.allowed_roots", json.dumps(normalized, ensure_ascii=False))

        if body.notify_ui_events is not None:
            set_setting(conn, "notify.ui.events", _clean_event_csv(body.notify_ui_events))

        if body.notify_discord_events is not None:
            set_setting(conn, "notify.discord.events", _clean_event_csv(body.notify_discord_events))

        if body.notify_telegram_events is not None:
            set_setting(conn, "notify.telegram.events", _clean_event_csv(body.notify_telegram_events))

        if body.path_mappings is not None:
            set_setting(conn, "library.path_mappings",
                        json.dumps(_clean_path_mappings(body.path_mappings), ensure_ascii=False))

        conn.commit()
        # Log WHICH settings changed (names only — never values, some are secrets).
        changed = sorted(body.model_dump(exclude_none=True).keys())
        if changed:
            logger.info("Ajustes guardados: %s", ", ".join(changed))
        return _build_response(conn)
