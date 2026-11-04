"""Datos del panel (Dashboard): resumen, diagnóstico, actividad reciente y recomendaciones."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from ...models import LocalStatus

from ..emu_format import _split_languages
from .listado import _MISSING_STATUSES


def get_dashboard_summary(conn: sqlite3.Connection) -> dict:
    """Return aggregated counts from library_items.

    Restricted to item_type IN ('movie','episode') — real content units —
    so series/season rollup rows (organizational, not real content) never
    double-count against these totals (a series with 10 episodes must
    contribute 10, not 11 by also counting the series row itself)."""
    # When "ignorar especiales" is on, missing episodes of a special season
    # (season 0) don't count as Faltantes on the dashboard.
    from ..settings import leer_ajuste
    ignore_specials = leer_ajuste(conn, "series_ignore_specials")

    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS available,
            SUM(CASE WHEN local_status IN ({missing_ph})
                     AND NOT (? = 1 AND item_type = 'episode' AND COALESCE(season_number, -1) = 0)
                THEN 1 ELSE 0 END) AS missing_count,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS uploading,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS uploaded,
            SUM(CASE WHEN instance_type = 'radarr' THEN 1 ELSE 0 END) AS radarr_items,
            SUM(CASE WHEN instance_type = 'sonarr' THEN 1 ELSE 0 END) AS sonarr_items
        FROM library_items
        WHERE item_type IN ('movie', 'episode')
        """.format(missing_ph=", ".join(["?"] * len(_MISSING_STATUSES))),
        [
            LocalStatus.AVAILABLE.value,
            *_MISSING_STATUSES,
            1 if ignore_specials else 0,
            LocalStatus.UPLOADING.value,
            LocalStatus.UPLOADED.value,
        ],
    ).fetchone()

    # "Contenido único": lo disponible que sale como "No" en ¿En eMuwarez?
    # (emu_in_catalog = 0). Se cuenta por unidad subible: cada película, cada
    # temporada completa de serie/documental, y sus capítulos. emu_in_catalog
    # se calcula a nivel de película y de serie/temporada (nunca por episodio),
    # así que los capítulos se cuentan por su temporada única.
    #
    # Una temporada solo cuenta como "subible" si además de local_status =
    # Disponible cumple lo mismo que exige build_season_pack_plan: sus 5 campos
    # de rollup (services/library.py's _update_season_rollup, sync-time) NO son
    # NULL — null en cualquiera de ellos significa justo que sus capítulos no
    # coinciden entre sí (resolución/source/códecs/idiomas) — y todos sus
    # capítulos llevan castellano de alguna forma (has_spanish_ok = 1).
    #
    # Los subtítulos NO se comprueban por igualdad, ni siquiera por presencia:
    # eMuwarez acepta el pack aunque las pistas difieran mientras todas lleven
    # castellano, y no los exige en absoluto si el audio ya está en castellano
    # (una temporada doblada no necesita subtítulos). Exigir
    # subtitle_languages IS NOT NULL dejaba fuera temporadas que sí son
    # subibles. isSeasonReady/seasonNotReadyReason en el frontend usan la misma
    # señal. Sin este filtro, esta tarjeta contaba temporadas completas pero
    # técnicamente inconsistentes como si se pudieran subir.
    avail = LocalStatus.AVAILABLE.value
    from ..season_pack import pack_rollup_sql
    uniq = conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN item_type = 'movie'  THEN 1 ELSE 0 END) AS movies,
            SUM(CASE WHEN item_type = 'season' THEN 1 ELSE 0 END) AS seasons
        FROM library_items
        WHERE emu_in_catalog = 0 AND local_status = ?
          -- Castilian applies to EVERY kind, not just seasons: a film without
          -- it is blocked by the pre-upload checks exactly the same way
          -- (services/upload_checks.py), so counting it here as ready to go
          -- would be a lie the moment you clicked Subir.
          AND has_spanish_ok = 1
          -- Lo que un pack exige que coincida en todos sus capítulos. El
          -- fragmento lo genera season_pack.pack_rollup_sql() desde la misma
          -- definición que usa la regla de verdad, para que no haya que
          -- acertar en tres consultas cada vez que cambia.
          AND (item_type != 'season' OR ({pack_rollup_sql()}))
        """,
        [avail],
    ).fetchone()
    uniq_ep = conn.execute(
        f"""
        SELECT COUNT(*) AS n
        FROM library_items e
        JOIN library_items s ON e.parent_id = s.id
        WHERE e.item_type = 'episode' AND e.local_status = ?
          AND s.item_type = 'season' AND s.emu_in_catalog = 0
          AND {pack_rollup_sql("s")}
          AND s.has_spanish_ok = 1
        """,
        [avail],
    ).fetchone()
    unique_movies = int(uniq["movies"] or 0)
    unique_seasons = int(uniq["seasons"] or 0)
    unique_episodes = int(uniq_ep["n"] or 0)

    last_sync = conn.execute(
        "SELECT started_at FROM task_runs WHERE name = 'sync-library' AND status = 'completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    from ..scheduler import TASK_LIBRARY_SYNC, get_scheduled_task
    tarea = get_scheduled_task(conn, TASK_LIBRARY_SYNC)

    return {
        "library_total": int(row["total"] or 0),
        "available": int(row["available"] or 0),
        "missing": int(row["missing_count"] or 0),
        "uploading": int(row["uploading"] or 0),
        "completed": int(row["uploaded"] or 0),
        # Headline = unidades subibles (películas + temporadas completas).
        "unique_content": unique_movies + unique_seasons,
        "unique_movies": unique_movies,
        "unique_seasons": unique_seasons,
        "unique_episodes": unique_episodes,
        "radarr_items": int(row["radarr_items"] or 0),
        "sonarr_items": int(row["sonarr_items"] or 0),
        "last_sync_at": last_sync["started_at"] if last_sync else None,
        "next_sync_at": tarea["next_run_at"] if tarea["enabled"] else None,
    }


def get_dashboard_diagnostics(conn: sqlite3.Connection) -> dict:
    """Return Phase 8A diagnostic counts for the dashboard."""
    try:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN file_exists = 1 THEN 1 ELSE 0 END) AS files_verified,
                SUM(CASE WHEN local_status = 'Disponible' AND file_exists = 0 AND file_verified_at IS NOT NULL THEN 1 ELSE 0 END) AS files_missing_on_disk,
                SUM(CASE WHEN recommended_action = 'adapt_nomenclature' THEN 1 ELSE 0 END) AS items_ready_for_nomenclature,
                SUM(CASE WHEN recommended_action IN ('upload', 'run_preflight') THEN 1 ELSE 0 END) AS items_ready_for_upload,
                SUM(CASE WHEN arr_queue_status IN ('downloading', 'queued') THEN 1 ELSE 0 END) AS items_waiting_download,
                SUM(CASE WHEN recommended_action = 'review_arr' THEN 1 ELSE 0 END) AS items_need_arr_review
            FROM library_items
            """
        ).fetchone()
        if row:
            return {
                "files_verified": int(row["files_verified"] or 0),
                "files_missing_on_disk": int(row["files_missing_on_disk"] or 0),
                "items_ready_for_nomenclature": int(row["items_ready_for_nomenclature"] or 0),
                "items_ready_for_upload": int(row["items_ready_for_upload"] or 0),
                "items_waiting_download": int(row["items_waiting_download"] or 0),
                "items_need_arr_review": int(row["items_need_arr_review"] or 0),
            }
    except Exception:
        pass
    return {
        "files_verified": 0,
        "files_missing_on_disk": 0,
        "items_ready_for_nomenclature": 0,
        "items_ready_for_upload": 0,
        "items_waiting_download": 0,
        "items_need_arr_review": 0,
    }


