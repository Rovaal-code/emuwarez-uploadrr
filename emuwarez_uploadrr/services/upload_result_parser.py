"""Parse and classify Uploadrr stdout/stderr output.

Safety rules:
- Never invent URLs or torrent IDs not explicitly present in the text.
- Never expose secrets. Callers must redact before passing text.
- Does not write to DB; pure functions only.
"""
from __future__ import annotations

import re

URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+")

TORRENT_ID_PATTERNS = [
    re.compile(r"\btorrent[_\s]?id[:\s=]+(\d+)", re.IGNORECASE),
    re.compile(r"\buploaded[_\s]?id[:\s=]+(\d+)", re.IGNORECASE),
    re.compile(r"\bid[:\s=]+(\d{4,})", re.IGNORECASE),
]


def extract_urls(text: str) -> list[str]:
    """Extract http/https URLs from text. Does not invent data."""
    if not text:
        return []
    found = URL_PATTERN.findall(text)
    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for url in found:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def extract_possible_torrent_ids(text: str) -> list[str]:
    """Extract torrent/upload IDs only when an explicit pattern is present. Never invents."""
    if not text:
        return []
    ids: list[str] = []
    for pattern in TORRENT_ID_PATTERNS:
        for m in pattern.finditer(text):
            ids.append(m.group(1))
    seen: set[str] = set()
    result = []
    for id_ in ids:
        if id_ not in seen:
            seen.add(id_)
            result.append(id_)
    return result


def build_error_summary(stderr: str, stdout: str, exit_code: int | None) -> str | None:
    """Build a human-readable error summary from stderr/stdout. Redacted text expected by caller."""
    lines: list[str] = []
    if stderr:
        nonempty = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
        lines.extend(nonempty[-3:])
    if not lines and stdout:
        nonempty = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        lines.extend(nonempty[-2:])
    if exit_code is not None and exit_code != 0:
        lines.append(f"Exit code: {exit_code}")
    return "\n".join(lines) if lines else None


SEASON_PACK_PATTERN = re.compile(r"^Incomplete season pack: season (\d+|\?)(?:, missing episodes ([\d, ]+))?", re.MULTILINE)


def season_pack_warning(text: str) -> str | None:
    """Aviso en castellano si Uploadrr-EMU (mkbrr) vio un pack de temporada incompleto; None si no."""
    m = SEASON_PACK_PATTERN.search(text or "")
    if not m:
        return None
    aviso = f"Pack de temporada posiblemente incompleto (temporada {m.group(1)})"
    episodios = [e.strip() for e in (m.group(2) or "").split(",") if e.strip()]
    if len(episodios) == 1:
        aviso += f": falta el episodio {episodios[0]}"
    elif episodios:
        aviso += f": faltan los episodios {', '.join(episodios[:-1])} y {episodios[-1]}"
    return aviso + "."


def classify_upload_result(
    stdout: str,
    stderr: str,
    exit_code: int | None,
) -> dict:
    """Classify the result of an Uploadrr run.

    Returns:
        status: "completed" | "failed"
        urls: list[str]
        torrent_ids: list[str]
        error_summary: str | None
        exit_code: int | None
        season_pack_warning: str | None
    """
    combined = (stdout or "") + "\n" + (stderr or "")
    urls = extract_urls(combined)
    torrent_ids = extract_possible_torrent_ids(combined)

    if exit_code == 0:
        status = "completed"
        error_summary = None
    else:
        status = "failed"
        error_summary = build_error_summary(stderr or "", stdout or "", exit_code)

    return {
        "status": status,
        "urls": urls,
        "torrent_ids": torrent_ids,
        "error_summary": error_summary,
        "exit_code": exit_code,
        "season_pack_warning": season_pack_warning(stdout or ""),
    }


def parse_uploadrr_output(text: str) -> dict:
    """Parse full Uploadrr output text.

    Returns dict with urls and torrent_ids detected.
    """
    return {
        "urls": extract_urls(text),
        "torrent_ids": extract_possible_torrent_ids(text),
    }


__all__ = [
    "extract_urls",
    "extract_possible_torrent_ids",
    "build_error_summary",
    "classify_upload_result",
    "parse_uploadrr_output",
    "season_pack_warning",
]
