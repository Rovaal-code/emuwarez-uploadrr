"""eMuwarez request synchronization and matching."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import sqlite3
import threading
import unicodedata
import urllib.parse
from typing import Optional, Sequence

from ..database import borrar_peticiones, get_json_state, get_setting_canonical, get_state, set_state
from .settings import leer_ajuste
from . import cli_config, emu_catalog
from .emu_perfil import PERFIL_STATE_KEY
from ..integrations import emu, tmdb
from ..integrations.base import IntegrationError, texto_de_error
from ..models import RequestItem, TaskStatus
from .library import content_display_title, grupos_de_release
from .request_readiness import _biblioteca, refresh_request_readiness
from .eventos import EVENTO_SYNC_EMPEZADA, EVENTO_SYNC_TERMINADA, publicar
from .tasks import start_task, finish_task
from .tmdb_titles import tmdb_configured
from .upload_states import ACTIVE_JOB_STATUSES
from .compatibility import (
    match_request_to_library,
    classify_request_match,
    estado_emu_de,
    peor_resolucion,
    peor_source,
    reclamada_por,
    tipo_de_peticion,
)

logger = logging.getLogger("emuwarez.requests")

SYNC_STATE_KEY = "last_emu_requests_sync_utc"
# «1» si el último recorrido cuadró con el total de eMuwarez: solo con esa base se sabe cuáles son nuevas.
SYNC_COMPLETA_KEY = "last_emu_requests_sync_complete"
MIN_SYNC_SECONDS = 3600


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def seconds_until_next_sync(conn: sqlite3.Connection) -> int:
    last = _parse_iso(get_state(conn, SYNC_STATE_KEY))
    if not last:
        return 0
    elapsed = (_utcnow() - last).total_seconds()
    return max(0, int(MIN_SYNC_SECONDS - elapsed))


def can_sync_requests(conn: sqlite3.Connection, *, force: bool = False) -> tuple[bool, int]:
    if force:
        return True, 0
    wait = seconds_until_next_sync(conn)
    return wait <= 0, wait


def get_request_sync_status(conn: sqlite3.Connection) -> dict:
    """Return sync status info: last_sync_at, wait_seconds, can_sync."""
    last_str = get_state(conn, SYNC_STATE_KEY)
    last = _parse_iso(last_str)
    wait = seconds_until_next_sync(conn)
    next_at = None
    if last:
        next_at = (last + dt.timedelta(seconds=MIN_SYNC_SECONDS)).isoformat()
    return {
        "last_sync_at": last_str,
        "next_sync_at": next_at,
        "can_sync": wait <= 0,
        "wait_seconds": wait,
        "min_interval_seconds": MIN_SYNC_SECONDS,
    }


def upsert_request(
    conn: sqlite3.Connection, item: RequestItem, *, seen_at: Optional[str] = None, commit: bool = True
) -> int:
    """Inserta o actualiza una petición. `seen_at` marca cuándo la vio la sincronización
    y `commit=False` deja la transacción abierta, para guardar varias de golpe."""
    conn.execute(
        """
        INSERT INTO request_items(
            emu_id, title, category, requested_source, requested_resolution,
            emu_status, points, comments, created_at, tmdb_id, imdb_id, tvdb_id, mal_id, url,
            author, author_visible, req_scope, req_season, req_episode, raw_json, last_seen_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(emu_id) DO UPDATE SET
            title = excluded.title,
            category = excluded.category,
            requested_source = excluded.requested_source,
            requested_resolution = excluded.requested_resolution,
            emu_status = excluded.emu_status,
            points = excluded.points,
            comments = excluded.comments,
            created_at = excluded.created_at,
            tmdb_id = excluded.tmdb_id,
            imdb_id = excluded.imdb_id,
            tvdb_id = excluded.tvdb_id,
            mal_id = excluded.mal_id,
            url = excluded.url,
            author = excluded.author,
            author_visible = excluded.author_visible,
            req_scope = excluded.req_scope,
            req_season = excluded.req_season,
            req_episode = excluded.req_episode,
            raw_json = excluded.raw_json,
            -- Si cambia con qué se busca en TMDb, el póster y el fondo se vuelven a pedir.
            tmdb_poster_url = CASE WHEN (request_items.tmdb_id, request_items.imdb_id, request_items.category,
                request_items.req_scope) IS (excluded.tmdb_id, excluded.imdb_id, excluded.category, excluded.req_scope)
                THEN request_items.tmdb_poster_url END,
            tmdb_backdrop_url = CASE WHEN (request_items.tmdb_id, request_items.imdb_id, request_items.category,
                request_items.req_scope) IS (excluded.tmdb_id, excluded.imdb_id, excluded.category, excluded.req_scope)
                THEN request_items.tmdb_backdrop_url END,
            last_seen_at = COALESCE(excluded.last_seen_at, request_items.last_seen_at),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            item.emu_id, item.title, item.category, item.requested_source,
            item.requested_resolution, item.emu_status, item.points, item.comments,
            item.created_at, item.tmdb_id, item.imdb_id, item.tvdb_id, item.mal_id, item.url, item.author,
            1 if item.author_visible else 0, item.req_scope, item.req_season, item.req_episode, item.raw_json,
            seen_at,
        ),
    )
    row = conn.execute("SELECT id FROM request_items WHERE emu_id = ?", (item.emu_id,)).fetchone()
    if commit:
        conn.commit()
    return int(row["id"])


# ---------------------------------------------------------------------------
# Primary sync function — UNIT3D api_token auth (Phase 5B)
# ---------------------------------------------------------------------------

def _resolve_emu_api_key(conn: sqlite3.Connection) -> Optional[str]:
    """La API key de eMuwarez: la interfaz la guarda en la BD
    (settings.emu.api_key) y esa es la fuente; la configuración del CLI antiguo
    es solo un respaldo. Leer únicamente esta última hacía que la tarea de
    peticiones dijera "No hay API Key" teniéndola configurada.

    El respaldo se lee con services/cli_config, no con legacy.load_app_config:
    aquella podía terminar en SystemExit o pidiendo una contraseña por teclado
    desde el hilo del servidor. Ver la cabecera de cli_config.py."""
    key = get_setting_canonical(conn, "emu.api_key")
    if key:
        return key
    return cli_config.emu_api_key()


_SYNC_EN_CURSO = threading.Lock()
# Las subidas que gastan llamadas de eMuwarez: todas las activas menos las que esperan en la cola.
ESTADOS_EN_MARCHA = ACTIVE_JOB_STATUSES - {"queued"}


def _motivo_ocupado(conn: sqlite3.Connection) -> Optional[str]:
    """Por qué ahora no toca sincronizar: el catálogo y las subidas gastan las mismas 30 llamadas por minuto de la clave.
    Una subida que espera turno en la cola (`queued`) no gasta ninguna, así que no cuenta: si no, un lote largo dejaría
    horas sin peticiones nuevas. Las que se preparan o suben, sí."""
    if emu_catalog.get_sync_progress().get("active"):
        return "Se está sincronizando el catálogo de eMuwarez; vuelve a probar cuando termine."
    en_marcha = tuple(sorted(ESTADOS_EN_MARCHA))
    if conn.execute(
        f"SELECT 1 FROM upload_jobs WHERE status IN ({','.join('?' * len(en_marcha))}) LIMIT 1", en_marcha
    ).fetchone():
        return "Hay una subida en marcha; vuelve a probar cuando termine."
    return None


def sync_emu_requests(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
) -> dict[str, int | str]:
    """Sync EMU requests using UNIT3D ?api_token= auth. Rate-limited to 1/hour.

    Nunca a la vez que otra sincronización de peticiones, que la del catálogo o que una subida:
    devuelve {"status": "busy", "message": ...} sin tocar nada.
    """
    allowed, wait = can_sync_requests(conn, force=force)
    if not allowed:
        return {"status": "throttled", "wait_seconds": wait, "imported": 0, "matched": 0}
    if not _SYNC_EN_CURSO.acquire(blocking=False):
        return {"status": "busy", "message": "Ya hay una sincronización de peticiones en marcha."}
    try:
        motivo = _motivo_ocupado(conn)
        if motivo:
            return {"status": "busy", "message": motivo}
        return _sincronizar_peticiones(conn)
    finally:
        _SYNC_EN_CURSO.release()


