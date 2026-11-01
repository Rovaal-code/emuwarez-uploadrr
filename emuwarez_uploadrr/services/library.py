"""Library synchronization and querying."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterator, Optional, Sequence, Union

from ..database import borrar_biblioteca, get_state, set_state
from ..integrations import radarr, sonarr
from ..integrations.base import IntegrationError
from ..models import InstanceConfig, LibraryItem, LocalStatus, MediaKind, NomenclatureStatus
from .source_assistant import EMU_PROVIDERS
from .instances import list_instances
from .tasks import start_task, finish_task
from .eventos import EVENTO_SYNC_EMPEZADA, EVENTO_SYNC_TERMINADA, publicar

# Only these two are real, downloadable leaf rows — series/season local_status
# is a rollup over their children (see LocalStatus.PARTIAL), so a rollup
# flipping to "Faltante" doesn't mean anything was newly requested-and-not-
# found, just that no child is available yet. Notifying on those would also
# double up with the leaf-level (episode) notification anyway.
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
        from .anime_lists import get_mal_id as _get_mal_id
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
        from .notification_center import emit
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
        from .notification_center import emit
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
        from .notification_center import emit
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
        from .tmdb_titles import resolve_series_title
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
    from .request_readiness import _biblioteca, evaluate_request_readiness
    from .requests import match_single_request, rellenar_posters
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
        from .tmdb_titles import resolve_english_title, resolve_movie_title
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

    from .anime_lists import ensure_anime_id_map
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
        from .tmdb_titles import series_titles_localized
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
    from ..database import connect, db_path
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
        from .emu_catalog import recompute_emu_catalog_status
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


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_MISSING_STATUSES = LocalStatus.not_available()

# ---------------------------------------------------------------------------
# Castilian audio and subtitles
# ---------------------------------------------------------------------------

# Statuses that mean "you actually hold this file", so it counts towards the
# season/series rollup. Same trio the eMuwarez comparison uses.
_HELD_STATUSES = (LocalStatus.AVAILABLE.value, LocalStatus.UPLOADED.value, LocalStatus.UPLOADING.value)

# (stored column, how to read it off a leaf row). The audio flag drives the
# Español column in Biblioteca; `has_spanish_ok` is what the upload rules gate
# on, and is an OR: Castilian in the audio makes subtitles unnecessary, since
# a dubbed release doesn't need them (see services/season_pack.py).
def _leaf_audio(row, has_castellano):
    return has_castellano(row["audio_languages"])


def _leaf_subs(row, has_castellano):
    return has_castellano(row["subtitle_languages"])


def _leaf_ok(row, has_castellano):
    """1 = Castilian present one way or the other, 0 = confirmed absent from
    both, None = can't tell yet (nothing read for at least one of them)."""
    audio = has_castellano(row["audio_languages"])
    subs = has_castellano(row["subtitle_languages"])
    if audio == 1 or subs == 1:
        return 1
    if audio == 0 and subs == 0:
        return 0
    return None


_SPANISH_FLAGS = (
    ("has_spanish_audio", _leaf_audio),
    ("has_spanish_subs", _leaf_subs),
    ("has_spanish_ok", _leaf_ok),
)


def _rollup_spanish(yes: int, no: int, unknown: int) -> Optional[int]:
    """Fold a set of children into the parent's value. "Sí" demands that EVERY
    held child is Sí, so a single confirmed No settles it as No even when other
    children are still unknown, and any remaining unknown blocks a Sí."""
    if no:
        return 0
    if unknown:
        return None
    return 1 if yes else None  # nothing held → unknown, not a vacuous "Sí"


