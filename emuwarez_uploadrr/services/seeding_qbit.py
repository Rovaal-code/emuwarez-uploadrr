"""La salud del seeding de cada subida completada, leída de qBittorrent. Solo lectura.

CÓMO SE CASA UNA SUBIDA CON SU TORRENT. La aplicación no guarda el info-hash: Uploadrr-EMU no lo imprime, y sacarlo
pediría una columna nueva y leer el .torrent (que vive en su `tmp`, que se limpia). Lo que sí sabe es la ruta que le
entregó (`upload_jobs.prepared_path`, dentro de `UPLOADRR_UPLOADS_DIR`), y Uploadrr-EMU se la pasa a qBittorrent como
ruta de guardado, así que el torrent acaba con `content_path` igual a esa ruta. En orden de fiabilidad:

1. `content_path` == ruta de la subida.
2. `save_path` + `name` == ruta de la subida (qBittorrent sin `content_path`, o con otro `content_layout`).
3. El nombre == el último trozo de la ruta, y solo si el torrent es de las subidas: lleva la etiqueta de Ajustes o,
   sin etiqueta, su `save_path` cuelga de la carpeta de subidas. Un torrent bajado con el mismo nombre de release
   desde otro sitio no cuenta.

En cada paso, si hay varios candidatos se estrecha por la etiqueta (la de Ajustes) y, si siguen siendo varios, el
casamiento es ambiguo: NO se adivina ni se baja al paso siguiente, la subida queda en «No se encuentra».

«FALTAN FICHEROS»: el estado `missingFiles` de qBittorrent, o `error` con el progreso por debajo del 100 %.

Una sola consulta en bloque a qBittorrent (`/torrents/info` de todos), con una caché corta en memoria: la lista de
Subidas y el detalle piden lo mismo a la vez. Un fallo también se recuerda unos segundos, para que un qBittorrent
caído no haga esperar cada petición. Ni la URL ni las credenciales salen de aquí, ni en la respuesta ni en el registro.
"""
from __future__ import annotations

import logging
import math
import posixpath
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..integrations import http_cliente
from ..integrations.base import texto_de_error
from ..integrations.qbittorrent import ErrorQbit, qbit_listar_torrents
from .ajustes_registro import error_de_url_publica
from .carpeta_subida import RAIZ_SUBIDAS
from .settings import get_setting_canonical

logger = logging.getLogger(__name__)

TTL_CACHE = 60.0            # segundos que vale una lista bien leída
TTL_FALLO = 15.0            # y uno fallido
_TIMEOUT = 5                # por intento
_INTENTOS = 2               # un reintento si no hay conexión (no si las credenciales fallan)
_PLAZO_TOTAL = 20.0         # reloj de toda la consulta, DNS incluido

# estado de qBittorrent -> (clave estable, etiqueta). `error` y `missingFiles` se miran aparte.
_ESTADOS: dict[str, tuple[str, str]] = {
    "uploading": ("sembrando", "Sembrando"),
    "stalledUP": ("sembrando", "Sembrando"),
    "forcedUP": ("sembrando", "Sembrando"),
    "queuedUP": ("en_cola", "En cola"),
    "pausedUP": ("pausado", "Pausado"),
    "stoppedUP": ("pausado", "Pausado"),
    "pausedDL": ("pausado", "Pausado"),
    "stoppedDL": ("pausado", "Pausado"),
    "checkingUP": ("comprobando", "Comprobando"),
    "checkingDL": ("comprobando", "Comprobando"),
    "checkingResumeData": ("comprobando", "Comprobando"),
    "moving": ("moviendo", "Moviendo"),
    "allocating": ("incompleto", "Incompleto"),
    "downloading": ("incompleto", "Incompleto"),
    "forcedDL": ("incompleto", "Incompleto"),
    "stalledDL": ("incompleto", "Incompleto"),
    "queuedDL": ("incompleto", "Incompleto"),
    "metaDL": ("incompleto", "Incompleto"),
    "forcedMetaDL": ("incompleto", "Incompleto"),
}
ETIQUETAS = {
    "error": "Error", "faltan_ficheros": "Faltan ficheros", "no_encontrado": "No se encuentra",
    "desconocido": "Desconocido",
}

MENSAJE_SIN_CONFIGURAR = "qBittorrent no está configurado"
MENSAJE_SIN_RESPUESTA = "No se pudo conectar con qBittorrent"

_candado = threading.Lock()
# (huella de la configuración, cuándo, lista | None si falló, mensaje del fallo)
_cache: Optional[tuple[tuple[str, str, str], float, Optional[list[dict[str, Any]]], str]] = None


def olvidar_cache() -> None:
    global _cache
    with _candado:
        _cache = None


def _norm(ruta: Any) -> str:
    return str(ruta or "").replace("\\", "/").rstrip("/")