# Progreso de la sincronización de peticiones, para que la interfaz enseñe la barra y no tenga una petición HTTP
# colgada durante minutos. Un solo proceso: un dict en memoria basta, igual que en el catálogo (emu_catalog).
_PROGRESO_LOCK = threading.Lock()
_PROGRESO: dict = {"active": False, "done": False, "phase": "", "page": 0, "total_pages": None,
                   "imported": 0, "message": "", "error": None}


def get_request_sync_progress() -> dict:
    with _PROGRESO_LOCK:
        return dict(_PROGRESO)


def _set_progress(**kw) -> None:
    with _PROGRESO_LOCK:
        _PROGRESO.update(kw)


def _sincronizar_peticiones(conn: sqlite3.Connection) -> dict[str, int | str]:
    """Una sincronización, con su progreso y sus avisos: es el único sitio donde corre, la arranque quien la
    arranque (el botón, la tarea programada o el CLI)."""
    _set_progress(active=True, done=False, phase="Iniciando…", page=0, total_pages=None, imported=0, message="",
                  error=None)
    publicar(EVENTO_SYNC_EMPEZADA, {"que": "peticiones"})
    try:
        result = _importar_peticiones(conn)
        _set_progress(message=resumen_de_sincronizacion(result), imported=int(result.get("imported", 0)))
        return result
    except Exception as exc:  # noqa: BLE001 — se enseña en la barra y se vuelve a lanzar
        _set_progress(error=texto_de_error(exc), phase="Error")
        raise
    finally:
        _set_progress(active=False, done=True)
        publicar(EVENTO_SYNC_TERMINADA, {"que": "peticiones"})


def resumen_de_sincronizacion(result: dict) -> str:
    texto = f"{result.get('imported', 0)} peticiones importadas, {result.get('matched', 0)} cruces actualizados."
    return texto + (f" {result['removed']} retiradas." if result.get("removed") else "")


def start_requests_sync_background(force: bool = False) -> dict:
    """Arranca la sincronización en un hilo y vuelve al instante; la interfaz sigue el progreso.

    Devuelve {"status": "started"}, {"status": "throttled", "wait_seconds"} o {"status": "busy", "message"}.
    Sin API key lanza IntegrationError, como antes: no hace falta un hilo para saber que no va a salir.

    El candado de sync_emu_requests se toma aquí y pasa al hilo, que lo suelta al terminar: así dos pulsaciones
    seguidas, o la tarea programada, no pueden arrancar dos a la vez ni pisarse el progreso."""
    from ..database import connect, db_path
    if not _SYNC_EN_CURSO.acquire(blocking=False):
        if get_request_sync_progress()["active"]:
            return {"status": "started"}  # ya hay una: se sigue esa
        return {"status": "busy", "message": "Ya hay una sincronización de peticiones en marcha."}

    def _run() -> None:
        c = connect(db_path())
        try:
            _sincronizar_peticiones(c)  # el candado ya es nuestro
        except Exception as exc:  # noqa: BLE001 — _sincronizar_peticiones ya dejó su error; esto es lo que falle antes
            if not get_request_sync_progress()["error"]:
                _set_progress(error=texto_de_error(exc))
        finally:
            c.close()
            _set_progress(active=False, done=True)  # pase lo que pase, la barra no se queda encendida
            _SYNC_EN_CURSO.release()

    lanzado = False
    conn = connect(db_path())
    try:
        allowed, wait = can_sync_requests(conn, force=force)
        if not allowed:
            return {"status": "throttled", "wait_seconds": wait}
        motivo = _motivo_ocupado(conn)
        if motivo:
            return {"status": "busy", "message": motivo}
        if not _resolve_emu_api_key(conn):
            raise IntegrationError("No hay API key de eMuwarez configurada")
        # Activa antes de que el hilo arranque: la interfaz la sigue desde que esta respuesta llega.
        _set_progress(active=True, done=False, phase="Iniciando…", page=0, total_pages=None, imported=0, message="",
                      error=None)
        try:
            threading.Thread(target=_run, daemon=True).start()
        except Exception:
            _set_progress(active=False, done=True)
            raise
        lanzado = True
        return {"status": "started"}
    finally:
        conn.close()
        if not lanzado:
            _SYNC_EN_CURSO.release()


def _importar_peticiones(conn: sqlite3.Connection) -> dict[str, int | str]:
    task_id = start_task(conn, "sync-emu-requests", "Sincronizando peticiones EMU")
    api_key = _resolve_emu_api_key(conn)
    if not api_key:
        finish_task(conn, task_id, TaskStatus.FAILED.value, "No hay API key de eMuwarez configurada")
        raise IntegrationError("No hay API key de eMuwarez configurada")

    # Record the throttle at START (not at the end), so a slow fetch or a page
    # refresh mid-sync can't relaunch it. Restored if the sync fails, so a
    # failed run doesn't lock the user out for an hour.
    prev_sync = get_state(conn, SYNC_STATE_KEY)
    set_state(conn, SYNC_STATE_KEY, _utcnow().isoformat())
    conn.commit()

    def _restore_throttle() -> None:
        conn.rollback()  # lo que se hubiera importado a medias no se queda
        set_state(conn, SYNC_STATE_KEY, prev_sync or "")
        conn.commit()

    # Sin un recorrido previo completo (la primera vez, o tras uno cortado) todo lo que llega ya estaba ahí: no se avisa.
    conocidas = ({r[0] for r in conn.execute("SELECT emu_id FROM request_items")}
                 if get_state(conn, SYNC_COMPLETA_KEY) == "1" else None)

    logger.info("Sincronización de peticiones iniciada")
    try:
        _set_progress(phase="Descargando peticiones…")
        raw_items, total = emu.emu_fetch_all_pages(
            api_key, progress=lambda pagina, ultima, filas: _set_progress(page=pagina, total_pages=ultima, imported=filas))
        items = emu.normalize_requests(raw_items)
        _set_progress(phase="Guardando peticiones…", imported=len(items))
        sync_at = _utcnow().isoformat()
        for item in items:
            upsert_request(conn, item, seen_at=sync_at, commit=False)
        if conocidas is not None:
            conn.executemany("UPDATE request_items SET aviso_pendiente = 1 WHERE emu_id = ?",
                             [(i.emu_id,) for i in items if i.emu_id not in conocidas])
        # Solo un recorrido que cuadra con el total de eMuwarez dice cuáles ya no están abiertas.
        complete = total is not None and len(items) == total == len({i.emu_id for i in items})
        if complete:
            set_state(conn, SYNC_COMPLETA_KEY, "1")  # un recorrido cortado después no quita la base que ya había
        else:
            logger.warning("El recorrido de peticiones no cuadra con el total de eMuwarez; no se borra ninguna")
        removed = borrar_peticiones(conn, "last_seen_at IS NULL OR last_seen_at != ?", (sync_at,)) if complete else 0
        set_state(conn, SYNC_STATE_KEY, _utcnow().isoformat())
        conn.commit()
        _set_progress(phase="Cruzando con tu biblioteca…")
        matched = match_all_requests(conn)
        # La preparación no se calcula sola: sin esto el detalle de cada petición nueva daba 404. Si falla no tumba
        # la sincronización: lo importado vale, y «Recalcular» la repite sin volver a llamar a eMuwarez.
        _set_progress(phase="Calculando qué está listo para subir…")
        try:
            sin_preparar = refresh_request_readiness(conn)["errors"]
        except Exception:
            conn.rollback()
            logger.exception("No se pudo calcular la preparación de las peticiones")
            sin_preparar = None
        if sin_preparar is not None:
            _avisar_peticiones_nuevas_listas(conn)
        # Igual que la preparación: unos pósters que no llegan no tumban la sincronización.
        _set_progress(phase="Trayendo los pósters…")
        try:
            rellenar_posters(conn)
        except Exception:
            conn.rollback()
            logger.exception("No se pudieron traer los pósters de TMDb")
        summary = f"{len(items)} peticiones importadas, {matched} cruces"
        if removed:
            summary += f", {removed} retiradas"
        if sin_preparar is None:
            summary += ", preparación sin calcular (ver el log)"
        elif sin_preparar:
            summary += f", {sin_preparar} sin preparación (ver el log)"
        finish_task(conn, task_id, TaskStatus.COMPLETED.value, summary)
        logger.info("Sincronización de peticiones terminada: %d importadas, %d retiradas, %d cruzadas con tu biblioteca",
                    len(items), removed, matched)
        return {"status": "ok", "imported": len(items), "matched": matched, "removed": removed}
    except IntegrationError as exc:
        _restore_throttle()
        finish_task(conn, task_id, TaskStatus.FAILED.value, texto_de_error(exc))
        logger.warning("Sincronización de peticiones fallida: %s", texto_de_error(exc))
        raise
    except Exception as exc:
        _restore_throttle()
        finish_task(conn, task_id, TaskStatus.FAILED.value, texto_de_error(exc))
        logger.error("Sincronización de peticiones fallida: %s", texto_de_error(exc))
        raise


