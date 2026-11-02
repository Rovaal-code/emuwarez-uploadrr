"""El widget para Homepage (gethomepage.dev, widget `customapi`).

`GET /api/widget` devuelve unos pocos contadores. No lo abre una sesión sino una
clave de solo lectura propia: Homepage guarda esa clave en su `services.yaml` (en
claro, a la vista de quien lea esa carpeta), así que no puede ser el token de una
sesión, que lo abre todo. La clave solo sirve para ese endpoint.

De la clave solo se guarda su SHA-256, como los tokens de sesión: se genera con 256
bits de azar, así que no hace falta un hash lento, y ni la base de datos ni una
copia de seguridad pueden devolverla. Se enseña entera una sola vez, al generarla.
Por eso `widget.api_key_hash` cuenta como secreto (services/settings.py): una
copia sin claves no lo lleva.

Los contadores salen de las mismas funciones que alimentan el Panel, no de
consultas nuevas; solo `en_cola` y `subidas_hoy` no existían.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .settings import get_setting_canonical, set_setting

CLAVE_HASH_SETTING = "widget.api_key_hash"
_PREFIJO = "emuw_"


def _hash(clave: str) -> str:
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def clave_configurada(conn: sqlite3.Connection) -> bool:
    return bool((get_setting_canonical(conn, CLAVE_HASH_SETTING) or "").strip())


def generar_clave(conn: sqlite3.Connection) -> str:
    """Una clave nueva, que sustituye a la anterior. Devuelve la clave en claro: es la única vez que existe
    fuera de Homepage. NO confirma."""
    clave = _PREFIJO + secrets.token_urlsafe(32)
    set_setting(conn, CLAVE_HASH_SETTING, _hash(clave))
    return clave


def quitar_clave(conn: sqlite3.Connection) -> None:
    """Desactiva el widget. NO confirma."""
    set_setting(conn, CLAVE_HASH_SETTING, "")


def clave_valida(conn: sqlite3.Connection, candidata: Optional[str]) -> bool:
    """Si `candidata` es la clave vigente. Sin clave puesta, nada vale."""
    guardado = (get_setting_canonical(conn, CLAVE_HASH_SETTING) or "").strip()
    if not guardado or not candidata:
        return False
    return hmac.compare_digest(_hash(candidata), guardado)


def _inicio_de_hoy_utc() -> str:
    """Las 00:00 de hoy en la zona horaria del servidor (TZ), en UTC y en el formato de datetime() de SQLite."""
    from .scheduler import zona_horaria
    ahora = datetime.now(timezone.utc).astimezone(zona_horaria())
    inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    return inicio.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def contadores(conn: sqlite3.Connection) -> dict[str, int]:
    """Los contadores del widget, planos y numéricos para mapearlos a Homepage.

    - peticiones_listas: peticiones «listas para subir» (el contador del Panel).
    - subiendo / subidas_fallidas: los `uploads_running` y `uploads_failed` del Panel. Las fallidas son las que
      siguen en la lista de Subidas: desaparecen al borrarlas o reintentarlas.
    - en_cola: subidas esperando su turno o preparándose (aún no lanzadas).
    - subidas_hoy: subidas terminadas con éxito desde las 00:00 de la zona horaria del servidor.
    """
    from .request_readiness import get_dashboard_readiness_counts
    from .upload_queue import dashboard_upload_counters

    subidas = dashboard_upload_counters(conn)
    listas = get_dashboard_readiness_counts(conn)["requests_ready_to_upload"]

    def _cuenta(sql: str, params: tuple = ()) -> int:
        return int(conn.execute(sql, params).fetchone()[0] or 0)

    en_cola = _cuenta("SELECT COUNT(*) FROM upload_jobs WHERE status IN ('queued', 'staging', 'preparing')")
    # datetime() entiende las dos formas en que se escribe la fecha (con «T» y +00:00, o CURRENT_TIMESTAMP).
    hoy = _cuenta(
        "SELECT COUNT(*) FROM upload_jobs WHERE status = 'completed' "
        "AND datetime(COALESCE(finished_at, updated_at)) >= datetime(?)",
        (_inicio_de_hoy_utc(),),
    )
    return {
        "peticiones_listas": int(listas),
        "subidas_hoy": hoy,
        "subidas_fallidas": subidas["uploads_failed"],
        "en_cola": en_cola,
        "subiendo": subidas["uploads_running"],
    }
