"""Consultas de la lista de Biblioteca (filtros, orden, paginación y recuentos), faltantes, y las
escrituras puntuales de estado de un elemento."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional, Sequence, Union

from ...models import LocalStatus

from .rollups import _provider_label, _specials_clause


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_MISSING_STATUSES = LocalStatus.not_available()


NOT_AVAILABLE_STATUS_FILTER = "__not_available__"

# Sentinel parent_id value meaning "top level only" (WHERE parent_id IS
# NULL) — 0 is never a real row id (AUTOINCREMENT starts at 1), so it's
# safe to use as a sentinel. Must be checked with `is not None`, never a
# bare `if parent_id:`, since 0 would otherwise be mistaken for "no filter".
TOP_LEVEL_PARENT_FILTER = 0


# Una columna filtrada admite varios valores (se suman con OR); las columnas entre sí, con AND.
Filtro = Union[str, int, Sequence[Union[str, int]], None]


def _valores(v: Filtro) -> list:
    if v is None or v == "":
        return []
    return [x for x in ([v] if isinstance(v, (str, int)) else v) if x not in (None, "")]


def _en(columna: str, valores: list, where: list[str], params: list) -> None:
    if valores:
        where.append(f"{columna} IN ({','.join('?' * len(valores))})")
        params.extend(valores)


# Los filtros de columna (Proveedor, Resolución, Source, Grupo) también ocultan:
# un valor con «!» delante es «todo menos este».
def _incluir_excluir(valores: Filtro) -> tuple[list, list]:
    vs = _valores(valores)
    return ([v for v in vs if not v.startswith("!")], [v[1:] for v in vs if v.startswith("!")])


def _en_columna(columna: str, valores: Filtro, where: list[str], params: list) -> None:
    incluir, excluir = _incluir_excluir(valores)
    _en(columna, incluir, where, params)
    if excluir:
        where.append(f"COALESCE({columna}, '') NOT IN ({','.join('?' * len(excluir))})")
        params.extend(excluir)


# Los casos de la columna Español. Tienen que cuadrar EXACTAMENTE con lo que
# enseña la celda (frontend utils/castellano.ts::estadoCastellano) o filtrarías
# por "Audio" y te saldrían filas que dicen otra cosa. Lo vigila
# tests/test_copias_frontend.
_CASTELLANO_SQL = {
    "ambos": "has_spanish_audio = 1 AND has_spanish_subs = 1",
    "audio": "has_spanish_audio = 1 AND COALESCE(has_spanish_subs, 0) != 1",
    "subs": "COALESCE(has_spanish_audio, 0) != 1 AND has_spanish_subs = 1",
    "no": "has_spanish_audio = 0 AND has_spanish_subs = 0",
    # Ni uno ni otro confirmados: no es "no tiene", es que falta leerlo.
    #
    # Todo en positivo con COALESCE, y no con NOT: en SQL `NOT (NULL = 1)`
    # es NULL, no TRUE, así que la versión con NOT no devolvía NINGUNA de
    # las tres filas que tenían que salir. Lo pilló el cruce de los 9 casos
    # contra la regla del frontend.
    "desconocido": (
        "COALESCE(has_spanish_audio, 0) != 1 AND COALESCE(has_spanish_subs, 0) != 1"
        " AND NOT (COALESCE(has_spanish_audio, -1) = 0"
        " AND COALESCE(has_spanish_subs, -1) = 0)"),
}


def _build_library_filter(
    *,
    status: Filtro = None,
    request: Filtro = None,
    nomenclature: Filtro = None,
    item_type: Filtro = None,
    origin: Filtro = None,
    instance_id: Filtro = None,
    parent_id: Optional[int] = None,
    search: Optional[str] = None,
    spanish: Filtro = None,
) -> tuple[list[str], list]:
    """Shared WHERE-clause builder for list_library()/count_library() — used
    to be duplicated (and count_library() silently dropped request/
    nomenclature/origin, making its `total` wrong once those filters were
    used), now both always apply the exact same filters."""
    where = []
    params: list = []
    estados: list = []
    for v in _valores(status):
        estados.extend(_MISSING_STATUSES if v == NOT_AVAILABLE_STATUS_FILTER else [v])
    _en("local_status", list(dict.fromkeys(estados)), where, params)
    _en("request_status", _valores(request), where, params)
    _en("nomenclature_status", _valores(nomenclature), where, params)
    _en("item_type", _valores(item_type), where, params)
    _en("instance_type", _valores(origin), where, params)
    _en("instance_id", _valores(instance_id), where, params)
    # Filtered in SQL, not in the browser: the Español column is the whole
    # library's worth of rows, and filtering it client-side would mean fetching
    # every level up to LOAD_LIMIT just to throw most of it away.
    casos = [_CASTELLANO_SQL[v] for v in _valores(spanish) if v in _CASTELLANO_SQL]
    if casos:
        where.append("(" + " OR ".join(f"({c})" for c in casos) + ")")
    if parent_id is not None:
        if parent_id == TOP_LEVEL_PARENT_FILTER:
            where.append("parent_id IS NULL")
        else:
            where.append("parent_id = ?")
            params.append(parent_id)
    if search:
        if parent_id == TOP_LEVEL_PARENT_FILTER:
            # Buscando en la vista de árbol, un acierto SUBE hasta su serie.
            #
            # Los títulos de temporadas y capítulos llevan dentro el de la
            # serie, así que buscar "One Piece" acertaba en los tres niveles y
            # la tabla escupía la serie, sus 20 temporadas y sus 1000 capítulos
            # como filas hermanas. Lo que se busca es el contenido, y el
            # contenido es la serie: lo de dentro se ve expandiéndola.
            #
            # De paso, buscar algo que solo existe por debajo ("T2E1") ya no
            # devuelve la fila suelta y descolgada, sino la serie que lo tiene.
            where.append("""(title LIKE ? OR EXISTS (
                SELECT 1 FROM library_items d
                 WHERE (d.parent_id = library_items.id
                     OR d.parent_id IN (SELECT s.id FROM library_items s
                                         WHERE s.parent_id = library_items.id))
                   AND d.title LIKE ?))""")
            params.extend([f"%{search}%", f"%{search}%"])
        else:
            where.append("title LIKE ?")
            params.append(f"%{search}%")
    return where, params


# User-selectable ordering for the top-level library list. Applied as the
# tie-break AFTER the season/episode numeric ordering, so expanding a series
# always shows its seasons/episodes in numeric order regardless of this choice.
# "title_asc" (COLLATE NOCASE) gives símbolos < números < A-Z, the default.
# TITLE_SORT (registered in database.connect) folds accents and orders
# símbolos < números < letras; NOCASE would drop accented titles at the end.
# El tamaño que hay que usar para ordenar, que es el MISMO que enseña la
# columna Tamaño. Una serie o una temporada no guardan tamaño propio (es NULL):
# el que se ve es la suma de lo que cuelga de ellas, y se calculaba solo al
# pintar. Ordenando por la columna cruda, una serie que enseña 11 GB caía por
# detrás de una película de 4 GB en "Tamaño (Más)" — el orden contradecía a la
# vista (auditoría de tablas).
#
# Suma solo capítulos, igual que _size_rollup: la sincronización SÍ guarda en
# la temporada la suma de sus capítulos (_update_season_rollup), así que sumar
# temporadas + capítulos contaba la serie dos veces, y una serie de 54 GB se
# ordenaba como si tuviera 109 y adelantaba a una película de 76.
#
# Solo corre la subconsulta para series y temporadas (una minoría), y va por
# el índice idx_library_parent. Si no tienen capítulos con tamaño, se queda con
# el propio, igual que la columna. Con «ignorar especiales» la serie deja fuera
# la temporada 0, como _batch_rollups al pintarla.
def _tamano_efectivo(ignore_specials: bool) -> str:
    return f"""COALESCE(CASE item_type
    WHEN 'season' THEN (
        SELECT SUM(e.size_bytes) FROM library_items e
         WHERE e.parent_id = library_items.id AND e.item_type = 'episode')
    WHEN 'series' THEN (
        SELECT SUM(e.size_bytes) FROM library_items e
          JOIN library_items se ON e.parent_id = se.id
         WHERE se.parent_id = library_items.id AND e.item_type = 'episode'{_specials_clause("se", ignore_specials)})
END, size_bytes)"""

_LIBRARY_SORT = {
    "title_asc": "title COLLATE TITLE_SORT ASC, updated_at DESC",
    "title_desc": "title COLLATE TITLE_SORT DESC, updated_at DESC",
    "updated_desc": "updated_at DESC, title COLLATE TITLE_SORT ASC",
    "year_desc": "year IS NULL, year DESC, title COLLATE TITLE_SORT ASC",
    "year_asc": "year IS NULL, year ASC, title COLLATE TITLE_SORT ASC",
    # Ver _tamano_efectivo: hay que ordenar por lo MISMO que enseña la columna.
    # Lo que sigue sin tener tamaño (nada descargado) va al final en los dos
    # sentidos, en vez de amontonarse arriba en el ascendente, que nunca es lo
    # que estás buscando.
    "size_desc": "{tamano} IS NULL, {tamano} DESC, title COLLATE TITLE_SORT ASC",
    "size_asc": "{tamano} IS NULL, {tamano} ASC, title COLLATE TITLE_SORT ASC",
}
DEFAULT_LIBRARY_SORT = "title_asc"


def _columnas_de_lista(conn: sqlite3.Connection) -> str:
    # Todo menos raw_json: la lista no lo usa y es lo que más pesa de cada fila.
    return ", ".join(c[1] for c in conn.execute("PRAGMA table_info(library_items)") if c[1] != "raw_json")


def _orden_de_lista(sort: Optional[str], ignore_specials: bool) -> str:
    # Seasons/episodes carry season_number/episode_number and must sort
    # numerically (Temporada 1, 2, …, 10, not string order). Top-level rows
    # (movies/series) have both NULL, so they tie there and fall through to the
    # user-selected sort.
    sort_sql = _LIBRARY_SORT.get(sort or DEFAULT_LIBRARY_SORT, _LIBRARY_SORT[DEFAULT_LIBRARY_SORT]).format(
        tamano=_tamano_efectivo(ignore_specials))
    # El id desempata: con títulos repetidos y el mismo updated_at, cada página (una consulta aparte)
    # podría ordenarlos distinto y repetir u omitir una fila.
    return f" ORDER BY season_number IS NOT NULL, season_number, episode_number, {sort_sql}, id"


def list_library(
    conn: sqlite3.Connection,
    *,
    status: Filtro = None,
    request: Filtro = None,
    nomenclature: Filtro = None,
    item_type: Filtro = None,
    origin: Filtro = None,
    instance_id: Filtro = None,
    parent_id: Optional[int] = None,
    search: Optional[str] = None,
    spanish: Filtro = None,
    sort: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    ignore_specials: bool = True,
    provider: Filtro = None,
    resolution: Filtro = None,
    source: Filtro = None,
    release_group: Filtro = None,
    emu: Filtro = None,
) -> list[dict]:
    where, params = _build_library_filter(
        status=status, request=request, nomenclature=nomenclature,
        item_type=item_type, origin=origin, instance_id=instance_id,
        parent_id=parent_id, search=search, spanish=spanish,
    )
    # Recorte previo para filtrar_por_lo_que_se_ve: en películas y capítulos la
    # columna es su propio valor, así que los que no cumplen ni se leen. Series
    # y temporadas se quedan: lo suyo sale de sus capítulos.
    hoja: list[str] = []
    hoja_params: list = []
    # Excluir proveedores no recorta aquí: lo hace filtrar_por_lo_que_se_ve.
    proveedores = set(_incluir_excluir(provider)[0])
    if proveedores:
        # El proveedor sale de la ruta: basta con que lleve alguno de sus nombres.
        from ..nomenclature import _PROVIDER_TOKEN_MAP
        tokens = [t for t, c in _PROVIDER_TOKEN_MAP.items() if _provider_label(c) in proveedores]
        hoja.append(f"({' OR '.join(['path LIKE ?'] * len(tokens))})" if tokens else "0")
        hoja_params.extend(f"%{t}%" for t in tokens)
    _en_columna("resolution", resolution, hoja, hoja_params)
    _en_columna("source", source, hoja, hoja_params)
    _en_columna("release_group", release_group, hoja, hoja_params)
    _en("emu_in_catalog", [{"candidate": 0, "present": 1}[v] for v in _valores(emu)], hoja, hoja_params)
    if hoja:
        where.append(f"(item_type IN ('series', 'season') OR ({' AND '.join(hoja)}))")
        params.extend(hoja_params)
    sql = f"SELECT {_columnas_de_lista(conn)} FROM library_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += _orden_de_lista(sort, ignore_specials) + " LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


# Cada fila sube hasta su película o serie: un capítulo, a la serie de su temporada; una temporada, a su serie.
_RAIZ_SQL = """CASE WHEN parent_id IS NULL THEN id ELSE COALESCE(
    (SELECT p.parent_id FROM library_items p WHERE p.id = library_items.parent_id AND p.item_type = 'season'),
    parent_id) END"""


def _paginar_raices(
    conn: sqlite3.Connection, raices_sql: str, params: list, *, sort: Optional[str], ignore_specials: bool,
    limit: int, offset: int,
) -> tuple[list[dict], int]:
    """Las películas y series (nivel raíz) cuyo id sale de `raices_sql`, ya ordenadas y
    paginadas en SQL, y cuántas son en total."""
    base = f" FROM library_items WHERE parent_id IS NULL AND id IN ({raices_sql})"
    # El total sale de la misma consulta que la página (COUNT(*) OVER () se calcula antes del
    # LIMIT): con dos consultas, una sincronización entre ambas daba un total de otra biblioteca.
    sql = (f"SELECT {_columnas_de_lista(conn)}, COUNT(*) OVER () AS _total_raices{base}"
           f"{_orden_de_lista(sort, ignore_specials)} LIMIT ? OFFSET ?")
    filas = [dict(r) for r in conn.execute(sql, [*params, limit, offset])]
    if filas:
        total = filas[0]["_total_raices"]
        for fila in filas:
            del fila["_total_raices"]
        return filas, total
    # Una página vacía (desplazamiento más allá del final) no trae el total: se cuenta aparte.
    return [], conn.execute("SELECT COUNT(*)" + base, params).fetchone()[0]


def list_library_agrupada(
    conn: sqlite3.Connection,
    *,
    status: Filtro = None,
    request: Filtro = None,
    nomenclature: Filtro = None,
    origin: Filtro = None,
    instance_id: Filtro = None,
    search: Optional[str] = None,
    spanish: Filtro = None,
    sort: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    ignore_specials: bool = True,
) -> tuple[list[dict], int]:
    """La biblioteca filtrada en plano, con lo que cumple subido hasta su
    película o serie (ver subir_a_su_serie), pero todo en SQL: solo se leen las
    filas de la página. Devuelve la página y el total."""
    where, params = _build_library_filter(
        status=status, request=request, nomenclature=nomenclature, origin=origin,
        instance_id=instance_id, search=search, spanish=spanish,
    )
    # Ignorando especiales, la fila de la serie no los cuenta: no la traen.
    if ignore_specials:
        where.append("(season_number IS NULL OR season_number != 0)")
    raices = f"SELECT {_RAIZ_SQL} FROM library_items" + (" WHERE " + " AND ".join(where) if where else "")
    return _paginar_raices(conn, raices, params, sort=sort, ignore_specials=ignore_specials,
                           limit=limit, offset=offset)


# Aportar solo tiene sentido con algo que tienes: una película o un capítulo
# en disco, o una serie/temporada al menos Parcial.
APORTE_ELIGIBLE_STATUS = frozenset({"Disponible", "Subido", "Subiendo", "Parcial"})


def _es_aporte(it: dict) -> bool:
    return it["local_status"] in APORTE_ELIGIBLE_STATUS and (
        it["emu_in_catalog"] == 0 or (it["emu_in_catalog"] == 1 and bool(it["emu_aportes"])))


def filtrar_por_lo_que_se_ve(
    filas: list[dict],
    *,
    provider: Filtro = None,
    resolution: Filtro = None,
    source: Filtro = None,
    release_group: Filtro = None,
    emu: Filtro = None,
    aporte: Optional[str] = None,
) -> list[dict]:
    """Proveedor, Resolución, Source, Grupo, eMuwarez y Aportes filtran por lo
    que ENSEÑA la columna, que en una serie o temporada es lo que comparten sus
    capítulos: `filas` son las ya montadas para la respuesta, en todos los niveles.

    Agrupar lo que cumple bajo su serie es cosa de subir_a_su_serie.
    """
    elegidos = [(k, *_incluir_excluir(v)) for k, v in (
        ("provider_label", provider), ("resolution", resolution),
        ("source", source), ("release_group", release_group)) if _valores(v)]
    emus = _valores(emu)
    if not (elegidos or emus or aporte):
        return filas

    def cumple(it: dict) -> bool:
        # Una serie a medias (emu_in_catalog 2) no es ni Sí ni No: lo son sus temporadas.
        return (all((not si or it[k] in si) and it[k] not in no for k, si, no in elegidos)
                and (not emus or ("candidate" in emus and it["emu_in_catalog"] == 0)
                     or ("present" in emus and it["emu_in_catalog"] == 1))
                and (not aporte or (_es_aporte(it) if aporte == "yes"
                                    else it["emu_in_catalog"] == 1 and not _es_aporte(it))))

    return [it for it in filas if cumple(it)]


def subir_a_su_serie(
    conn: sqlite3.Connection, filas: list[dict], *, sort: Optional[str] = None, ignore_specials: bool = True,
    limit: int = -1, offset: int = 0,
) -> tuple[list[dict], int]:
    """La biblioteca filtrada en plano sube cada fila que cumple hasta su
    película o serie, como ya hacía buscar: lo de dentro se ve desplegándola.
    Devuelve la página pedida (ordenada y recortada en SQL) y el total.

    Quedarse con el nivel más alto que cumple no bastaba: con Estado =
    Disponible una serie Parcial no cumple, con eMuwarez = No una serie a
    medias tampoco, y sus capítulos salían sueltos, ordenados por número.
    """
    serie_de = dict(conn.execute("SELECT id, parent_id FROM library_items WHERE item_type = 'season'"))
    # Ignorando especiales, la fila de la serie no los cuenta: no la traen.
    raices = {it["id"] if it["parent_id"] is None else serie_de.get(it["parent_id"], it["parent_id"])
              for it in filas if not (ignore_specials and it["season_number"] == 0)}
    return _paginar_raices(conn, "SELECT value FROM json_each(?)", [json.dumps(list(raices - {None}))],
                           sort=sort, ignore_specials=ignore_specials, limit=limit, offset=offset)


def count_library(
    conn: sqlite3.Connection,
    *,
    status: Filtro = None,
    request: Filtro = None,
    nomenclature: Filtro = None,
    item_type: Filtro = None,
    origin: Filtro = None,
    instance_id: Filtro = None,
    parent_id: Optional[int] = None,
    search: Optional[str] = None,
    spanish: Filtro = None,
) -> int:
    where, params = _build_library_filter(
        status=status, request=request, nomenclature=nomenclature,
        item_type=item_type, origin=origin, instance_id=instance_id,
        parent_id=parent_id, search=search, spanish=spanish,
    )
    sql = "SELECT COUNT(*) FROM library_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


# Los estados en que el archivo está EN TU DISCO. Mismo criterio que usan
# nomenclature_check y emu_catalog: "Subiendo" y "Subido" siguen siendo tuyos,
# subirlo no lo borra.
TIENES_EL_ARCHIVO = ("Disponible", "Subiendo", "Subido")


def contar_archivos(conn: sqlite3.Connection) -> int:
    """Cuántos archivos de vídeo tienes de verdad.

    Solo películas y capítulos, que es lo único que es un fichero: una serie y
    una temporada son agrupaciones, no algo que ocupe disco. Y solo los que
    tienes — un "Faltante" es algo que Radarr o Sonarr conocen pero que no has
    descargado.

    Es a propósito distinto de `count_library`, que cuenta FILAS de la tabla
    con los filtros puestos. Ese número sirve para la tabla; este contesta
    "cuánto tengo", que es otra pregunta y la que hace el subtítulo de
    Biblioteca. Antes ese subtítulo enseñaba el de las filas, así que una serie
    con 90 capítulos contaba 1.
    """
    marcas = ",".join("?" * len(TIENES_EL_ARCHIVO))
    row = conn.execute(
        f"""SELECT COUNT(*) FROM library_items
             WHERE item_type IN ('movie', 'episode')
               AND local_status IN ({marcas})""",
        TIENES_EL_ARCHIVO,
    ).fetchone()
    return int(row[0]) if row else 0


def get_library_item(conn: sqlite3.Connection, item_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def list_missing(conn: sqlite3.Connection, *, limit: int = 50, offset: int = 0) -> list[dict]:
    placeholders = ", ".join(["?"] * len(_MISSING_STATUSES))
    sql = (
        f"SELECT * FROM library_items WHERE local_status IN ({placeholders})"
        " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, [*_MISSING_STATUSES, limit, offset]).fetchall()
    return [dict(row) for row in rows]


def count_missing(conn: sqlite3.Connection) -> int:
    """Cuántos elementos cuentan como faltantes, sin paginar."""
    placeholders = ", ".join(["?"] * len(_MISSING_STATUSES))
    row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM library_items WHERE local_status IN ({placeholders})",
        list(_MISSING_STATUSES),
    ).fetchone()
    return int(row["cnt"] or 0) if row else 0


def update_request_status(
    conn: sqlite3.Connection,
    library_item_id: int,
    request_status: str,
    request_id: Optional[int] = None,
) -> None:
    conn.execute(
        "UPDATE library_items SET request_status = ?, request_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (request_status, request_id, library_item_id),
    )
    conn.commit()


def mark_nomenclature(conn: sqlite3.Connection, library_item_id: int, status: str) -> None:
    conn.execute(
        "UPDATE library_items SET nomenclature_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, library_item_id),
    )
    conn.commit()


def list_library_diagnostics(
    *, status: str | None = None, search: str | None = None,
    limit: int = 50, offset: int = 0, conn,
) -> tuple[list[dict], int]:
    """La lista de diagnósticos con sus filtros, y el total sin paginar.
    Construía el WHERE a mano dentro del endpoint."""
    condiciones, params = [], []
    if status:
        condiciones.append("li.local_status = ?")
        params.append(status)
    if search:
        condiciones.append("li.title LIKE ?")
        params.append(f"%{search}%")
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    filas = conn.execute(
        f"""SELECT li.id, li.title, li.local_status, li.file_exists,
                   li.file_verified_at, li.file_verification_error,
                   li.arr_queue_status, li.arr_history_status, li.arr_history_error,
                   li.diagnostic_status, li.diagnostic_summary,
                   li.recommended_action, li.recommendation_reasons_json,
                   li.recommendation_updated_at
            FROM library_items li {where}
            ORDER BY li.updated_at DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    total_row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM library_items li {where}", params
    ).fetchone()
    return [dict(r) for r in filas], (int(total_row["cnt"] or 0) if total_row else 0)


def list_missing_diagnostics(*, limit: int = 50, offset: int = 0, conn) -> tuple[list[dict], int]:
    """Los faltantes con su diagnóstico, y el total. Qué cuenta como faltante
    lo decide LocalStatus.not_available(), no una lista escrita en el
    endpoint."""
    estados = list(LocalStatus.not_available())
    marcas = ",".join("?" * len(estados))
    filas = conn.execute(
        f"""SELECT id, title, item_type, year, instance_type, instance_name,
                   tmdb_id, imdb_id, local_status, request_status,
                   arr_queue_status, arr_queue_progress, arr_queue_timeleft, arr_queue_error,
                   arr_history_status, arr_history_error,
                   file_exists, diagnostic_status, diagnostic_summary,
                   recommended_action, recommendation_reasons_json, updated_at
            FROM library_items WHERE local_status IN ({marcas})
            ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
        estados + [limit, offset],
    ).fetchall()
    total_row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM library_items WHERE local_status IN ({marcas})", estados
    ).fetchone()
    return [dict(r) for r in filas], (int(total_row["cnt"] or 0) if total_row else 0)
