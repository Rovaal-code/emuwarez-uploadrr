"""Audio y subtítulos en castellano: qué hoja cuenta y cómo se resume en series y temporadas."""
from __future__ import annotations

import sqlite3
from typing import Optional

from ...models import LocalStatus

from .rollups import _specials_clause


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
    from ..emu_format import has_castellano

    if ignore_specials is None:
        from ...database import get_setting_canonical
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
