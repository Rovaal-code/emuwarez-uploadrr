"""eMuwarez API connector.

eMuwarez runs on the UNIT3D platform (https://emu-warez.com).
UNIT3D API authentication uses ?api_token=<key> as a query parameter.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Iterable, Optional

from .base import IntegrationError, build_url, request_json
from ..constants import EMU_BASE_URL
from ..models import RequestItem

# Ids de UNIT3D en eMuwarez. El filtro de categorías de la API sale de EMU_CATEGORIAS.
EMU_CATEGORIAS = {1: "Películas", 2: "Series", 4: "Documentales"}
EMU_TIPOS = {1: "Full Disc", 2: "Remux", 3: "Encode", 4: "WEB-DL", 5: "WEBRIP", 6: "HDTV", 7: "SD", 8: "STEAMRIP"}
EMU_RESOLUCIONES = {
    1: "4320p", 2: "2160p", 3: "1080p", 4: "1080i", 5: "720p", 6: "576p", 7: "540p", 8: "480p", 10: "Otras",
}


# ---------------------------------------------------------------------------
# UNIT3D-pattern functions (primary, api_token query param)
# ---------------------------------------------------------------------------

def emu_test_connection(api_key: str, base_url: str | None = None) -> dict[str, Any]:
    """Test connectivity to eMuwarez using UNIT3D ?api_token= auth."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, "/api/torrents/filter", {"api_token": api_key, "perPage": "1"})
    return request_json("GET", url)


def emu_get_requests(
    api_key: str,
    base_url: str | None = None,
    page: int = 1,
    per_page: int = 100,
) -> dict[str, Any]:
    """Una página de las peticiones abiertas (sin llenar o reclamadas) de las
    categorías de EMU_CATEGORIAS; el filtro lo aplica el servidor.

    Devuelve la respuesta entera: data[] y meta.last_page / meta.total.
    """
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(
        base,
        "/api/requests/filter",
        {"api_token": api_key, "page": page, "perPage": per_page, "filled": 0,
         "category_id[]": list(EMU_CATEGORIAS)},
    )
    return _pedir_pagina(url)


