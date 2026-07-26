"""Real progress signals for an upload job's phases.

`parse_uploadrr_progress` is a literal port of the regex-based parser that
already lived in `legacy.py` (`parse_uploadrr_progress`, pre-service-layer
script) — it reads Uploadrr-EMU's own stdout/stderr fragments and identifies
exactly which of Uploadrr-EMU's own internal phases is running. That parser
was never carried over when the upload flow moved into `upload_execution.py`,
so the modern job detail view had no real progress at all until now.

Unlike legacy.py (which fed everything into a single CLI progress bar),
each of Uploadrr-EMU's internal phases gets its OWN row in PHASES below —
queue -> video processing -> MediaInfo export -> video metadata -> dupe
check -> screenshots generate -> screenshots upload -> hashing -> torrent
creation -> uploading to eMuwarez — plus this app's own pipeline stages
that run before Uploadrr-EMU is even invoked (integrity -> nomenclature ->
remux -> preflight). Each phase has a fixed weight based on typical
wall-clock duration, so a single job-wide percentage can be computed as
phases complete.
"""
from __future__ import annotations

import re
from typing import Optional

# (stage key, display label, weight-out-of-100). Order matters — the running
# sub-phases (everything after "verificacion_presubida") are also the
# sequence Uploadrr-EMU itself reports them in, used by
# advance_running_phase() to mark every earlier running sub-phase done once
# a later one is seen.
#
# Several rows here are a merge of what used to be multiple separate phases
# (see PHASE_KEY_ALIASES below) — "duplicates" was dropped as its own row
# (nothing else in the codebase branches on its result, it was purely a
# progress marker) and its weight folded into "metadata_processing", the
# group it chronologically sits inside.
PHASES: list[tuple[str, str, int]] = [
    ("verificacion_presubida", "Verificación pre-subida", 10),  # integrity(5) + preflight(5)
    ("nomenclature", "Aplicación de nomenclatura", 5),
    ("remux", "Reordenación de pistas", 15),
    ("queue_processing", "Inicio de Uploader", 2),
    ("metadata_processing", "Procesamiento de metadatos", 10),  # video_processing(2)+mediainfo_export(3)+video_metadata(2)+duplicates(3)
    ("screenshots", "Generación y subida de capturas", 20),  # screenshots_generate(10)+screenshots_upload(10)
    ("hash_torrent", "Cálculo de hash del torrent", 28),  # hashing(20)+torrent_create(8)
    ("uploading_emu", "Subida a eMuwarez", 7),
    ("qbittorrent_add", "Subida a qBittorrent", 3),
]

PHASE_ORDER = [key for key, _label, _weight in PHASES]
PHASE_LABELS = {key: label for key, label, _weight in PHASES}
PHASE_WEIGHTS = {key: weight for key, _label, weight in PHASES}

# The sub-phases Uploadrr-EMU's own subprocess output walks through, in
# order — everything parse_uploadrr_progress() can identify. These are RAW
# keys (one per regex trigger) — parse_uploadrr_progress() is unchanged and
# still reports at this granularity; PHASE_KEY_ALIASES below is what rolls
# several of them up into a single displayed PHASES row.
RUNNING_SUB_PHASE_ORDER = [
    "queue_processing", "video_processing", "mediainfo_export", "video_metadata",
    "duplicates", "screenshots_generate", "screenshots_upload", "hashing",
    "torrent_create", "uploading_emu", "qbittorrent_add",
]

# Raw sub-phase -> merged, displayed PHASES key. A raw key absent from this
# map displays as itself (queue_processing/uploading_emu/qbittorrent_add are
# not merged with anything).
PHASE_KEY_ALIASES: dict[str, str] = {
    "video_processing": "metadata_processing",
    "mediainfo_export": "metadata_processing",
    "video_metadata": "metadata_processing",
    "duplicates": "metadata_processing",
    "screenshots_generate": "screenshots",
    "screenshots_upload": "screenshots",
    "hashing": "hash_torrent",
    "torrent_create": "hash_torrent",
}

