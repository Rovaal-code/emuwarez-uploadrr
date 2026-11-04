"""eMuwarez API connector.

eMuwarez runs on the UNIT3D platform (https://emu-warez.com).
UNIT3D API authentication uses ?api_token=<key> as a query parameter.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional

from . import emu_limitador
from .base import IntegrationError, build_url, request_json
from .emu_limitador import EMU_ESPERA_429
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

def emu_test_connection(api_key: str, base_url: str | None = None, *, interactiva: bool = True) -> dict[str, Any]:
    """Test connectivity to eMuwarez using UNIT3D ?api_token= auth.

    `interactiva=False` cuando es el primer paso de un recorrido largo: espera su turno en vez de fallar."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, "/api/torrents/filter", {"api_token": api_key, "perPage": "1"})
    return _pedir(url, api_key, interactiva=interactiva)


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
    return _pedir_pagina(url, api_key)


def emu_get_request_detail(
    api_key: str,
    request_id: int,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Fetch detail for a single EMU request by ID."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, f"/api/requests/{request_id}", {"api_token": api_key})
    return _pedir(url, api_key, interactiva=True)


def emu_get_torrent(api_key: str, torrent_id: int, base_url: str | None = None) -> dict[str, Any]:
    """Un torrent (/api/torrents/{id}) con sus contadores del tracker: seeders, leechers, times_completed...
    UNIT3D los da en `attributes`; devuelve ese diccionario, o la respuesta entera si viene plana."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, f"/api/torrents/{int(torrent_id)}", {"api_token": api_key})
    data = _pedir(url, api_key, interactiva=True)
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        return data["attributes"]
    if not isinstance(data, dict):
        raise IntegrationError("eMuwarez ha devuelto el torrent en un formato que no se reconoce")
    return data


def emu_get_user(api_key: str, base_url: str | None = None) -> dict[str, Any]:
    """Tu cuenta (/api/user): usuario, grupo, subido, bajado, ratio, buffer, seeding, leeching, bonus y H&R."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    url = build_url(base, "/api/user", {"api_token": api_key})
    try:
        data = _pedir(url, api_key, interactiva=True)
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
    """Recorre las peticiones abiertas página a página, al ritmo del limitador compartido (emu_limitador).

    Devuelve (filas, total). `total` es el meta.total de eMuwarez, o None si no
    vino o cambió durante el recorrido: entonces no se puede dar por completo.
    Lanza IntegrationError si el recorrido no puede terminar.

    `progress(pagina, ultima_pagina, filas_hasta_ahora)` se llama tras cada página.
    """
    filas: list[dict[str, Any]] = []
    totales: set[Optional[int]] = set()
    pagina = ultima = 1
    while pagina <= ultima:
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


# eMuwarez limita la API a 30 peticiones por minuto por clave (x-ratelimit-limit: 30) y perPage a 100, así que el
# catálogo entero (~13k torrents) son ~130 páginas seguidas. El ritmo lo pone emu_limitador, compartido por todas
# las peticiones del proceso: cada recorrido ya no se pausa por su cuenta.
EMU_PETICIONES_MAX_PAGINAS = 50
# Si aun así llega un 429, el limitador pausa a todos EMU_ESPERA_429 s y la página se repite.
EMU_REINTENTOS_429 = 3

# Con estos estados, en la primera página, se prueba otra vez sin pedir un orden (puede ser lo que rechaza).
_RECHAZO_DE_ORDEN = (400, 422, 500)

# Lo que se enseña en vez del texto de request_json, que lleva la URL.
_MENSAJE_POR_ESTADO = {
    401: "eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)",
    403: "eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)",
    429: "eMuwarez ha limitado las peticiones; prueba en unos minutos",
}


def _pedir(url: str, api_key: str, *, interactiva: bool) -> Any:
    """Toda petición a eMuwarez pasa por aquí: espera su turno en el limitador y, si llega un 429, pausa a todos."""
    emu_limitador.esperar_turno(api_key, interactiva=interactiva)
    try:
        return request_json("GET", url)
    except IntegrationError as e:
        if e.status == 429:
            emu_limitador.penalizar(api_key, EMU_ESPERA_429)
        raise


def _pedir_pagina(url: str, api_key: str) -> Any:
    """Una página de un recorrido largo: un 429 se repite, tras la pausa que ya ha puesto `_pedir`."""
    for intento in range(EMU_REINTENTOS_429 + 1):
        try:
            return _pedir(url, api_key, interactiva=False)
        except IntegrationError as e:
            if e.status != 429 or intento == EMU_REINTENTOS_429:
                raise


def emu_fetch_all_torrents(
    api_key: str,
    base_url: str | None = None,
    per_page: int = 100,
    max_pages: int = 500,
    progress=None,
    stop_after_id: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch eMuwarez torrents (paginated /api/torrents/filter), newest first.
    Returns the flat list of raw torrent objects ({type, id, attributes}).

    Incremental: when `stop_after_id` is given, the walk stops as soon as a
    torrent already known (id <= stop_after_id) is reached — so only the
    newly-uploaded torrents come back, instead of re-downloading the whole
    catalog. Se pide ordenado por created_at desc (UNIT3D ordena por defecto por bumped_at, y un torrent
    antiguo resubido saldría el primero y cortaría el recorrido): los ids bajan página a página y el primer
    id conocido significa que lo que sigue también se conoce. Si el tracker rechaza el orden en la primera
    página, el recorrido completo sigue sin él (su orden por defecto) en vez de dejar la sincronización sin
    funcionar; el incremental falla, porque sin orden no puede fiarse de dónde parar.

    El ritmo lo pone el limitador compartido (emu_limitador).

    `progress(page, total_pages, items_so_far, total_items)` is called after each
    page (total_pages/total_items from the API `meta`, or None if absent)."""
    base = (base_url or EMU_BASE_URL).rstrip("/")
    all_items: list[dict[str, Any]] = []
    total_pages: int | None = None
    total_items: int | None = None
    page = 1
    reached_known = False
    orden = {"sortField": "created_at", "sortDirection": "desc"}

    def pedir(n: int) -> Any:
        return _pedir_pagina(build_url(base, "/api/torrents/filter", {
            "api_token": api_key, "perPage": str(per_page), "page": str(n), **orden}), api_key)

    while page <= max_pages and not reached_known:
        try:
            data = pedir(page)
        except IntegrationError as exc:
            # Sin orden, un torrent resubido saldría el primero y cortaría el recorrido incremental: solo se prueba
            # sin él en el completo.
            if page > 1 or not orden or exc.status not in _RECHAZO_DE_ORDEN or stop_after_id is not None:
                raise
            orden = {}
            data = pedir(page)
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