_MAX_TITULOS_EN_EL_AVISO = 5


def _avisar_peticiones_nuevas_listas(conn: sqlite3.Connection) -> None:
    """Un solo aviso con las peticiones que esta sincronización vio por primera vez y que ya se pueden rellenar
    (preparación «ready_to_upload», el mismo criterio que enseña la lista). Cada petición se mira una vez: se
    apaga su marca esté lista o no. Solo se deja encendida la que no tiene preparación calculada, que se mira
    en la siguiente. Best-effort: un fallo aquí no tumba la sincronización."""
    try:
        filas = conn.execute(
            "SELECT title, readiness_status FROM request_items WHERE aviso_pendiente = 1 ORDER BY created_at, id"
        ).fetchall()
        # Apagadas antes de avisar: si el aviso falla a medias, mejor ninguno que el mismo cada día.
        conn.execute("UPDATE request_items SET aviso_pendiente = 0 "
                     "WHERE aviso_pendiente = 1 AND readiness_status IS NOT NULL")
        conn.commit()
        titulos = [r["title"] for r in filas if r["readiness_status"] == "ready_to_upload"]
        if not titulos:
            return
        from .notification_center import emit
        # El título lo escribe cualquier usuario del tracker: un «@everyone» no debe avisar a todo el canal de Discord.
        primeros = ", ".join(f"«{t.replace('@', '@' + chr(0x200b))}»" for t in titulos[:_MAX_TITULOS_EN_EL_AVISO])
        resto = len(titulos) - _MAX_TITULOS_EN_EL_AVISO
        cuerpo = (f"Hay una petición nueva que ya puedes rellenar: {primeros}." if len(titulos) == 1 else
                  f"Hay {len(titulos)} peticiones nuevas que ya puedes rellenar: {primeros}"
                  + (f" y {resto} más." if resto > 0 else "."))
        emit(conn, "request_new_ready", "Peticiones nuevas listas para subir", cuerpo, link="/requests", level="info")
    except Exception:
        conn.rollback()
        logging.getLogger("emuwarez.notifications").exception(
            "No se pudo avisar de las peticiones nuevas listas para subir")


_TMDB_IMAGEN = "https://image.tmdb.org/t/p/original"  # el frontend cambia "original" por el tamaño (posterUrl)
_FALLOS_SEGUIDOS_TMDB = 3


def rellenar_posters(conn: sqlite3.Connection, peticiones: Optional[Sequence[int]] = None) -> int:
    """Póster y fondo de TMDb para las peticiones que no casan con nada de la biblioteca, que es de donde salía el
    póster. Una vez por petición: '' guarda que TMDb no tiene. Con `peticiones`, solo esas. Devuelve cuántos
    pósters ha traído."""
    if not tmdb_configured(conn):
        return 0
    sql = ("SELECT ri.id, ri.category, ri.req_scope, ri.tmdb_id, ri.imdb_id FROM request_items ri "
           "WHERE ri.tmdb_poster_url IS NULL AND NOT EXISTS (SELECT 1 FROM request_matches rm "
           "JOIN library_items li ON li.id = rm.library_item_id "
           "WHERE rm.request_item_id = ri.id AND li.poster_url IS NOT NULL)")
    if peticiones is not None:
        sql += f" AND ri.id IN ({','.join('?' * len(peticiones))})"
    pendientes = conn.execute(sql, tuple(peticiones or ())).fetchall()
    traidos = fallos = 0
    for p in pendientes:
        tipo = tipo_de_peticion(p["category"]) or ("series" if p["req_scope"] in ("season", "episode") else None)
        try:
            if tipo and p["tmdb_id"]:
                poster, fondo = tmdb.get_images("movie" if tipo == "movie" else "tv", p["tmdb_id"], conn=conn)
            elif p["imdb_id"]:
                # Un documental sin temporada puede ser película o serie: con el tmdb se podría coger otra cosa.
                poster, fondo = tmdb.find_images_by_imdb(p["imdb_id"], conn=conn)
            else:
                poster = fondo = None
        except IntegrationError as exc:
            if exc.status != 404:
                # Red, límite o clave: no se guarda y la siguiente sincronización lo vuelve a probar.
                fallos += 1
                if fallos == _FALLOS_SEGUIDOS_TMDB:
                    logger.warning("TMDb no responde; los pósters que faltan se piden en la próxima sincronización")
                    break
                continue
            poster = fondo = None
        fallos = 0
        conn.execute("UPDATE request_items SET tmdb_poster_url = ?, tmdb_backdrop_url = ? WHERE id = ?",
                     (_TMDB_IMAGEN + poster if poster else "", _TMDB_IMAGEN + fondo if fondo else "", p["id"]))
        conn.commit()  # una a una: si no, la base de datos queda bloqueada mientras se espera a TMDb
        traidos += bool(poster)
    return traidos


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

_AVAILABLE = {"Disponible", "Subido", "Subiendo", "Parcial"}


def _uniq(values) -> Optional[str]:
    s = {v for v in values}
    return next(iter(s)) if len(s) == 1 else None


def _relevant_episodes(conn, matched_id, matched_type, scope, season, episode, ignore_specials):
    """Episode rows that a request's scope points at within the matched
    series/season (the single episode, the season's episodes, or all
    non-special episodes of the series)."""
    if matched_type == "series":
        if scope == "episode" and season is not None and episode is not None:
            return conn.execute(
                "SELECT e.* FROM library_items e JOIN library_items se ON e.parent_id = se.id "
                "WHERE se.parent_id = ? AND se.item_type = 'season' AND se.season_number = ? "
                "AND e.item_type = 'episode' AND e.episode_number = ?",
                (matched_id, season, episode)).fetchall()
        if scope == "season" and season is not None:
            return conn.execute(
                "SELECT e.* FROM library_items e JOIN library_items se ON e.parent_id = se.id "
                "WHERE se.parent_id = ? AND se.item_type = 'season' AND se.season_number = ? "
                "AND e.item_type = 'episode'",
                (matched_id, season)).fetchall()
        clause = " AND (se.season_number IS NULL OR se.season_number != 0)" if ignore_specials else ""
        return conn.execute(
            "SELECT e.* FROM library_items e JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'" + clause,
            (matched_id,)).fetchall()
    if matched_type == "season":
        if scope == "episode" and episode is not None:
            return conn.execute(
                "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode' AND episode_number = ?",
                (matched_id, episode)).fetchall()
        return conn.execute(
            "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode'",
            (matched_id,)).fetchall()
    return []


def _pack_blocked_reason(conn: sqlite3.Connection, matched_item: dict, req: dict) -> Optional[str]:
    """Por qué la temporada que pide esta petición no puede subirse como pack.

    None cuando sí puede, o cuando la petición no es de temporada/serie
    completa (un capítulo suelto no necesita pack).
    """
    if req.get("req_scope") == "episode":
        return None
    from .season_pack import can_pack_from_rollup

    season_id = _scoped_library_id(conn, matched_item, req)
    row = conn.execute(
        "SELECT * FROM library_items WHERE id = ? AND item_type = 'season'", (season_id,)
    ).fetchone()
    if not row:
        return None
    season = dict(row)
    if can_pack_from_rollup(season):
        return None
    if not season.get("video_codec"):
        falta = "los capítulos no coinciden en códec de vídeo"
    else:
        falta = "algún capítulo no tiene castellano"
    return (f"La temporada no puede subirse como pack: {falta}. "
            "Sus capítulos sí se pueden subir uno a uno.")


def _scoped_library_id(conn: sqlite3.Connection, matched_item: dict, req: dict) -> int:
    """The library row the request actually refers to: the season row for a
    season-scoped request, the episode row for an episode-scoped one, and the
    matched row itself otherwise. Used for the links out of a request, so
    "Los Tudor (2007) - Temporada 2" opens that season and not the whole
    series."""
    matched_id = int(matched_item["id"])
    if matched_item.get("item_type") not in ("series", "season"):
        return matched_id
    season = req.get("req_season")
    episode = req.get("req_episode")
    if season is None:
        return matched_id

    season_id = matched_id
    if matched_item.get("item_type") == "series":
        row = conn.execute(
            "SELECT id FROM library_items WHERE parent_id = ? AND item_type = 'season' "
            "AND season_number = ?",
            (matched_id, season),
        ).fetchone()
        if not row:
            return matched_id
        season_id = int(row["id"])

    if req.get("req_scope") == "episode" and episode is not None:
        row = conn.execute(
            "SELECT id FROM library_items WHERE parent_id = ? AND item_type = 'episode' "
            "AND episode_number = ?",
            (season_id, episode),
        ).fetchone()
        if row:
            return int(row["id"])
    return season_id