# Original per-raw-sub-phase weights (pre-merge) — used only to interpolate
# a merged phase's displayed 0-100 pct as its raw members fire in sequence;
# never rendered directly. Each merged group's members sum to exactly that
# group's own PHASE_WEIGHTS entry, so this interpolation never changes the
# job-wide global_pct total versus the old, unmerged phase list.
RAW_SUBPHASE_WEIGHTS: dict[str, int] = {
    "queue_processing": 2,
    "video_processing": 2,
    "mediainfo_export": 3,
    "video_metadata": 2,
    "duplicates": 3,
    "screenshots_generate": 10,
    "screenshots_upload": 10,
    "hashing": 20,
    "torrent_create": 8,
    "uploading_emu": 7,
    "qbittorrent_add": 3,
}

# Deduped, first-appearance order of DISPLAYED (merged) phase keys within
# the Uploadrr-EMU running window — what advance_running_phase() marks
# started/done against, instead of the raw per-trigger keys.
RUNNING_DISPLAY_ORDER: list[str] = []
for _raw_key in RUNNING_SUB_PHASE_ORDER:
    _display_key = PHASE_KEY_ALIASES.get(_raw_key, _raw_key)
    if _display_key not in RUNNING_DISPLAY_ORDER:
        RUNNING_DISPLAY_ORDER.append(_display_key)


def resolve_display_progress(raw_key: str, raw_pct: int) -> tuple[str, int]:
    """Map a raw Uploadrr-EMU sub-phase key + its own 0-100 pct to the
    merged, displayed phase key and an interpolated 0-100 pct within that
    merged phase.

    For an unmerged raw key this is a no-op passthrough. For a merged group
    (e.g. hashing+torrent_create), the group's first raw trigger starts the
    displayed phase near 0% and only the LAST raw member reaching 100%
    completes it — weighted by each raw member's own share of the group,
    so progress within the group still advances smoothly instead of
    jumping between fixed fractions.
    """
    display_key = PHASE_KEY_ALIASES.get(raw_key, raw_key)
    group = [k for k in RUNNING_SUB_PHASE_ORDER if PHASE_KEY_ALIASES.get(k, k) == display_key]
    if len(group) <= 1:
        return display_key, max(0, min(100, raw_pct))
    group_total = sum(RAW_SUBPHASE_WEIGHTS[k] for k in group)
    before = sum(RAW_SUBPHASE_WEIGHTS[k] for k in group[: group.index(raw_key)])
    this_weight = RAW_SUBPHASE_WEIGHTS[raw_key]
    display_pct = round(100 * (before + this_weight * (raw_pct / 100.0)) / group_total)
    return display_key, max(0, min(100, display_pct))


def _strip_ansi(text: str) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\x1b\][^\a]*(?:\a|\x1b\\)", "", text)
    return text.replace("\b", "")