def emu_get_request_detail(
    api_key: str,
    request_id: int,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Fetch detail for a single EMU request by ID."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, f"/api/requests/{request_id}", {"api_token": api_key})
    return request_json("GET", url)


def emu_get_user(api_key: str, base_url: str | None = None) -> dict[str, Any]:
    """Tu cuenta (/api/user): usuario, grupo, subido, bajado, ratio, buffer, seeding, leeching, bonus y H&R."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, "/api/user", {"api_token": api_key})
    try:
        data = request_json("GET", url)
    except IntegrationError as exc:
        if exc.status in _MENSAJE_POR_ESTADO:
            raise IntegrationError(_MENSAJE_POR_ESTADO[exc.status], status=exc.status) from None
        raise
    if not isinstance(data, dict) or not data.get("username"):
        raise IntegrationError("eMuwarez ha devuelto tu perfil en un formato que no se reconoce")
    return data


def emu_fetch_all_pages(
    api_key: str, base_url: str | None = None, progress=None
) -> tuple[list[dict[str, Any]], Optional[int]]:
    """Recorre las peticiones abiertas página a página, con una pausa entre una y otra.

    Devuelve (filas, total). `total` es el meta.total de eMuwarez, o None si no
    vino o cambió durante el recorrido: entonces no se puede dar por completo.
    Lanza IntegrationError si el recorrido no puede terminar.

    `progress(pagina, ultima_pagina, filas_hasta_ahora)` se llama tras cada página.
    """
    filas: list[dict[str, Any]] = []
    totales: set[Optional[int]] = set()
    pagina = ultima = 1
    while pagina <= ultima:
        if pagina > 1:
            time.sleep(EMU_PETICIONES_INTERVALO)
        try:
            data = emu_get_requests(api_key, base_url=base_url, page=pagina)
        except IntegrationError as exc:
            if exc.status in _MENSAJE_POR_ESTADO:
                raise IntegrationError(_MENSAJE_POR_ESTADO[exc.status], status=exc.status) from None
            raise
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise IntegrationError("eMuwarez ha devuelto las peticiones en un formato que no se reconoce")
        filas.extend(data["data"])
        meta = data["meta"] if isinstance(data.get("meta"), dict) else {}
        ultima = _entero(meta.get("last_page")) or 1
        if ultima > EMU_PETICIONES_MAX_PAGINAS:
            raise IntegrationError(
                f"eMuwarez tiene más de {EMU_PETICIONES_MAX_PAGINAS} páginas de peticiones abiertas; no se sincronizan")
        totales.add(_entero(meta.get("total")))
        if progress:
            try:
                progress(pagina, ultima, len(filas))
            except Exception:  # noqa: BLE001 — el progreso es lo de menos
                pass
        pagina += 1
    return filas, (totales.pop() if len(totales) == 1 else None)


# eMuwarez rate-limits the API to 30 requests/minute (x-ratelimit-limit: 30)
# and caps perPage at 100 server-side, so a full ~13k-torrent catalog is ~130
# sequential requests. 2,2 s entre peticiones queda por debajo del límite (cada
# petición tarda además ~3 s); antes eran 6 s y la completa tardaba 17 min.
EMU_MIN_REQUEST_INTERVAL = 2.2  # seconds between torrent-catalog requests
# Pocas páginas, y la clave la comparten Sonarr, Radarr, qui, autobrr y las subidas: se va despacio.
EMU_PETICIONES_INTERVALO = 6.0  # seconds between request pages
EMU_PETICIONES_MAX_PAGINAS = 50
# Si aun así llega un 429, se espera a que se vacíe la ventana del minuto y se repite la página.
EMU_ESPERA_429 = 60.0
EMU_REINTENTOS_429 = 3

# Lo que se enseña en vez del texto de request_json, que lleva la URL.
_MENSAJE_POR_ESTADO = {
    401: "eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)",
    403: "eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)",
    429: "eMuwarez ha limitado las peticiones; prueba en unos minutos",
}


def _pedir_pagina(url: str) -> Any:
    for intento in range(EMU_REINTENTOS_429 + 1):
        try:
            return request_json("GET", url)
        except IntegrationError as e:
            if e.status != 429 or intento == EMU_REINTENTOS_429:
                raise
            time.sleep(EMU_ESPERA_429)


def emu_fetch_all_torrents(
    api_key: str,
    base_url: str | None = None,
    per_page: int = 100,
    max_pages: int = 500,
    progress=None,
    stop_after_id: int | None = None,
    min_interval: float = EMU_MIN_REQUEST_INTERVAL,
) -> list[dict[str, Any]]:
    """Fetch eMuwarez torrents (paginated /api/torrents/filter), newest first.
    Returns the flat list of raw torrent objects ({type, id, attributes}).

    Incremental: when `stop_after_id` is given, the walk stops as soon as a
    torrent already known (id <= stop_after_id) is reached — so only the
    newly-uploaded torrents come back, instead of re-downloading the whole
    catalog. Se pide ordenado por created_at desc (UNIT3D ordena por defecto por bumped_at, y un torrent
    antiguo resubido saldría el primero y cortaría el recorrido): los ids bajan página a página y el primer
    id conocido significa que lo que sigue también se conoce.

    Requests are paced to `min_interval` seconds apart (rate limit).

    `progress(page, total_pages, items_so_far, total_items)` is called after each
    page (total_pages/total_items from the API `meta`, or None if absent)."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    all_items: list[dict[str, Any]] = []
    total_pages: int | None = None
    total_items: int | None = None
    page = 1
    reached_known = False
    while page <= max_pages and not reached_known:
        if page > 1:
            time.sleep(min_interval)  # rate limit (see EMU_MIN_REQUEST_INTERVAL)
        url = build_url(base, "/api/torrents/filter", {
            "api_token": api_key, "perPage": str(per_page), "page": str(page),
            "sortField": "created_at", "sortDirection": "desc",
        })
        data = _pedir_pagina(url)
        items = data.get("data") if isinstance(data, dict) else None
        meta = data.get("meta") if isinstance(data, dict) else None
        if isinstance(meta, dict):
            total_pages = meta.get("last_page") or total_pages
            total_items = meta.get("total") or total_items
        if not isinstance(items, list) or not items:
            break
        if stop_after_id is not None:
            for t in items:
                try:
                    tid = int(t.get("id") or 0)
                except (TypeError, ValueError):
                    tid = 0
                if tid <= stop_after_id:
                    reached_known = True
                    break
                all_items.append(t)
        else:
            all_items.extend(items)
        if progress:
            try:
                progress(page, total_pages, len(all_items), total_items)
            except Exception:  # noqa: BLE001 — progress is best-effort
                pass
        if len(items) < per_page:
            break
        page += 1
    return all_items


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _entero(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _id_externo(value: Any) -> Optional[str]:
    """tmdb/tvdb/mal como texto; None si falta o es 0 (UNIT3D guarda 0 para «sin id»)."""
    n = _entero(value)
    return str(n) if n else None


_ESPECIALES = re.compile(r"\b(?:especiales?|specials?)\b", re.I)


def normalize_request(raw: dict[str, Any]) -> RequestItem:
    """Una fila plana de /api/requests/filter. Sea cual sea el campo que falte, no falla."""
    emu_id = str(raw.get("id", ""))
    imdb = _entero(raw.get("imdb"))
    usuario = raw.get("user")
    autor = usuario if usuario and str(usuario).lower() != "anonymous" else None
    titulo = str(raw.get("name") or "Sin título")
    temporada, capitulo = _entero(raw.get("season_number")), _entero(raw.get("episode_number"))
    # UNIT3D guarda 0 para «sin temporada»: es la serie entera salvo que el nombre diga Especiales.
    if temporada == 0 and not capitulo and not _ESPECIALES.search(titulo):
        temporada = None
    return RequestItem(
        id=None,
        emu_id=emu_id,
        title=titulo,
        category=EMU_CATEGORIAS.get(_entero(raw.get("category_id"))),
        requested_source=EMU_TIPOS.get(_entero(raw.get("type_id"))),
        requested_resolution=EMU_RESOLUCIONES.get(_entero(raw.get("resolution_id"))),
        emu_status=raw.get("status"),
        points=_entero(raw.get("bounty")),
        created_at=raw.get("created"),
        tmdb_id=_id_externo(raw.get("tmdb")),
        imdb_id=f"tt{imdb:07d}" if imdb else None,
        tvdb_id=_id_externo(raw.get("tvdb")),
        mal_id=_id_externo(raw.get("mal")),
        url=f"{EMU_BASE_URL}/requests/{emu_id}",
        author=autor,
        author_visible=autor is not None,
        req_scope="episode" if capitulo else "season" if temporada is not None else None,
        req_season=temporada,
        req_episode=capitulo,
        raw_json=json.dumps(raw, ensure_ascii=False),
    )


def normalize_requests(raw_items: Iterable[dict[str, Any]]) -> list[RequestItem]:
    return [normalize_request(item) for item in raw_items if isinstance(item, dict) and item.get("id") is not None]