def _effective_target(conn: sqlite3.Connection, matched_item: dict, req: dict) -> dict:
    """A copy of the matched library item with resolution/source/codecs/audio/
    subs/size/path/local_status reflecting the request's SCOPE, so a
    series/season rollup (which stores none of its own) is classified and shown
    against its real episodes: the specific episode, or the WORST of the available
    episodes (la resolución y la fuente más bajas: si esas cumplen lo pedido,
    cumplen todas; un capítulo que falta no cuenta)."""
    it = dict(matched_item)
    if it.get("item_type") not in ("series", "season"):
        return it
    ignore_specials = leer_ajuste(conn, "series_ignore_specials")
    eps = [dict(e) for e in _relevant_episodes(
        conn, it["id"], it["item_type"], req.get("req_scope"),
        req.get("req_season"), req.get("req_episode"), ignore_specials)]
    if not eps:
        # La serie (o la temporada, si se pide un capítulo) no tiene lo pedido: que esté disponible no lo hace compatible.
        if it["item_type"] == "series" or req.get("req_scope") == "episode":
            it["local_status"] = "Faltante"
        return it
    single = eps[0] if len(eps) == 1 else None
    disponibles = [e for e in eps if e.get("local_status") in _AVAILABLE]
    for key in ("resolution", "source", "video_codec", "audio_languages", "subtitle_languages"):
        if single:
            it[key] = single[key]
        elif key == "resolution":
            it[key] = peor_resolucion(e.get(key) for e in disponibles)
        elif key == "source":
            it[key] = peor_source(e.get(key) for e in disponibles)
        else:
            it[key] = _uniq(e.get(key) for e in disponibles) if disponibles else None
    it["release_groups"] = grupos_de_release(disponibles)
    if single:
        it["size_bytes"] = single.get("size_bytes")
        it["path"] = single.get("path")
        it["title"] = single.get("title") or it.get("title")
        it["local_status"] = single.get("local_status")
        it["id"] = single["id"]
    else:
        it["size_bytes"] = sum(e.get("size_bytes") or 0 for e in eps) or None
        statuses = [e.get("local_status") for e in eps]
        avail = [s for s in statuses if s in _AVAILABLE]
        it["local_status"] = "Disponible" if len(avail) == len(statuses) and avail else ("Parcial" if avail else "Faltante")
        paths = [e["path"] for e in eps if e.get("path")]
        if paths:
            dirs = {os.path.dirname(p) for p in paths}
            it["path"] = next(iter(dirs)) if len(dirs) == 1 else os.path.commonpath(paths)
    return it


_ORDEN_DEL_CASAMIENTO = {"Compatible": 0, "No disponible": 1, "Parcial": 2, "No compatible": 3}


def mi_usuario_emu(conn: sqlite3.Connection) -> Optional[str]:
    """Tu usuario de eMuwarez sin llamar a la API: el del perfil guardado (emu_perfil) y, si aún no hay, el de
    Ajustes. Sirve para saber si una petición reclamada la has reclamado tú."""
    perfil = (get_json_state(conn, PERFIL_STATE_KEY) or {}).get("perfil") or {}
    return perfil.get("username") or get_setting_canonical(conn, "emu.username") or None


def clasificar_peticion(
    conn: sqlite3.Connection, req: dict, item: dict, *, id_match: bool = False, title_match: bool = False,
    base_confidence: float = 0.90, mi_usuario: Optional[str] = None,
) -> tuple[dict, dict]:
    """(fila con lo que de verdad tiene lo pedido, clasificación). Es LA definición de «compatible»: la usan el cruce
    guardado, el detalle y «lista para subir», para que la lista, el Panel y los avisos digan lo mismo que la ficha."""
    efectiva = _effective_target(conn, item, req)
    if mi_usuario is None:
        mi_usuario = mi_usuario_emu(conn)
    cls = classify_request_match(req, efectiva, id_match=id_match, title_match=title_match,
                                 base_confidence=base_confidence, mi_usuario=mi_usuario)
    # Una petición de temporada o serie completa se cubre con un PACK. Si ese pack no puede armarse (los capítulos no
    # coinciden en resolución o en códec de vídeo), "Compatible" prometería algo que la subida va a rechazar: baja
    # a Parcial y se dice por qué. Los capítulos sueltos sí se pueden subir, y el motivo lo dice.
    if cls["status"] == "Compatible":
        motivo = _pack_blocked_reason(conn, item, req)
        if motivo:
            cls["status"] = "Parcial"
            cls["reasons"] = [*cls["reasons"], motivo]
    return efectiva, cls


def _mejor_candidato(
    conn: sqlite3.Connection, req: dict, candidates: list[dict], mi_usuario: Optional[str] = None,
) -> tuple[dict, dict]:
    """De los candidatos igual de seguros (la misma película en Radarr y en Radarr 4K) el que mejor atiende la
    petición, con su clasificación: el primero de la lista podía ser la copia de 1080p de una petición de 2160p."""
    empatados = [c for c in candidates if c["confidence"] == candidates[0]["confidence"]]
    clasificados = [(c, clasificar_peticion(
        conn, req, c["item"], id_match=c["id_match"], title_match=c["title_match"], base_confidence=c["confidence"],
        mi_usuario=mi_usuario,
    )[1]) for c in empatados]
    return min(clasificados, key=lambda par: _ORDEN_DEL_CASAMIENTO.get(par[1]["status"], 9))


_INSERTAR_CASAMIENTO = """
    INSERT INTO request_matches(
        library_item_id, request_item_id, status, confidence,
        resolution_match, source_match, type_match, reasons, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
"""


def _casar(
    conn: sqlite3.Connection, req: dict, library: list[dict], mi_usuario: Optional[str] = None,
) -> Optional[tuple]:
    """(petición, candidata, clasificación, fila a la que va el estado) o None si no casa con nada. Solo lee."""
    candidates = match_request_to_library(req, library)
    if not candidates:
        return None
    best, classification = _mejor_candidato(conn, req, candidates, mi_usuario)
    # A la fila que la petición pide DE VERDAD, no a la que cruzó el emparejador. Para una petición de temporada
    # eso es la temporada y no la serie entera (todas las temporadas comparten su tmdb_id).
    return req, best, classification, _scoped_library_id(conn, best["item"], req)


