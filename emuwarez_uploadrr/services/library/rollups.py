"""Agregación de una temporada o serie a partir de sus hijos (estado, nomenclatura, ruta, calidad, tamaño)."""
from __future__ import annotations

import json
import os
from typing import Optional

from ...models import LocalStatus
from ..source_assistant import EMU_PROVIDERS



_ROLLUP_EMPTY = {
    "provider": None, "resolution": None, "source": None, "release_group": None, "video_codec": None,
    "audio_codec": None, "audio_languages": None, "subtitle_languages": None, "release_groups": None,
}


def grupos_de_release(rows: list) -> list[str]:
    """Los grupos de release distintos de unos capítulos, sin los que no tienen."""
    return sorted({r["release_group"] for r in rows if r["release_group"]}, key=str.casefold)


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
        from ..nomenclature import infer_provider_from_item
        providers.add(infer_provider_from_item({"path": r["path"], "source": r["source"]}))
        if len(providers) > 1:
            break
    return {
        "provider": next(iter(providers)) if len(providers) == 1 else None,
        "resolution": uniq("resolution"),
        "source": uniq("source"),
        "release_group": uniq("release_group"),
        "release_groups": grupos_de_release(rows),
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

    from ..nomenclature import infer_provider_from_item

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
        "release_groups": grupos_de_release(rows),
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