def recompute_spanish_flags(conn: sqlite3.Connection, ignore_specials: Optional[bool] = None) -> int:
    """Recompute has_spanish_audio/has_spanish_subs/has_spanish_ok for every
    row, and return how many rows ended up with a known (non-NULL) audio value.

    Three levels per flag: movie/episode leaves read their own *_languages
    column; a season folds its held episodes; a series folds the held episodes
    of all its seasons. Folding the series over episodes rather than over its
    seasons' stored values is deliberate and equivalent: a season with no held
    episodes is unknown, and letting it propagate would turn the whole series
    unknown instead of just skipping it.

    La serie no cuenta los especiales (temporada 0) con «ignorar especiales», igual que su estado, tamaño y
    nomenclatura; sin indicarlo se lee de los ajustes."""
    from .emu_format import has_castellano

    if ignore_specials is None:
        from ..database import get_setting_canonical
        ignore_specials = (get_setting_canonical(conn, "series.ignore_specials") or "true") != "false"
    held = ",".join("?" * len(_HELD_STATUSES))

    # Read once, reused by all three flags.
    leaves = conn.execute(
        "SELECT id, audio_languages, subtitle_languages FROM library_items "
        "WHERE item_type IN ('movie','episode')"
    ).fetchall()

    for flag, read_leaf in _SPANISH_FLAGS:
        # 1) Leaves — the only rows carrying a language list of their own.
        conn.executemany(
            f"UPDATE library_items SET {flag} = ? WHERE id = ?",
            [(read_leaf(r, has_castellano), r["id"]) for r in leaves],
        )

        # 2) Seasons — fold their own held episodes.
        conn.execute(
            f"UPDATE library_items SET {flag} = NULL WHERE item_type IN ('series','season')"
        )
        season_rows = conn.execute(
            f"""
            SELECT parent_id AS pid,
                   SUM(CASE WHEN {flag} = 1 THEN 1 ELSE 0 END) AS yes,
                   SUM(CASE WHEN {flag} = 0 THEN 1 ELSE 0 END) AS no,
                   SUM(CASE WHEN {flag} IS NULL THEN 1 ELSE 0 END) AS unk
              FROM library_items
             WHERE item_type = 'episode' AND parent_id IS NOT NULL AND local_status IN ({held})
             GROUP BY parent_id
            """,
            _HELD_STATUSES,
        ).fetchall()
        conn.executemany(
            f"UPDATE library_items SET {flag} = ? WHERE id = ? AND item_type = 'season'",
            [(_rollup_spanish(r["yes"], r["no"], r["unk"]), r["pid"]) for r in season_rows],
        )

        # 3) Series — fold every held episode hanging off any of its seasons.
        series_rows = conn.execute(
            f"""
            SELECT s.parent_id AS pid,
                   SUM(CASE WHEN e.{flag} = 1 THEN 1 ELSE 0 END) AS yes,
                   SUM(CASE WHEN e.{flag} = 0 THEN 1 ELSE 0 END) AS no,
                   SUM(CASE WHEN e.{flag} IS NULL THEN 1 ELSE 0 END) AS unk
              FROM library_items e
              JOIN library_items s ON e.parent_id = s.id AND s.item_type = 'season'
             WHERE e.item_type = 'episode' AND s.parent_id IS NOT NULL AND e.local_status IN ({held})
               {_specials_clause("s", ignore_specials)}
             GROUP BY s.parent_id
            """,
            _HELD_STATUSES,
        ).fetchall()
        conn.executemany(
            f"UPDATE library_items SET {flag} = ? WHERE id = ? AND item_type = 'series'",
            [(_rollup_spanish(r["yes"], r["no"], r["unk"]), r["pid"]) for r in series_rows],
        )

    conn.commit()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM library_items WHERE has_spanish_audio IS NOT NULL"
    ).fetchone()
    return int(row["n"]) if row else 0


