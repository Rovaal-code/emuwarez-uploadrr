"""Sincronización de la biblioteca con Radarr/Sonarr: alta y actualización de elementos, avisos de faltantes,
progreso y bloqueo de la sincronización."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from ...database import borrar_biblioteca, get_state, set_state
from ...integrations import radarr, sonarr
from ...integrations.base import IntegrationError
from ...models import InstanceConfig, LibraryItem, LocalStatus, MediaKind
from ..instances import list_instances
from ..tasks import start_task, finish_task
from ..eventos import EVENTO_SYNC_EMPEZADA, EVENTO_SYNC_TERMINADA, publicar

from .castellano import recompute_spanish_flags
from .valores import olvidar_valores_de_filtro


_NOTIFIABLE_ITEM_TYPES = (MediaKind.MOVIE.value, MediaKind.EPISODE.value)

logger = logging.getLogger("emuwarez.library")

# Lo que una ficha sin archivo solo sabe por la cola de descargas (o por no haberla podido leer).
_ESTADOS_QUE_DA_LA_COLA = (
    LocalStatus.QUEUED.value, LocalStatus.DOWNLOADING.value, LocalStatus.PENDING_IMPORT.value,
    LocalStatus.IMPORT_ERROR.value, LocalStatus.ERROR.value, LocalStatus.UNKNOWN.value,
)


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_library_item(
    conn: sqlite3.Connection, item: LibraryItem, *, notify_missing: bool = True,
    defer_to: Optional[list] = None, seen_at: Optional[str] = None, sin_perder_disponible: bool = False,
    cola_desconocida: bool = False,
) -> int:
    """`defer_to`: collect the "turned Faltante" notification into this list as
    (item, item_id) instead of emitting it right away. Used by the Sonarr sync
    so a season whose episodes ALL went missing at once can send one season
    notification instead of one per episode (see _emit_missing_notifications).
    `seen_at`: la marca del recorrido que lo ve (ver sync_instance).
    `sin_perder_disponible`: una ficha Disponible no pasa a otro estado (la resincronización de una ficha).
    `cola_desconocida`: no se leyó la cola de descargas; una ficha sin archivo conserva su estado de cola, y una
    nueva queda en Desconocido, en vez de pasar a Faltante (y avisar)."""
    # Captured BEFORE the upsert overwrites it — this is what lets us fire a
    # notification on the exact sync pass where the item turns Faltante,
    # instead of guessing from a date (see services/notification_center.py's
    # "content_missing_new" event). A row that doesn't exist yet counts as
    # "wasn't Faltante" too, since a brand-new item that's already missing on
    # its very first sync is exactly the case we want to catch (the user's
    # Monday-request scenario) — not just later status flips.
    check_transition = notify_missing and item.item_type in _NOTIFIABLE_ITEM_TYPES
    prev_row = None
    if check_transition or sin_perder_disponible or cola_desconocida:
        prev_row = conn.execute(
            "SELECT id, local_status FROM library_items WHERE instance_id = ? AND item_type = ? AND external_id = ?",
            (item.instance_id, item.item_type, item.external_id),
        ).fetchone()
    prev_status = prev_row["local_status"] if prev_row else None
    if sin_perder_disponible and prev_status == LocalStatus.AVAILABLE.value and item.local_status != prev_status:
        return int(prev_row["id"])
    if cola_desconocida and item.local_status == LocalStatus.MISSING.value:
        if prev_status is None:
            item.local_status = LocalStatus.UNKNOWN.value
        elif prev_status in _ESTADOS_QUE_DA_LA_COLA:
            item.local_status = prev_status

    data = item.to_dict()
    # mal_id: Radarr/Sonarr never provide this — resolve it against the local
    # Fribb/anime-lists mirror instead (see services/anime_lists.py). Runs on
    # every upsert (not just new rows), so a mal_id that disappears from a
    # later refresh of that table self-corrects back to None on the next
    # sync instead of staying permanently stale. La tabla la deja al día
    # sync_instance una vez por recorrido, no cada ficha.
    has_relevant_id = item.tmdb_id if item.item_type == MediaKind.MOVIE.value else item.tvdb_id
    if has_relevant_id:
        from ..anime_lists import get_mal_id as _get_mal_id
        data["mal_id"] = _get_mal_id(
            conn, item_type=item.item_type, tvdb_id=item.tvdb_id,
            tmdb_id=item.tmdb_id, season_number=item.season_number,
        )
    # Only meaningful on the INSERT path (a brand-new row) — the DO UPDATE
    # SET clause below overrides it with a CASE that only bumps it on a
    # genuine transition INTO Faltante, never on a resync that leaves an
    # already-missing item missing (see _migrate_library_items_missing_since).
    data["missing_since"] = (
        datetime.now(timezone.utc).isoformat() if item.local_status == LocalStatus.MISSING.value else None
    )
    data["last_seen_at"] = seen_at
    columns = [
        "item_type", "title", "year", "original_title", "english_title", "instance_id", "instance_type",
        "instance_name", "external_id", "tmdb_id", "imdb_id", "tvdb_id", "tvmaze_id", "title_slug",
        "season_number", "episode_number", "parent_id", "path",
        "quality", "resolution", "source", "release_group", "video_codec", "audio_codec", "audio_languages",
        "audio_channels", "dynamic_range", "subtitle_languages", "size_bytes", "local_status",
        "request_status", "nomenclature_status", "request_id", "added_at", "raw_json",
        "poster_url", "backdrop_url", "mal_id", "missing_since", "last_seen_at",
    ]
    values = [data.get(col) for col in columns]
    conn.execute(
        f"""
        INSERT INTO library_items({', '.join(columns)}, updated_at)
        VALUES ({', '.join(['?'] * len(columns))}, CURRENT_TIMESTAMP)
        ON CONFLICT(instance_id, item_type, external_id) DO UPDATE SET
            title = excluded.title,
            year = excluded.year,
            original_title = excluded.original_title,
            english_title = excluded.english_title,
            instance_type = excluded.instance_type,
            instance_name = excluded.instance_name,
            tmdb_id = excluded.tmdb_id,
            imdb_id = excluded.imdb_id,
            tvdb_id = excluded.tvdb_id,
            tvmaze_id = excluded.tvmaze_id,
            title_slug = excluded.title_slug,
            season_number = excluded.season_number,
            episode_number = excluded.episode_number,
            parent_id = excluded.parent_id,
            path = excluded.path,
            quality = excluded.quality,
            resolution = excluded.resolution,
            source = excluded.source,
            release_group = excluded.release_group,
            video_codec = excluded.video_codec,
            audio_codec = excluded.audio_codec,
            audio_languages = excluded.audio_languages,
            audio_channels = excluded.audio_channels,
            dynamic_range = excluded.dynamic_range,
            subtitle_languages = excluded.subtitle_languages,
            size_bytes = excluded.size_bytes,
            local_status = excluded.local_status,
            -- Keep the strict nomenclature verdict while the FILE is unchanged
            -- (same path + size); reset to whatever the sync brings ('No
            -- comprobada') when the file is new or changed (e.g. renamed after
            -- an upload / re-downloaded).
            nomenclature_status = CASE
                WHEN library_items.path IS excluded.path
                 AND library_items.size_bytes IS excluded.size_bytes
                THEN library_items.nomenclature_status
                ELSE excluded.nomenclature_status END,
            nomenclature_expected = CASE
                WHEN library_items.path IS excluded.path
                 AND library_items.size_bytes IS excluded.size_bytes
                THEN library_items.nomenclature_expected ELSE NULL END,
            nomenclature_checked_at = CASE
                WHEN library_items.path IS excluded.path
                 AND library_items.size_bytes IS excluded.size_bytes
                THEN library_items.nomenclature_checked_at ELSE NULL END,
            raw_json = excluded.raw_json,
            poster_url = excluded.poster_url,
            backdrop_url = excluded.backdrop_url,
            mal_id = excluded.mal_id,
            -- Only bump on a genuine transition INTO Faltante — an item that
            -- was already Faltante and stays Faltante keeps its original
            -- missing_since, so a resync never makes it look freshly missing.
            missing_since = CASE
                WHEN excluded.local_status = 'Faltante' AND library_items.local_status IS NOT 'Faltante'
                THEN excluded.missing_since
                ELSE library_items.missing_since END,
            last_seen_at = COALESCE(excluded.last_seen_at, library_items.last_seen_at),
            updated_at = CURRENT_TIMESTAMP
        """,
        values,
    )
    row = conn.execute(
        "SELECT id FROM library_items WHERE instance_id = ? AND item_type = ? AND external_id = ?",
        (item.instance_id, item.item_type, item.external_id),
    ).fetchone()
    conn.commit()
    item_id = int(row["id"])

    if (
        check_transition
        and item.local_status == LocalStatus.MISSING.value
        and prev_status != LocalStatus.MISSING.value
    ):
        if defer_to is None:
            _notify_new_missing(conn, item, item_id)
        else:
            defer_to.append((item, item_id))

    return item_id


def _notify_new_missing(conn: sqlite3.Connection, item: LibraryItem, item_id: int) -> None:
    """Best-effort — never raises, mirrors the existing notification call
    sites (see upload_execution.py::_notify_upload_completed)."""
    try:
        from ..notification_center import emit
        title = item.title or "Contenido"
        year_part = f" ({item.year})" if item.year else ""
        # A movie added to Radarr before it's actually released (still
        # "inCinemas"/"announced") can't be requested on eMuwarez yet — same
        # status='released' gate get_dashboard_recommendations' "Faltante"
        # group already requires. Say so instead of unconditionally
        # suggesting "you may want to create a request" for something with
        # no downloadable release to request in the first place.
        body = "No está disponible. Puede que quieras crear una petición en eMuwarez."
        if item.item_type == MediaKind.MOVIE.value and item.raw_json:
            try:
                radarr_status = json.loads(item.raw_json).get("status")
            except (TypeError, ValueError):
                radarr_status = None
            if radarr_status and radarr_status != "released":
                body = "Todavía no se ha estrenado (según Radarr) — no se puede pedir en eMuwarez hasta que salga."
        emit(
            conn, "content_missing_new",
            "Contenido nuevo faltante",
            body,
            link="/library",
            level="warning",
            entity_type="library_item",
            entity_id=item_id,
            poster_url=item.poster_url,
            content_title=f"{title}{year_part}",
        )
    except Exception:
        logger.exception("No se pudo emitir la notificación de contenido faltante para el item %s", item_id)


def _notify_new_missing_series(
    conn: sqlite3.Connection, series_item: LibraryItem, series_row_id: Optional[int],
    season_count: int, episode_count: int,
) -> None:
    """One notification for a series that is missing in its entirety, instead of
    one per season. Best-effort — never raises."""
    try:
        from ..notification_center import emit
        year_part = f" ({series_item.year})" if series_item.year else ""
        emit(
            conn, "content_missing_new",
            "Serie nueva faltante",
            f"No tienes ningún capítulo de sus {season_count} temporadas "
            f"({episode_count} capítulos en total). "
            "Puede que quieras crear una petición en eMuwarez.",
            link="/library",
            level="warning",
            entity_type="library_item",
            entity_id=series_row_id,
            poster_url=series_item.poster_url,
            content_title=f"{series_item.title or 'Serie'}{year_part}",
        )
    except Exception:
        logger.exception(
            "No se pudo emitir la notificación de serie faltante (%s)", series_item.title,
        )


def _notify_new_missing_season(
    conn: sqlite3.Connection, series_title: str, year, season_number: int,
    season_row_id: Optional[int], poster_url: Optional[str], episode_count: int,
) -> None:
    """One notification for a whole season that went missing, instead of one per
    episode. Best-effort — never raises, same as _notify_new_missing."""
    try:
        from ..notification_center import emit
        year_part = f" ({year})" if year else ""
        emit(
            conn, "content_missing_new",
            "Temporada nueva faltante",
            f"No tienes ninguno de sus {episode_count} capítulos. "
            "Puede que quieras crear una petición en eMuwarez.",
            link="/library",
            level="warning",
            entity_type="library_item",
            entity_id=season_row_id,
            poster_url=poster_url,
            content_title=f"{series_title}{year_part} - Temporada {season_number}",
        )
    except Exception:
        logger.exception(
            "No se pudo emitir la notificación de temporada faltante (%s T%s)",
            series_title, season_number,
        )


# A season notification replaces the per-episode ones only when there is more
# than one episode to replace: for a single-episode season the two say exactly
# the same thing, and the episode-level one is the more precise of the two.
_MIN_EPISODES_FOR_SEASON_NOTIFICATION = 2


# Below this, one notification per season is already quiet enough, and naming
# the seasons is more useful than collapsing them into the series.
_MIN_SEASONS_FOR_SERIES_NOTIFICATION = 2


def _emit_missing_notifications(
    conn: sqlite3.Connection,
    pending: list,
    ep_items_by_season: dict,
    season_row_id_by_number: dict,
    series_item: LibraryItem,
    series_row_id: Optional[int] = None,
) -> None:
    """Decide, per season, whether to send one season notification or the
    individual episode ones collected during the sync pass.

    Adding a series to Sonarr with nothing downloaded used to fire one
    notification per episode — twenty for a normal season, hundreds for a long
    running show — which buried everything else in the bell. A season whose
    episodes are ALL missing says the same thing in one line, and a series
    whose seasons are ALL missing says it in one line for the whole show."""
    if not pending:
        return

    deferred_ids = {id(item) for item, _ in pending}
    handled: set[int] = set()

    # Seasons that actually hold episodes — an empty (unaired) season says
    # nothing about whether the series is missing, so it must not be what
    # stops the whole series from collapsing into one notification.
    seasons_with_episodes = {n: eps for n, eps in ep_items_by_season.items() if eps}

    # The whole series missing → one notification for it, not one per season.
    # This is the "just added an 8 season show to Sonarr" case, which was ~150
    # notifications before any of this and would still be 8 with only the
    # per-season grouping below.
    if len(seasons_with_episodes) >= _MIN_SEASONS_FOR_SERIES_NOTIFICATION and all(
        all(e.local_status == LocalStatus.MISSING.value for e in eps)
        for eps in seasons_with_episodes.values()
    ) and any(id(e) in deferred_ids for eps in seasons_with_episodes.values() for e in eps):
        _notify_new_missing_series(
            conn, series_item, series_row_id, len(seasons_with_episodes),
            sum(len(eps) for eps in seasons_with_episodes.values()),
        )
        return

    for season_num, eps in ep_items_by_season.items():
        if len(eps) < _MIN_EPISODES_FOR_SEASON_NOTIFICATION:
            continue
        # Every episode of the season missing, and at least one of them newly
        # so — a season already fully missing on the previous pass has nothing
        # new to report.
        if not all(e.local_status == LocalStatus.MISSING.value for e in eps):
            continue
        if not any(id(e) in deferred_ids for e in eps):
            continue
        _notify_new_missing_season(
            conn, series_item.title or "Serie", series_item.year, season_num,
            season_row_id_by_number.get(season_num), series_item.poster_url, len(eps),
        )
        handled.update(id(e) for e in eps)

    for item, item_id in pending:
        if id(item) not in handled:
            _notify_new_missing(conn, item, item_id)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

# The season-level "Información técnica" fields — a value only appears when
# every AVAILABLE episode agrees on it, same idea as the movie-level fields
# but rolled up across a season's episodes instead of read from one file.
_SEASON_ROLLUP_FIELDS = (
    "resolution", "source", "video_codec", "audio_codec",
    "audio_languages", "subtitle_languages",
)


def _update_season_rollup(conn: sqlite3.Connection, season_row_id: int, episode_items: list[LibraryItem]) -> None:
    available = [e for e in episode_items if e.local_status == LocalStatus.AVAILABLE.value]
    values: dict[str, str | None] = {}
    for field in _SEASON_ROLLUP_FIELDS:
        distinct = {getattr(e, field) for e in available}
        values[field] = next(iter(distinct)) if len(distinct) == 1 and None not in distinct else None
    # Tamaño (size_bytes) is a SUM, not an agreement rollup — episodes are
    # naturally different sizes, that's not a "disagreement" to hide.
    sizes = [e.size_bytes for e in available if e.size_bytes is not None]
    total_size = sum(sizes) if sizes else None
    conn.execute(
        "UPDATE library_items SET resolution = ?, source = ?, video_codec = ?, "
        "audio_codec = ?, audio_languages = ?, subtitle_languages = ?, size_bytes = ? WHERE id = ?",
        (
            values["resolution"], values["source"], values["video_codec"],
            values["audio_codec"], values["audio_languages"], values["subtitle_languages"],
            total_size, season_row_id,
        ),
    )


def _comprobar_capitulos(
    conn: sqlite3.Connection, series: dict, series_row_id: int, episodes: list[dict], files_by_id: dict,
) -> None:
    """Lanza si los capítulos de Sonarr no cuadran con lo que se sabe de la serie: ninguno cuando tiene o tenía, o
    capítulos con un archivo que no ha mandado. Guardarlo los borraría o los daría por faltantes, con su aviso."""
    nombre = series.get("title") or series["id"]
    if not episodes:
        estadisticas = [series.get("statistics") or {}] + [t.get("statistics") or {} for t in series.get("seasons") or []]
        esperados = max(int(e.get("totalEpisodeCount") or e.get("episodeCount") or 0) for e in estadisticas)
        guardados = conn.execute(
            "SELECT 1 FROM library_items e JOIN library_items s ON e.parent_id = s.id "
            "WHERE s.parent_id = ? AND e.item_type = 'episode' LIMIT 1", (series_row_id,),
        ).fetchone()
        if esperados or guardados:
            raise IntegrationError(f"Sonarr no ha devuelto los capítulos de la serie {nombre}")
    if {e["episodeFileId"] for e in episodes if e.get("episodeFileId")} - files_by_id.keys():
        raise IntegrationError(f"Sonarr no ha devuelto todos los archivos de la serie {nombre}")


def _sync_one_series(
    conn: sqlite3.Connection,
    instance: InstanceConfig,
    series: dict,
    *,
    localize_titles: bool,
    series_queue: Optional[dict] = None,
    ep_queue: Optional[dict] = None,
    include_episodes: bool = True,
    bump_fn=None,
    notify_missing: bool = True,
    seen_at: Optional[str] = None,
    sin_perder_disponible: bool = False,
    cola_desconocida: bool = False,
) -> int:
    """Upsert one series row (+ its seasons/episodes if include_episodes) from
    a single Sonarr `series` dict. Extracted from sync_instance's own Sonarr
    loop body so a single-item resync (resync_single_item, below) can reuse
    the exact same conversion/assembly logic for just one series instead of
    re-fetching and re-walking the whole instance. Calls `bump_fn()` once per
    row written (mirrors sync_instance's own progress bump) and returns the
    missing-count for just this series."""
    missing = 0

    def _bump() -> None:
        if bump_fn:
            bump_fn()

    if localize_titles and series.get("title") and series.get("tmdbId"):
        from ..tmdb_titles import resolve_series_title
        # El título que manda Sonarr se guarda ANTES de pisarlo con el español.
        # Sonarr no tiene un campo `originalTitle` como Radarr, así que el
        # mapeador lo buscaba y no lo encontraba nunca: el inglés se perdía
        # aquí mismo y después el asistente pagaba una llamada a TMDb para
        # recuperar lo que ya habíamos tenido delante.
        #
        # Se guarda solo si de verdad cambia. Si TMDb devuelve lo mismo que
        # Sonarr (una serie nunca retitulada, como One Piece), no hay dos
        # títulos que ofrecer y anotarlo haría que el desplegable enseñara la
        # misma cadena dos veces.
        titulo_de_sonarr = series["title"]
        series["title"] = resolve_series_title(conn, series.get("tmdbId"), titulo_de_sonarr)
        if series["title"] != titulo_de_sonarr:
            series["englishTitle"] = titulo_de_sonarr
    series_item = sonarr.series_to_library_item(
        series,
        instance_id=int(instance.id),
        instance_name=instance.name,
        series_queue_map=series_queue,
    )
    series_row_id = upsert_library_item(
        conn, series_item, notify_missing=notify_missing, seen_at=seen_at, sin_perder_disponible=sin_perder_disponible,
        cola_desconocida=cola_desconocida)
    _bump()
    if series_item.local_status in LocalStatus.not_available():
        missing += 1

    if include_episodes and series.get("id"):
        files = sonarr.get_episode_files(instance.url, instance.api_key, int(series["id"]))
        files_by_id = {f.get("id"): f for f in files if f.get("id") is not None}
        episodes = sonarr.get_episodes(instance.url, instance.api_key, int(series["id"]))
        _comprobar_capitulos(conn, series, series_row_id, episodes, files_by_id)

        episodes_by_season: dict[int, list[dict]] = {}
        for ep in episodes:
            season_num = ep.get("seasonNumber")
            if season_num is None:
                continue
            episodes_by_season.setdefault(int(season_num), []).append(ep)

        def _file_count(season_eps: list[dict]) -> int:
            return sum(
                1 for ep in season_eps
                if ep.get("episodeFileId") and files_by_id.get(ep.get("episodeFileId"))
            )

        season_row_id_by_number: dict[int, int] = {}
        seen_season_numbers: set[int] = set()
        for season_entry in series.get("seasons") or []:
            season_num = season_entry.get("seasonNumber")
            if season_num is None:
                continue
            season_num = int(season_num)
            seen_season_numbers.add(season_num)
            season_eps = episodes_by_season.get(season_num, [])
            stats_present = bool(season_entry.get("statistics"))
            season_item = sonarr.season_to_library_item(
                series, season_entry,
                instance_id=int(instance.id),
                instance_name=instance.name,
                parent_id=series_row_id,
                episode_count_override=None if stats_present else len(season_eps),
                file_count_override=None if stats_present else _file_count(season_eps),
            )
            season_row_id_by_number[season_num] = upsert_library_item(
                conn, season_item, notify_missing=notify_missing, seen_at=seen_at,
                sin_perder_disponible=sin_perder_disponible)
            _bump()
            if season_item.local_status in LocalStatus.not_available():
                missing += 1

        for season_num, season_eps in episodes_by_season.items():
            if season_num in seen_season_numbers:
                continue
            synthetic_entry = {"seasonNumber": season_num, "statistics": {}}
            season_item = sonarr.season_to_library_item(
                series, synthetic_entry,
                instance_id=int(instance.id),
                instance_name=instance.name,
                parent_id=series_row_id,
                episode_count_override=len(season_eps),
                file_count_override=_file_count(season_eps),
            )
            season_row_id_by_number[season_num] = upsert_library_item(
                conn, season_item, notify_missing=notify_missing, seen_at=seen_at,
                sin_perder_disponible=sin_perder_disponible)
            _bump()
            if season_item.local_status in LocalStatus.not_available():
                missing += 1

        ep_items_by_season: dict[int, list[LibraryItem]] = {}
        # (item, item_id) for every episode that turned Faltante on this pass.
        pending_missing: list[tuple[LibraryItem, int]] = []
        for episode in episodes:
            ep_file = (
                files_by_id.get(episode.get("episodeFileId"))
                if episode.get("episodeFileId")
                else None
            )
            season_num = episode.get("seasonNumber")
            parent_season_id = (
                season_row_id_by_number.get(int(season_num))
                if season_num is not None else None
            )
            ep_item = sonarr.episode_to_library_item(
                episode, ep_file, series,
                instance_id=int(instance.id),
                instance_name=instance.name,
                ep_queue_map=ep_queue,
                parent_id=parent_season_id,
            )
            # Collected, not emitted: the decision of "one season notification
            # or twenty episode ones" can only be made once every episode of
            # the season has been through here.
            upsert_library_item(
                conn, ep_item, notify_missing=notify_missing, defer_to=pending_missing, seen_at=seen_at,
                sin_perder_disponible=sin_perder_disponible, cola_desconocida=cola_desconocida,
            )
            _bump()
            if ep_item.local_status != LocalStatus.AVAILABLE.value:
                missing += 1
            if season_num is not None:
                ep_items_by_season.setdefault(int(season_num), []).append(ep_item)

        # Season-level rollup (resolution/source/codecs/audio/subs): only
        # set when every AVAILABLE episode agrees, so the "Información
        # técnica" card's "–" genuinely means "these episodes disagree"
        # instead of the field simply never having been computed at all
        # (season_to_library_item never sets these — they defaulted to None
        # unconditionally, for every season, agreeing or not).
        for season_num, season_row_id in season_row_id_by_number.items():
            _update_season_rollup(conn, season_row_id, ep_items_by_season.get(season_num, []))

        _emit_missing_notifications(
            conn, pending_missing, ep_items_by_season, season_row_id_by_number, series_item,
            series_row_id,
        )

    return missing


def volver_a_cruzar_peticiones(conn: sqlite3.Connection, peticiones: list[int]) -> None:
    """Las peticiones que casaban con algo que se ha borrado casan ya con la copia que quede (la de 4K) o con
    nada, y entonces enseñan el póster de TMDb, sin esperar a la sincronización de peticiones, que es diaria.
    Nunca lanza: el borrado ya está hecho, y esa sincronización vuelve a cruzarlas todas."""
    if not peticiones:
        return
    from ..request_readiness import _biblioteca, evaluate_request_readiness
    from ..requests import match_single_request, rellenar_posters
    try:
        biblioteca = _biblioteca(conn)
        for rid in peticiones:
            match_single_request(conn, rid)
            evaluate_request_readiness(rid, conn, biblioteca)
        # Solo estas: tras actualizar, todas las que no casan esperan aún su primer póster.
        rellenar_posters(conn, peticiones)
    except Exception:
        conn.rollback()
        logger.exception("No se pudieron volver a cruzar las peticiones de lo borrado de la biblioteca")


class SincronizacionParcial(IntegrationError):
    """El recorrido de la instancia terminó pero alguna serie falló: el resto está al día y esas siguen como estaban."""

    def __init__(self, mensaje: str, imported: int, missing: int):
        super().__init__(mensaje)
        self.imported = imported
        self.missing = missing


# Marca de la instancia cuyo primer recorrido no ha acabado: sin filas aún, o cortado por un error o una parada.
_PRIMERA_SYNC_SIN_ACABAR = "biblioteca_primera_sync_sin_acabar_{}"


def _marcar_serie_vista(conn: sqlite3.Connection, instance_id: int, series_id, visto: str) -> None:
    """Que su recorrido fallara no es que ya no estén: la serie y lo que cuelga de ella cuentan como vistos."""
    conn.execute(
        "WITH RECURSIVE rama(id) AS ("
        "SELECT id FROM library_items WHERE instance_id = ? AND item_type = 'series' AND external_id = ? "
        "UNION SELECT h.id FROM library_items h JOIN rama ON h.parent_id = rama.id) "
        "UPDATE library_items SET last_seen_at = ? WHERE id IN (SELECT id FROM rama)",
        (instance_id, str(series_id), visto),
    )


def _prepare_movie(conn: sqlite3.Connection, movie: dict) -> None:
    """Deja en la ficha de Radarr el título en español y el inglés (TMDb, con caché), para que generar la nomenclatura
    no salga a la red. `originalTitle` no vale de inglés: en un anime es japonés."""
    if movie.get("tmdbId") and movie.get("title"):
        from ..tmdb_titles import resolve_english_title, resolve_movie_title
        movie["title"] = resolve_movie_title(conn, movie.get("tmdbId"), movie["title"])
        movie["englishTitle"] = resolve_english_title(conn, "movie", movie.get("tmdbId"), movie.get("originalTitle"))


def sync_instance(
    conn: sqlite3.Connection,
    instance: InstanceConfig,
    *,
    include_episodes: bool = False,
    on_progress=None,
    on_total=None,
) -> tuple[int, int]:
    imported = 0
    missing = 0
    # Lo que acabe el recorrido sin esta marca ya no está en Radarr/Sonarr.
    visto = datetime.now(timezone.utc).isoformat()

    # Suppress "content_missing_new" notifications during this instance's very
    # first sync — a fresh Radarr/Sonarr connection can insert hundreds of
    # already-missing rows in one pass, and none of those were "just
    # requested" the way the feature is meant to catch. Later, incremental
    # syncs (this instance already has rows) behave normally. Un primer
    # recorrido cortado deja filas a medias: la marca hace que el siguiente
    # siga contando como primero.
    sin_acabar = _PRIMERA_SYNC_SIN_ACABAR.format(instance.id)
    tiene_filas = conn.execute(
        "SELECT 1 FROM library_items WHERE instance_id = ? LIMIT 1", (instance.id,)
    ).fetchone() is not None
    if not tiene_filas:
        set_state(conn, sin_acabar, "1")
        conn.commit()
    notify_missing = tiene_filas and get_state(conn, sin_acabar) != "1"
    fallos: list[str] = []
    cola_desconocida = False

    def _bump() -> None:
        nonlocal imported
        imported = imported + 1
        if on_progress:
            on_progress(imported)

    def _vacio(que: str) -> IntegrationError:
        return IntegrationError(
            f"{instance.type.capitalize()} «{instance.name}» ha devuelto 0 {que} y su biblioteca ya tiene elementos: "
            "no se borra nada. Si la has vaciado a propósito, quita la instancia.")

    def _sin_cola(exc: Exception) -> None:
        # La cola no es un listado de lo que tienes: sin ella se sigue, y lo que se descarga conserva su estado.
        nonlocal cola_desconocida
        cola_desconocida = True
        logger.warning("No se pudo leer la cola de %s «%s»; lo que se descarga conserva su estado: %s",
                       instance.type, instance.name, exc)

    from ..anime_lists import ensure_anime_id_map
    if instance.type == "radarr":
        queue_map = {}
        try:
            queue_map = radarr.build_queue_map(radarr.get_queue(instance.url, instance.api_key))
        except Exception as exc:
            _sin_cola(exc)
        movies = list(radarr.get_movies(instance.url, instance.api_key))
        # [] solo es de fiar si la instancia aún no tiene nada: si no, borraría todo lo suyo.
        if not movies and tiene_filas:
            raise _vacio("películas")
        ensure_anime_id_map(conn)
        if on_total:
            on_total(len(movies))  # total items to import from this instance
        for movie in movies:
            _prepare_movie(conn, movie)
            item = radarr.movie_to_library_item(
                movie,
                instance_id=int(instance.id),
                instance_name=instance.name,
                queue_map=queue_map,
            )
            upsert_library_item(
                conn, item, notify_missing=notify_missing, seen_at=visto, cola_desconocida=cola_desconocida)
            _bump()
            if item.local_status != LocalStatus.AVAILABLE.value:
                missing += 1

    elif instance.type == "sonarr":
        from ..tmdb_titles import series_titles_localized
        localize_titles = series_titles_localized(conn)
        series_queue, ep_queue = {}, {}
        try:
            queue_records = sonarr.get_queue(instance.url, instance.api_key)
            series_queue = sonarr.build_series_queue_map(queue_records)
            ep_queue = sonarr.build_episode_queue_map(queue_records)
        except Exception as exc:
            _sin_cola(exc)
        series_list = list(sonarr.get_series(instance.url, instance.api_key))
        if not series_list and tiene_filas:
            raise _vacio("series")
        ensure_anime_id_map(conn)
        if on_total:
            # One row per series + one per season + all their episodes (from
            # Sonarr's own stats) — _bump() below fires once for EACH of
            # these three levels, so all three must be counted here or
            # "done" runs past "total" partway through (seasons were
            # missing from this count entirely before). series["seasons"]
            # is already present on each series from get_series() above, no
            # extra request needed. totalEpisodeCount is Sonarr's own cached
            # stat and can drift slightly from the episode list fetched
            # per-series below — an occasional few-off "total" from that is
            # expected and self-corrects next sync, unlike the season gap.
            total = len(series_list) + sum(len(s.get("seasons") or []) for s in series_list)
            if include_episodes:
                total += sum(int((s.get("statistics") or {}).get("totalEpisodeCount") or 0) for s in series_list)
            on_total(total)
        for series in series_list:
            # Una serie que falla (un error de Sonarr con sus capítulos) no frena a las demás.
            try:
                missing += _sync_one_series(
                    conn, instance, series,
                    localize_titles=localize_titles, series_queue=series_queue, ep_queue=ep_queue,
                    include_episodes=include_episodes, bump_fn=_bump,
                    notify_missing=notify_missing, seen_at=visto, cola_desconocida=cola_desconocida,
                )
            except sqlite3.Error:
                raise
            except Exception as exc:
                fallos.append(f"{series.get('title') or series.get('id')}: {exc}")
                logger.warning("No se pudo sincronizar la serie %s de «%s»: %s", series.get("title"), instance.name, exc)
                _marcar_serie_vista(conn, instance.id, series.get("id"), visto)

    # Solo se llega aquí tras recorrer los listados: uno que falla lanza y no se borra nada.
    donde = "instance_id = ? AND (last_seen_at IS NULL OR last_seen_at != ?)"
    if not include_episodes:
        # Sin capítulos no se recorren temporadas ni capítulos: no haberlos visto no dice que ya no estén.
        donde += " AND item_type IN ('movie', 'series')"
    borrados, peticiones = borrar_biblioteca(conn, donde, (instance.id, visto))
    # Con series sin sincronizar, sin saber qué se descarga o sin capítulos (`sync` del CLI sin --episodes), el
    # primer recorrido sigue sin acabar: lo que falta saldría como nuevo faltante en el siguiente.
    sin_capitulos = instance.type == "sonarr" and not include_episodes
    set_state(conn, sin_acabar, "1" if (fallos or cola_desconocida or sin_capitulos) and not notify_missing else "0")
    conn.commit()
    if borrados:
        logger.info("Borrados %d elementos que %s «%s» ya no tiene", borrados, instance.type, instance.name)
    volver_a_cruzar_peticiones(conn, peticiones)
    if fallos:
        raise SincronizacionParcial(
            f"{len(fallos)} serie(s) sin sincronizar, siguen como estaban: " + "; ".join(fallos[:3]), imported, missing)
    return imported, missing


# Live progress of the library sync, so the UI can show a card with the running
# element count. Single-process app → an in-memory dict is enough.
_LIB_SYNC_LOCK = threading.Lock()
_LIB_SYNC_PROGRESS: dict = {"active": False, "done": False, "phase": "", "imported": 0,
                           "missing": 0, "total": 0, "instance": "", "instance_type": "", "error": None}


def get_lib_sync_progress() -> dict:
    with _LIB_SYNC_LOCK:
        return dict(_LIB_SYNC_PROGRESS)


def _set_lib_progress(**kw) -> None:
    with _LIB_SYNC_LOCK:
        _LIB_SYNC_PROGRESS.update(kw)


class SyncAlreadyRunning(Exception):
    """Raised by _lib_sync_guard() when a library sync is already active."""


@contextmanager
def _lib_sync_guard() -> Iterator[None]:
    """Claims _LIB_SYNC_PROGRESS for the duration of a sync_all() call, so
    every caller — the background "sincronizar biblioteca" button, the
    scheduled sync-library task (automatic tick or manual "Ejecutar ahora"),
    and the setup wizard's blocking /sync right after finishing — shares the
    exact same active/done lifecycle. Previously only the background-button
    path set `active`, so a sync triggered by the other two never showed up
    in the UI's sync banner and never blocked the manual button, and nothing
    stopped them running concurrently and interleaving writes into the same
    shared dict. Raises SyncAlreadyRunning instead of starting a second
    overlapping sync_all() if one is already in flight — every caller decides
    for itself how to report that (skip this tick, tell the user, etc.)."""
    with _LIB_SYNC_LOCK:
        if _LIB_SYNC_PROGRESS.get("active"):
            raise SyncAlreadyRunning()
        _LIB_SYNC_PROGRESS.update(active=True, done=False, error=None, phase="Iniciando…",
                                  imported=0, missing=0, total=0, instance="", instance_type="")
    # Fuera del candado, que publicar no tiene por qué sujetarlo. La barra de
    # arriba tiene que aparecer al EMPEZAR, y hasta ahora eso se descubría con
    # un sondeo cada 8 segundos por si la había lanzado otra pestaña o una
    # tarea programada.
    publicar(EVENTO_SYNC_EMPEZADA, {"que": "biblioteca"})
    try:
        yield
    except Exception as exc:  # noqa: BLE001 — surfaced to the progress card
        _set_lib_progress(error=str(exc), phase="Error")
        raise
    finally:
        _set_lib_progress(active=False, done=True)
        # Aquí termina TODA sincronización de biblioteca, la arranque quien la
        # arranque (el botón, la tarea programada o el asistente de setup), así
        # que es el único sitio donde hace falta avisar.
        publicar(EVENTO_SYNC_TERMINADA, {"que": "biblioteca"})


@contextmanager
def _sin_sincronizar() -> Iterator[None]:
    """Para lo que no puede pasar a la vez que una sincronización de biblioteca: con una en marcha lanza
    SyncAlreadyRunning, y la que quiera empezar espera a que acabe. Sin la barra ni los avisos de _lib_sync_guard."""
    with _LIB_SYNC_LOCK:
        if _LIB_SYNC_PROGRESS.get("active"):
            raise SyncAlreadyRunning()
        yield


def start_library_sync_background(include_episodes: bool = True) -> dict:
    """Run sync_all in a background thread so the UI can poll the element count."""
    from ...database import connect, db_path
    with _LIB_SYNC_LOCK:
        if _LIB_SYNC_PROGRESS.get("active"):
            return {"status": "started"}  # one already running — just watch it

    def _run() -> None:
        c = connect(db_path())
        try:
            with _lib_sync_guard():
                sync_all(c, include_episodes=include_episodes)
        except SyncAlreadyRunning:
            pass  # lost the race between the check above and here — fine
        finally:
            c.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started"}


def recompute_after_sync(conn: sqlite3.Connection) -> None:
    """Derived columns every library sync must refresh once its rows are in —
    the global one and the per-instance button alike."""
    # Newly-added/changed items have emu_in_catalog=NULL until compared —
    # recompute now (against whatever eMu catalog snapshot is already
    # stored, no network call) so they're immediately eligible for
    # Recomendaciones' Group 2/3 instead of waiting on a separate eMu
    # catalog sync that may not run again for a while.
    try:
        from ..emu_catalog import recompute_emu_catalog_status
        recompute_emu_catalog_status(conn)
    except Exception:
        logger.warning("No se pudo recalcular el estado de eMuwarez tras la sincronización de biblioteca", exc_info=True)
    # Same reasoning for the Castilian flags: audio_languages and
    # subtitle_languages just changed for whatever came in, and the season/
    # series rollups above them can only be recomputed once every episode
    # of the pass is stored.
    try:
        recompute_spanish_flags(conn)
    except Exception:
        logger.warning("No se pudo recalcular el castellano (audio/subtítulos) tras la sincronización de biblioteca", exc_info=True)
    olvidar_valores_de_filtro()


def sync_all(conn: sqlite3.Connection, *, include_episodes: bool = False) -> dict:
    task_id = start_task(conn, "sync-library", "Sincronizando Radarr/Sonarr")
    total = 0
    missing = 0
    grand_total = 0  # total items expected (all instances), for the progress bar
    details: list[str] = []
    errors: list[str] = []
    sincronizadas = 0  # instancias que se leyeron, aunque alguna serie de ellas fallara

    def _report_total(t: int) -> None:
        nonlocal grand_total
        grand_total += t
        _set_lib_progress(total=grand_total)

    logger.info("Sincronización de biblioteca iniciada (episodios=%s)", include_episodes)
    try:
        for instance in list_instances(conn, enabled_only=True):
            base = total  # cumulative count before this instance
            _set_lib_progress(phase=f"Sincronizando {instance.type.capitalize()}: {instance.name}…",
                              instance=instance.name, instance_type=instance.type)
            try:
                imported, miss = sync_instance(
                    conn, instance, include_episodes=include_episodes,
                    on_progress=lambda c, b=base: _set_lib_progress(imported=b + c),
                    on_total=_report_total,
                )
                total += imported
                missing += miss
                sincronizadas += 1
                _set_lib_progress(imported=total, missing=missing)
                details.append(f"{instance.type}:{instance.name}: {imported} importados, {miss} faltantes")
                logger.info("Sincronizado %s «%s»: %d importados, %d faltantes",
                            instance.type, instance.name, imported, miss)
            except SincronizacionParcial as exc:
                total += exc.imported
                missing += exc.missing
                sincronizadas += 1
                _set_lib_progress(imported=total, missing=missing)
                err = f"{instance.type}:{instance.name}: {exc}"
                errors.append(err)
                details.append(f"ERROR — {err}")
                logger.warning("Sincronización parcial de %s «%s»: %s", instance.type, instance.name, exc)
            except Exception as exc:
                err = f"{instance.type}:{instance.name}: {exc}"
                errors.append(err)
                details.append(f"ERROR — {err}")
                logger.warning("Error sincronizando %s «%s»: %s", instance.type, instance.name, exc)
        recompute_after_sync(conn)
        summary =f"{total} elementos sincronizados; {missing} no disponibles"
        # Con todas caídas no se ha leído nada: «completada» diría al Panel que la biblioteca está al día.
        estado = "failed" if errors and not sincronizadas else "completed"
        if estado == "failed":
            summary = f"No se pudo leer ninguna instancia ({len(errors)} con error)"
            _set_lib_progress(error="; ".join(errors)[:300], phase="Error")
        finish_task(conn, task_id, estado, summary, "\n".join(details))
        logger.info("Sincronización de biblioteca terminada: %d elementos, %d no disponibles%s",
                    total, missing, f" ({len(errors)} instancias con error)" if errors else "")
        return {"imported": total, "missing": missing, "instances": len(list_instances(conn)), "errors": errors,
                "status": estado}
    except Exception as exc:
        finish_task(conn, task_id, "failed", str(exc), "\n".join(details))
        logger.error("Sincronización de biblioteca fallida: %s", exc)
        raise