def _etiquetas(t: dict[str, Any]) -> set[str]:
    return {e.strip() for e in str(t.get("tags") or "").split(",") if e.strip()}


def _numero(valor: Any, por_defecto: Optional[float] = None) -> Optional[float]:
    if not isinstance(valor, (int, float)) or isinstance(valor, bool):
        return por_defecto
    numero = float(valor)
    return numero if math.isfinite(numero) else por_defecto  # inf y nan no caben en el JSON de la respuesta


def _resumir(t: dict[str, Any]) -> dict[str, Any]:
    """Lo único que se guarda de cada torrent de qBittorrent."""
    return {
        "hash": str(t.get("hash") or ""), "name": str(t.get("name") or ""),
        "save_path": _norm(t.get("save_path")), "content_path": _norm(t.get("content_path")),
        "state": str(t.get("state") or ""), "tags": str(t.get("tags") or ""),
        "progress": _numero(t.get("progress"), 0.0), "ratio": _numero(t.get("ratio"), 0.0),
        "uploaded": int(_numero(t.get("uploaded"), 0) or 0),
        "num_complete": _numero(t.get("num_complete")), "num_incomplete": _numero(t.get("num_incomplete")),
    }


def _configuracion(conn: sqlite3.Connection) -> tuple[str, str, str, str]:
    """(url, usuario, contraseña, etiqueta). Con el proxy de qui se consulta ese, sin credenciales (como la subida)."""
    qui = (get_setting_canonical(conn, "qbit.qui_proxy_url") or "").strip()
    etiqueta = (get_setting_canonical(conn, "qbit.tag") or "").strip()
    if qui:
        return qui, "", "", etiqueta
    return ((get_setting_canonical(conn, "qbit.url") or "").strip(),
            get_setting_canonical(conn, "qbit.username") or "", get_setting_canonical(conn, "qbit.password") or "",
            etiqueta)


def _consultar(url: str, usuario: str, clave: str) -> list[dict[str, Any]]:
    """La lista de qBittorrent con un reintento si no hay conexión y un reloj para toda la consulta."""
    def _una_vez() -> list[dict[str, Any]]:
        ultimo: Optional[ErrorQbit] = None
        for _ in range(_INTENTOS):
            try:
                return [_resumir(t) for t in qbit_listar_torrents(url, None, usuario, clave, timeout=_TIMEOUT)]
            except ErrorQbit as exc:
                if exc.credenciales:
                    raise
                ultimo = exc
        raise ultimo or ErrorQbit(MENSAJE_SIN_RESPUESTA)

    try:
        return http_cliente.con_plazo(_una_vez, _PLAZO_TOTAL)
    except http_cliente.PlazoAgotado:
        raise ErrorQbit(MENSAJE_SIN_RESPUESTA) from None


def _torrents(url: str, usuario: str, clave: str, *, refrescar: bool) -> tuple[Optional[list[dict[str, Any]]], str, float]:
    """(torrents | None, motivo del fallo, cuándo se leyó), de la caché si sigue vigente."""
    global _cache
    huella = (url, usuario, clave)
    with _candado:  # uno solo consulta; el que espera detrás encuentra la caché
        ahora = time.time()
        if _cache and _cache[0] == huella and not refrescar:
            ttl = TTL_CACHE if _cache[2] is not None else TTL_FALLO
            if ahora - _cache[1] < ttl:
                return _cache[2], _cache[3], _cache[1]
        try:
            lista, motivo = _consultar(url, usuario, clave), ""
        except ErrorQbit as exc:
            lista, motivo = None, texto_de_error(exc, clave)
            # Ni la excepción ni la URL: solo que falló.
            logger.warning("Seeding: no se pudo leer qBittorrent (%s)", motivo)
        _cache = (huella, time.time(), lista, motivo)
        return lista, motivo, _cache[1]


def estado_de(t: dict[str, Any]) -> tuple[str, str]:
    """(clave, etiqueta) del estado de un torrent ya resumido."""
    estado, progreso = t.get("state", ""), t.get("progress") or 0.0
    if estado == "missingFiles" or (estado == "error" and progreso < 1):
        return "faltan_ficheros", ETIQUETAS["faltan_ficheros"]
    if estado == "error":
        return "error", ETIQUETAS["error"]
    if estado in _ESTADOS:
        clave, etiqueta = _ESTADOS[estado]
        # Un torrent que debía estar entero y no lo está: parado o en cola sin todos los datos.
        if clave in ("pausado", "en_cola") and progreso < 1:
            return "incompleto", "Incompleto"
        return clave, etiqueta
    return "desconocido", ETIQUETAS["desconocido"]


def _unico(candidatos: list[dict[str, Any]], etiqueta: str) -> Optional[dict[str, Any]]:
    """El torrent si solo hay uno (estrechando por la etiqueta si hace falta); None si no hay o es ambiguo."""
    if len(candidatos) > 1 and etiqueta:
        candidatos = [t for t in candidatos if etiqueta in _etiquetas(t)]
    return candidatos[0] if len(candidatos) == 1 else None


