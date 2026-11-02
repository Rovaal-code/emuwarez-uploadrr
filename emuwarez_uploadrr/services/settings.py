"""La ÚNICA puerta a la tabla `settings`.

Las claves usan espacios de nombres con punto: tmdb.api_key, emu.api_key,
uploadrr.path… Los secretos se guardan con is_secret=1 y salen enmascarados en
las respuestas del API: primeros 4 + "…" + últimos 4, si pasan de 8 caracteres.

Vivía en `web/services/` hasta el 2026-08-01, y eso obligaba a los servicios a
importar hacia arriba, de la capa de dominio a la web (auditoría, hallazgo
6.1). Leer un ajuste es cosa del dominio; enmascarar un secreto para una
respuesta HTTP, de la web.

**Nadie consulta la tabla por su cuenta.** Había 14 `SELECT ... FROM settings`
repartidos que se saltaban el mapa de alias de claves antiguas, y de ahí salió
un fallo real: Diagnóstico decía "Secretos sin configurar" a quien las tenía
puestas, por preguntar por la grafía con guion bajo. Lo vigila
tests/test_una_sola_puerta_a_settings.py.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..database import CANONICAL_SETTING_ALIASES
from ..database import get_setting_canonical as _get_setting_canonical
from .ajustes_registro import AJUSTES, CLAVES_SECRETAS, a_texto, desde_texto

# Las claves secretas que expone Configuración están en el registro
# (services/ajustes_registro.py). Lo que también es una clave aunque no salga
# allí: emu.endpoint_url (lleva la clave en la query), los alias antiguos con
# guion bajo de los secretos del registro y las API keys de los hosts de
# imágenes (una por host, imghost.key.<id>). widget.api_key_hash es el hash de la
# clave del widget de Homepage (services/widget.py): no se edita desde un PUT.
_OTROS_SECRETOS: frozenset[str] = frozenset(
    ["emu.endpoint_url", "widget.api_key_hash"]
    + [CANONICAL_SETTING_ALIASES[k] for k in CLAVES_SECRETAS if k in CANONICAL_SETTING_ALIASES]
)
_PREFIJOS_SECRETOS: tuple[str, ...] = ("imghost.key.",)


def es_secreto(key: str) -> bool:
    """Si el ajuste guarda una clave. Lo usa también la copia de configuración
    (services/backup_service.py), que las deja vacías si no se piden."""
    return key in CLAVES_SECRETAS or key in _OTROS_SECRETOS or key.startswith(_PREFIJOS_SECRETOS)


def _is_secret(key: str) -> int:
    return 1 if es_secreto(key) else 0


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return value[:4] + "…" + value[-4:]


def get_setting_raw(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    """Lee la clave TAL CUAL, sin resolver el alias antiguo con guion bajo.

    Se llama `_raw` a propósito: para casi todo lo que quieres es
    `get_setting_canonical`. Esta solo sirve cuando de verdad te interesa esa
    clave exacta y ninguna otra (por ejemplo al exportar la configuración). Se
    llamaba `get_setting` y elegirla mal era un descuido silencioso."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a setting. Does NOT commit."""
    conn.execute(
        """
        INSERT INTO settings (key, value, is_secret, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            is_secret = excluded.is_secret,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value, _is_secret(key)),
    )


def get_setting_canonical(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    """Read `key` (a canonical dotted key), falling back to its legacy
    underscore alias when unset. Dotted always wins. See
    database.CANONICAL_SETTING_ALIASES for the alias table."""
    return _get_setting_canonical(conn, key, default)


def set_setting_canonical(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write a setting using its canonical dotted key only. Never writes the
    legacy underscore alias — new writes should only ever produce one key."""
    set_setting(conn, key, value)


def get_secret_setting(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    """Same as get_setting_canonical, for call sites reading a secret
    (tmdb.api_key / emu.api_key) — returns the raw value, never masked."""
    return _get_setting_canonical(conn, key, default)


def set_secret_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    set_setting(conn, key, value)


def get_configured(conn: sqlite3.Connection, key: str) -> bool:
    """Return True if key (or its legacy underscore alias) has a non-empty value."""
    v = _get_setting_canonical(conn, key)
    return bool(v and v.strip())


def get_settings_status(conn: sqlite3.Connection) -> dict:
    """Return a summary of each configuration section, with masked values."""
    def _entry(key: str) -> dict:
        value = _get_setting_canonical(conn, key)
        configured = bool(value and value.strip())
        if configured and _is_secret(key):
            masked = mask_secret(value)  # type: ignore[arg-type]
        else:
            masked = value if configured else None
        return {"configured": configured, "masked_value": masked}

    return {
        "tmdb": _entry("tmdb.api_key"),
        "emu_api_key": _entry("emu.api_key"),
        "emu_endpoint": _entry("emu.endpoint_url"),
        "uploadrr_path": _entry("uploadrr.path"),
        "uploadrr_python_path": _entry("uploadrr.python_path"),
        "uploadrr_runtime_type": _entry("uploadrr.runtime_type"),
        "uploadrr_timeout": _entry("uploadrr.timeout"),
        "uploadrr_allowed_roots": _entry("uploadrr.allowed_roots"),
    }


def all_settings(conn: sqlite3.Connection) -> dict[str, Optional[str]]:
    """Toda la tabla, clave -> valor. Para exportar la configuración, que es
    el único caso donde interesa el contenido entero y literal: sin resolver
    alias, sin enmascarar."""
    try:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    except Exception:
        return {}


def setting_exists(conn: sqlite3.Connection, key: str) -> bool:
    """Si la clave EXACTA está en la tabla. No mira el alias antiguo: quien
    pregunta esto está decidiendo entre INSERT y UPDATE, no leyendo un valor."""
    return conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone() is not None


def leer_ajuste(conn: sqlite3.Connection, campo: str) -> Any:
    """El valor de un ajuste del registro, ya convertido y con su valor por
    defecto. `campo` es su nombre en el API (ajustes_registro.AJUSTES)."""
    ajuste = AJUSTES[campo]
    return desde_texto(ajuste, _get_setting_canonical(conn, ajuste.clave))


def escribir_ajuste(conn: sqlite3.Connection, campo: str, valor: Any) -> None:
    """Guarda un valor ya validado (ajustes_registro.error_de). Does NOT commit."""
    ajuste = AJUSTES[campo]
    set_setting(conn, ajuste.clave, a_texto(ajuste, valor))


def estado_secreto(conn: sqlite3.Connection, campo: str) -> tuple[bool, Optional[str]]:
    """Si un secreto del registro está puesto, y enmascarado si lo está."""
    value = _get_setting_canonical(conn, AJUSTES[campo].clave)
    if value and value.strip():
        return True, mask_secret(value)
    return False, None
