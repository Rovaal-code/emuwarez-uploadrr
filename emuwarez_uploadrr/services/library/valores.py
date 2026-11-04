"""Valores de filtro de cada columna de Biblioteca (con su caché) y campos de ficha."""
from __future__ import annotations

import time


from .rollups import _provider_label


def library_filter_values(conn) -> dict:
    """Los valores que de verdad existen en la biblioteca, para el desplegable
    de filtro de cada columna de Biblioteca.

    Estilo Excel: un filtro solo ofrece lo que ocurre en los datos, nunca una
    lista fija inventada (LocalStatus tiene una decena de valores posibles y
    solo deben salir los que algún elemento tiene de verdad). Vivía dentro del
    endpoint con sus nueve consultas y su criterio de ordenación por calidad
    real (auditoría, hallazgo 6.2).
    """
    import json as _json

    qrows = conn.execute(
        "SELECT DISTINCT resolution, source FROM library_items "
        "WHERE resolution IS NOT NULL OR source IS NOT NULL"
    ).fetchall()
    # Order by real quality: resolution first (higher → better), then source.
    _RES_RANK = {"4320p": 8, "2160p": 7, "1080p": 6, "1080i": 5, "720p": 4, "576p": 3, "540p": 2, "480p": 1}
    _SRC_RANK = {"BDRemux": 6, "Remux": 6, "BluRay": 5, "WEB-DL": 4, "WEBRip": 3, "HDTV": 2, "DVD": 1}
    # Calidad and Source are now their own table columns/filters (see
    # Biblioteca's list view) — each needs its own distinct-values list
    # instead of the old single "resolution · source" combined string.
    resolutions = {r["resolution"] for r in qrows if r["resolution"]}
    sources_seen = {r["source"] for r in qrows if r["source"]}
    qualities = sorted(resolutions, key=lambda r: _RES_RANK.get(r, 0), reverse=True)
    sources = sorted(sources_seen, key=lambda s: _SRC_RANK.get(s, 0), reverse=True)
    prows = conn.execute(
        "SELECT path, source FROM library_items "
        "WHERE item_type IN ('movie', 'episode') AND path IS NOT NULL"
    ).fetchall()
    from ..nomenclature import infer_provider_from_item
    codes = set()
    for r in prows:
        c = infer_provider_from_item({"path": r["path"], "source": r["source"]})
        if c:
            codes.add(c)
    providers = sorted({lbl for c in codes if (lbl := _provider_label(c))})
    release_groups = [r[0] for r in conn.execute(
        "SELECT DISTINCT release_group FROM library_items "
        "WHERE release_group IS NOT NULL AND release_group != '' ORDER BY release_group COLLATE NOCASE"
    ).fetchall()]

    types = [r[0] for r in conn.execute(
        "SELECT DISTINCT item_type FROM library_items WHERE item_type IS NOT NULL ORDER BY item_type"
    ).fetchall()]
    statuses = [r[0] for r in conn.execute(
        "SELECT DISTINCT local_status FROM library_items WHERE local_status IS NOT NULL ORDER BY local_status"
    ).fetchall()]
    request_statuses = [r[0] for r in conn.execute(
        "SELECT DISTINCT request_status FROM library_items WHERE request_status IS NOT NULL ORDER BY request_status"
    ).fetchall()]
    nomenclature_statuses = [r[0] for r in conn.execute(
        "SELECT DISTINCT nomenclature_status FROM library_items WHERE nomenclature_status IS NOT NULL ORDER BY nomenclature_status"
    ).fetchall()]
    instances = [
        {"id": r["id"], "type": r["type"], "name": r["name"]}
        for r in conn.execute(
            "SELECT DISTINCT i.id, i.type, i.name FROM instances i "
            "WHERE EXISTS (SELECT 1 FROM library_items li WHERE li.instance_id = i.id) "
            "ORDER BY i.name"
        ).fetchall()
    ]

    # emu_in_catalog/emu_aportes only get computed by the (throttled)
    # eMuwarez catalog sync — derive both which "¿En eMuwarez?" values and
    # which "Aportes" values actually occur, rather than always offering both
    # fixed options regardless of whether any item currently has them.
    # Valores distintos, no una lectura de todas las filas.
    emu_vistos = {r[0] for r in conn.execute(
        "SELECT DISTINCT emu_in_catalog FROM library_items WHERE emu_in_catalog IN (0, 1)")}
    has_candidate, has_present = 0 in emu_vistos, 1 in emu_vistos
    has_aporte_yes, has_aporte_no = has_candidate, False
    if has_present:
        for (raw,) in conn.execute("SELECT DISTINCT emu_aportes FROM library_items WHERE emu_in_catalog = 1"):
            try:
                aportes = _json.loads(raw) if raw else []
            except (TypeError, ValueError):
                aportes = []
            if aportes:
                has_aporte_yes = True
            else:
                has_aporte_no = True
    emu_states = [v for v, present in [("candidate", has_candidate), ("present", has_present)] if present]
    aporte_states = [v for v, present in [("yes", has_aporte_yes), ("no", has_aporte_no)] if present]

    # Same "only offer what actually occurs" rule for the Español column, ahora
    # con los cuatro casos que enseña la celda. Se calcula con las MISMAS
    # combinaciones que la regla del frontend (utils/castellano.ts) y no
    # mirando has_spanish_audio a secas, que era lo de antes: ofrecería "No"
    # para una fila que la tabla enseña como "Subs".
    #
    # "desconocido" se ofrece aunque parezca raro: en una biblioteca recién
    # sincronizada y sin leer es el único valor que hay, y esconderlo dejaría
    # el filtro sin nada que elegir.
    combinaciones = {(r[0], r[1]) for r in conn.execute(
        "SELECT DISTINCT has_spanish_audio, has_spanish_subs FROM library_items"
    ).fetchall()}

    def _estado(audio, subs) -> str:
        if audio == 1 and subs == 1:
            return "ambos"
        if audio == 1:
            return "audio"
        if subs == 1:
            return "subs"
        if audio == 0 and subs == 0:
            return "no"
        return "desconocido"

    presentes = {_estado(a, s) for a, s in combinaciones}
    spanish_states = [v for v in ("ambos", "audio", "subs", "no", "desconocido")
                      if v in presentes]

    return {
    "providers": providers,
    "qualities": qualities,
    "sources": sources,
    "release_groups": release_groups,
    "types": types,
    "statuses": statuses,
    "request_statuses": request_statuses,
    "nomenclature_statuses": nomenclature_statuses,
    "instances": instances,
    "emu_states": emu_states,
    "aporte_states": aporte_states,
    "spanish_states": spanish_states,
    }