def _indices(torrents: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    por_contenido: dict[str, list[dict[str, Any]]] = {}
    por_guardado: dict[str, list[dict[str, Any]]] = {}
    por_nombre: dict[str, list[dict[str, Any]]] = {}
    for t in torrents:
        if t["content_path"]:
            por_contenido.setdefault(t["content_path"], []).append(t)
        if t["save_path"] and t["name"]:
            por_guardado.setdefault(f"{t['save_path']}/{t['name']}", []).append(t)
        if t["name"]:
            por_nombre.setdefault(t["name"], []).append(t)
    return {"contenido": por_contenido, "guardado": por_guardado, "nombre": por_nombre}


def casar(ruta: Optional[str], indices: dict[str, dict[str, list[dict[str, Any]]]], etiqueta: str,
          raiz: str = RAIZ_SUBIDAS) -> tuple[Optional[dict[str, Any]], str]:
    """(torrent, cómo se casó: 'ruta' | 'nombre' | ''). Sin torrent si no hay ninguno o el casamiento es ambiguo."""
    ruta = _norm(ruta)
    if not ruta:
        return None, ""
    for indice in (indices["contenido"], indices["guardado"]):
        candidatos = indice.get(ruta)
        if candidatos:
            elegido = _unico(candidatos, etiqueta)
            return elegido, "ruta" if elegido else ""
    raiz = _norm(raiz)
    propios = [
        t for t in indices["nombre"].get(posixpath.basename(ruta), [])
        if (etiqueta in _etiquetas(t) if etiqueta else t["save_path"] == raiz or t["save_path"].startswith(raiz + "/"))
    ]
    elegido = _unico(propios, etiqueta)
    return elegido, "nombre" if elegido else ""


def _entrada(job_id: int, t: Optional[dict[str, Any]], como: str) -> dict[str, Any]:
    if t is None:
        return {"job_id": job_id, "estado": "no_encontrado", "etiqueta": ETIQUETAS["no_encontrado"]}
    clave, etiqueta = estado_de(t)
    peers = t["num_incomplete"]
    seeds = t["num_complete"]
    return {
        "job_id": job_id, "estado": clave, "etiqueta": etiqueta,
        "ratio": round(t["ratio"], 2), "subido": t["uploaded"], "progreso": round(t["progress"], 4),
        # El enjambre entero (num_complete / num_incomplete); -1 es que qBittorrent no lo sabe.
        "seeds": int(seeds) if seeds is not None and seeds >= 0 else None,
        "peers": int(peers) if peers is not None and peers >= 0 else None,
        "hash": t["hash"], "casamiento": como,
    }


def url_publica(conn: sqlite3.Connection) -> Optional[str]:
    """La URL con la que el usuario abre la WebUI de qBittorrent (ajuste opcional), o None. Se vuelve a comprobar
    al leerla: una copia de configuración restaurada no pasó por la validación del PUT, y una URL con credenciales
    no sale nunca."""
    url = (get_setting_canonical(conn, "qbit.public_url") or "").strip()
    return url if url and error_de_url_publica(url) is None else None


def salud_del_seeding(conn: sqlite3.Connection, *, refrescar: bool = False) -> dict[str, Any]:
    """Para cada subida con torrent subido, su estado en qBittorrent.

    Devuelve {configurado, disponible, mensaje, actualizado, items, url_publica}. Sin qBittorrent configurado o
    sin respuesta,
    `items` va vacío y `disponible` es False: quien lo pide enseña «Sin datos de qBittorrent» y sigue."""
    url, usuario, clave, etiqueta = _configuracion(conn)
    publica = url_publica(conn)
    if not url:
        return {"configurado": False, "disponible": False, "mensaje": MENSAJE_SIN_CONFIGURAR,
                "actualizado": None, "items": [], "url_publica": publica}
    torrents, motivo, leido = _torrents(url, usuario, clave, refrescar=refrescar)
    actualizado = datetime.fromtimestamp(leido, tz=timezone.utc).isoformat(timespec="seconds")
    if torrents is None:
        return {"configurado": True, "disponible": False, "mensaje": motivo or MENSAJE_SIN_RESPUESTA,
                "actualizado": actualizado, "items": [], "url_publica": publica}
    indices = _indices(torrents)
    filas = conn.execute(
        "SELECT id, prepared_path FROM upload_jobs WHERE status = 'completed' OR torrent_subido = 1 ORDER BY id"
    ).fetchall()
    items = []
    for fila in filas:
        t, como = casar(fila["prepared_path"], indices, etiqueta)
        items.append(_entrada(fila["id"], t, como))
    return {"configurado": True, "disponible": True, "mensaje": None, "actualizado": actualizado,
            "items": items, "url_publica": publica}
