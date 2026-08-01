"""Authoritative nomenclature check against the eMuwarez guide, using MediaInfo.

Radarr/Sonarr only expose a *summary* mediaInfo (one audio codec/channels, not
per-track), so the exact eMuwarez name — which needs the per-track audio —
can only be built by reading MediaInfo from the actual file. This module:

  1. reads MediaInfo (legacy.read_media_info),
  2. builds the expected file name (build_emu_title → to_filesystem_name),
  3. compares it to the real file name, ignoring the group after the last '-',
  4. yields 'Correcta' / 'No adaptada' + a per-token diff for the UI.

States: 'No comprobada' (default, MediaInfo not run) · 'No adaptada' (checked,
does not comply) · 'Correcta' (checked, complies) · 'N/A' (no file).
Only DISPONIBLE + 'No comprobada' items are checked (unless force=True); the
sync resets a checked item back to 'No comprobada' when its file changes.
"""
from __future__ import annotations

import os
from typing import Optional

from .mkv_title import to_filesystem_name

STATUS_UNCHECKED = "No comprobada"
STATUS_CORRECT = "Correcta"
STATUS_NOT_ADAPTED = "No adaptada"
STATUS_NA = "N/A"

# Local statuses that mean the file is on disk (i.e. checkable).
_AVAILABLE = {"Disponible", "Subido", "Subiendo"}


def _strip_group(core_dotted: str) -> str:
    """Remove the trailing '-GROUP' (uploader), which is optional.

    The group is always the tail of the LAST dot-segment (e.g. '5.1-GRUPO' →
    last segment '1-GRUPO'). Splitting only inside that last segment keeps
    mid-name compounds like 'WEB-DL' / 'DTS-HD' intact even when there is no
    group at all."""
    parts = core_dotted.split(".")
    if parts and "-" in parts[-1]:
        parts[-1] = parts[-1].rsplit("-", 1)[0]
        if not parts[-1]:
            parts = parts[:-1]
    return ".".join(parts)


_RES_RE = None


def _provider_codes() -> set[str]:
    from .source_assistant import EMU_PROVIDERS
    return {p["code"].lower() for p in EMU_PROVIDERS}


def _drop_optional_provider(tokens: list[str]) -> list[str]:
    """Provider is optional and sits right after the resolution (e.g.
    '1080p AMZN WEB-DL'). Drop it so a name with or without provider both match
    the expected (which is built without one)."""
    import re
    codes = _provider_codes()
    out = list(tokens)
    for i, t in enumerate(out):
        if re.fullmatch(r"(4320p|2160p|1080p|1080i|720p|576p|540p|480p)", t, re.I):
            if i + 1 < len(out) and out[i + 1].lower() in codes:
                del out[i + 1]
            break
    return out


def expected_core(title: str, year, media, season=None, episode=None) -> str:
    """Expected file-name core (dotted, accent-free, without the group tag)."""
    from .emu_title import build_emu_title
    torrent = build_emu_title(title or "", str(year) if year else "", media,
                              tag="EMUWAREZ", season=season, episode=episode)
    return _strip_group(to_filesystem_name(torrent))


def compare(actual_filename: str, exp_core: str) -> tuple[bool, list[str]]:
    """(matches, diff). The real file complies if its cleaned core (group and
    optional provider aside) equals the expected core, token by token,
    case-insensitively."""
    base = os.path.splitext(actual_filename)[0]
    actual_core = _strip_group(to_filesystem_name(base))
    # Provider is optional (before the source) — ignore it on BOTH sides so it
    # never drives the verdict, whether or not each name carries it.
    at = _drop_optional_provider([t for t in actual_core.split(".") if t])
    et = _drop_optional_provider([t for t in exp_core.split(".") if t])
    if [t.lower() for t in at] == [t.lower() for t in et]:
        return True, []
    diff: list[str] = []
    for i in range(max(len(at), len(et))):
        av = at[i] if i < len(at) else "—"
        ev = et[i] if i < len(et) else "—"
        if av.lower() != ev.lower():
            diff.append(f"'{av}' ≠ esperado '{ev}'")
    return False, diff or ["El nombre no coincide con el esperado"]


# --- DB-facing service ------------------------------------------------------

def _leaf_episodes(conn, item_id: int, item_type: str) -> list[dict]:
    """Real files under a rollup (a season's episodes, a series' episodes)."""
    if item_type == "movie":
        return [dict(r) for r in conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,))]
    if item_type == "episode":
        return [dict(r) for r in conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,))]
    if item_type == "season":
        return [dict(r) for r in conn.execute(
            "SELECT * FROM library_items WHERE parent_id = ? AND item_type = 'episode'", (item_id,))]
    if item_type == "series":
        return [dict(r) for r in conn.execute(
            "SELECT e.* FROM library_items e JOIN library_items se ON e.parent_id = se.id "
            "WHERE se.parent_id = ? AND e.item_type = 'episode'", (item_id,))]
    return []