# Sentinel status value the Biblioteca filter uses for "todos los no
# disponibles" — expands to the same LocalStatus.not_available() set that
# list_missing()/the dashboard's `missing` count already use, so removing
# the standalone Faltantes tab doesn't lose the ability to see this
# combined view from Biblioteca's own status filter.
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
            where.append(f"""(title LIKE ? OR EXISTS (
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
        from .nomenclature import _PROVIDER_TOKEN_MAP
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


def rollup_all_values(conn: sqlite3.Connection, item: dict) -> Optional[dict]:
    """TODOS los valores técnicos presentes bajo una serie o temporada.

    Las columnas de rollup de la fila guardan el valor SOLO cuando todos los
    capítulos coinciden, y NULL cuando no (_update_season_rollup). Eso es lo
    que hace de señal de acuerdo para la regla del pack, así que no se puede
    tocar. Pero como dato para enseñar es pobre: una temporada con capítulos
    en x264 y x265 salía con un guion, y ese guion no dice qué tienes.

    Esto lo calcula aparte, recorriendo los capítulos: "x264, x265". Es solo
    para la ficha; nada decide nada con esto.

    Devuelve None para películas y capítulos, que ya tienen sus propios
    valores y no resumen nada.
    """
    if item.get("item_type") not in ("series", "season"):
        return None
    if item.get("item_type") == "season":
        rows = conn.execute(
            "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode'",
            (item["id"],),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT e.* FROM library_items e
               JOIN library_items s ON e.parent_id = s.id
               WHERE s.parent_id = ? AND s.item_type = 'season' AND e.item_type = 'episode'""",
            (item["id"],),
        ).fetchall()
    # Solo los capítulos que tienes: los que faltan no aportan datos técnicos.
    disponibles = [dict(r) for r in rows if r["local_status"] == LocalStatus.AVAILABLE.value]
    if not disponibles:
        return None

    # Los idiomas se FUNDEN, no se listan. Un capítulo ya guarda varios en un
    # solo campo ("jpn/spa"), así que tratarlos como un valor entero daba
    # "jpn/spa, jpn/spa/eng": el mismo idioma repetido y nada legible. Se
    # parten y se unen en una sola lista: "jpn, spa, eng".
    _MULTIVALOR = ("audio_languages", "subtitle_languages")

    out: dict[str, str] = {}
    for field in _SEASON_ROLLUP_FIELDS:
        vistos: list[str] = []
        for ep in disponibles:
            raw = (ep.get(field) or "").strip()
            if not raw:
                continue
            partes = re.split(r"[/,]", raw) if field in _MULTIVALOR else [raw]
            for parte in partes:
                parte = parte.strip()
                if parte and parte not in vistos:
                    vistos.append(parte)
        if vistos:
            out[field] = ", ".join(vistos)

    # El proveedor (AMZN, NF, DSNP...) no es una columna: se deduce de la ruta
    # y el source de cada capítulo, así que se suma igual pero calculándolo.
    from .nomenclature import infer_provider_from_item
    proveedores: list[str] = []
    for ep in disponibles:
        code = infer_provider_from_item({"path": ep.get("path"), "source": ep.get("source")})
        if code and code not in proveedores:
            proveedores.append(code)
    if proveedores:
        # Lista, no cadena pegada: la ficha pinta un ProviderTag por cada uno,
        # con su icono y su nombre completo, y para eso necesita los códigos
        # sueltos. Pegarlos en "AMZN, NF" obligaba a enseñarlos en texto pelado.
        out["provider_codes"] = proveedores

    return out or None


def _resolve_arr_top(conn: sqlite3.Connection, item_id: int) -> dict:
    """Walk up to the movie/series row an item belongs to — Radarr/Sonarr's
    refresh/rescan commands target that level; a season/episode has none of
    its own. Returns {"ok": False, "message": ...} on any resolution
    failure, or {"ok": True, "top": ..., "instance": ...} once a usable
    Radarr/Sonarr instance is found."""
    item = get_library_item(conn, item_id)
    if not item:
        return {"ok": False, "message": "Item no encontrado."}
    top = item
    seen: set[int] = set()
    while top and top.get("item_type") not in ("movie", "series") and top.get("parent_id"):
        if top["id"] in seen:
            break
        seen.add(top["id"])
        top = get_library_item(conn, top["parent_id"])
    if not top or top.get("item_type") not in ("movie", "series"):
        return {"ok": False, "message": "No se encontró la película/serie asociada."}

    instance_id = top.get("instance_id")
    external_id = top.get("external_id")
    if not instance_id or not external_id:
        return {"ok": False, "message": "El elemento no tiene instancia/ID externo de Radarr/Sonarr."}

    from .instances import get_instance
    instance = get_instance(conn, int(instance_id))
    if not instance:
        return {"ok": False, "message": "Instancia no encontrada."}

    return {"ok": True, "top": top, "instance": instance}


