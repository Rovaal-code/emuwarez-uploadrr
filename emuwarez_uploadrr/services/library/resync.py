"""Releer un elemento: lo que cambia en Radarr/Sonarr tras renombrar o escribir en el original, y los valores
técnicos de una serie o temporada."""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from typing import Callable, Optional

from ...integrations import radarr, sonarr
from ...models import LocalStatus

from .listado import get_library_item
from .sync import _SEASON_ROLLUP_FIELDS, _prepare_movie, _sync_one_series, upsert_library_item

logger = logging.getLogger("emuwarez.library")


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
    from ..nomenclature import infer_provider_from_item
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

    from ..instances import get_instance
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
            from ..tmdb_titles import series_titles_localized
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