def get_recent_activity(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict]:
    """Return recent task_runs as activity feed."""
    rows = conn.execute(
        "SELECT * FROM task_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


# Phase 11F — dashboard "Actividad reciente" priority: items with a filled
# (satisfied) EMU request first, then compatible/partial candidates, then
# everything else; ties broken by most-recently-updated (a deterministic,
# honest stand-in for "then random" — re-shuffling on every dashboard load
# would be noisy, not more useful).
_REQUEST_PRIORITY_SQL = """
    CASE request_status
        WHEN 'Llena' THEN 0
        WHEN 'Compatible' THEN 1
        WHEN 'Parcial' THEN 2
        WHEN 'No compatible' THEN 3
        WHEN 'Desconocida' THEN 4
        ELSE 5
    END
"""


def get_dashboard_library_activity(conn: sqlite3.Connection, *, limit: int = 10) -> list[dict]:
    """Top-level items only (parent_id IS NULL) — movies and series, never
    raw episode/season rows flooding the 'Actividad reciente' feed."""
    rows = conn.execute(
        f"SELECT * FROM library_items WHERE parent_id IS NULL "
        f"ORDER BY {_REQUEST_PRIORITY_SQL}, updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


# Phase 11G — dashboard "Recomendaciones": actionable content, in three ranked
# groups. (1) content you have that satisfies a *compatible* eMuwarez request
# → click goes to that request. (2) content you have available that is NOT in
# eMuwarez yet ("Contenido único") → an upload opportunity. (3) content you are
# *missing* and that is monitored in Radarr/Sonarr and not on eMuwarez → a
# candidate to request on eMuwarez. Within each group items are ordered by
# type (movie / complete series → season → loose episode) then by title, like
# the library. Groups 2 & 3 link to the content's own detail page.
def _rec_series_title_year(conn: sqlite3.Connection, row: dict) -> tuple:
    """Series title + premiere year for a library item — walks up parent_id from
    a season/episode; a series/movie row returns its own title/year."""
    if row.get("item_type") == "series":
        return row.get("title"), row.get("year")
    pid = row.get("parent_id")
    seen: set = set()
    while pid and pid not in seen:
        seen.add(pid)
        prow = conn.execute(
            "SELECT title, year, item_type, parent_id FROM library_items WHERE id = ?", (pid,)
        ).fetchone()
        if not prow:
            break
        prow = dict(prow)
        if prow.get("item_type") == "series":
            return prow.get("title"), prow.get("year")
        pid = prow.get("parent_id")
    return row.get("title"), row.get("year")


def _rec_content_name(
    conn: sqlite3.Connection, row: dict, *,
    season: int | None = None, episode: int | None = None,
    scope: str | None = None,
) -> str:
    """Friendly display name, same convention the Petición form itself uses
    (see RequestFormModal): "Título (Año)" for a movie, "Serie (Año) -
    Temporada X" for a whole season, "Serie (Año) - SxxEyy" for one episode
    — never both suffixes at once. Uses the given request scope/season/
    episode (falls back to the row's own season_number/episode_number when
    none is passed, e.g. a season/episode library row)."""
    it = row.get("item_type")
    sn = season if season is not None else row.get("season_number")
    ep = episode if episode is not None else row.get("episode_number")
    if it == "movie":
        name = row.get("title") or ""
        if row.get("year"):
            name += f" ({row.get('year')})"
        return name
    title, year = _rec_series_title_year(conn, row)
    name = title or row.get("title") or ""
    if year:
        name += f" ({year})"
    if sn is None:
        return name
    is_episode = (scope == "episode") or (scope is None and (it == "episode" or ep is not None))
    if is_episode and ep is not None:
        try:
            return name + f" - S{int(sn):02d}E{int(ep):02d}"
        except (TypeError, ValueError):
            pass
    return name + f" - Temporada {sn}"


def content_display_title(
    conn: sqlite3.Connection, row: dict, *,
    season: int | None = None, episode: int | None = None,
    scope: str | None = None,
) -> str:
    """Public entry point for _rec_content_name's canonical display title
    ("Serie (Año)" / "Serie (Año) - Temporada X" / "Serie (Año) - SxxEyy",
    "Título (Año)" for a movie) — reused by Biblioteca/Subidas/Peticiones'
    own dedicated pages so they all agree on the same format."""
    return _rec_content_name(conn, row, season=season, episode=episode, scope=scope)


def episode_own_name(row: dict) -> str | None:
    """Sonarr's own per-episode title (e.g. "Cat's in the Bag...") — not a
    separate column, only ever baked into the raw stored title as
    "{series} SxxEyy - {episode title}" (episode_to_library_item,
    integrations/sonarr.py), so it's extracted back out here. Used only by
    Biblioteca's own episode ficha, the one place the canonical
    "Serie (Año) - SxxEyy" display title still appends it."""
    m = re.search(r"S\d{2}E\d{2,3}\s*-\s*(.+)$", row.get("title") or "")
    return m.group(1).strip() if m else None


def _rec_rolled_size(conn: sqlite3.Connection, row: dict, *, season: int | None = None, episode: int | None = None):
    """Size to show for a recommendation. Movies/episodes use their own file
    size; a series/season has none of its own, so we sum the file sizes of the
    episodes underneath (optionally restricted to one season, or a single
    episode of it). Returns None when nothing on disk contributes a size, so the
    UI shows "—"."""
    it = row.get("item_type")
    if it in ("movie", "episode"):
        return row.get("size_bytes")
    rid = int(row["id"])
    # A specific episode of a series → drill series → season → episode.
    if it == "series" and season is not None and episode is not None:
        r = conn.execute(
            "SELECT e.size_bytes AS s FROM library_items e "
            "JOIN library_items se ON se.id = e.parent_id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode' "
            "AND se.season_number = ? AND e.episode_number = ? LIMIT 1",
            (rid, season, episode),
        ).fetchone()
        return r["s"] if r else None
    if it == "season":
        r = conn.execute(
            "SELECT SUM(size_bytes) AS s, COUNT(size_bytes) AS c "
            "FROM library_items WHERE parent_id = ? AND item_type = 'episode'",
            (rid,),
        ).fetchone()
    elif season is not None:
        r = conn.execute(
            "SELECT SUM(e.size_bytes) AS s, COUNT(e.size_bytes) AS c "
            "FROM library_items e JOIN library_items se ON se.id = e.parent_id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode' AND se.season_number = ?",
            (rid, season),
        ).fetchone()
    else:
        r = conn.execute(
            "SELECT SUM(e.size_bytes) AS s, COUNT(e.size_bytes) AS c "
            "FROM library_items e JOIN library_items se ON se.id = e.parent_id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'",
            (rid,),
        ).fetchone()
    return r["s"] if r and r["c"] else None


def _repartir_cupo(listas: list[list], cupo: int) -> list[list]:
    """Recorta cada lista (conservando su orden) para que entre todas no pasen de `cupo`: el cupo se reparte a partes
    iguales entre las que no están vacías y lo que una no usa pasa a las demás."""
    cuotas = [0] * len(listas)
    pendiente = max(cupo, 0)
    while pendiente > 0:
        con_hueco = [i for i, lista in enumerate(listas) if len(lista) > cuotas[i]]
        if not con_hueco:
            break
        parte = max(pendiente // len(con_hueco), 1)
        for i in con_hueco:
            dado = min(parte, len(listas[i]) - cuotas[i], pendiente)
            cuotas[i] += dado
            pendiente -= dado
            if pendiente == 0:
                break
    return [lista[:cuota] for lista, cuota in zip(listas, cuotas)]


def get_dashboard_recommendations(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    from ..season_pack import pack_rollup_sql
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    g1_recs: list[dict] = []  # group 1, already in its final order (the SQL's)
    recs: list[dict] = []  # groups 2, 3 & 4, sorted at the end
    seen_lib: set[int] = set()  # library ids already shown (so a piece of
    # content isn't repeated across groups 2 & 3 or after appearing in group 1)

    cols = ("id, item_type, title, year, poster_url, local_status, added_at, missing_since, "
            "season_number, episode_number, parent_id, size_bytes, "
            "resolution, source, release_group, audio_languages, subtitle_languages, "
            "tmdb_id, imdb_id, tvdb_id, instance_type, instance_id, title_slug")

    # Group 1 — every *compatible* eMuwarez request, sourced from the match
    # table (library_items.request_status only records one request per item, so
    # a series with several compatible requests would otherwise show just once).
    # One row per request, named/sized at the request's own scope (season /
    # episode), linking to that request.
    # Lo que más paga primero, para ver qué conviene subir antes: la recompensa
    # (points) de mayor a menor, las que no la dicen al final y, a igual
    # recompensa, la petición más nueva delante (el mismo orden que «Puntos /
    # recompensa» en Peticiones, points_desc).
    # Sin las que su copia no tiene castellano: eMuwarez solo admite contenido
    # con castellano (en el audio o, si no, en los subtítulos) y la subida las
    # rechazaría. Lo dice la preparación ya guardada (request_readiness:
    # no_castellano, con has_spanish_ok = 0 de la fila pedida, temporada o
    # capítulo incluidos), la misma que pintan Peticiones y el aviso; una
    # petición que aún no se ha evaluado (NULL) se queda.
    g1 = conn.execute(
        """
        SELECT ri.id AS req_id, ri.req_scope, ri.req_season, ri.req_episode, ri.points,
               (SELECT rm.library_item_id FROM request_matches rm
                WHERE rm.request_item_id = ri.id ORDER BY rm.confidence DESC LIMIT 1) AS lib_id
        FROM request_items ri
        WHERE (SELECT rm.status FROM request_matches rm
               WHERE rm.request_item_id = ri.id ORDER BY rm.confidence DESC LIMIT 1) = 'Compatible'
          AND COALESCE(ri.readiness_status, '') <> 'no_castellano'
        ORDER BY ri.points IS NULL, ri.points DESC, ri.created_at DESC, ri.id DESC
        """
    ).fetchall()
    for r in g1:
        lib_id = r["lib_id"]
        if lib_id is None:
            continue
        lib_row = conn.execute(f"SELECT {cols} FROM library_items WHERE id = ?", (lib_id,)).fetchone()
        if not lib_row:
            continue
        lib = dict(lib_row)
        scope, season, episode = r["req_scope"], r["req_season"], r["req_episode"]
        # Display type follows the request scope, not the matched row (which is
        # usually the series): season request → "Temporada", episode → "Capítulo".
        if lib["item_type"] == "movie":
            disp_type = "movie"
        elif scope == "episode" or episode is not None:
            disp_type = "episode"
        elif season is not None:
            disp_type = "season"
        else:
            disp_type = lib["item_type"]
        d = dict(lib)
        d["item_type"] = disp_type
        # Expose the request's scope so the "Subir" action can pre-select the
        # right season/episode in the upload wizard.
        d["season_number"] = season
        d["episode_number"] = episode
        d["rec_group"] = 1
        d["rec_request_id"] = r["req_id"]
        d["rec_points"] = r["points"]
        # La fila a la que se refiere la petición (la temporada o el capítulo, no la serie que cruzó el
        # emparejador): el asistente de «Subir» se abre sobre ella, como el de Peticiones. De ella salen también la
        # calidad y el castellano, que una serie no guarda.
        from ..requests import _scoped_library_id
        target_id = _scoped_library_id(conn, lib, {"req_scope": scope, "req_season": season, "req_episode": episode})
        d["library_target_id"] = target_id
        target = conn.execute(
            "SELECT resolution, source, release_group, audio_languages, subtitle_languages, "
            "has_spanish_audio, has_spanish_subs FROM library_items WHERE id = ?",
            (target_id,),
        ).fetchone()
        d.update(dict(target))
        d["content_name"] = _rec_content_name(conn, lib, season=season, episode=episode, scope=scope)
        size_episode = episode if (scope == "episode" or disp_type == "episode") else None
        d["size_bytes"] = _rec_rolled_size(conn, lib, season=season, episode=size_episode)
        d["missing_count"] = None
        d["rec_aportes"] = []
        g1_recs.append(d)
        seen_lib.add(int(lib_id))
        seen_lib.add(int(target_id))  # la temporada o el capítulo pedidos tampoco se repiten como idea sin petición

    def _push(row: dict, group: int, *, name: str | None = None, size=None, missing_count=None,
              aportes: list | None = None):
        rid = int(row["id"])
        if rid in seen_lib:
            return
        seen_lib.add(rid)
        d = dict(row)
        d["rec_group"] = group
        d["content_name"] = name if name is not None else _rec_content_name(conn, d)
        d["size_bytes"] = size if size is not None else _rec_rolled_size(conn, d)
        d["rec_request_id"] = None
        d["rec_points"] = None
        d["missing_count"] = missing_count
        d["rec_aportes"] = aportes or []
        # Recency: for a Faltante candidate (group 3), when it actually BECAME
        # missing (missing_since) is what "newest first" should mean — falls
        # back to Radarr/Sonarr's own "added" date (when Radarr/Sonarr first
        # saw it) for group 2 (missing_since is never set for a Disponible
        # row) and for any Faltante row synced before missing_since existed.
        d["_added"] = row.get("missing_since") or row.get("arr_added") or row.get("added_at") or ""
        recs.append(d)

    # Group 2 — available content not in eMuwarez ("Contenido único"): movies
    # and unique seasons — never the whole series as one collapsed row, even
    # when every one of its seasons is unique: eMuwarez uploads happen per
    # season pack (or episode), never "a series" as a single unit, and each
    # season can have its own readiness independent of its siblings, which a
    # single combined "series" row would hide.
    # A season also needs every episode to actually agree on resolution/
    # source/codecs/audio (services/library.py's _update_season_rollup only
    # fills these in when they do) AND to carry Castilian in every one of
    # them — otherwise it's genuinely unique but not actually uploadable as a
    # pack (build_season_pack_plan blocks it), so it shouldn't be recommended
    # as if it were ready to go. Castilian counts from the audio OR the
    # subtitles: a dubbed season needs no subtitles at all, and when it isn't
    # dubbed the subtitle tracks may still differ between episodes.
    for row in conn.execute(
        f"""SELECT {cols},
              COALESCE(json_extract(li.raw_json, '$.added'),
                       (SELECT json_extract(p.raw_json, '$.added')
                        FROM library_items p WHERE p.id = li.parent_id)) AS arr_added
            FROM library_items li
            WHERE li.local_status = 'Disponible' AND li.emu_in_catalog = 0
              AND li.item_type IN ('movie', 'season')
              -- Castilian applies to films too, not just seasons (see the
              -- same condition in get_dashboard_summary).
              AND li.has_spanish_ok = 1
              AND (li.item_type != 'season' OR ({pack_rollup_sql("li")}))"""
    ).fetchall():
        _push(dict(row), 2)

    # Group 4 — «Mejoras posibles»: lo que tienes disponible y YA está en eMuwarez, pero tu copia aporta algo que
    # no tiene ninguno de sus torrents (mayor resolución, mejor source, un códec más eficiente o el castellano que
    # les falta): lo que la ficha de Biblioteca marca como «Aportas» (emu_in_catalog = 1 con emu_aportes). Mismas
    # unidades subibles y mismas exigencias de castellano y de pack que el grupo 2. No es un permiso para subir:
    # eMuwarez tiene reglas de trumps y el Resumen del asistente enseña el veredicto frente a cada torrent.
    for row in conn.execute(
        f"""SELECT {cols}, li.emu_aportes,
              COALESCE(json_extract(li.raw_json, '$.added'),
                       (SELECT json_extract(p.raw_json, '$.added')
                        FROM library_items p WHERE p.id = li.parent_id)) AS arr_added
            FROM library_items li
            WHERE li.local_status = 'Disponible' AND li.emu_in_catalog = 1
              AND li.item_type IN ('movie', 'season')
              AND json_valid(li.emu_aportes) AND json_array_length(li.emu_aportes) > 0
              AND li.has_spanish_ok = 1
              AND (li.item_type != 'season' OR ({pack_rollup_sql("li")}))"""
    ).fetchall():
        row = dict(row)
        try:
            aportes = [a for a in json.loads(row.pop("emu_aportes") or "[]") if isinstance(a, dict)]
        except ValueError:
            continue
        if aportes:
            _push(row, 4, aportes=aportes)

    # Group 3 — monitored content you're missing and that isn't on eMuwarez, a
    # candidate to request. Excludes anything not yet released (unreleased /
    # future air date / "TBA") — you can't request content that doesn't exist
    # yet. Movies directly; series rolled up to the season with monitored
    # missing episodes (you'd request the season, not each episode).
    for row in conn.execute(
        f"""SELECT {cols}, json_extract(raw_json, '$.added') AS arr_added
            FROM library_items
            WHERE item_type = 'movie' AND local_status = 'Faltante'
              AND emu_in_catalog = 0
              AND json_extract(raw_json, '$.monitored') = 1
              AND json_extract(raw_json, '$.status') = 'released'"""
    ).fetchall():
        _push(dict(row), 3)

    for row in conn.execute(
        f"""SELECT {cols}, cnt.missing_count,
              (SELECT json_extract(se.raw_json, '$.added')
               FROM library_items se WHERE se.id = s.parent_id) AS arr_added
            FROM library_items s
            JOIN (
                SELECT ep.parent_id AS sid, COUNT(*) AS missing_count
                FROM library_items ep
                WHERE ep.item_type = 'episode' AND ep.local_status = 'Faltante'
                  AND ep.emu_in_catalog = 0
                  AND json_extract(ep.raw_json, '$.episode.monitored') = 1
                  AND json_extract(ep.raw_json, '$.episode.airDateUtc') IS NOT NULL
                  AND json_extract(ep.raw_json, '$.episode.airDateUtc') <= ?
                  AND UPPER(COALESCE(json_extract(ep.raw_json, '$.episode.title'), '')) <> 'TBA'
                GROUP BY ep.parent_id
            ) cnt ON cnt.sid = s.id
            WHERE s.item_type = 'season'""",
        (now_iso,),
    ).fetchall():
        row = dict(row)
        missing_count = row.get("missing_count")
        # Exactly one monitored episode missing from an otherwise-complete
        # season → name it as that specific episode (Serie (Año) - SxxEyy),
        # same as if you'd request just that one; more than one missing
        # still means "the whole season" (Serie (Año) - Temporada X).
        single_missing_episode = None
        if missing_count == 1:
            ep_row = conn.execute(
                """SELECT episode_number FROM library_items
                   WHERE parent_id = ? AND item_type = 'episode' AND local_status = 'Faltante'
                     AND emu_in_catalog = 0
                     AND json_extract(raw_json, '$.episode.monitored') = 1
                     AND json_extract(raw_json, '$.episode.airDateUtc') IS NOT NULL
                     AND json_extract(raw_json, '$.episode.airDateUtc') <= ?
                     AND UPPER(COALESCE(json_extract(raw_json, '$.episode.title'), '')) <> 'TBA'
                   LIMIT 1""",
                (row["id"], now_iso),
            ).fetchone()
            single_missing_episode = ep_row["episode_number"] if ep_row else None
        _push(row, 3, name=_rec_content_name(conn, row, episode=single_missing_episode),
              missing_count=missing_count)

    # Groups 2, 3 & 4: newest-first within each group (stable sort: order by
    # recency, then by group so the blocks stay in order 2 → 3 → 4). Group 1 keeps
    # its own order (by reward, from the SQL) and goes first.
    recs.sort(key=lambda d: d.get("_added") or "", reverse=True)
    recs.sort(key=lambda d: d["rec_group"])
    for d in recs:
        d.pop("_added", None)
    # El tope corta por el final, pero no deja un grupo sin sitio: las peticiones (grupo 1) van primero y lo que
    # sobra se reparte a partes iguales entre los grupos 2, 3 y 4 (el que no llena su parte la cede a los demás).
    if limit > 0:
        g1_recs = g1_recs[:limit]
        por_grupo = [[d for d in recs if d["rec_group"] == g] for g in (2, 3, 4)]
        recs = [d for lista in _repartir_cupo(por_grupo, limit - len(g1_recs)) for d in lista]
    recs = g1_recs + recs
    # Los idiomas salen ya como códigos de eMuwarez (ESP primero), los mismos que lleva el nombre del torrent.
    for d in recs:
        d["audio_languages"] = _split_languages(d.get("audio_languages"))
        d["subtitle_languages"] = _split_languages(d.get("subtitle_languages"))
    return recs