def _guardar_casamientos(conn: sqlite3.Connection, casamientos: list[tuple], peticion: Optional[int] = None) -> None:
    """Cambia de una vez lo guardado (de todas las peticiones, o solo de `peticion`) por los casamientos nuevos.

    Se limpia antes de escribir: sin esto, un estado se quedaba pegado en la fila donde se escribió una vez y ya
    nadie lo movía, y un casamiento que ya no vale se seguía enseñando en la lista. Todo en una transacción:
    si algo falla a mitad, queda lo de antes en vez de las peticiones sin cruce."""
    try:
        if peticion is None:
            conn.execute(
                "UPDATE library_items SET request_status = 'Sin petición', request_id = NULL "
                "WHERE request_status != 'Sin petición' OR request_id IS NOT NULL"
            )
            conn.execute("DELETE FROM request_matches")
        else:
            conn.execute("DELETE FROM request_matches WHERE request_item_id = ?", (peticion,))
            conn.execute(
                "UPDATE library_items SET request_status = 'Sin petición', request_id = NULL WHERE request_id = ?",
                (peticion,),
            )
        for req, best, cls, destino in casamientos:
            conn.execute(_INSERTAR_CASAMIENTO, (
                best["item"]["id"],
                req["id"],
                cls["status"],
                cls["confidence"],
                None if cls["resolution_match"] is None else int(bool(cls["resolution_match"])),
                None if cls["source_match"] is None else int(bool(cls["source_match"])),
                1 if best["id_match"] else 0,
                "\n".join(cls["reasons"]),
            ))
            conn.execute(
                "UPDATE library_items SET request_status = ?, request_id = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?", (cls["status"], int(req["id"]), destino),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def match_all_requests(conn: sqlite3.Connection) -> int:
    """Re-run compatibility matching for all request items. Returns updated count.

    Es solo comparar con lo que ya hay en la base de datos: no llama a eMuwarez.
    """
    # Snapshot which requests already had compatible content, so afterwards we
    # only notify about the ones that *newly* became satisfiable this run.
    before_compatible = _compatible_request_ids(conn)

    requests = [dict(r) for r in conn.execute("SELECT * FROM request_items").fetchall()]
    library = _biblioteca(conn)
    usuario = mi_usuario_emu(conn) or ""
    casamientos = [c for c in (_casar(conn, req, library, usuario) for req in requests) if c]
    _guardar_casamientos(conn, casamientos)
    _notify_new_compatible_matches(conn, before_compatible)
    return len(casamientos)


_MAX_AVISOS_SUELTOS = 5


def _compatible_request_ids(conn: sqlite3.Connection) -> set[int]:
    """request_item_ids that currently have at least one 'Compatible' match."""
    rows = conn.execute(
        "SELECT DISTINCT request_item_id FROM request_matches WHERE status = 'Compatible'"
    ).fetchall()
    return {int(r[0]) for r in rows}


def _notify_new_compatible_matches(conn: sqlite3.Connection, before_ids: set[int]) -> None:
    """Emit one notification per request that became satisfiable this run.
    Best-effort: never lets a notification failure break matching."""
    try:
        new_ids = _compatible_request_ids(conn) - before_ids
        if not new_ids:
            return
        from .notification_center import emit
        # La primera sincronización encuentra de golpe todo lo compatible: un aviso de resumen, no uno por petición.
        if len(new_ids) > _MAX_AVISOS_SUELTOS:
            emit(
                conn, "request_match_found",
                "Contenido compatible",
                f"Tienes contenido compatible con {len(new_ids)} peticiones.",
                link="/requests",
                level="info",
            )
            return
        for rid in new_ids:
            row = conn.execute(
                "SELECT title, url, req_scope, req_season, req_episode"
                " FROM request_items WHERE id = ?", (rid,)
            ).fetchone()
            title = (row["title"] if row else None) or f"Petición #{rid}"
            # request_items has neither a poster of its own nor a title that
            # says WHICH season or episode was asked for — both come from the
            # library item behind the very 'Compatible' match this
            # notification is about, so they're read from one single row.
            lib_row = conn.execute(
                """SELECT li.*
                   FROM request_matches rm JOIN library_items li ON li.id = rm.library_item_id
                   WHERE rm.request_item_id = ? AND rm.status = 'Compatible'
                   LIMIT 1""",
                (rid,),
            ).fetchone()
            if row is not None and lib_row is not None:
                # Same canonical title the rest of the app shows ("Serie (Año)
                # - Temporada 2", "Serie (Año) - S02E05", "Título (Año)"), via
                # the shared builder instead of a format of its own. Without
                # the season/episode, every season of the same series notified
                # under the bare series name and they were indistinguishable.
                title = content_display_title(
                    conn, dict(lib_row),
                    season=row["req_season"], episode=row["req_episode"],
                    scope=row["req_scope"],
                ) or title
            emit(
                conn, "request_match_found",
                "Contenido compatible",
                "Tienes contenido compatible con esta petición.",
                link=(row["url"] if row and row["url"] else "/requests"),
                level="info",
                entity_type="request_item",
                entity_id=rid,
                poster_url=lib_row["poster_url"] if lib_row is not None else None,
                content_title=title,
            )
    except Exception:
        logging.getLogger("emuwarez.notifications").exception(
            "No se pudieron emitir notificaciones de peticiones compatibles"
        )


def match_single_request(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    """Re-match a single request against library. Returns best match dict or None."""
    req_row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    if not req_row:
        return None
    # Lo de la vez anterior se recalcula entero: si ya no casa, no queda nada viejo enseñándose.
    casamiento = _casar(conn, dict(req_row), _biblioteca(conn))
    _guardar_casamientos(conn, [casamiento] if casamiento else [], peticion=request_id)
    if not casamiento:
        return None
    _, best, classification, _ = casamiento
    return {
        "library_item_id": best["item"]["id"],
        "library_title": best["item"].get("title"),
        **classification,
    }


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

_REQUEST_SORT = {
    "created_desc": "ri.created_at DESC, ri.updated_at DESC",
    "created_asc": "ri.created_at ASC, ri.updated_at ASC",
    "title": "ri.title COLLATE NOCASE ASC",
    "points_desc": "ri.points IS NULL, ri.points DESC, ri.created_at DESC",
    "points_asc": "COALESCE(ri.points, 0) ASC, ri.created_at DESC",      # menos coins pedidas
    "votes_desc": "COALESCE(ri.votes, 0) DESC, ri.created_at DESC",       # más me gusta
    "comments_desc": "COALESCE(ri.comments, 0) DESC, ri.created_at DESC", # más comentarios
}
_FILLED_STATUSES = ("filled", "1", "lleno", "llena")
# Lo que enseña la tabla para una resolución o un source sin pedir; los filtros lo usan como valor.
CUALQUIERA = "Cualquiera"


def list_request_items(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    status: Sequence[str] = (),
    category: Sequence[str] = (),
    resolution: Sequence[str] = (),
    source: Sequence[str] = (),
    author: Sequence[str] = (),
    instance_id: Sequence[int] = (),
    emu_status: Optional[str] = None,
    sort: Optional[str] = None,
) -> dict:
    """Return paginated request items enriched with best match info.

    Cada filtro de columna admite varios valores (OR); las columnas entre sí, con AND."""
    where_clauses: list[str] = []
    params: list = []

    def en(columna: str, valores: Sequence) -> None:
        if valores:
            where_clauses.append(f"{columna} IN ({','.join('?' * len(valores))})")
            params.extend(valores)

    def pedido(columna: str, valores: Sequence[str]) -> None:
        # Sin resolución o source pedidos la columna dice «Cualquiera», y así se filtra.
        if not valores:
            return
        concretos = [v for v in valores if v != CUALQUIERA]
        partes = [f"{columna} IN ({','.join('?' * len(concretos))})"] if concretos else []
        if len(concretos) < len(valores):
            partes.append(f"COALESCE({columna}, '') = ''")
        where_clauses.append("(" + " OR ".join(partes) + ")")
        params.extend(concretos)

    if search:
        where_clauses.append("ri.title LIKE ?")
        params.append(f"%{search}%")
    mi_usuario = mi_usuario_emu(conn) or ""
    if status:
        # Mirrors compatibility.estado_emu_de() — a request with zero
        # library candidates has no request_matches row at all, but can still
        # be Reclamado/Pendiente/Llena on the tracker itself; keep this SQL
        # fallback in sync with that function if its substring rules change.
        # Una reclamada por ti no cuenta como Reclamado: el claimed_by sale del raw_json.
        where_clauses.append(f"""
            COALESCE(
                rm.status,
                CASE
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%reclam%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%claim%' THEN
                        CASE WHEN ? != '' AND LOWER(TRIM(COALESCE(CASE WHEN json_valid(ri.raw_json) THEN
                                COALESCE(json_extract(ri.raw_json, '$.claimed_by.username'),
                                         json_extract(ri.raw_json, '$.claimed_by.name'),
                                         json_extract(ri.raw_json, '$.claimed_by')) END, ''))) = ?
                             THEN 'Sin coincidencia' ELSE 'Reclamado' END
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%pend%' THEN 'Pendiente'
                    -- "Sin llenar" = petición abierta: no es un override, y
                    -- como aquí ya no hay cruce con la biblioteca (rm.status
                    -- es NULL), cae en el mismo 'Sin coincidencia' que
                    -- devuelve _safe_request_dict. Antes daba NULL, así que
                    -- estas filas se pintaban con un estado por el que luego
                    -- no se las podía filtrar. Va antes que '%llena%' porque
                    -- "llenar" contiene "llena".
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%sin llen%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%unfilled%'
                         OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%open%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%abiert%' THEN 'Sin coincidencia'
                    WHEN LOWER(COALESCE(ri.emu_status,'')) LIKE '%lleno%' OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%llena%'
                         OR LOWER(COALESCE(ri.emu_status,'')) LIKE '%filled%' OR ri.emu_status = '1' THEN 'Llena'
                    ELSE 'Sin coincidencia'
                END
            ) IN ({','.join('?' * len(status))})
        """)
        params.extend([mi_usuario.strip().lower()] * 2 + list(status))
    en("ri.category", category)
    pedido("ri.requested_resolution", resolution)
    pedido("ri.requested_source", source)
    if author:
        en("ri.author", author)
        where_clauses.append("ri.author_visible = 1")
    en("li.instance_id", instance_id)
    if emu_status == "filled":
        where_clauses.append(f"LOWER(COALESCE(ri.emu_status,'')) IN ({','.join('?' * len(_FILLED_STATUSES))})")
        params.extend(_FILLED_STATUSES)
    elif emu_status == "open":
        where_clauses.append(f"LOWER(COALESCE(ri.emu_status,'')) NOT IN ({','.join('?' * len(_FILLED_STATUSES))})")
        params.extend(_FILLED_STATUSES)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    order_sql = _REQUEST_SORT.get(sort or "created_desc", _REQUEST_SORT["created_desc"])

    count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM request_items ri
        LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
          AND rm.id = (
            SELECT id FROM request_matches rm2
            WHERE rm2.request_item_id = ri.id
            ORDER BY rm2.confidence DESC LIMIT 1
          )
        LEFT JOIN library_items li ON li.id = rm.library_item_id
        {where_sql}
    """
    total_row = conn.execute(count_sql, params).fetchone()
    total = int(total_row["cnt"] if total_row else 0)

    items_sql = f"""
        SELECT
            ri.*,
            rm.status AS compatibility_status,
            rm.confidence AS compatibility_confidence,
            rm.resolution_match,
            rm.source_match,
            rm.type_match,
            rm.reasons AS match_reasons,
            rm.library_item_id,
            li.title AS library_title,
            li.year AS library_year,
            li.local_status,
            -- Sin cruce con póster, el que se trajo de TMDb ('' = TMDb no tiene).
            COALESCE(li.poster_url, NULLIF(ri.tmdb_poster_url, '')) AS poster_url,
            COALESCE(li.backdrop_url, NULLIF(ri.tmdb_backdrop_url, '')) AS backdrop_url,
            -- Origen: la instancia de Radarr/Sonarr donde tienes el contenido.
            -- Sale del item de biblioteca cruzado, así que una petición sin
            -- cruce (No importada) los trae en NULL y la columna pinta un
            -- guion. title_slug/tmdb_id son para el enlace directo a la
            -- instancia, igual que en Biblioteca y Subidas.
            li.instance_type,
            li.instance_name,
            li.instance_id,
            li.title_slug,
            li.tmdb_id AS library_tmdb_id
        FROM request_items ri
        LEFT JOIN request_matches rm ON rm.request_item_id = ri.id
          AND rm.id = (
            SELECT id FROM request_matches rm2
            WHERE rm2.request_item_id = ri.id
            ORDER BY rm2.confidence DESC LIMIT 1
          )
        LEFT JOIN library_items li ON li.id = rm.library_item_id
        {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(items_sql, params + [limit, offset]).fetchall()
    return {
        "items": [_safe_request_dict(dict(r), mi_usuario) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_request_item(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    """Return a single request_item dict (no match info)."""
    row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    return _safe_request_dict(dict(row), mi_usuario_emu(conn) or "") if row else None


# ---------------------------------------------------------------------------
# La petición en la ficha de Biblioteca
# ---------------------------------------------------------------------------

_CAMPOS_DE_LA_FICHA = (
    "ri.id AS peticion_id, ri.title, ri.author, ri.author_visible, ri.points, ri.url, ri.emu_status, "
    "ri.created_at, ri.req_scope, ri.req_season, ri.req_episode"
)


def _url_publica(url: Optional[str]) -> Optional[str]:
    """La página de la petición en eMuwarez, sin nada que pueda llevar una clave.

    `normalize_request` guarda la página pública (`…/requests/<id>`), que no lleva consulta; aun así no se devuelve
    tal cual: la clave de eMuwarez viaja en la consulta (`api_token=…`) y una fila escrita por otra versión podría
    traerla. Se quitan la consulta, el fragmento y el usuario:contraseña; lo que no sea http(s), fuera."""
    if not url:
        return None
    try:
        partes = urllib.parse.urlsplit(str(url).strip())
    except ValueError:
        return None
    if partes.scheme.lower() not in ("http", "https") or not partes.hostname:
        return None
    return urllib.parse.urlunsplit((partes.scheme, partes.netloc.rpartition("@")[2], partes.path, "", ""))


def _resumen_para_la_ficha(fila: dict, mi_usuario: str) -> dict:
    """Lo que la ficha enseña de una petición. El autor, solo si eMuwarez lo deja ver (la misma regla que
    `_safe_request_dict`): una petición anónima no tiene autor que enseñar."""
    autor = (fila.get("author") or "").strip() if fila.get("author_visible") else ""
    return {
        "id": int(fila["peticion_id"]),
        "title": fila.get("title"),
        "author": autor or None,
        "is_mine": bool(autor and mi_usuario and autor.lower() == mi_usuario.strip().lower()),
        "points": fila.get("points"),
        "url": _url_publica(fila.get("url")),
        "emu_status": fila.get("emu_status"),
        "created_at": fila.get("created_at"),
        "req_scope": fila.get("req_scope"),
        "req_season": fila.get("req_season"),
        "req_episode": fila.get("req_episode"),
    }


def _cubre(peticion: dict, fila: dict) -> bool:
    """Si la petición guardada en un antepasado (serie o temporada) pide también esta temporada o capítulo."""
    temporada = peticion.get("req_season")
    if temporada is None:
        return True  # la serie entera
    if fila.get("season_number") != temporada:
        return False
    if peticion.get("req_scope") == "episode":
        return fila.get("item_type") == "episode" and fila.get("episode_number") == peticion.get("req_episode")
    return True


def peticiones_heredadas(conn: sqlite3.Connection, ids: list[int]) -> dict[int, str]:
    """De qué antepasado heredan la petición, en la lista, las temporadas y capítulos de `ids` sin una propia:
    {id: «serie» | «temporada»}. Las mismas reglas que la ficha (`peticiones_de_la_ficha`): la `request_id` de su
    temporada o serie, si la cubre (`_cubre`), y gana la más cercana. Una sola consulta para toda la página; solo
    lee, y no cambia el estado guardado ni lo que filtra la columna."""
    if not ids:
        return {}
    lista = json.dumps([int(i) for i in ids])
    # Las filas, sus padres y sus abuelos (capítulo → temporada → serie), con la petición que guarda cada una.
    filas = {r["id"]: dict(r) for r in conn.execute(
        """SELECT li.id, li.item_type, li.parent_id, li.season_number, li.episode_number,
                  ri.id AS peticion, ri.req_scope, ri.req_season, ri.req_episode
           FROM library_items li LEFT JOIN request_items ri ON ri.id = li.request_id
           WHERE li.id IN (SELECT value FROM json_each(?1))
              OR li.id IN (SELECT parent_id FROM library_items WHERE id IN (SELECT value FROM json_each(?1)))
              OR li.id IN (SELECT p.parent_id FROM library_items p JOIN library_items h ON h.parent_id = p.id
                           WHERE h.id IN (SELECT value FROM json_each(?1)))""",
        (lista,),
    )}
    heredadas: dict[int, str] = {}
    for item_id in ids:
        fila = filas.get(item_id)
        if not fila or fila["peticion"] is not None or fila["item_type"] not in ("season", "episode"):
            continue
        padre, vistos = fila["parent_id"], set()
        while padre in filas and padre not in vistos:
            vistos.add(padre)
            p = filas[padre]
            if p["peticion"] is not None and _cubre(p, fila):
                heredadas[item_id] = "serie" if p["item_type"] == "series" else "temporada"
                break
            padre = p["parent_id"]
    return heredadas


def peticion_que_enlazar(conn: sqlite3.Connection, item_id: int) -> Optional[int]:
    """La petición abierta que enlazaría una subida de esta fila sin que nadie la elija (un lote desde Biblioteca),
    o None si no hay ninguna o hay más de una (ambiguo: mejor sin enlazar que enlazar la que no es).

    Las mismas reglas que el resto: una petición cuenta si su cruce guardado es «Compatible» (las que el Panel ofrece
    en «Listo para subir» con su `rec_request_id`), y es de esta fila si la fila a la que va (`_scoped_library_id`)
    es esta o, como en la ficha (`peticiones_de_la_ficha`), una temporada o serie de la que cuelga y la petición la
    cubre (`_cubre`; la de la serie entera cubre cada temporada). Gana la más cercana: la de la propia fila, luego la
    de su temporada, luego la de su serie. Solo lee."""
    fila = conn.execute("SELECT id, item_type, parent_id, season_number, episode_number FROM library_items "
                        "WHERE id = ?", (item_id,)).fetchone()
    if not fila:
        return None
    fila = dict(fila)
    # La fila y sus antepasados, del más cercano al más lejano (el control de vistos, por si hay un ciclo).
    linea = [int(fila["id"])]
    padre = fila.get("parent_id")
    while padre is not None and padre not in linea:
        linea.append(int(padre))
        p = conn.execute("SELECT parent_id FROM library_items WHERE id = ?", (padre,)).fetchone()
        padre = p["parent_id"] if p else None
    marcas = ",".join("?" * len(linea))
    # El cruce que cuenta de cada petición es el más seguro, como en el Panel.
    candidatas = conn.execute(
        f"""SELECT ri.id, ri.req_scope, ri.req_season, ri.req_episode, li.id AS lib_id, li.item_type
            FROM request_matches rm
            JOIN request_items ri ON ri.id = rm.request_item_id
            JOIN library_items li ON li.id = rm.library_item_id
            WHERE rm.library_item_id IN ({marcas}) AND rm.status = 'Compatible'
              AND rm.id = (SELECT rm2.id FROM request_matches rm2 WHERE rm2.request_item_id = ri.id
                           ORDER BY rm2.confidence DESC LIMIT 1)""",
        linea,
    ).fetchall()
    por_nivel: dict[int, set[int]] = {}
    for c in candidatas:
        peticion = dict(c)
        destino = _scoped_library_id(conn, {"id": peticion["lib_id"], "item_type": peticion["item_type"]}, peticion)
        if destino in linea and _cubre(peticion, fila):
            por_nivel.setdefault(linea.index(destino), set()).add(int(peticion["id"]))
    if not por_nivel:
        return None
    cercanas = por_nivel[min(por_nivel)]
    return next(iter(cercanas)) if len(cercanas) == 1 else None


def peticiones_de_la_ficha(conn: sqlite3.Connection, fila: dict) -> dict:
    """La petición de una fila de la biblioteca para su ficha, y las de lo que tiene debajo.

    `peticion`: la de `library_items.request_id` de la fila (una por fila: la escribe `_guardar_casamientos` en la
    fila que la petición pide de verdad). Si la fila no tiene una propia, una temporada o un capítulo heredan la de
    su temporada o su serie cuando esa petición los cubre (la de la serie entera cubre todas sus temporadas), con
    `heredada_de` = «temporada» o «serie». Su estado guardado no cambia: la lista sigue diciendo «Sin petición».
    `estado` es el de la fila que la guarda.

    `peticiones_debajo`: en una serie o una temporada, las que guardan sus temporadas y capítulos (una serie con
    una petición por temporada), en orden. Solo para la ficha: son unas pocas consultas por elemento."""
    mi_usuario = mi_usuario_emu(conn) or ""

    def leer(peticion_id) -> Optional[dict]:
        if peticion_id is None:
            return None
        r = conn.execute(f"SELECT {_CAMPOS_DE_LA_FICHA} FROM request_items ri WHERE ri.id = ?",
                         (peticion_id,)).fetchone()
        return dict(r) if r else None

    peticion = None
    propia = leer(fila.get("request_id"))
    if propia:
        peticion = {**_resumen_para_la_ficha(propia, mi_usuario), "heredada_de": None,
                    "estado": fila.get("request_status"), "library_item_id": fila.get("id")}
    elif fila.get("item_type") in ("season", "episode"):
        padre, vistos = fila.get("parent_id"), set()
        while padre is not None and padre not in vistos:
            vistos.add(padre)
            p = conn.execute("SELECT id, item_type, parent_id, request_id, request_status FROM library_items "
                             "WHERE id = ?", (padre,)).fetchone()
            if not p:
                break
            p = dict(p)
            suya = leer(p.get("request_id"))
            if suya and _cubre(suya, fila):
                peticion = {**_resumen_para_la_ficha(suya, mi_usuario),
                            "heredada_de": "serie" if p["item_type"] == "series" else "temporada",
                            "estado": p.get("request_status"), "library_item_id": p["id"]}
                break
            padre = p.get("parent_id")

    debajo: list[dict] = []
    if fila.get("item_type") in ("series", "season"):
        filas = conn.execute(
            f"""SELECT {_CAMPOS_DE_LA_FICHA}, li.id AS library_item_id, li.request_status AS estado
                FROM library_items li JOIN request_items ri ON ri.id = li.request_id
                WHERE li.parent_id = ?
                   OR li.parent_id IN (SELECT id FROM library_items WHERE parent_id = ?)
                ORDER BY li.season_number, COALESCE(li.episode_number, -1), li.id""",
            (fila["id"], fila["id"]),
        ).fetchall()
        for r in filas:
            r = dict(r)
            debajo.append({**_resumen_para_la_ficha(r, mi_usuario), "heredada_de": None,
                           "estado": r.get("estado"), "library_item_id": r["library_item_id"]})
    return {"peticion": peticion, "peticiones_debajo": debajo}


def _series_title_year(conn, lib: dict) -> tuple:
    """Resolve the series title + premiere year for a library item (walking up
    parent_id from a season/episode to its series)."""
    if lib.get("item_type") == "series":
        return lib.get("title"), lib.get("year")
    pid = lib.get("parent_id")
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
    return lib.get("title"), lib.get("year")


def _comparison_content_name(conn, lib: dict, req: dict) -> str:
    """Friendly name for the comparison table: "Serie (año) - Temporada N" and,
    for an episode request, "Serie (año) - Temporada N - SxxEyy"; "Título (año)"
    for a movie.

    "Temporada" and not "Season": this is the only place in the app that said it
    in English, so the same content read "Temporada 2" everywhere else and
    "Season 2" here."""
    scope, season, episode = req.get("req_scope"), req.get("req_season"), req.get("req_episode")
    if lib.get("item_type") in ("series", "season", "episode") or season is not None:
        title, year = _series_title_year(conn, lib)
        name = title or req.get("title") or ""
        if year:
            name += f" ({year})"
        if season is not None:
            name += f" - Temporada {season}"
            if scope == "episode" and episode is not None:
                try:
                    name += f" - S{int(season):02d}E{int(episode):02d}"
                except (TypeError, ValueError):
                    pass
        return name
    name = lib.get("title") or req.get("title") or ""
    if lib.get("year"):
        name += f" ({lib.get('year')})"
    return name


def get_request_detail(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    """Return request + best match info."""
    req_row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    if not req_row:
        return None
    mi_usuario = mi_usuario_emu(conn) or ""
    result = _safe_request_dict(dict(req_row), mi_usuario)
    # El de TMDb ('' = no tiene); el de la biblioteca, si hay cruce con póster, va delante.
    result["poster_url"] = result.get("tmdb_poster_url") or None
    result["backdrop_url"] = result.get("tmdb_backdrop_url") or None
    match_row = conn.execute(
        """
        SELECT rm.*, li.title AS library_title, li.year AS library_year, li.local_status, li.resolution AS local_resolution,
               li.source AS local_source, li.path AS local_path, li.nomenclature_status,
               li.poster_url AS poster_url, li.backdrop_url AS backdrop_url, li.video_codec AS local_video_codec,
               li.audio_languages AS local_audio_languages, li.size_bytes AS local_size,
               li.release_group AS local_release_group,
               li.tmdb_id AS local_tmdb_id, li.imdb_id AS local_imdb_id, li.tvdb_id AS local_tvdb_id,
               li.mal_id AS local_mal_id,
               li.instance_type, li.instance_name, li.instance_id, li.title_slug
        FROM request_matches rm
        JOIN library_items li ON li.id = rm.library_item_id
        WHERE rm.request_item_id = ?
        ORDER BY rm.confidence DESC
        LIMIT 1
        """,
        (request_id,),
    ).fetchone()
    if match_row:
        md = dict(match_row)
        reasons = md.get("reasons") or ""
        result["poster_url"] = md.get("poster_url") or result["poster_url"]
        result["backdrop_url"] = md.get("backdrop_url") or result["backdrop_url"]
        result["library_year"] = md.get("library_year")
        # Mismos nombres que en la lista, para que la columna Origen de la
        # tabla y el campo Origen de la ficha lean lo mismo.
        result["instance_type"] = md.get("instance_type")
        result["instance_name"] = md.get("instance_name")
        result["instance_id"] = md.get("instance_id")
        result["title_slug"] = md.get("title_slug")
        result["library_tmdb_id"] = md.get("local_tmdb_id")
        result["match"] = {
            "id": md["id"],
            "library_item_id": md["library_item_id"],
            "library_title": md.get("library_title"),
            "local_status": md.get("local_status"),
            "local_resolution": md.get("local_resolution"),
            "local_source": md.get("local_source"),
            "local_video_codec": md.get("local_video_codec"),
            "local_audio_languages": md.get("local_audio_languages"),
            "local_size": md.get("local_size"),
            "local_release_groups": [md["local_release_group"]] if md.get("local_release_group") else [],
            "local_tmdb_id": md.get("local_tmdb_id"),
            "local_imdb_id": md.get("local_imdb_id"),
            "local_tvdb_id": md.get("local_tvdb_id"),
            "local_mal_id": md.get("local_mal_id"),
            "local_path": md.get("local_path"),
            "nomenclature_status": md.get("nomenclature_status"),
            "status": md["status"],
            "confidence": float(md["confidence"]),
            "resolution_match": bool(md["resolution_match"]) if md["resolution_match"] is not None else None,
            "source_match": bool(md["source_match"]) if md["source_match"] is not None else None,
            "id_match": bool(md.get("type_match")),
            "reasons": [r for r in reasons.splitlines() if r],
        }
        # The stored match was computed against the matched library item; for a
        # series/season rollup resolve the SCOPE's effective attributes (a
        # specific episode, or the uniform value across the relevant episodes)
        # and re-classify, so the comparison shows real data and the status is
        # consistent with those checks (e.g. a T2·E5 request that IS 1080p is
        # Compatible, not Parcial against an empty rollup).
        lib_row = conn.execute(
            "SELECT * FROM library_items WHERE id = ?", (md["library_item_id"],)
        ).fetchone()
        if lib_row:
            result["match"]["content_name"] = _comparison_content_name(conn, dict(lib_row), result)
            # Which library row this request is really about. The MATCH points
            # at whatever the matcher found — for a season request that is the
            # series row, because every season of a series shares the series'
            # tmdb_id — so following it landed you on the series instead of the
            # season you clicked. This resolves the scope's own row.
            result["match"]["library_target_id"] = _scoped_library_id(conn, dict(lib_row), result)
            # Same canonical "Serie (Año) - SxxEyy" title Biblioteca/Subidas'
            # own dedicated pages use — request's own scope (not the matched
            # row's) so a request matched against a series/season rollup still
            # shows the exact season/episode it's actually asking for.
            result["display_title"] = content_display_title(
                conn, dict(lib_row),
                season=result.get("req_season"), episode=result.get("req_episode"),
                scope=result.get("req_scope"),
            )
        if lib_row and dict(lib_row).get("item_type") in ("series", "season"):
            eff, cls = clasificar_peticion(
                conn, result, dict(lib_row), mi_usuario=mi_usuario,
                id_match=bool(md.get("type_match")),
                base_confidence=float(md["confidence"]),
            )
            result["match"].update({
                "status": cls["status"],
                "resolution_match": cls["resolution_match"],
                "source_match": cls["source_match"],
                "local_status": eff.get("local_status"),
                "local_resolution": eff.get("resolution"),
                "local_source": eff.get("source"),
                "local_video_codec": eff.get("video_codec"),
                "local_audio_languages": eff.get("audio_languages"),
                "local_size": eff.get("size_bytes"),
                "local_release_groups": eff.get("release_groups") or [],
                "local_path": eff.get("path"),
            })
    else:
        result["match"] = None
    return result


def mark_request_reviewed(conn: sqlite3.Connection, request_id: int) -> bool:
    """Set reviewed_at = now on a request_item. Returns True if found."""
    row = conn.execute("SELECT id FROM request_items WHERE id = ?", (request_id,)).fetchone()
    if not row:
        return False
    try:
        conn.execute(
            "UPDATE request_items SET reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (request_id,),
        )
        conn.commit()
    except Exception:
        # reviewed_at column may not exist yet (pre-migration DB); silently succeed
        conn.rollback()
    return True


# ---------------------------------------------------------------------------
# Legacy query functions (backward compat)
# ---------------------------------------------------------------------------

def list_requests(conn: sqlite3.Connection, *, limit: int = 50, search: Optional[str] = None) -> list[dict]:
    params: list = []
    sql = "SELECT * FROM request_items"
    if search:
        sql += " WHERE title LIKE ?"
        params.append(f"%{search}%")
    sql += " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ?"
    params.append(limit)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_request(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM request_items WHERE id = ?", (request_id,)).fetchone()
    return dict(row) if row else None


def get_match_for_request(conn: sqlite3.Connection, request_id: int) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT rm.*, li.title AS library_title, li.local_status, li.resolution AS local_resolution,
               li.source AS local_source, li.path AS local_path
        FROM request_matches rm
        JOIN library_items li ON li.id = rm.library_item_id
        WHERE rm.request_item_id = ?
        ORDER BY rm.confidence DESC
        LIMIT 1
        """,
        (request_id,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _safe_request_dict(d: dict, mi_usuario: Optional[str] = None) -> dict:
    """Remove author info if author_visible=0.

    Also fills in compatibility_status when there's no request_matches row at
    all (no library candidate ever matched this request) — Reclamado/
    Pendiente/Llena describe the request's own state on the tracker, true
    regardless of whether your library holds anything for it, so a request
    with zero candidates would otherwise silently read as "Sin coincidencia"
    even when eMuwarez itself already says it's Reclamado.

    Failing both, it settles on "Sin coincidencia" (shown as "No importada")
    rather than staying null. The status filter above already resolves this
    same case to that exact string, so leaving it null here made a row the
    UI could paint but not filter: it showed a bare dash and had no entry in
    the Compatibilidad dropdown.

    `reclamada_por` («ti», «otro», «desconocido» o None) dice quién la tiene reclamada; la tuya no es Reclamado."""
    if not d.get("author_visible"):
        d.pop("author", None)
    if not d.get("compatibility_status"):
        d["compatibility_status"] = estado_emu_de(d, mi_usuario) or "Sin coincidencia"
    d["reclamada_por"] = reclamada_por(d, mi_usuario)
    return d


def dashboard_request_counters(conn: sqlite3.Connection) -> dict[str, int | str | None]:
    """Los contadores de peticiones del Panel.

    Vivían dentro del endpoint (auditoría, hallazgo 6.2), y no eran consultas
    tontas: "Compatible" cuenta peticiones cuya MEJOR coincidencia lo es, no
    filas de coincidencia; "Mías" exige author_visible porque una fila sin
    autor visible no es tuya aunque el texto coincida por casualidad; y
    "Reclamadas" busca por subcadena porque eMuwarez no dice si la reclamación
    es tuya. Ese criterio es de dominio, no de HTTP."""
    from .settings import get_setting_canonical

    def _cuenta(sql: str, params: tuple = ()) -> int:
        try:
            row = conn.execute(sql, params).fetchone()
            return int(row["cnt"] or 0) if row else 0
        except Exception:
            return 0

    try:
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN LOWER(COALESCE(emu_status,'')) IN ('filled','llena','lleno','1')
                               THEN 1 ELSE 0 END) AS filled
               FROM request_items"""
        ).fetchone()
        total, filled = (int(row["total"] or 0), int(row["filled"] or 0)) if row else (0, 0)
    except Exception:
        total = filled = 0

    def _mejor(status: str) -> int:
        return _cuenta(
            """SELECT COUNT(*) AS cnt FROM request_items ri
               WHERE (SELECT rm.status FROM request_matches rm
                      WHERE rm.request_item_id = ri.id
                      ORDER BY rm.confidence DESC LIMIT 1) = ?""",
            (status,),
        )

    mias = 0
    usuario = get_setting_canonical(conn, "emu.username")
    if usuario:
        mias = _cuenta(
            "SELECT COUNT(*) AS cnt FROM request_items "
            "WHERE author_visible = 1 AND LOWER(TRIM(author)) = LOWER(TRIM(?))",
            (usuario,),
        )

    return {
        "requests_total": total,
        "requests_filled": filled,
        "requests_compatible": _mejor("Compatible"),
        "requests_partial": _mejor("Parcial"),
        "requests_mine": mias,
        "requests_reclaimed": _cuenta(
            "SELECT COUNT(*) AS cnt FROM request_items "
            "WHERE LOWER(COALESCE(emu_status,'')) LIKE '%reclam%' "
            "   OR LOWER(COALESCE(emu_status,'')) LIKE '%claim%'"
        ),
        "requests_last_sync_at": get_state(conn, "last_emu_requests_sync_utc"),
    }
