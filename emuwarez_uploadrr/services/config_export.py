"""Settings export/import — secrets masked by default, explicit confirmation to include them."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

EXPORT_SECRETS_CONFIRMATION = "EXPORTAR_SECRETOS"
IMPORT_CONFIRMATION = "IMPORTAR_CONFIG"

# key → {secret: bool} — controls masking in export and validation on import
SETTINGS_SCHEMA: dict[str, dict] = {
    "app_name": {"secret": False},
    "timezone": {"secret": False},
    "uploadrr_path": {"secret": False},
    "tmdb_api_key": {"secret": True},
    "tmdb_region": {"secret": False},
    "emu_base_url": {"secret": False},
    "emu_api_key": {"secret": True},
    "emu_requests_min_interval_minutes": {"secret": False},
    "jellyfin_enabled": {"secret": False},
}

_MASKED = "***MASKED***"


def mask_exported_secret(value: str | None) -> str | None:
    if value is None:
        return None
    return _MASKED if value else None


def _get_db_path() -> Path:
    env = os.environ.get("CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".config" / "emuwarez-renamer"
    return base / "emuwarez_uploadrr.db"


def _read_settings_from_db() -> dict[str, str | None]:
    db = _get_db_path()
    if not db.exists():
        return {}
    conn = sqlite3.connect(str(db))
    try:
        from .settings import all_settings
        conn.row_factory = sqlite3.Row
        return all_settings(conn)
    finally:
        conn.close()


def _write_settings_to_db(settings: dict[str, str | None]) -> int:
    db = _get_db_path()
    conn = sqlite3.connect(str(db))
    updated = 0
    try:
        # Por la puerta (services/settings.set_setting), que además marca los
        # secretos con is_secret=1. Escribiendo el INSERT a mano, una API key
        # importada quedaba sin marcar y salía sin enmascarar en las
        # respuestas del API.
        from .settings import set_setting
        conn.row_factory = sqlite3.Row
        for key, value in settings.items():
            set_setting(conn, key, "" if value is None else str(value))
            updated += 1
        conn.commit()
    finally:
        conn.close()
    return updated


def export_settings(
    *,
    include_secrets: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Export settings as dict. Secrets are masked unless include_secrets=True with correct confirmation."""
    if include_secrets and confirmation != EXPORT_SECRETS_CONFIRMATION:
        return {
            "ok": False,
            "error": f"Para exportar secretos, pasa confirmation='{EXPORT_SECRETS_CONFIRMATION}'",
        }

    raw = _read_settings_from_db()
    exported: dict[str, str | None] = {}
    secret_count = 0
    for key, meta in SETTINGS_SCHEMA.items():
        value = raw.get(key)
        if meta["secret"]:
            secret_count += 1
            if include_secrets:
                exported[key] = value
            else:
                exported[key] = mask_exported_secret(value)
        else:
            exported[key] = value

    return {
        "ok": True,
        "settings": exported,
        "include_secrets": include_secrets,
        "secrets_masked": not include_secrets,
        "total_keys": len(SETTINGS_SCHEMA),
        "secret_keys_count": secret_count,
    }


def import_settings(
    payload: dict,
    *,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Import settings from a dict payload.

    Unknown keys are rejected.  Masked values (_MASKED) are skipped — they are not overwritten.
    dry_run=True previews without writing. apply=True requires confirmation=IMPORTAR_CONFIG.
    """
    do_apply = apply and not dry_run
    if do_apply and confirmation != IMPORT_CONFIRMATION:
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": f"Confirmación requerida: pasa confirmation='{IMPORT_CONFIRMATION}'",
        }

    unknown = [k for k in payload if k not in SETTINGS_SCHEMA]
    if unknown:
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": f"Claves desconocidas: {unknown}",
        }

    to_write: dict[str, str | None] = {}
    skipped_masked: list[str] = []
    for key, value in payload.items():
        if value == _MASKED:
            skipped_masked.append(key)
            continue
        to_write[key] = str(value) if value is not None else None

    if dry_run or not do_apply:
        return {
            "ok": True,
            "dry_run": True,
            "action": "preview",
            "keys_to_write": list(to_write.keys()),
            "keys_skipped_masked": skipped_masked,
            "message": "Previsualización — no se han escrito ajustes",
        }

    updated = _write_settings_to_db(to_write)
    return {
        "ok": True,
        "dry_run": False,
        "action": "imported",
        "keys_written": updated,
        "keys_skipped_masked": skipped_masked,
        "message": f"Importación completada: {updated} ajustes escritos",
    }
