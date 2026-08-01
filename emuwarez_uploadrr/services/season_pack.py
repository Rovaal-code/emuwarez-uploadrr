"""Season pack: one single upload release for a whole Temporada row.

Ports (does not rewrite) legacy.py::build_plan()'s `season_pack` branch to
the modern service layer: each available episode gets its own individually
correct nomenclature-adapted filename (reusing
nomenclature.py::build_nomenclature_proposal() as-is — already computes
real codec/audio/provider per Phases 6A/6E), and the pack gets ONE overall
title (using the first available episode's own metadata as representative,
same as legacy). services/uploadrr_contract.py::build_uploadrr_emu_command()
already supports this exact shape (season set, episode=None -> only
`-season Sxx`, never `-episode`) — nothing there needs to change.

A pack requires every available episode to already live in the same
directory (the common Sonarr/Radarr convention: one folder per season) —
that shared folder becomes the pack folder and each episode is renamed in
place there, same technique nomenclature.py uses for a single file. There
is no way to unify episodes scattered across different folders into one
pack; the folder they already share IS the pack folder.

The whole season is required to be consistent (same video/audio codec,
audio languages, resolution, source across every available episode) and
complete (every episode of the season must be Disponible) — both are hard
blocks, not warnings, since a mismatched or partial pack would be a broken
release. Subtitles are the one exception: they may differ between episodes,
and aren't required at all when the audio is already in Castilian (see
_spanish_errors).

SAFETY CONTRACT: identical to filesystem_apply.py — this module never
moves/deletes a source file, only renames it in place. It only calls the
existing generic build_safe_rename_plan()/apply_rename_plan() primitives
once per episode. Confirmation-token gating for a REAL apply happens once,
server-side, in services/upload_queue.py (same as the single-file
nomenclature step) — this module has no confirmation token of its own.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from ..database import connect, row_to_dict
from ..models import LocalStatus
from .filesystem_apply import apply_rename_plan, build_safe_rename_plan
from .nomenclature import (
    _get_release_tag,
    build_nomenclature_proposal,
)

# Progress reporting while build_season_pack_plan() churns through episodes
# (each one calls build_nomenclature_proposal, real work) — same in-memory
# dict+lock pattern as upload_checks.py's _CHECKS_PROGRESS, keyed by
# season_id so the wizard can poll "Comprobando N de M capítulos…" while a
# single slow request is in flight.
_PLAN_LOCK = threading.Lock()
_PLAN_PROGRESS: dict[int, dict] = {}
# Seasons whose in-flight plan the user asked to abandon (they closed the
# wizard). Building a plan runs build_nomenclature_proposal once per episode,
# which is real work — without this the server kept churning through a 24
# episode season nobody was waiting for any more.
_PLAN_CANCELLED: set[int] = set()


class SeasonPlanCancelled(Exception):
    """Raised out of the per-episode loop when the user closed the wizard."""


def get_season_plan_progress(season_id: int) -> dict:
    with _PLAN_LOCK:
        return dict(_PLAN_PROGRESS.get(season_id, {"done": 0, "total": 0, "current_title": None}))


def request_season_plan_cancel(season_id: int) -> None:
    """Ask an in-flight build_season_pack_plan for this season to stop at its
    next episode boundary. A no-op if none is running: the flag is cleared when
    a plan starts, so it can't leak into the next one the user opens."""
    with _PLAN_LOCK:
        _PLAN_CANCELLED.add(season_id)


def _raise_if_cancelled(season_id: int) -> None:
    with _PLAN_LOCK:
        cancelled = season_id in _PLAN_CANCELLED
    if cancelled:
        raise SeasonPlanCancelled()


def _clear_season_plan_cancel(season_id: int) -> None:
    with _PLAN_LOCK:
        _PLAN_CANCELLED.discard(season_id)


def _set_season_plan_progress(season_id: int, *, done: int, total: int, current_title: Optional[str] = None) -> None:
    with _PLAN_LOCK:
        _PLAN_PROGRESS[season_id] = {"done": done, "total": total, "current_title": current_title}


def _get_season_row(season_id: int, conn) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM library_items WHERE id = ? AND item_type = 'season'", (season_id,)
    ).fetchone()
    return row_to_dict(row)


def _get_series_row(series_id: int, conn) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM library_items WHERE id = ? AND item_type = 'series'", (series_id,)
    ).fetchone()
    return row_to_dict(row)