def resync_single_item(conn: sqlite3.Connection, item_id: int) -> dict:
    """Re-fetch just ONE movie/series from Radarr/Sonarr and upsert it (+
    seasons/episodes for a series) — the single-item equivalent of
    sync_instance, for a caller that only needs one item refreshed (e.g.
    right after refresh_arr_and_resync's Radarr/Sonarr refresh completes)
    instead of paying for a full library resync. Best-effort: never raises.

    Sin cola de descargas y con Radarr/Sonarr quizá a medio escanear: lo Disponible no pasa a otro estado ni avisa
    de faltante; eso lo decide la sincronización completa."""
    try:
        resolved = _resolve_arr_top(conn, item_id)
        if not resolved["ok"]:
            return resolved
        top, instance = resolved["top"], resolved["instance"]
        external_id = top["external_id"]

        if top["item_type"] == "movie":
            movie = radarr.get_movie(instance.url, instance.api_key, int(external_id))
            _prepare_movie(conn, movie)
            movie_item = radarr.movie_to_library_item(
                movie, instance_id=int(instance.id), instance_name=instance.name,
            )
            upsert_library_item(
                conn, movie_item, notify_missing=False, sin_perder_disponible=True, cola_desconocida=True)
        else:
            from .tmdb_titles import series_titles_localized
            localize_titles = series_titles_localized(conn)
            series = sonarr.get_series_by_id(instance.url, instance.api_key, int(external_id))
            _sync_one_series(
                conn, instance, series, localize_titles=localize_titles, include_episodes=True,
                notify_missing=False, sin_perder_disponible=True, cola_desconocida=True,
            )
        conn.commit()
        return {"ok": True}
    except Exception as exc:
        logger.warning("No se pudo resincronizar el item %s tras el renombrado: %s", item_id, exc)
        return {"ok": False, "message": str(exc)}


def refresh_arr_and_resync(
    conn: sqlite3.Connection, item_id: int, *,
    on_log: Optional[Callable[[str, str], None]] = None,
    poll_timeout: float = 45.0,
    poll_interval: float = 2.0,
) -> dict:
    """Best-effort post-rename reconciliation: ask Radarr/Sonarr to refresh
    this movie/series' metadata + rescan its folder (RefreshMovie/
    RefreshSeries — Radarr/Sonarr's own "Refresh & Scan"), wait for that
    command to finish, then resync just this item so our own library_items
    row reflects whatever Radarr/Sonarr now reports about the renamed file.

    Never raises — a failure at any step here only means our own cache
    stays stale until the next sync; the real renamed file on disk and
    Radarr/Sonarr's own state are unaffected either way. `on_log`, if given,
    is called as `on_log(level, message)` for every step (so a caller with
    an upload job can mirror all of this into its own Actividad log)."""
    def _log(level: str, message: str) -> None:
        if on_log:
            try:
                on_log(level, message)
            except Exception:
                pass
        (logger.warning if level == "warning" else logger.info)(message)

    try:
        resolved = _resolve_arr_top(conn, item_id)
        if not resolved["ok"]:
            _log("warning", f"No se pudo localizar la instancia de Radarr/Sonarr: {resolved['message']}")
            return resolved
        top, instance = resolved["top"], resolved["instance"]
        external_id = int(top["external_id"])
        is_movie = top["item_type"] == "movie"
        service = "Radarr" if is_movie else "Sonarr"

        _log("info", f"Avisando a {service} para que actualice y escanee la ficha…")
        cmd = (
            radarr.refresh_movie(instance.url, instance.api_key, external_id) if is_movie
            else sonarr.refresh_series(instance.url, instance.api_key, external_id)
        )
        command_id = cmd.get("id") if isinstance(cmd, dict) else None

        status = None
        if not command_id:
            _log("warning", f"{service} no devolvió un id de comando; no se puede esperar a que termine.")
        else:
            deadline = time.monotonic() + poll_timeout
            while time.monotonic() < deadline:
                time.sleep(poll_interval)
                try:
                    poll = (
                        radarr.get_command_status(instance.url, instance.api_key, int(command_id)) if is_movie
                        else sonarr.get_command_status(instance.url, instance.api_key, int(command_id))
                    )
                except Exception as exc:
                    _log("warning", f"No se pudo consultar el estado del comando en {service}: {exc}")
                    break
                status = (poll or {}).get("status")
                if status in ("completed", "failed", "cancelled"):
                    break
            if status == "completed":
                _log("info", f"{service} ha terminado de actualizar y escanear.")
            elif status in ("failed", "cancelled"):
                _log("warning", f"{service} no pudo completar la actualización (estado: {status}).")
            else:
                _log("warning", f"{service} no confirmó haber terminado a tiempo; se continúa de todas formas.")

        _log("info", f"Sincronizando la ficha con los datos actualizados de {service}…")
        result = resync_single_item(conn, item_id)
        if result.get("ok"):
            _log("info", "Ficha sincronizada correctamente.")
        else:
            _log("warning", f"No se pudo sincronizar la ficha: {result.get('message')}")
        return {"ok": True}
    except Exception as exc:
        _log("warning", f"No se pudo completar la actualización con Radarr/Sonarr tras el renombrado: {exc}")
        return {"ok": False, "message": str(exc)}