# Calcularlos recorre la biblioteca entera y el desplegable los pide al abrir
# Biblioteca: se guardan hasta que termine una sincronización, y un minuto como
# mucho porque un estado nuevo (una subida acabada) también cambia la lista.
_VALORES_DE_FILTRO_SEGUNDOS = 60
_valores_de_filtro: dict[str, tuple[float, dict]] = {}
# Sube con cada olvidar_valores_de_filtro(): un cálculo que empezó antes de una
# sincronización no guarda lo que leyó, que ya es viejo.
_generacion_de_filtros = 0


def valores_de_filtro(conn) -> dict:
    ruta = getattr(conn, "ruta", None)
    guardado = _valores_de_filtro.get(ruta)
    if guardado and time.monotonic() - guardado[0] < _VALORES_DE_FILTRO_SEGUNDOS:
        return guardado[1]
    generacion = _generacion_de_filtros
    valores = library_filter_values(conn)
    if ruta and generacion == _generacion_de_filtros:
        _valores_de_filtro[ruta] = (time.monotonic(), valores)
    return valores


def olvidar_valores_de_filtro() -> None:
    global _generacion_de_filtros
    _generacion_de_filtros += 1
    _valores_de_filtro.clear()


# Los campos con los que la lista de Subidas adorna cada trabajo: carátula,
# origen, estado de petición… SELECT explícito y no `*` para no arrastrar la
# fila entera por cada trabajo de la lista.
_CAMPOS_ADORNO = (
    "id, item_type, poster_url, backdrop_url, instance_type, instance_name, "
    "request_status, year, instance_id, tmdb_id, title_slug"
)


def _grupos_de_release_de(ids: list[int], conn) -> dict[int, list[str]]:
    """Los grupos de release distintos de cada elemento: el suyo si es un capítulo o una película, y los de todos sus
    capítulos si es una temporada o una serie (los rollups no se guardan, se leen)."""
    marcas = ",".join("?" * len(ids))
    grupos: dict[int, set[str]] = {}
    for fila in conn.execute(
        f"""SELECT li.id AS raiz, d.release_group AS grupo FROM library_items li
            JOIN library_items d ON d.id = li.id OR d.parent_id = li.id
                 OR d.parent_id IN (SELECT id FROM library_items WHERE parent_id = li.id)
            WHERE li.id IN ({marcas}) AND d.release_group IS NOT NULL AND d.release_group <> ''""", tuple(ids)):
        grupos.setdefault(fila["raiz"], set()).add(fila["grupo"])
    return {i: sorted(g, key=str.casefold) for i, g in grupos.items()}


def library_display_fields(item_ids, conn) -> dict[int, dict]:
    """Los campos de adorno de varios elementos, indexados por id. El endpoint
    de Subidas construía el IN a mano."""
    ids = [int(i) for i in item_ids if i]
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    filas = conn.execute(
        f"SELECT {_CAMPOS_ADORNO} FROM library_items WHERE id IN ({marcas})", tuple(ids)
    ).fetchall()
    grupos = _grupos_de_release_de(ids, conn)
    return {r["id"]: {**dict(r), "release_groups": grupos.get(r["id"], [])} for r in filas}


def library_display_fields_one(item_id: int, conn) -> dict | None:
    """Lo mismo para uno solo, con los campos extra que pide la ficha de una
    subida (título, temporada, capítulo, padre)."""
    row = conn.execute(
        f"SELECT {_CAMPOS_ADORNO}, title, season_number, episode_number, parent_id "
        "FROM library_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if not row:
        return None
    return {**dict(row), "release_groups": _grupos_de_release_de([item_id], conn).get(item_id, [])}