def _is_available(item: dict) -> bool:
    return (item.get("local_status") or "") in _AVAILABLE and bool(item.get("path"))


def count_pending(conn, item_id: int, item_type: str) -> tuple[int, int, int]:
    """(pending, available_total, seasons) for the confirmation message.
    pending = available files still 'No comprobada'."""
    eps = _leaf_episodes(conn, item_id, item_type)
    avail = [e for e in eps if _is_available(e)]
    pending = sum(1 for e in avail if (e.get("nomenclature_status") or STATUS_UNCHECKED) == STATUS_UNCHECKED)
    seasons = 0
    if item_type == "series":
        seasons = conn.execute(
            "SELECT COUNT(*) FROM library_items WHERE parent_id = ? AND item_type = 'season'", (item_id,)
        ).fetchone()[0]
    return pending, len(avail), seasons


def _store_result(conn, item_id: int, status: str, expected: Optional[str]) -> None:
    conn.execute(
        "UPDATE library_items SET nomenclature_status = ?, nomenclature_expected = ?, "
        "nomenclature_checked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, expected, item_id),
    )


def check_one(conn, item: dict) -> dict:
    """Evaluate a single leaf item (movie/episode) and persist. Returns the
    result dict. Skips (returns status) non-available items."""
    if not _is_available(item):
        return {"id": item["id"], "status": item.get("nomenclature_status") or STATUS_NA, "skipped": True}
    season = item.get("season_number")
    episode = item.get("episode_number")
    res = evaluate_file(item["path"], item["title"], item.get("year"),
                        season=season if item["item_type"] == "episode" else None,
                        episode=episode if item["item_type"] == "episode" else None)
    _store_result(conn, item["id"], res["status"], res.get("expected"))
    res["id"] = item["id"]
    return res


def check_item(conn, item_id: int, *, force: bool = False) -> dict:
    """Check a leaf, a season (all its episodes) or a series (all episodes).
    Only 'No comprobada' available files are checked unless force=True.

    Returns {attempted, evaluated, correct, not_adapted, errors, error_detail,
    results}. A file whose MediaInfo can't be read (not accessible, no
    `mediainfo` binary) is counted as an *error*, NOT as evaluated — its status
    stays 'No comprobada' so it isn't wrongly marked 'No adaptada'."""
    row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return {"error": "not found"}
    item = dict(row)
    eps = _leaf_episodes(conn, item_id, item["item_type"])
    targets = [e for e in eps if _is_available(e) and
               (force or (e.get("nomenclature_status") or STATUS_UNCHECKED) == STATUS_UNCHECKED)]
    results, correct, not_adapted, errors = [], 0, 0, 0
    error_detail = None
    for e in targets:
        try:
            r = check_one(conn, e)
        except Exception as exc:  # MediaInfo unreadable, etc. — leave unchecked
            r = {"id": e["id"], "status": STATUS_UNCHECKED, "error": str(exc)}
        results.append(r)
        if r.get("status") == STATUS_CORRECT:
            correct += 1
        elif r.get("status") == STATUS_NOT_ADAPTED:
            not_adapted += 1
        if r.get("error"):
            errors += 1
            error_detail = error_detail or r["error"]
    conn.commit()
    return {
        "attempted": len(targets),
        "evaluated": correct + not_adapted,
        "correct": correct,
        "not_adapted": not_adapted,
        "errors": errors,
        "error_detail": error_detail,
        "results": results,
    }


def evaluate_file(path: str, title: str, year, *, season=None, episode=None) -> dict:
    """Read MediaInfo of `path` and return the verdict.
    {status, expected, actual, diff}. Requires the file + `mediainfo` binary."""
    from pathlib import Path
    # media_probe y no legacy: la de legacy PREGUNTA por teclado cuando no
    # reconoce el idioma de una pista, y esto corre dentro de una petición.
    from .media_probe import read_media_info
    from .path_mapping import resolve_local_path
    path = resolve_local_path(path)
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"El archivo no existe o no es accesible: {path or '(sin ruta)'}")
    media = read_media_info(Path(path))
    if media is None:
        raise RuntimeError("MediaInfo no devolvió datos (¿está instalado el binario 'mediainfo'?)")
    # If the file name already carries a streaming provider (AMZN/NF/DSNP…) in a
    # WEB-DL, include it in the expected name (provider goes before the source).
    # It's optional, so `compare` ignores it on both sides — this just makes the
    # shown expected match the real name.
    if (media.source or "").upper().startswith("WEB-DL"):
        from .nomenclature import infer_provider_from_item
        prov = infer_provider_from_item({"path": path})
        if prov:
            media.source = f"{prov} {media.source}"
    exp = expected_core(title, year, media, season=season, episode=episode)
    matches, diff = compare(os.path.basename(path), exp)
    return {
        "status": STATUS_CORRECT if matches else STATUS_NOT_ADAPTED,
        "expected": exp,
        "actual": to_filesystem_name(os.path.splitext(os.path.basename(path))[0]),
        "diff": diff,
    }