def list_missing(conn: sqlite3.Connection, *, limit: int = 50, offset: int = 0) -> list[dict]:
    placeholders = ", ".join(["?"] * len(_MISSING_STATUSES))
    sql = (
        f"SELECT * FROM library_items WHERE local_status IN ({placeholders})"
        " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, [*_MISSING_STATUSES, limit, offset]).fetchall()
    return [dict(row) for row in rows]


def get_dashboard_summary(conn: sqlite3.Connection) -> dict:
    """Return aggregated counts from library_items.

    Restricted to item_type IN ('movie','episode') — real content units —
    so series/season rollup rows (organizational, not real content) never
    double-count against these totals (a series with 10 episodes must
    contribute 10, not 11 by also counting the series row itself)."""
    # When "ignorar especiales" is on, missing episodes of a special season
    # (season 0) don't count as Faltantes on the dashboard.
    from ..database import get_setting_canonical
    ignore_specials = (get_setting_canonical(conn, "series.ignore_specials") or "true") != "false"

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
    from .season_pack import pack_rollup_sql
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


def get_dashboard_recommendations(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    from .season_pack import pack_rollup_sql
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    recs: list[dict] = []
    seen_lib: set[int] = set()  # library ids already shown (so a piece of
    # content isn't repeated across groups 2 & 3 or after appearing in group 1)

    cols = ("id, item_type, title, year, poster_url, local_status, added_at, missing_since, "
            "season_number, episode_number, parent_id, size_bytes, "
            "resolution, source, tmdb_id, imdb_id, tvdb_id, instance_type, "
            "instance_id, title_slug")

    # Group 1 — every *compatible* eMuwarez request, sourced from the match
    # table (library_items.request_status only records one request per item, so
    # a series with several compatible requests would otherwise show just once).
    # One row per request, named/sized at the request's own scope (season /
    # episode), linking to that request. Ordered newest request first.
    g1 = conn.execute(
        """
        SELECT ri.id AS req_id, ri.req_scope, ri.req_season, ri.req_episode, ri.created_at AS req_created,
               (SELECT rm.library_item_id FROM request_matches rm
                WHERE rm.request_item_id = ri.id ORDER BY rm.confidence DESC LIMIT 1) AS lib_id
        FROM request_items ri
        WHERE (SELECT rm.status FROM request_matches rm
               WHERE rm.request_item_id = ri.id ORDER BY rm.confidence DESC LIMIT 1) = 'Compatible'
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
        d["content_name"] = _rec_content_name(conn, lib, season=season, episode=episode, scope=scope)
        size_episode = episode if (scope == "episode" or disp_type == "episode") else None
        d["size_bytes"] = _rec_rolled_size(conn, lib, season=season, episode=size_episode)
        d["missing_count"] = None
        d["_added"] = r["req_created"] or ""
        recs.append(d)
        seen_lib.add(int(lib_id))

    def _push(row: dict, group: int, *, name: str | None = None, size=None, missing_count=None):
        rid = int(row["id"])
        if rid in seen_lib:
            return
        seen_lib.add(rid)
        d = dict(row)
        d["rec_group"] = group
        d["content_name"] = name if name is not None else _rec_content_name(conn, d)
        d["size_bytes"] = size if size is not None else _rec_rolled_size(conn, d)
        d["rec_request_id"] = None
        d["missing_count"] = missing_count
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

    # Newest-first within each group (stable sort: order by recency, then by
    # group so the three blocks stay in order 1 → 2 → 3).
    recs.sort(key=lambda d: d.get("_added") or "", reverse=True)
    recs.sort(key=lambda d: d["rec_group"])
    for d in recs:
        d.pop("_added", None)
    return recs if limit <= 0 else recs[:limit]


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


_ROLLUP_EMPTY = {
    "provider": None, "resolution": None, "source": None, "release_group": None, "video_codec": None,
    "audio_codec": None, "audio_languages": None, "subtitle_languages": None,
}


def _aggregate_local_status(statuses: list) -> Optional[str]:
    counts: dict = {}
    for s in statuses:
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return None
    available = counts.get("Disponible", 0)
    if available == total:
        return "Disponible"
    if available == 0:
        return "Faltante"
    return "Parcial"


def _aggregate_nomenclature(statuses: list) -> Optional[str]:
    counts: dict = {}
    for s in statuses:
        counts[s] = counts.get(s, 0) + 1
    if sum(counts.values()) == 0:
        return None
    correct = counts.get("Correcta", 0)
    not_adapted = counts.get("No adaptada", 0)
    unchecked = counts.get("No comprobada", 0)
    available = correct + not_adapted + unchecked
    if available == 0:
        return "N/A"
    if unchecked > 0:
        return "No comprobada"
    if correct == available:
        return "Correcta"
    if not_adapted == available:
        return "No adaptada"
    return "Parcial"


def _aggregate_path(rows: list[dict]) -> Optional[str]:
    paths = [r["path"] for r in rows if r["path"]]
    if not paths:
        return None
    dirs = {os.path.dirname(p) for p in paths}
    if len(dirs) == 1:
        return next(iter(dirs))
    try:
        return os.path.commonpath(paths)
    except ValueError:
        return None


def _aggregate_quality(rows: list[dict]) -> dict:
    # Solo lo que se tiene: un capítulo faltante lleva todo a NULL y vaciaría la temporada entera.
    rows = [r for r in rows if r["local_status"] == LocalStatus.AVAILABLE.value]
    if not rows:
        return dict(_ROLLUP_EMPTY)

    def uniq(key: str):
        vals = {r[key] for r in rows}
        return next(iter(vals)) if len(vals) == 1 else None

    providers: set = set()
    for r in rows:
        from .nomenclature import infer_provider_from_item
        providers.add(infer_provider_from_item({"path": r["path"], "source": r["source"]}))
        if len(providers) > 1:
            break
    return {
        "provider": next(iter(providers)) if len(providers) == 1 else None,
        "resolution": uniq("resolution"),
        "source": uniq("source"),
        "release_group": uniq("release_group"),
        "video_codec": uniq("video_codec"),
        "audio_codec": uniq("audio_codec"),
        "audio_languages": uniq("audio_languages"),
        "subtitle_languages": uniq("subtitle_languages"),
    }


def _aggregate_size(sizes: list) -> Optional[int]:
    if not any(s is not None for s in sizes):
        return None
    return sum(s for s in sizes if s is not None)


# code -> nombre del proveedor, para etiquetar los valores del filtro.
_PROVIDER_NAME_BY_CODE = {p["code"]: p["name"] for p in EMU_PROVIDERS}


def _provider_label(code: Optional[str]) -> Optional[str]:
    """'Nombre (CÓDIGO)' for a provider code, e.g. 'Amazon (AMZN)'."""
    if not code:
        return None
    name = _PROVIDER_NAME_BY_CODE.get(code)
    return f"{name} ({code})" if name else code


# ---------------------------------------------------------------------------
# Agregación de una temporada/serie a partir de sus hijos, y valores de filtro
#
# Vivían dentro de web/api/library.py (auditoría, hallazgo 6.2). Son
# conocimiento de dominio: cómo se suma el tamaño de una serie, de dónde sale
# la ruta de una temporada, qué valores ofrece cada filtro.
# ---------------------------------------------------------------------------

def _specials_clause(alias: str, ignore_specials: bool) -> str:
    """SQL fragment excluding season-0 episodes when ignore_specials is on."""
    if not ignore_specials:
        return ""
    return f" AND ({alias}.season_number IS NULL OR {alias}.season_number != 0)"


def _nomenclature_rollup(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> Optional[str]:
    """Aggregate the nomenclature status of a Season (from its episodes) or a
    Series (from all its episodes). 'Correcta' only when EVERY episode is
    'Correcta' — a missing/unadapted episode (N/A or No adaptada) prevents it.
    Returns:
      - 'Correcta'    when every episode is adapted,
      - 'No adaptada' when none is adapted (and none is N/A),
      - 'N/A'         when every episode is N/A (nothing to adapt yet),
      - 'Parcial'     otherwise (a mix),
      - None          when there's nothing to aggregate (keep the row's own).
    """
    if conn is None:
        return None
    if item_type == "season":
        sql = (
            "SELECT nomenclature_status AS s, COUNT(*) AS c FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode' GROUP BY nomenclature_status"
        )
    elif item_type == "series":
        sql = (
            "SELECT e.nomenclature_status AS s, COUNT(*) AS c FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'"
            + _specials_clause("se", ignore_specials)
            + " GROUP BY e.nomenclature_status"
        )
    else:
        return None
    counts = {r["s"]: r["c"] for r in conn.execute(sql, (item_id,)).fetchall()}
    if sum(counts.values()) == 0:
        return None
    correct = counts.get("Correcta", 0)
    not_adapted = counts.get("No adaptada", 0)
    unchecked = counts.get("No comprobada", 0)
    available = correct + not_adapted + unchecked  # episodes with a file
    if available == 0:
        return "N/A"                 # nothing on disk to adapt yet
    if unchecked > 0:
        return "No comprobada"       # some available episode still not checked
    if correct == available:
        return "Correcta"            # all available checked and correct
    if not_adapted == available:
        return "No adaptada"
    return "Parcial"


def _local_status_rollup(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> Optional[str]:
    """Availability of a Season/Series computed from its real EPISODES, not from
    Sonarr's own status (which reports 'Disponible' even when episodes are
    missing). 'Disponible' only when every counted episode has a file,
    'Faltante' when none does, 'Parcial' otherwise. With ignore_specials on,
    season-0 episodes are excluded from a Series' count."""
    if conn is None:
        return None
    if item_type == "season":
        sql = (
            "SELECT local_status AS s, COUNT(*) AS c FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode' GROUP BY local_status"
        )
    elif item_type == "series":
        sql = (
            "SELECT e.local_status AS s, COUNT(*) AS c FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'"
            + _specials_clause("se", ignore_specials)
            + " GROUP BY e.local_status"
        )
    else:
        return None
    counts = {r["s"]: r["c"] for r in conn.execute(sql, (item_id,)).fetchall()}
    total = sum(counts.values())
    if total == 0:
        return None
    available = counts.get("Disponible", 0)
    if available == total:
        return "Disponible"
    if available == 0:
        return "Faltante"
    return "Parcial"


def _size_rollup(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> Optional[int]:
    """Total size of a Season/Series as the sum of its episodes' file sizes —
    season/series rows have no file of their own, so their size only makes
    sense as the aggregate of the episodes below them."""
    if conn is None:
        return None
    if item_type == "season":
        r = conn.execute(
            "SELECT SUM(size_bytes) AS s FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode'",
            (item_id,),
        ).fetchone()
    elif item_type == "series":
        r = conn.execute(
            "SELECT SUM(e.size_bytes) AS s FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'" + _specials_clause("se", ignore_specials),
            (item_id,),
        ).fetchone()
    else:
        return None
    return int(r["s"]) if r and r["s"] is not None else None


def _rollup_path(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> Optional[str]:
    """Folder path for a Season/Series rollup, derived from its episodes'
    files: the common parent directory (a season's own folder, e.g.
    '…/Attack on Titan/Season 2'; a series' root folder)."""
    if conn is None:
        return None
    if item_type == "season":
        rows = conn.execute(
            "SELECT path FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode' AND path IS NOT NULL",
            (item_id,),
        ).fetchall()
    elif item_type == "series":
        rows = conn.execute(
            "SELECT e.path AS path FROM library_items e "
            "JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode' AND e.path IS NOT NULL"
            + _specials_clause("se", ignore_specials),
            (item_id,),
        ).fetchall()
    else:
        return None
    paths = [r["path"] for r in rows if r["path"]]
    if not paths:
        return None
    dirs = {os.path.dirname(p) for p in paths}
    if len(dirs) == 1:
        return next(iter(dirs))
    try:
        return os.path.commonpath(paths)
    except ValueError:
        return None


def _child_quality_rollup(conn, item_id: int, item_type: str, ignore_specials: bool = False) -> dict:
    """Per-attribute value shared by ALL episodes of a Season/Series (or None
    when they differ or are absent): provider, resolution, source, video/audio
    codec, audio and subtitle languages. Lets a uniform season/series show the
    same attributes as its episodes. Specials (season 0) are excluded from a
    Series rollup when ignore_specials is on."""
    if conn is None:
        return dict(_ROLLUP_EMPTY)
    if item_type == "season":
        rows = conn.execute(
            "SELECT path, resolution, source, release_group, video_codec, audio_codec, "
            "audio_languages, subtitle_languages FROM library_items "
            "WHERE parent_id = ? AND item_type = 'episode' AND local_status = ?",
            (item_id, LocalStatus.AVAILABLE.value),
        ).fetchall()
    elif item_type == "series":
        rows = conn.execute(
            "SELECT e.path AS path, e.resolution AS resolution, e.source AS source, "
            "e.release_group AS release_group, e.video_codec AS video_codec, e.audio_codec AS audio_codec, "
            "e.audio_languages AS audio_languages, e.subtitle_languages AS subtitle_languages "
            "FROM library_items e JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode' AND e.local_status = ?"
            + _specials_clause("se", ignore_specials),
            (item_id, LocalStatus.AVAILABLE.value),
        ).fetchall()
    else:
        return dict(_ROLLUP_EMPTY)
    if not rows:
        return dict(_ROLLUP_EMPTY)

    def uniq(key: str):
        vals = {r[key] for r in rows}
        return next(iter(vals)) if len(vals) == 1 else None

    from .nomenclature import infer_provider_from_item

    providers: set = set()
    for r in rows:
        providers.add(infer_provider_from_item({"path": r["path"], "source": r["source"]}))
        if len(providers) > 1:
            break
    return {
        "provider": next(iter(providers)) if len(providers) == 1 else None,
        "resolution": uniq("resolution"),
        "source": uniq("source"),
        "release_group": uniq("release_group"),
        "video_codec": uniq("video_codec"),
        "audio_codec": uniq("audio_codec"),
        "audio_languages": uniq("audio_languages"),
        "subtitle_languages": uniq("subtitle_languages"),
    }


def _batch_rollups(conn, series_ids: list[int], season_ids: list[int], ignore_specials: bool) -> dict[int, dict]:
    """{item_id: {"nomenclature", "size", "local_status", "quality", "path"}}
    for every id in series_ids/season_ids, computed from a single query
    instead of ~5 queries per id."""
    groups: dict[int, list[dict]] = {}
    if not (series_ids or season_ids):
        return {}

    # Una sola lectura de los capítulos: en plano están la serie y sus
    # temporadas a la vez, y cada capítulo se leía una vez para cada una. Los
    # ids van como un JSON por lista, sin el tope de parámetros de SQLite.
    condiciones, params = [], []
    if season_ids:
        condiciones.append("se.id IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(season_ids))
    if series_ids:
        condiciones.append("se.parent_id IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(series_ids))
    rows = conn.execute(
        "SELECT se.id AS season_id, se.parent_id AS series_id, se.season_number AS season_number, "
        "e.path AS path, e.resolution AS resolution, e.source AS source, "
        "e.release_group AS release_group, e.video_codec AS video_codec, e.audio_codec AS audio_codec, "
        "e.audio_languages AS audio_languages, e.subtitle_languages AS subtitle_languages, "
        "e.nomenclature_status AS nomenclature_status, e.local_status AS local_status, e.size_bytes AS size_bytes "
        "FROM library_items e JOIN library_items se ON e.parent_id = se.id "
        f"WHERE e.item_type = 'episode' AND ({' OR '.join(condiciones)})",
        params,
    ).fetchall()
    temporadas, series = set(season_ids), set(series_ids)
    for r in rows:
        fila = dict(r)
        if r["season_id"] in temporadas:
            groups.setdefault(r["season_id"], []).append(fila)
        if r["series_id"] in series and not (ignore_specials and r["season_number"] == 0):
            groups.setdefault(r["series_id"], []).append(fila)

    result: dict[int, dict] = {}
    for gid, episode_rows in groups.items():
        result[gid] = {
            "nomenclature": _aggregate_nomenclature([r["nomenclature_status"] for r in episode_rows]),
            "size": _aggregate_size([r["size_bytes"] for r in episode_rows]),
            "local_status": _aggregate_local_status([r["local_status"] for r in episode_rows]),
            "quality": _aggregate_quality(episode_rows),
            "path": _aggregate_path(episode_rows),
        }
    return result


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
    from .nomenclature import infer_provider_from_item
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
    return {r["id"]: dict(r) for r in filas}


def library_display_fields_one(item_id: int, conn) -> dict | None:
    """Lo mismo para uno solo, con los campos extra que pide la ficha de una
    subida (título, temporada, capítulo, padre)."""
    row = conn.execute(
        f"SELECT {_CAMPOS_ADORNO}, title, season_number, episode_number, parent_id "
        "FROM library_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    return dict(row) if row else None


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
