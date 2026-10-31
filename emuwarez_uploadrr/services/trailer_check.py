"""Post-upload trailer check.

Uploadrr-EMU writes its own `[EMU]DESCRIPTION.txt` under its `tmp/` dir right
before uploading, and — confirmed by reading Uploadrr-EMU's own source
(src/trackers/UNIT3D.py) — that exact file is read back verbatim and sent as
the torrent's real description to eMuwarez. So finding a `[youtube]KEY
[/youtube]` tag in it means the trailer really is on the eMuwarez page, not
just a guess.

This is a best-effort, read-only convenience check — never blocks anything.
If the description file can't even be located, that's inconclusive (not a
"no trailer" result): Uploadrr's tmp folder naming isn't 100% predictable
from the outside, so this tries a couple of likely candidate names before
falling back to the most recently modified `[EMU]DESCRIPTION.txt` under
tmp/, same strategy the legacy CLI already used (legacy.py::
find_emu_description_file) when this only existed for the interactive path.
"""
from __future__ import annotations

import glob
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_YOUTUBE_RE = re.compile(r"\[youtube\]\s*([A-Za-z0-9_-]+)\s*\[/youtube\]", re.I)


def _instante(desde) -> Optional[float]:
    """`desde` (el started_at ISO del trabajo) como marca de tiempo; None si no hay."""
    if not desde:
        return None
    try:
        dt = datetime.fromisoformat(str(desde))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def find_emu_description_file(uploadrr_path: str, candidate_names: list[str],
                              desde=None) -> Optional[Path]:
    """Locate the [EMU]DESCRIPTION.txt Uploadrr-EMU generated for this
    upload. `candidate_names` are the tmp/ subfolder names most likely to
    match (the applied filename for a single file, the season-pack's own
    eMuwarez title for a pack) — checked first since they're exact and free;
    the mtime-sorted scan of the whole tmp/ tree is the fallback, and it only
    accepts a file written after `desde` (when the job started): otherwise it
    picked up the previous job's description and reported its trailer."""
    if not uploadrr_path:
        return None
    tmp_dir = Path(uploadrr_path) / "tmp"
    if not tmp_dir.exists():
        return None

    for name in candidate_names:
        if not name:
            continue
        exact = tmp_dir / name / "[EMU]DESCRIPTION.txt"
        if exact.exists():
            return exact

    try:
        # rglob() treats [...] as a glob character class, not literal
        # brackets — glob.escape() is needed or "[EMU]DESCRIPTION.txt"
        # would actually match e.g. "EDESCRIPTION.txt" (one char from
        # {E,U,M}) and never the real filename.
        candidates = sorted(
            tmp_dir.rglob(glob.escape("[EMU]DESCRIPTION.txt")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    limite = _instante(desde)
    if limite is None:
        return None
    try:
        candidates = [c for c in candidates if c.stat().st_mtime >= limite]
    except OSError:
        return None
    if not candidates:
        return None

    preferred = {n for n in candidate_names if n}
    for c in candidates:
        if c.parent.name in preferred:
            return c
    return candidates[0]


def extract_youtube_trailer_url(description_file: Path) -> Optional[str]:
    try:
        text = description_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = _YOUTUBE_RE.search(text)
    if not m:
        return None
    return f"https://www.youtube.com/watch?v={m.group(1)}"


def check_trailer_for_job(uploadrr_path: str, candidate_names: list[str], desde=None) -> dict:
    """{checked, found, url}. `checked=False` means the description file
    itself couldn't be located at all (inconclusive — say nothing rather
    than falsely claim "no trailer"). `checked=True, found=False` means the
    file WAS read but had no [youtube] tag — a real "not found"."""
    desc_file = find_emu_description_file(uploadrr_path, candidate_names, desde=desde)
    if not desc_file:
        return {"checked": False, "found": False, "url": None}
    url = extract_youtube_trailer_url(desc_file)
    return {"checked": True, "found": bool(url), "url": url}