def parse_uploadrr_progress(fragment: str) -> Optional[tuple[str, int, Optional[bool]]]:
    """Parse one line/fragment of Uploadrr-EMU's own output into
    (phase_key, pct_within_phase, ok_state) — phase_key is one of
    RUNNING_SUB_PHASE_ORDER, pct_within_phase is 0-100 within that phase only
    (not the job-wide percentage). Returns None if the fragment doesn't match
    any known Uploadrr-EMU output pattern."""
    clean = _strip_ansi(fragment)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return None

    if "Rejected Upload" in clean or "Validation Error" in clean or '"success":false' in clean:
        return "uploading_emu", 100, False
    if re.search(r"(?:Torrent uploaded successfully|Uploaded successfully|Upload complete|Upload completed)", clean, re.I):
        return "uploading_emu", 100, True

    if "Starting queue processing" in clean:
        return "queue_processing", 100, True
    if "Processing as video" in clean:
        return "video_processing", 100, None
    if "Exporting MediaInfo" in clean:
        return "mediainfo_export", 50, None
    if "MediaInfo JSON Exported" in clean or "MediaInfo text Exported" in clean:
        return "mediainfo_export", 100, True
    if "Processing video metadata" in clean:
        return "video_metadata", 100, None
    if "Searching for existing torrents" in clean:
        return "duplicates", 50, None
    if "No dupes found" in clean:
        return "duplicates", 100, True

    # Generación de capturas: con o sin paréntesis.
    m = re.search(r"\bGenerating\s+(?:screenshots|screens|images)\s*\(?\s*(\d+)\s*/\s*(\d+)\s*\)?", clean, re.I)
    if m:
        cur, total = int(m.group(1)), max(1, int(m.group(2)))
        pct = int((cur / total) * 100)
        return "screenshots_generate", pct, cur >= total

    if re.search(r"\bGenerating\s+(?:screenshots|screens|images)\b", clean, re.I):
        return "screenshots_generate", 0, None

    # Subida de capturas: con o sin paréntesis.
    m = re.search(r"\bUploading\s+(?:screenshots|screens|images)\s*\(?\s*(\d+)\s*/\s*(\d+)\s*\)?", clean, re.I)
    if m:
        cur, total = int(m.group(1)), max(1, int(m.group(2)))
        pct = int((cur / total) * 100)
        return "screenshots_upload", pct, cur >= total

    if re.search(r"\bUploading\s+(?:screenshots|screens|images)\b", clean, re.I):
        return "screenshots_upload", 0, None

    # Hash/generación del torrent.
    m = re.search(r"\bHashing(?:\s+with\s+[A-Za-z0-9_.-]+)?\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*%", clean, re.I)
    if m:
        hp = max(0.0, min(100.0, float(m.group(1))))
        return "hashing", int(hp), None

    m = re.search(r"\b(?:Creating|Generating|Building)\s+torrent\s*:?\s*([0-9]+(?:\.[0-9]+)?)?\s*%?", clean, re.I)
    if m:
        if m.group(1):
            hp = max(0.0, min(100.0, float(m.group(1))))
            return "torrent_create", int(hp), None
        return "torrent_create", 0, None

    if "Uploading to EMU" in clean:
        return "uploading_emu", 0, None

    # Only reached once the eMuwarez upload itself succeeded (src/utils/
    # upload.py only calls client.add_to_client() after tracker_instance.
    # upload() returns True) — see src/clients.py::_add_to_qbittorrent.
    if "Adding and rechecking torrent" in clean:
        return "qbittorrent_add", 0, None
    if re.match(r"^Added to:", clean):
        return "qbittorrent_add", 100, True
    return None


def parse_mkvmerge_gui_progress(fragment: str) -> Optional[int]:
    """Parse an mkvmerge `--gui-mode` line (`#GUI#progress 42%`) into a 0-100
    int, or None if the fragment isn't a progress line."""
    m = re.search(r"#GUI#progress\s+(\d+)%", fragment)
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


def build_phase_state(
    completed: list[str],
    current: Optional[str] = None,
    current_pct: int = 0,
) -> dict:
    """Build the `{"phases": [...], "global_pct": N}` dict persisted to
    `upload_jobs.progress_json`.

    `completed` — stage keys that have fully finished (counted as 100%).
    `current` — the stage key in progress right now (if any), whose
    percentage is `current_pct` (0-100, within that phase only).
    Any stage not in `completed` and not `current` is pending (0%).
    """
    phases = []
    global_pct = 0.0
    for key, label, weight in PHASES:
        if key in completed:
            pct = 100
            status = "done"
        elif key == current:
            pct = max(0, min(100, current_pct))
            status = "running" if pct < 100 else "done"
        else:
            pct = 0
            status = "pending"
        phases.append({"key": key, "label": label, "status": status, "pct": pct})
        global_pct += weight * (pct / 100.0)

    return {"phases": phases, "global_pct": int(round(global_pct))}


def with_phase_timestamps(
    state: dict,
    previous_phases: Optional[list[dict]],
    now: Optional[str] = None,
) -> dict:
    """Stamp each phase in `state["phases"]` (from build_phase_state) with
    started_at/finished_at, carrying forward whatever `previous_phases`
    already had (never rewritten once set) and only stamping `now` the
    first time a phase becomes running/done — so the Fases table can show
    Creado/Finalizado/Duración per phase, not just the current snapshot.
    """
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc).isoformat()
    prev_by_key = {p["key"]: p for p in (previous_phases or [])}

    stamped = []
    for p in state["phases"]:
        prev = prev_by_key.get(p["key"], {})
        started_at = prev.get("started_at")
        finished_at = prev.get("finished_at")
        if p["status"] in ("running", "done") and started_at is None:
            started_at = now
        if p["status"] == "done" and finished_at is None:
            finished_at = now
        stamped.append({**p, "started_at": started_at, "finished_at": finished_at})

    return {"phases": stamped, "global_pct": state["global_pct"]}
