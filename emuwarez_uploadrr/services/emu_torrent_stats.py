"""Las estadísticas que eMuwarez da de un torrent que subiste: seeders, leechers y veces completado.

La subida guarda la ficha del torrent (`upload_jobs.result_tracker`, la línea `Torrent URL:` de Uploadrr-EMU); de ella
sale solo el id numérico (`/torrents/<id>`) y se pide `GET /api/torrents/<id>` a eMuwarez (la constante `EMU_BASE_URL`), nunca a
la URL que traiga la subida. Una llamada por subida y no por la lista: la clave de eMuwarez la comparten Sonarr, Radarr, qui
y las subidas con 30 peticiones por minuto, así que solo se pide al abrir el detalle, con una caché corta en memoria.
La respuesta nunca lleva la URL ni la clave. Solo lectura.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..integrations.base import IntegrationError, texto_de_error
from ..integrations.emu import emu_get_torrent
from .settings import get_setting_canonical

logger = logging.getLogger(__name__)

TTL_CACHE = 300.0       # segundos que vale una lectura buena
TTL_FALLO = 30.0        # y una fallida
_FICHA = re.compile(r"/torrents/(\d+)(?:[/?#]|$)")

_lock = threading.Lock()
_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}


def id_de_la_ficha(url: Optional[str]) -> Optional[int]:
    """El id del torrent en una URL de ficha (`https://…/torrents/123`), o None."""
    encontrada = _FICHA.search(url or "")
    return int(encontrada.group(1)) if encontrada else None


def _entero(valor: Any) -> Optional[int]:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _resumir(atributos: dict[str, Any]) -> dict[str, Any]:
    return {
        "seeders": _entero(atributos.get("seeders")),
        "leechers": _entero(atributos.get("leechers")),
        "completadas": _entero(atributos.get("times_completed")),
        "freeleech": str(atributos["freeleech"]) if atributos.get("freeleech") not in (None, "", "0%") else None,
        "doble_subida": bool(atributos.get("double_upload")),
    }


def estadisticas_de_la_subida(conn: sqlite3.Connection, job_id: int, *, refrescar: bool = False) -> dict[str, Any]:
    """`{aplica, configurado, disponible, mensaje, actualizado, seeders, leechers, completadas, ...}`.
    `aplica` es falso si la subida no existe o no llegó a eMuwarez (sin ficha). Un fallo del tracker es
    `disponible: false` con su mensaje, nunca una excepción."""
    fila = conn.execute("SELECT status, result_tracker FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
    torrent_id = id_de_la_ficha(fila["result_tracker"]) if fila and fila["status"] == "completed" else None
    base = {"aplica": torrent_id is not None, "configurado": False, "disponible": False, "mensaje": None,
            "actualizado": None}
    if torrent_id is None:
        return base
    clave = (get_setting_canonical(conn, "emu.api_key") or "").strip()
    if not clave:
        return {**base, "mensaje": "Falta la API key de eMuwarez en Configuración."}
    base["configurado"] = True
    huella = hashlib.sha256(clave.encode()).hexdigest()
    llave = (huella, torrent_id)
    ahora = time.monotonic()
    with _lock:
        guardado = _cache.get(llave)
        if guardado and not refrescar and ahora - guardado[0] < (TTL_CACHE if guardado[1].get("disponible") else TTL_FALLO):
            return {**base, **guardado[1]}
    try:
        atributos = emu_get_torrent(clave, torrent_id)
        resultado = {"disponible": True, "actualizado": datetime.now(timezone.utc).isoformat(), **_resumir(atributos)}
    except IntegrationError as exc:
        logger.warning("No se pudieron leer las estadísticas del torrent %s en eMuwarez: %s", torrent_id, texto_de_error(exc))
        resultado = {"disponible": False, "mensaje": texto_de_error(exc)}
    with _lock:
        _cache[llave] = (time.monotonic(), resultado)
    return {**base, **resultado}


def olvidar_cache() -> None:
    with _lock:
        _cache.clear()