def _get_season_episodes(season_id: int, conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode' "
        "ORDER BY episode_number",
        (season_id,),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def _build_season_pack_title(
    *,
    title: str,
    year: Optional[int],
    season_number: Optional[int],
    resolution: Optional[str],
    source: Optional[str],
    video_codec: Optional[str],
    audio_summary: Optional[str],
    subtitle_summary: Optional[str],
    release_tag: Optional[str],
    provider: Optional[str] = None,
    custom: bool = False,
) -> str:
    """Modern equivalent of legacy.py::build_emu_title(..., pack=True) — one
    representative title for the whole pack (season only, no per-episode
    numbering)."""
    from .source_assistant import _build_source_string
    prefix = f"{title} S{season_number:02d}" if season_number is not None else title
    parts = [prefix]
    if year:
        parts.append(str(year))
    if resolution:
        parts.append(resolution)
    # CUSTOM va entre la resolución y el proveedor, que es donde lo pone el
    # catálogo de eMuwarez ("… 2160p 4K UHD CUSTOM AMZN WEB-DL HEVC …").
    # Aquí marca que los capítulos no traen el mismo audio, así que el nombre
    # lista varias pistas del mismo idioma y ninguna está en todos.
    if custom:
        parts.append("CUSTOM")
    # Provider (AMZN/NF/DSNP...) attaches to Source, in front of it — same
    # combiner the single-file builder uses (nomenclature.py's
    # _build_proposed_filename) — without this a season pack's title never
    # showed the provider even when its source was WEB-DL from a platform.
    source_str = _build_source_string(source, provider)
    if source_str:
        parts.append(source_str)
    if video_codec:
        parts.append(video_codec)
    if audio_summary:
        parts.append(audio_summary)
    if subtitle_summary:
        parts.append(subtitle_summary)
    text = " ".join(p for p in parts if p)
    return f"{text}-{release_tag}" if release_tag else text


def preview_season_pack_title(fields: dict) -> dict:
    """Recompute just the season pack title string from already-known field
    values — no disk/DB I/O, no re-running build_nomenclature_proposal per
    episode. Mirrors source_assistant.update_nomenclature_fields_preview()'s
    role for a single item: backs the wizard's live preview while editing
    Source/Proveedor/Tag, called on every debounced keystroke, so it must
    stay cheap. `fields` carries the season's own already-loaded base values
    (title/year/season_number/resolution/video_codec/audio_summary/
    subtitle_summary) plus whatever the user is currently editing
    (source/provider/tag)."""
    title = _build_season_pack_title(
        title=fields.get("title") or "",
        year=fields.get("year"),
        season_number=fields.get("season_number"),
        resolution=fields.get("resolution"),
        source=fields.get("source"),
        provider=fields.get("provider"),
        video_codec=fields.get("video_codec"),
        audio_summary=fields.get("audio_summary"),
        subtitle_summary=fields.get("subtitle_summary"),
        release_tag=fields.get("tag"),
        custom=bool(fields.get("custom")),
    )
    return {"torrent_name": title}


# The 5 properties every available episode of a season pack must share.
# Compared on the RAW library_items columns (not the nomenclature
# proposal's already-combined display strings like audio_summary) for
# video_codec/audio_codec/audio_languages, and on the proposal's own resolved
# values for resolution/source (each episode's proposal already ran
# _infer_resolution_from_item/_infer_source_from_item).
#
# subtitle_languages is deliberately NOT in this list: eMuwarez accepts a
# season pack whose episodes carry different subtitle tracks as long as every
# one of them has Castilian, so requiring them to be identical blocked packs
# the tracker would have taken. That looser rule is _spanish_errors() below,
# which also exempts subtitles entirely when the audio is already Castilian.
#
# audio_languages, by contrast, MUST stay here: the pack has a single release
# name stating one audio for the whole thing, so episodes that disagree on it
# would make that name lie about half the pack.
# Lo ÚNICO que tiene que coincidir en todos los capítulos para que la
# temporada pueda subirse como pack. Antes eran cinco campos: además de la
# resolución, el códec de vídeo, el de audio, los idiomas y el source. Eso
# rechazaba packs perfectamente válidos (una temporada donde un capítulo trae
# una pista de audio extra, o viene de otra fuente, sigue siendo la misma
# temporada).
#
# Los demás campos ya no bloquean: se resumen en el nombre del pack, ver
# _aggregate_pack_fields.
_CONSISTENCY_FIELDS: list[tuple[str, str, Any]] = [
    ("resolution", "resolución", lambda ep, prop: prop.get("resolution")),
    ("video_codec", "códec de vídeo", lambda ep, prop: prop.get("video_codec")),
]

# Los mismos campos, para quien solo tiene la fila de rollup de la temporada y
# no va a recorrer los capítulos.
_PACK_ROLLUP_FIELDS = tuple(key for key, _label, _getter in _CONSISTENCY_FIELDS)


def pack_rollup_sql(alias: str = "") -> str:
    """El equivalente en SQL de la parte de can_pack_from_rollup que mira los
    campos técnicos, para quien filtra en la base y no puede llamar a Python.

    Se GENERA desde _PACK_ROLLUP_FIELDS en vez de escribirse a mano en cada
    consulta: esa expresión estaba copiada en tres sitios de library.py (la
    tarjeta Contenido único, la cuenta de episodios y Recomendaciones) con
    alias distintos, y cuando la regla cambió hubo que acertar en las tres.
    Ahora cambia sola con la definición.

    No incluye el castellano (has_spanish_ok): las tres consultas lo aplican a
    todos los tipos de contenido, no solo a las temporadas, así que cada una
    lo pone en su sitio.
    """
    prefix = f"{alias}." if alias else ""
    return " AND ".join(f"{prefix}{field} IS NOT NULL" for field in _PACK_ROLLUP_FIELDS)


def can_pack_from_rollup(row: dict) -> bool:
    """Si esta temporada podría subirse como pack, mirando solo su fila.

    Es la MISMA regla que build_season_pack_plan aplica de verdad, en versión
    barata: las columnas de rollup solo se rellenan cuando todos los capítulos
    coinciden en ese campo (library._update_season_rollup), así que un NULL
    significa "no coinciden".

    Existe para que Biblioteca, el Panel, Recomendaciones y Peticiones no
    tengan que reimplementar cada uno la condición: esa expresión copiada en
    cinco sitios ya se quedó desincronizada tres veces (ver docs/auditoria.md,
    hallazgo 2.1). Sirve para PINTAR, CONTAR y FILTRAR; quien decide de verdad
    si la subida sale sigue siendo build_season_pack_plan.
    """
    return (
        all(row.get(field) for field in _PACK_ROLLUP_FIELDS)
        and row.get("has_spanish_ok") == 1
    )


def _consistency_errors(episode_entries: list[dict]) -> list[str]:
    """One message per (episode, field) that doesn't match the first
    available episode's value — names the differing episode so the user
    knows exactly what to fix."""
    if len(episode_entries) < 2:
        return []
    baseline_ep, baseline_prop = episode_entries[0]["episode"], episode_entries[0]["proposal"]
    errors: list[str] = []
    for _key, label, getter in _CONSISTENCY_FIELDS:
        baseline = getter(baseline_ep, baseline_prop)
        for entry in episode_entries[1:]:
            ep, prop = entry["episode"], entry["proposal"]
            value = getter(ep, prop)
            if value != baseline:
                errors.append(
                    f"El capítulo {ep.get('episode_number')} tiene {label} distinto "
                    f"({value or 'desconocido'}) al del capítulo {baseline_ep.get('episode_number')} "
                    f"({baseline or 'desconocido'})."
                )
    return errors


def _aggregate_pack_fields(episode_entries: list[dict], conn=None) -> dict:
    """Los valores que describen al PACK, sacados de sus capítulos.

    Solo la resolución tiene que coincidir (lo garantiza _consistency_errors).
    Con el resto:

    - Los idiomas de audio se SUMAN. El pack CONTIENE todos, así que
      anunciarlos todos es exacto: un capítulo con "ESP" y otro con "ESP-ING"
      dan un pack "ESP-ING".
    - Códec de vídeo, códec de audio y source se dejan VACÍOS si difieren. Un
      nombre que dijera "x264 x265" anunciaría dos códecs para un solo release
      y no describiría nada; mejor no decir nada que decir algo falso.
    - El audio conserva su códec y canales solo si TODOS los capítulos traen
      exactamente el mismo resumen; si no, se queda en los idiomas a secas.

    Cada capítulo mantiene aparte su propia nomenclatura completa, con lo que
    de verdad tiene dentro (get_season_episode_names).
    """
    from .emu_format import build_audio_string, _split_languages

    def comun(getter):
        """El valor si TODOS coinciden; None si difieren o falta alguno."""
        valores = {getter(e) for e in episode_entries}
        if len(valores) == 1:
            unico = valores.pop()
            return unico or None
        return None

    audio, custom = _aggregate_pack_audio(episode_entries, conn)

    return {
        "resolution": comun(lambda e: e["proposal"].get("resolution")),
        # El source y el proveedor se vacían si difieren: un release no puede
        # ser BluRay y WEB-DL a la vez, y no hay nada que sumar.
        "source": comun(lambda e: e["proposal"].get("source")),
        "video_codec": comun(lambda e: e["proposal"].get("video_codec")),
        "audio_summary": audio,
        "subtitle_summary": comun(lambda e: e["proposal"].get("subtitle_summary")),
        "custom": custom,
    }


def _episode_audio_by_language(ep: dict, conn) -> dict:
    """La mejor pista de cada idioma de UN capítulo: {"ESP": "DD+ 5.1", ...}.

    Sale del informe de MediaInfo, que ya está cacheado por fichero desde que
    lo leyó la nomenclatura de este mismo capítulo."""
    from .media_info_service import build_mediainfo_report
    from .path_mapping import resolve_local_path
    from .emu_format import _split_languages
    path = ep.get("path")
    if path:
        report = build_mediainfo_report(resolve_local_path(path, conn=conn) or path)
        por_idioma = report.get("audio_by_language") or {}
        if por_idioma:
            return {lang: f"{v['codec']} {v['channels']}".strip()
                    for lang, v in por_idioma.items()}

    # Sin MediaInfo (fichero no accesible, o Radarr/Sonarr como única fuente)
    # se cae a las columnas de la biblioteca. Ahí solo hay un códec para todo
    # el capítulo, así que todos sus idiomas comparten pista: se pierde el
    # detalle por idioma, pero seguir sabiendo QUÉ idiomas trae cada capítulo
    # basta para no anunciar uno que falte en la mitad del pack.
    codec = ep.get("audio_codec") or ""
    return {lang: codec for lang in _split_languages(ep.get("audio_languages"))}


def _aggregate_pack_audio(episode_entries: list[dict], conn=None) -> tuple[Optional[str], bool]:
    """El audio del pack y si hay que marcarlo CUSTOM.

    La regla es "no mentir": una pista solo puede nombrarse si TODOS los
    capítulos la tienen.

    - Un idioma que en todos los capítulos trae la misma pista se nombra tal
      cual. Si dentro de cada capítulo ese idioma viene además en una pista
      peor, nombrar la mejor no miente: todos la tienen (eso ya lo resuelve
      media_info_service antes de llegar aquí).
    - Un idioma cuya pista CAMBIA de un capítulo a otro no se puede resumir en
      una: decir la mejor mentiría sobre los capítulos que solo tienen la peor.
      Se nombran todas sus variantes y el pack se marca CUSTOM.
    - Un idioma que solo está en algunos capítulos es el mismo caso: falta en
      los demás, así que también marca CUSTOM.

    Devuelve (cadena de audio, custom).
    """
    from .emu_format import (build_audio_string, audio_track_quality,
                             format_audio_codec, format_channels)

    por_capitulo = [_episode_audio_by_language(e["episode"], conn) for e in episode_entries]
    por_capitulo = [d for d in por_capitulo if d]
    if not por_capitulo:
        return None, False

    idiomas: list[str] = []
    for d in por_capitulo:
        for lang in d:
            if lang not in idiomas:
                idiomas.append(lang)

    custom = False
    # idioma -> pistas que hay que nombrar, en orden de calidad
    a_nombrar: list[tuple[str, str]] = []
    for lang in idiomas:
        variantes = [d.get(lang) for d in por_capitulo]
        distintas = {v for v in variantes if v}
        if len(distintas) == 1 and all(variantes):
            a_nombrar.append((lang, distintas.pop()))     # todos igual: no miente
        else:
            # Difieren, o falta en algún capítulo: se nombran todas y CUSTOM.
            custom = True
            # audio_track_quality ordena "menor es mejor".
            for v in sorted(distintas, key=lambda x: audio_track_quality(*_partir(x))):
                a_nombrar.append((lang, v))

    # Se agrupa por pista, como dentro de un capítulo: los idiomas que
    # comparten códec y canales van juntos ("ESP-CAT TrueHD 5.1").
    grupos: dict[str, list[str]] = {}
    for lang, pista in a_nombrar:
        grupos.setdefault(pista, [])
        if lang not in grupos[pista]:
            grupos[pista].append(lang)

    # De mejor a peor, igual que se ordenan las pistas dentro de un capítulo.
    orden = sorted(grupos.items(), key=lambda kv: audio_track_quality(*_partir(kv[0])))

    partes = []
    for pista, langs in orden:
        codec, canales = _partir(pista)
        if custom and len(langs) > 1:
            # En un pack CUSTOM un idioma puede salir en dos grupos, así que
            # no se colapsa a DUAL/MULTI: esos tokens dicen "este release trae
            # castellano e inglés" y aquí taparían de qué pista habla cada uno.
            partes.append(" ".join(x for x in ("-".join(langs),
                                               format_audio_codec(codec),
                                               format_channels(canales)) if x))
        else:
            partes.append(build_audio_string(codec, "/".join(langs), canales))
    return (" ".join(p for p in partes if p) or None), custom


def _partir(pista: str) -> tuple[str, str]:
    """"DD+ Atmos 5.1" -> ("DD+ Atmos", "5.1"). El último trozo son los canales."""
    trozos = (pista or "").rsplit(" ", 1)
    return (trozos[0], trozos[1]) if len(trozos) == 2 else (pista, "")


def _season_title_options(series: dict | None, season: dict, conn) -> list[dict]:
    """Título dropdown choices for a pack: the series' Spanish name and its
    original one.

    El original sale de la biblioteca cuando está guardado: desde el
    2026-08-01 la sincronización guarda el título que manda Sonarr (el que ves
    en Sonarr, normalmente en inglés) antes de pisarlo con el español. Antes se
    perdía ahí mismo, porque el mapeador buscaba un campo `originalTitle` que
    Sonarr no tiene, y había que pedírselo a TMDb.

    Se sigue preguntando a TMDb cuando no hay nada guardado, que es el caso de
    las bibliotecas sincronizadas antes de ese cambio. Una consulta por plan,
    cacheada, no una por capítulo."""
    from .source_assistant import build_title_options
    from .tmdb_titles import resolve_english_title
    spanish = (series or {}).get("title") or season.get("title")
    original = (series or {}).get("english_title") or season.get("english_title")
    tmdb_id = (series or {}).get("tmdb_id") or season.get("tmdb_id")
    if not (original or "").strip():
        # Solo las bibliotecas sincronizadas antes del esquema 37 llegan aquí.
        original = resolve_english_title(
            conn, "tv", tmdb_id,
            (series or {}).get("original_title") or season.get("original_title"),
        )
    return build_title_options(spanish, original)


def _spanish_errors(episode_entries: list[dict]) -> list[str]:
    """Every episode has to carry Castilian one way or the other: dubbed
    (audio) or at least subtitled. Reports the episodes that carry neither,
    naming what they actually have so it's obvious what to fix.

    Castilian AUDIO exempts an episode from needing subtitles at all — a dubbed
    pack with no subtitle tracks whatsoever is perfectly valid. Subtitles are
    only the fallback for when the audio isn't in Castilian, and then they don't
    have to match across episodes, they just each have to include it.

    The audio is the same across every episode of a pack anyway (audio_languages
    is in _CONSISTENCY_FIELDS — it has to be, since the pack's single release
    name states one audio for the whole thing), so in practice this either
    exempts the entire season or none of it.

    An episode with no info at all fails: "we never read it" is not evidence
    that it meets the rule."""
    from .emu_format import has_castellano

    errors: list[str] = []
    for entry in episode_entries:
        ep = entry["episode"]
        if has_castellano(ep.get("audio_languages")) == 1:
            continue
        if has_castellano(ep.get("subtitle_languages")) == 1:
            continue
        audio = ep.get("audio_languages")
        subs = ep.get("subtitle_languages")
        errors.append(
            f"El capítulo {ep.get('episode_number')} no tiene castellano ni en el audio "
            f"({audio or 'sin audio detectado'}) ni en los subtítulos "
            f"({subs or 'sin subtítulos detectados'})."
        )
    return errors


def build_season_pack_plan(
    season_id: int, conn=None,
    source_override: str | None = None, provider_override: str | None = None,
    tag_override: str | None = None, title_override: str | None = None,
) -> dict[str, Any]:
    """Build a dry-run plan for a season-pack upload. Never modifies the
    filesystem. Blocks (status="blocked") on: season not found, no episode
    available, episodes not all in the same folder, incomplete season, or
    an episode-vs-episode consistency mismatch — a season pack has no
    "warning, upload anyway" state, unlike a single file.

    `source_override`/`provider_override`/`tag_override` (set either by the
    automated-upload source-disparity gate, or by hand in the manual
    wizard's now-editable Source/Proveedor/Tag fields) are applied to every
    episode's own proposal — a pack requires every episode to share the same
    source anyway, so the override applies uniformly.

    `title_override` is the Título dropdown's pick (Spanish by default, or the
    original). A season has no nomenclature proposal row of its own to save it
    into, unlike a movie/episode, so it travels with the other overrides."""
    own = conn is None
    conn = conn or connect()
    try:
        empty = {
            "status": "blocked", "errors": [], "warnings": [],
            "season_pack_title": None, "pack_folder": None, "episodes": [],
        }

        season = _get_season_row(season_id, conn=conn)
        if not season:
            empty["errors"] = ["Temporada no encontrada."]
            return empty

        series = _get_series_row(season["parent_id"], conn=conn) if season.get("parent_id") else None
        series_title = (
            (title_override or "").strip()
            or (series or {}).get("title") or season.get("title") or "Serie"
        )
        year = (series or {}).get("year") or season.get("year")

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available_ids = {
            e["id"] for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value
        }
        available_episodes = [e for e in all_episodes if e["id"] in available_ids]

        errors: list[str] = []

        if not available_episodes:
            errors.append("La temporada no tiene ningún episodio disponible.")
            empty["errors"] = errors
            return empty

        # Blocking (not just warning): an incomplete pack would silently
        # upload a partial season as if it were the whole thing.
        if len(available_episodes) < len(all_episodes):
            missing = sorted(
                e.get("episode_number") for e in all_episodes
                if e["id"] not in available_ids and e.get("episode_number") is not None
            )
            errors.append(
                f"Temporada incompleta: faltan {len(all_episodes) - len(available_episodes)} "
                f"episodio(s) por estar Disponible(s)"
                + (f" (capítulo(s) {', '.join(str(m) for m in missing)})" if missing else "") + "."
            )
            empty["errors"] = errors
            return empty

        # A season pack needs ONE shared destination folder: every available
        # episode must already live in the same directory (the common
        # Sonarr/Radarr convention: one folder per season) — that shared
        # folder becomes the pack folder and each episode is renamed in
        # place there, same technique the single-file path uses.
        # Radarr/Sonarr-reported paths (raw convention, e.g. /data/media/…)
        # need mapping to where this app actually reaches the file (e.g. an
        # SSHFS/NFS mount) for every real filesystem check/operation — same
        # convention nomenclature.py::build_nomenclature_apply_plan follows
        # for a single file. Resolved once per episode, reused below.
        from .path_mapping import resolve_local_path
        local_paths: dict[int, Optional[str]] = {
            e["id"]: (resolve_local_path(e.get("path"), conn=conn) or e.get("path"))
            for e in available_episodes
        }

        dirs = {os.path.dirname(p or "") for p in local_paths.values()}
        dirs.discard("")
        if len(dirs) != 1:
            errors.append(
                "Los episodios de esta temporada no están todos en la misma carpeta, así que no "
                "se puede unificar el pack. Muévelos a una carpeta común."
            )
            empty["errors"] = errors
            return empty
        common_dir = next(iter(dirs))
        if not os.access(common_dir, os.W_OK):
            errors.append(f"La carpeta de los episodios no es escribible: {common_dir}")
            empty["errors"] = errors
            return empty

        # Per-episode proposals — reused as-is, already compute real
        # codec/audio/provider (Phases 6A/6E), not recomputed here. Progress
        # published as each one completes so the wizard can show "Comprobando
        # N de M capítulos…" while this (possibly slow) request is in flight.
        total = len(available_episodes)
        _clear_season_plan_cancel(season_id)
        _set_season_plan_progress(season_id, done=0, total=total)
        episode_entries = []
        for i, ep in enumerate(available_episodes):
            # Checked BEFORE each episode, so closing the wizard stops the work
            # at the next boundary instead of at the end of the whole season.
            _raise_if_cancelled(season_id)
            # El progreso se publica ANTES de trabajar, con el capítulo que se
            # va a mirar. Publicándolo después, el asistente se quedaba en
            # "0 de N" y sin ningún nombre durante todo el primer capítulo —
            # que es justo el más lento, porque es el que paga la consulta del
            # título a TMDb — y a partir de ahí enseñaba el nombre del capítulo
            # YA TERMINADO mientras trabajaba en el siguiente.
            _set_season_plan_progress(season_id, done=i, total=total,
                                      current_title=ep.get("title"))
            proposal = build_nomenclature_proposal(
                ep["id"], conn=conn,
                source_override=source_override, provider_override=provider_override,
                tag_override=tag_override, title_override=title_override,
            )
            episode_entries.append({"episode": ep, "proposal": proposal})
        _set_season_plan_progress(season_id, done=total, total=total, current_title=None)

        errors.extend(_consistency_errors(episode_entries))
        errors.extend(_spanish_errors(episode_entries))

        first_proposal = episode_entries[0]["proposal"]
        release_tag = tag_override or _get_release_tag(conn=conn)

        # Internal Source Tool comparison (name vs Radarr/Sonarr vs
        # MediaInfo-bitrate), computed once from the first available episode
        # — every episode already has to agree on source for the pack to be
        # valid at all, so this is representative of the whole season. Lets
        # the wizard show the same "blinking" alert + comparison link a
        # movie/episode gets right next to the season's own Source field.
        from .source_assistant import build_editable_nomenclature_fields
        source_comparison = build_editable_nomenclature_fields(
            available_episodes[0]["id"], conn=conn,
        ).get("source_comparison")

        # Provider: each episode's own proposal already tried the filename
        # first (nomenclature.py's _infer_provider_from_item); if NONE
        # revealed one and the source is WEB-DL, ONE TMDb lookup for the
        # whole season — not repeated per episode.
        provider = first_proposal.get("provider_final")
        if not provider and (first_proposal.get("source") or "").upper() == "WEB-DL":
            from .source_assistant import suggest_provider_for_item
            suggestion = suggest_provider_for_item(available_episodes[0]["id"], conn=conn)
            provider = suggestion.get("suggested")

        # Del conjunto de capítulos, no del primero: ya no tienen por qué
        # coincidir en todo (ver _aggregate_pack_fields).
        pack_fields = _aggregate_pack_fields(episode_entries, conn)
        season_pack_title = _build_season_pack_title(
            title=series_title,
            year=year,
            season_number=season.get("season_number"),
            release_tag=release_tag,
            provider=provider,
            **pack_fields,
        )

        # Rename-in-place: the episodes' own shared folder IS the pack folder,
        # nothing gets copied anywhere.
        pack_folder = common_dir

        episodes_out = []
        for entry in episode_entries:
            ep = entry["episode"]
            proposal = entry["proposal"]
            raw_source_path = ep.get("path")
            source_path = local_paths.get(ep["id"]) or raw_source_path
            proposed_filename = proposal.get("proposed_filename") or ep.get("title") or f"episode-{ep['id']}"
            ext = ""
            if source_path and os.path.isfile(source_path):
                ext = os.path.splitext(source_path)[1]
            destination_path = os.path.join(pack_folder, proposed_filename + ext)
            # Same raw dirname as the original (Radarr/Sonarr-reported) path —
            # what library_items.path should be updated to after the in-place
            # rename, mirroring nomenclature.py's raw_destination_path
            # convention for a single file, so future path-mapping stays
            # consistent.
            raw_destination_path = (
                os.path.join(os.path.dirname(raw_source_path), proposed_filename + ext)
                if raw_source_path else None
            )
            episodes_out.append({
                "episode_id": ep["id"],
                "title": ep.get("title"),
                "episode_number": ep.get("episode_number"),
                "source_path": source_path,
                "raw_source_path": raw_source_path,
                "raw_destination_path": raw_destination_path,
                "destination_path": destination_path,
                "proposed_filename": proposed_filename,
            })

        status = "blocked" if errors else "valid"

        return {
            "status": status,
            "errors": errors,
            "warnings": [],
            "season_pack_title": season_pack_title,
            "pack_folder": pack_folder,
            "episodes": episodes_out,
            # Used internally to build the upload_jobs row's Uploadrr command
            # once queued for real (upload_queue.py's season branch), AND
            # part of the public schema now — the wizard's live title-preview
            # call needs it (a season opened from its series' own ficha has
            # no season_number on the wizard's `item` prop, only the plan has it).
            "season_number": season.get("season_number"),
            # Del conjunto, no del primer capítulo: es lo que se usó para
            # construir el título y lo que la vista previa del asistente
            # reutiliza al editar Source/Proveedor/Tag.
            "resolution": pack_fields.get("resolution"),
            "source": pack_fields.get("source"),
            "tmdb_id": (series or {}).get("tmdb_id"),
            "provider": provider,
            # Rest of the field breakdown used to build season_pack_title,
            # kept on the return dict so a caller (upload_queue.py) can
            # snapshot the full nomenclature breakdown for the job detail
            # page, not just the pieces build_season_pack_plan itself needs.
            "video_codec": pack_fields.get("video_codec"),
            "audio_summary": pack_fields.get("audio_summary"),
            "subtitle_summary": pack_fields.get("subtitle_summary"),
            "custom": pack_fields.get("custom", False),
            "release_tag": release_tag,
            "series_title": series_title,
            "title_options": _season_title_options(series, season, conn),
            "year": year,
            "source_comparison": source_comparison,
        }
    except SeasonPlanCancelled:
        # Not an error: the user closed the wizard, so there is nothing to
        # report and nothing was written (this function never touches disk).
        # The endpoint turns this into a 499-style "cancelled" answer.
        return {
            "status": "cancelled", "errors": [], "warnings": [],
            "season_pack_title": None, "pack_folder": None, "episodes": [],
        }
    finally:
        _clear_season_plan_cancel(season_id)
        if own:
            conn.close()


def _sanitize_pack_folder_name(name: str) -> str:
    """A season_pack_title is built from free-text metadata (title, tag...)
    and is safe to use as a torrent/release name, but not blindly as a
    filesystem folder name — strip path separators and trim the whitespace/
    dots some filesystems reject at the edges of a name."""
    return name.replace("/", " ").replace("\\", " ").strip(" .")


def _build_safe_folder_rename_plan(source_dir: str, destination_dir: str) -> dict[str, Any]:
    """Validate an in-place rename of the season's shared folder itself (same
    parent directory, no move) — same safety posture as
    filesystem_apply.build_safe_rename_plan, but for the enclosing directory
    instead of a file inside it. Never touches the filesystem."""
    errors: list[str] = []
    src_exists = os.path.exists(source_dir) if source_dir else False
    if not source_dir:
        errors.append("Carpeta de origen no proporcionada.")
    elif not src_exists:
        errors.append(f"La carpeta de la temporada no existe: {source_dir}")
    elif os.path.islink(source_dir):
        errors.append("La carpeta de la temporada es un symlink. No se permite renombrarla.")
    elif not os.path.isdir(source_dir):
        errors.append(f"El origen no es una carpeta: {source_dir}")

    if not destination_dir:
        errors.append("Carpeta de destino no proporcionada.")
    elif src_exists:
        if os.path.dirname(os.path.abspath(destination_dir)) != os.path.dirname(os.path.abspath(source_dir)):
            errors.append("El destino debe estar en la misma carpeta padre que el origen.")
        elif os.path.abspath(destination_dir) != os.path.abspath(source_dir) and os.path.exists(destination_dir):
            errors.append(f"El destino ya existe: {destination_dir}.")
        if not os.access(os.path.dirname(source_dir) or ".", os.W_OK):
            errors.append(f"La carpeta padre no es escribible: {os.path.dirname(source_dir)}")

    status = "blocked" if errors else "ready"
    return {"status": status, "source_dir": source_dir, "destination_dir": destination_dir, "errors": errors}


def _apply_folder_rename(plan: dict[str, Any]) -> dict[str, Any]:
    """Execute the in-place folder rename planned by
    _build_safe_folder_rename_plan(). Only os.rename is allowed."""
    result = dict(plan)
    src, dst = plan.get("source_dir"), plan.get("destination_dir")
    if os.path.abspath(src) == os.path.abspath(dst):
        result["status"] = "applied"
        result["message"] = "La carpeta ya tenía el nombre correcto."
        return result
    if plan["status"] == "blocked":
        result["message"] = "Plan bloqueado. Ver errors para más detalles."
        return result
    try:
        os.rename(src, dst)
        result["status"] = "applied"
        result["message"] = f"Carpeta renombrada correctamente: '{dst}'."
    except OSError as exc:
        result["status"] = "failed"
        result["errors"] = list(plan.get("errors", [])) + [f"Error de sistema: {exc}"]
        result["message"] = f"Falló el renombrado de la carpeta: {exc}"
    return result


def apply_season_pack(
    season_id: int, conn, *, job_id: int | None = None,
    source_override: str | None = None, provider_override: str | None = None,
    tag_override: str | None = None, title_override: str | None = None,
) -> dict[str, Any]:
    """Rename every available episode in place to its final pack filename AND
    record each episode's prepared_path on its own library_items row —
    mirrors what nomenclature.py::apply_nomenclature_proposal does for a
    single file right after its own apply_rename_plan() call. Without this
    UPDATE, mkv_remux._get_target_path (which reads library_items.
    prepared_path) can't find the file at its new path, and the remux step
    that runs right after this one in upload_queue.py would either touch the
    original source file (breaks the never-touch-the-original contract) or
    fail to find anything to remux.

    No confirmation-token gate here — the caller (upload_queue.py) already
    gates the whole prep sequence once, same as it does for a single file's
    apply_nomenclature_proposal call.

    `source_override`/`provider_override`/`tag_override`/`title_override`: the
    job's stored field overrides (upload_jobs.season_overrides_json), if the
    user edited Título/Source/Proveedor/Tag by hand in the wizard — previously
    this function silently ignored them and recomputed everything from scratch,
    so a chosen override never actually reached the real renamed files."""
    plan = build_season_pack_plan(
        season_id, conn=conn,
        source_override=source_override, provider_override=provider_override,
        tag_override=tag_override, title_override=title_override,
    )
    if plan["status"] != "valid":
        return {
            "status": "blocked", "errors": plan["errors"], "episodes": [],
            "pack_folder": plan.get("pack_folder"),
            "season_pack_title": plan.get("season_pack_title"),
        }

    now = datetime.now(timezone.utc).isoformat()
    episode_results = []
    any_failed = False
    total = len(plan["episodes"])
    for idx, ep in enumerate(plan["episodes"]):
        if job_id is not None:
            from .upload_execution import append_upload_log
            append_upload_log(
                job_id, "info",
                f"Aplicando nomenclatura: capítulo {ep.get('episode_number')} ({idx + 1}/{total})…",
                stream="system", conn=conn,
            )
        file_plan = build_safe_rename_plan(ep["source_path"] or "", ep["destination_path"])
        result = apply_rename_plan(file_plan, dry_run=False)
        episode_results.append({
            "episode_id": ep["episode_id"],
            "title": ep["title"],
            "destination_path": ep["destination_path"],
            "status": result["status"],
            "message": result.get("message"),
            "errors": result.get("errors", []),
        })
        if result["status"] == "applied":
            # The original file was moved (renamed in place) — `path` must
            # follow it too (raw convention), same as nomenclature.py's
            # single-file rename branch.
            raw_dst = ep.get("raw_destination_path") or ep["destination_path"]
            conn.execute(
                "UPDATE library_items SET path = ?, prepared_path = ?, "
                "nomenclature_applied_at = ?, nomenclature_status = 'Correcta' WHERE id = ?",
                (raw_dst, ep["destination_path"], now, ep["episode_id"]),
            )
        else:
            any_failed = True
    conn.commit()

    # Only once every file inside is safely renamed: rename the shared
    # folder itself (Sonarr's own "Season N" folder) to match the pack's own
    # release title. Deliberately the LAST step, not the first — if any file
    # above failed, the folder is left exactly as it was (no orphaned
    # episodes pointing at a folder name that no longer exists on a retry),
    # and if the folder rename itself fails, every file is still exactly
    # where library_items already says it is. Without this, the folder
    # handed to Uploadrr-EMU as prepared_path stays named "Season N", and
    # since torf.Torrent() defaults its torrent name to
    # os.path.basename(path), that's literally what qBittorrent shows
    # instead of the real release name (2026-07-28: Los Tudor S02 torrent
    # named "Season 2" while eMuwarez itself got the correct name via -mt,
    # which only overrides the tracker's displayed title, never the
    # torrent's own name). A single movie/episode never hits this: its
    # prepared_path is already the renamed FILE, whose basename is the
    # release name by construction — only a season pack hands Uploadrr-EMU
    # a directory.
    old_pack_folder = plan["pack_folder"]
    pack_folder = old_pack_folder
    folder_rename_errors: list[str] = []
    if not any_failed:
        target_folder_name = _sanitize_pack_folder_name(plan["season_pack_title"])
        new_pack_folder = os.path.join(os.path.dirname(old_pack_folder), target_folder_name)
        if os.path.abspath(new_pack_folder) != os.path.abspath(old_pack_folder):
            folder_plan = _build_safe_folder_rename_plan(old_pack_folder, new_pack_folder)
            folder_result = _apply_folder_rename(folder_plan)
            if folder_result["status"] != "applied":
                any_failed = True
                folder_rename_errors = folder_result.get("errors") or [
                    folder_result.get("message") or "No se pudo renombrar la carpeta de la temporada."
                ]
            else:
                pack_folder = new_pack_folder
                if job_id is not None:
                    from .upload_execution import append_upload_log
                    append_upload_log(
                        job_id, "info",
                        f"Carpeta de la temporada renombrada a «{target_folder_name}»…",
                        stream="system", conn=conn,
                    )
                # Every episode's file already lives under the new folder
                # (the directory move carried them along with their already-
                # final basenames) — just repoint library_items to match,
                # same raw/local path-mapping convention as the per-file
                # rename above (path_mapping.resolve_local_path only ever
                # rewrites a leading prefix, so the raw path shares the same
                # leaf folder name as the local one).
                for ep in plan["episodes"]:
                    new_prepared = os.path.join(pack_folder, os.path.relpath(ep["destination_path"], old_pack_folder))
                    raw_dst = ep.get("raw_destination_path") or ep["destination_path"]
                    raw_old_dir = os.path.dirname(raw_dst)
                    raw_new_dir = os.path.join(os.path.dirname(raw_old_dir), target_folder_name)
                    new_raw = os.path.join(raw_new_dir, os.path.basename(raw_dst))
                    conn.execute(
                        "UPDATE library_items SET path = ?, prepared_path = ? WHERE id = ?",
                        (new_raw, new_prepared, ep["episode_id"]),
                    )
                conn.commit()

    generic_errors = folder_rename_errors or (
        ["Algunos episodios fallaron al renombrar. Ver episodes."] if any_failed else []
    )
    return {
        "status": "failed" if any_failed else "applied",
        "errors": generic_errors,
        "episodes": episode_results,
        "pack_folder": pack_folder,
        "season_pack_title": plan.get("season_pack_title"),
        # Full field breakdown, for the job detail page's nomenclature
        # snapshot — mirrors what apply_nomenclature_proposal()'s "proposal"
        # already carries for a single file.
        "series_title": plan.get("series_title"),
        "year": plan.get("year"),
        "season_number": plan.get("season_number"),
        "tmdb_id": plan.get("tmdb_id"),
        "resolution": plan.get("resolution"),
        "source": plan.get("source"),
        "provider": plan.get("provider"),
        "video_codec": plan.get("video_codec"),
        "audio_summary": plan.get("audio_summary"),
        "subtitle_summary": plan.get("subtitle_summary"),
        "release_tag": plan.get("release_tag"),
    }


def _episode_display_title(conn, ep: dict) -> str:
    """"Serie (Año) - SxxEyy - Título del capítulo" — the exact same
    canonical format Biblioteca/Subidas/Peticiones already use
    (library.py's content_display_title), plus the episode's own title
    (episode_own_name). Backs the wizard's per-episode "Ver MediaInfo"/
    "Ver Remux" accordion headers, which previously showed the raw stored
    title verbatim ("Serie SxxEyy - Título"), inconsistent with this format
    used everywhere else."""
    from .library import content_display_title, episode_own_name
    base = content_display_title(conn, ep, scope="episode")
    own_name = episode_own_name(ep)
    return f"{base} - {own_name}" if own_name else base


def get_season_episode_names(
    season_id: int, conn=None,
    source_override: str | None = None, provider_override: str | None = None,
    tag_override: str | None = None,
) -> dict:
    """Per-episode final torrent name + internal MKV title — backs the
    wizard's "Ver nombre de todos los capítulos" button (a season pack has
    no single "título del archivo interno", each episode file has its own).

    `source_override`/`provider_override`/`tag_override` — the season's own
    Source/Proveedor/Tag fields, if the user edited them by hand — applied
    uniformly to every episode, same as build_season_pack_plan(). Without
    this, each episode kept showing its own auto-detected values even after
    overriding the season pack's title, so they visibly disagreed."""
    own = conn is None
    conn = conn or connect()
    try:
        from .source_assistant import build_editable_nomenclature_fields

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available = [e for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
        out = []
        for ep in available:
            fields = build_editable_nomenclature_fields(
                ep["id"], conn=conn,
                source_override=source_override, provider_override=provider_override,
                tag_override=tag_override,
            )
            blocked = bool(fields.get("blocked"))
            out.append({
                "episode_id": ep["id"],
                "episode_number": ep.get("episode_number"),
                "title": ep.get("title"),
                # Mismo título que las cabeceras de "Ver MediaInfo"/"Ver
                # Remux": "Serie (Año) - SxxEyy - Título del capítulo".
                "display_title": _episode_display_title(conn, ep),
                "torrent_name": None if blocked else fields.get("torrent_name"),
                "internal_mkv_title": None if blocked else fields.get("internal_mkv_title"),
                "error": fields.get("error") if blocked else None,
            })
        return {"episodes": out}
    finally:
        if own:
            conn.close()


def get_season_episode_mediainfo(season_id: int, conn=None) -> dict:
    """Per-episode MediaInfo report — backs the wizard's "Ver MediaInfo"
    dropdown for a season target."""
    own = conn is None
    conn = conn or connect()
    try:
        from .media_info_service import build_mediainfo_report
        from .path_mapping import resolve_local_path
        from .source_assistant import build_editable_nomenclature_fields

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available = [e for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
        out = []
        # Name vs Radarr/Sonarr vs MediaInfo-bitrate cross-check (the
        # "Internal Source Tool" blinking link movies get) — computed ONCE,
        # from the first available episode, and reused for every episode
        # below. A season pack can only ever reach this screen when every
        # episode already agrees on source (build_season_pack_plan's
        # consistency check blocks the upload otherwise), so recomputing
        # this per episode would be redundant and re-run the engine's
        # (potentially slow) analysis needlessly.
        source_comparison = None
        if available:
            source_comparison = build_editable_nomenclature_fields(
                available[0]["id"], conn=conn,
            ).get("source_comparison")
        for ep in available:
            # Prefer prepared_path over the raw path — same convention
            # nomenclature.py/mkv_remux.py/mkv_title.py already follow: once
            # nomenclature has been applied before (e.g. a prior retry),
            # `path` may be stale (still the pre-rename name) while
            # prepared_path is the real current file. Reading raw `path`
            # here showed a stale Source (e.g. "WEBRIP" from the original
            # name) that disagreed with the actually-applied name (e.g.
            # "BluRay", from prepared_path) shown everywhere else.
            candidate_path = ep.get("prepared_path") or ep.get("path")
            local_path = resolve_local_path(candidate_path, conn=conn) or candidate_path
            # radarr_source: without it, the Source row's "eMuwarez" column
            # skips straight from "nombre del archivo" to the bitrate tool's
            # own estimate, silently disagreeing with the actually-applied
            # nomenclature (nomenclature.py::_infer_source_from_item, which
            # DOES fall back to Radarr/Sonarr before the bitrate tool) —
            # confirmed with real data (Los Tudor S02, 2026-07-30): showed
            # "WEBRip" here while the real season title said "BluRay".
            report = build_mediainfo_report(local_path or "", radarr_source=ep.get("source"))
            out.append({
                "episode_id": ep["id"],
                "episode_number": ep.get("episode_number"),
                "title": ep.get("title"),
                "display_title": _episode_display_title(conn, ep),
                "report": report,
                "source_comparison": source_comparison,
            })
        return {"episodes": out}
    finally:
        if own:
            conn.close()


def get_season_episode_remux_previews(season_id: int, conn=None) -> dict:
    """Per-episode track remux plan — backs the wizard's "Ver Remux"
    dropdown for a season target. Read-only preview only: manual per-track
    overrides aren't offered for season packs (each episode gets its own
    auto-computed plan applied as-is during the queued upload)."""
    own = conn is None
    conn = conn or connect()
    try:
        from .mkv_remux import build_remux_plan

        all_episodes = _get_season_episodes(season_id, conn=conn)
        available = [e for e in all_episodes if e.get("local_status") == LocalStatus.AVAILABLE.value]
        out = []
        for ep in available:
            plan = build_remux_plan(ep["id"], conn=conn)
            out.append({
                "episode_id": ep["id"],
                "episode_number": ep.get("episode_number"),
                "title": ep.get("title"),
                "display_title": _episode_display_title(conn, ep),
                "plan": plan,
            })
        return {"episodes": out}
    finally:
        if own:
            conn.close()
