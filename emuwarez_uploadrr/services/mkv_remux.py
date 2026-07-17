"""MKV track reordering + professional track naming via mkvmerge (Phase 12A).

Reorders and renames the EXISTING audio/subtitle/video tracks of a .mkv — a
real remux (stream copy, no re-encode): mkvmerge rewrites the container with
the tracks in the desired order and each one relabeled with a clear,
human-readable name (so a player's track-selector menu shows e.g. "Español
(Castellano) - DD+ 5.1" instead of a blank name or "Track 2"). Video/audio/
subtitle DATA is never touched — this changes container metadata/structure
only, nothing is re-encoded.

Default priority order (audio AND subtitles, independently): Español
(Castellano) → Català → Inglés → everything else, in original relative order.

SAFETY CONTRACT:
- dry_run=True by default; apply_remux() requires confirmation=REMUX_CONFIRMATION_TOKEN.
- Only operates on prepared_path (same convention as mkv_title.py), never source_path.
- Output is written to a temp file in the SAME directory as the original (same
  filesystem — works over SSHFS/NFS where a cross-device write would fail),
  then atomically replaces the original with os.replace(). If mkvmerge fails,
  the temp file is removed and the original is left untouched.
- mkvmerge is never called in tests (caller must mock subprocess / read_tracks_json).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..database import connect
from .mkv_title import _get_prepared_path

logger = logging.getLogger("emuwarez.mkv_remux")

REMUX_CONFIRMATION_TOKEN = "REORDENAR_PISTAS"


def _get_target_path(library_item_id: int, conn) -> tuple[str | None, bool]:
    """Track reorder/rename is independent of nomenclature — it only needs a
    real .mkv on disk, so it can be tried before nomenclature has ever run.
    Prefers `prepared_path` (the copy about to be uploaded, from a hardlink or
    a rename) when nomenclature already ran; otherwise falls back to the
    item's own file, resolved to the local mount (same convention nomenclature
    itself uses before it has a prepared copy). Returns (path, is_prepared)."""
    prepared = _get_prepared_path(library_item_id, conn)
    if prepared:
        return prepared, True
    row = conn.execute("SELECT path FROM library_items WHERE id = ?", (library_item_id,)).fetchone()
    raw_path = row["path"] if row else None
    if not raw_path:
        return None, False
    from .path_mapping import resolve_local_path
    return (resolve_local_path(raw_path, conn=conn) or raw_path), False

# ---------------------------------------------------------------------------
# Language: display name + sort priority + Latin-Spanish detection
# ---------------------------------------------------------------------------

# Spanish display names for a track's language, keyed by normalized ISO 639-1/
# 639-2 (both bibliographic and terminological where they differ) codes —
# mirrors the ESP/CAT/ING/... codes emu_format.LANG_MAP already uses elsewhere
# in the app, spelled out here for a track-selector menu. Covers the ISO 639-1
# set (not just the handful realistic for a Spanish tracker) so an unusual
# language still gets a proper Spanish name instead of falling back to the
# raw code — see lang_display_name().
_LANG_DISPLAY: dict[str, str] = {
    "es": "Español (Castellano)", "spa": "Español (Castellano)",
    "ca": "Català", "cat": "Català",
    "en": "Inglés", "eng": "Inglés",
    "fr": "Francés", "fra": "Francés", "fre": "Francés",
    "de": "Alemán", "deu": "Alemán", "ger": "Alemán",
    "it": "Italiano", "ita": "Italiano",
    "pt": "Portugués", "por": "Portugués",
    "ja": "Japonés", "jpn": "Japonés",
    "ko": "Coreano", "kor": "Coreano",
    "ru": "Ruso", "rus": "Ruso",
    "zh": "Chino", "chi": "Chino", "zho": "Chino",
    "eu": "Euskera", "baq": "Euskera", "eus": "Euskera",
    "gl": "Gallego", "glg": "Gallego",
    "af": "Afrikáans", "afr": "Afrikáans",
    "sq": "Albanés", "sqi": "Albanés", "alb": "Albanés",
    "am": "Amárico", "amh": "Amárico",
    "ar": "Árabe", "ara": "Árabe",
    "hy": "Armenio", "hye": "Armenio", "arm": "Armenio",
    "az": "Azerí", "aze": "Azerí",
    "be": "Bielorruso", "bel": "Bielorruso",
    "bn": "Bengalí", "ben": "Bengalí",
    "bs": "Bosnio", "bos": "Bosnio",
    "bg": "Búlgaro", "bul": "Búlgaro",
    "my": "Birmano", "mya": "Birmano", "bur": "Birmano",
    "hr": "Croata", "hrv": "Croata",
    "cs": "Checo", "ces": "Checo", "cze": "Checo",
    "da": "Danés", "dan": "Danés",
    "nl": "Neerlandés", "nld": "Neerlandés", "dut": "Neerlandés",
    "eo": "Esperanto", "epo": "Esperanto",
    "et": "Estonio", "est": "Estonio",
    "fi": "Finlandés", "fin": "Finlandés",
    "ka": "Georgiano", "kat": "Georgiano", "geo": "Georgiano",
    "el": "Griego", "ell": "Griego", "gre": "Griego",
    "gu": "Guyaratí", "guj": "Guyaratí",
    "he": "Hebreo", "heb": "Hebreo",
    "hi": "Hindi", "hin": "Hindi",
    "hu": "Húngaro", "hun": "Húngaro",
    "is": "Islandés", "isl": "Islandés", "ice": "Islandés",
    "id": "Indonesio", "ind": "Indonesio",
    "ga": "Irlandés", "gle": "Irlandés",
    "kn": "Canarés", "kan": "Canarés",
    "kk": "Kazajo", "kaz": "Kazajo",
    "km": "Jemer", "khm": "Jemer",
    "ku": "Kurdo", "kur": "Kurdo",
    "lo": "Lao", "lao": "Lao",
    "la": "Latín", "lat": "Latín",
    "lv": "Letón", "lav": "Letón",
    "lt": "Lituano", "lit": "Lituano",
    "mk": "Macedonio", "mkd": "Macedonio", "mac": "Macedonio",
    "ms": "Malayo", "msa": "Malayo", "may": "Malayo",
    "ml": "Malayalam", "mal": "Malayalam",
    "mt": "Maltés", "mlt": "Maltés",
    "mr": "Maratí", "mar": "Maratí",
    "mn": "Mongol", "mon": "Mongol",
    "ne": "Nepalí", "nep": "Nepalí",
    "no": "Noruego", "nor": "Noruego",
    "fa": "Persa", "fas": "Persa", "per": "Persa",
    "pl": "Polaco", "pol": "Polaco",
    "pa": "Panyabí", "pan": "Panyabí",
    "ro": "Rumano", "ron": "Rumano", "rum": "Rumano",
    "sr": "Serbio", "srp": "Serbio",
    "si": "Cingalés", "sin": "Cingalés",
    "sk": "Eslovaco", "slk": "Eslovaco", "slo": "Eslovaco",
    "sl": "Esloveno", "slv": "Esloveno",
    "so": "Somalí", "som": "Somalí",
    "sw": "Suajili", "swa": "Suajili",
    "sv": "Sueco", "swe": "Sueco",
    "tl": "Tagalo", "tgl": "Tagalo",
    "ta": "Tamil", "tam": "Tamil",
    "te": "Telugu", "tel": "Telugu",
    "th": "Tailandés", "tha": "Tailandés",
    "tr": "Turco", "tur": "Turco",
    "uk": "Ucraniano", "ukr": "Ucraniano",
    "ur": "Urdu", "urd": "Urdu",
    "uz": "Uzbeko", "uzb": "Uzbeko",
    "vi": "Vietnamita", "vie": "Vietnamita",
    "cy": "Galés", "cym": "Galés", "wel": "Galés",
    "xh": "Xhosa", "xho": "Xhosa",
    "yi": "Yidis", "yid": "Yidis",
    "zu": "Zulú", "zul": "Zulú",
}
_LATIN_SPANISH_NAME = "Español (Latinoamérica)"
_UNKNOWN_LANG_NAME = "Desconocido"

# Sort priority for the top 3 (0 = highest); everything else is bucket 3 and
# keeps its original relative order (Python's sort is stable).
_PRIORITY_CASTILIAN, _PRIORITY_CATALAN, _PRIORITY_ENGLISH, _PRIORITY_OTHER = 0, 1, 2, 3


def _is_latin_spanish(lang_ietf: str | None, existing_name: str | None) -> bool:
    """Castilian vs Latin American Spanish can't be told apart from the plain
    639-2 'spa' tag (it has no regional variant) — only from the BCP47
    `language_ietf` tag (e.g. 'es-419', 'es-MX') when the source set one, or
    from the track's own existing name already saying so."""
    if lang_ietf:
        ietf = lang_ietf.strip().lower()
        if ietf.startswith("es-") and ietf != "es-es":
            return True
    if existing_name:
        n = existing_name.strip().lower()
        if "latino" in n or "latin america" in n or "latinoameric" in n:
            return True
    return False


def _normalize_lang_code(lang: str | None) -> str:
    return (lang or "und").strip().lower()


def lang_display_name(lang: str | None, lang_ietf: str | None = None, existing_name: str | None = None) -> str:
    """Human-readable, Spanish-audience display name for a track's language."""
    code = _normalize_lang_code(lang)
    if code in ("es", "spa") and _is_latin_spanish(lang_ietf, existing_name):
        return _LATIN_SPANISH_NAME
    if code in ("", "und", "mis"):
        return _UNKNOWN_LANG_NAME
    return _LANG_DISPLAY.get(code, code.upper())


def lang_priority(lang: str | None, lang_ietf: str | None = None, existing_name: str | None = None) -> int:
    code = _normalize_lang_code(lang)
    if code in ("es", "spa"):
        return _PRIORITY_OTHER if _is_latin_spanish(lang_ietf, existing_name) else _PRIORITY_CASTILIAN
    if code in ("ca", "cat"):
        return _PRIORITY_CATALAN
    if code in ("en", "eng"):
        return _PRIORITY_ENGLISH
    return _PRIORITY_OTHER


# ---------------------------------------------------------------------------
# Codec / resolution labels for the track name
# ---------------------------------------------------------------------------

_CHANNELS_LABEL = {1: "Mono", 2: "2.0", 3: "3.0", 4: "3.1", 5: "5.0", 6: "5.1", 7: "6.1", 8: "7.1"}


def _audio_codec_label(mkv_codec: str | None) -> str:
    text = (mkv_codec or "").lower()
    if "truehd" in text:
        return "TrueHD"
    if "dts-hd master" in text or "dts-hd ma" in text:
        return "DTS-HD MA"
    if "dts-hd" in text:
        return "DTS-HD HRA"
    if "dts" in text:
        return "DTS"
    if "e-ac-3" in text or "eac3" in text or "dolby digital plus" in text:
        return "DD+"
    if "ac-3" in text or "ac3" in text or "dolby digital" in text:
        return "DD"
    if "aac" in text:
        return "AAC"
    if "flac" in text:
        return "FLAC"
    if "opus" in text:
        return "Opus"
    if "pcm" in text:
        return "PCM"
    return (mkv_codec or "").strip() or "?"


def _video_codec_label(mkv_codec: str | None) -> str:
    text = (mkv_codec or "").lower()
    if "hevc" in text or "h.265" in text or "h265" in text:
        return "HEVC"
    if "avc" in text or "h.264" in text or "h264" in text:
        return "AVC"
    if "av1" in text:
        return "AV1"
    if "vp9" in text:
        return "VP9"
    return (mkv_codec or "").strip() or "?"


def _resolution_label(pixel_dimensions: str | None) -> str | None:
    if not pixel_dimensions or "x" not in pixel_dimensions:
        return None
    try:
        _, h = pixel_dimensions.lower().split("x", 1)
        height = int(h.strip())
    except (ValueError, TypeError):
        return None
    if height >= 2000:
        return "2160p"
    if height >= 1000:
        return "1080p"
    if height >= 700:
        return "720p"
    if height >= 550:
        return "576p"
    return "480p"


def _channels_label(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "2.0"
    return _CHANNELS_LABEL.get(n, f"{n}.0")


# ---------------------------------------------------------------------------
# mkvmerge availability + track reading
# ---------------------------------------------------------------------------

def check_mkvmerge_available() -> dict:
    path = shutil.which("mkvmerge")
    if path:
        return {"available": True, "path": path}
    return {"available": False, "path": None, "message": "mkvmerge no encontrado en PATH (instala mkvtoolnix)"}


def read_tracks_json(path: str) -> dict:
    """Run `mkvmerge -J <path>` and return the parsed identification JSON, or
    {"ok": False, "error": ...} on any failure. Never raises."""
    try:
        result = subprocess.run(
            ["mkvmerge", "-J", path],
            capture_output=True, text=True, timeout=60, shell=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "mkvmerge no encontrado al ejecutar."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "mkvmerge -J agotó el timeout de 60s."}
    # mkvmerge -J still prints valid JSON even with warnings (exit 1); only a
    # genuine failure (exit 2, or unparsable output) counts as an error here.
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        return {"ok": False, "error": (result.stderr or "Salida de mkvmerge -J no es JSON válido.").strip()}
    return {"ok": True, "data": data}


# ---------------------------------------------------------------------------
# Plan building (pure — testable without the mkvmerge binary)
# ---------------------------------------------------------------------------

def build_track_plan(mkv_json: dict, *, known_resolution: str | None = None) -> dict:
    """Turn a parsed `mkvmerge -J` structure into a reorder+rename plan: which
    track ids go where, and what name each gets. Pure function — no I/O.

    `known_resolution` (e.g. "1080p", already resolved elsewhere in the app
    from Radarr/Sonarr's quality profile) is preferred over deriving it from
    the raw pixel height — a cropped/letterboxed encode (common for 2.35:1/
    2.40:1 sources) can store fewer pixel rows than its nominal resolution
    (e.g. 1920x800 for an actual 1080p master), which would otherwise mislabel
    the video track."""
    raw_tracks = mkv_json.get("tracks") or []
    tracks: list[dict] = []
    ietf_by_id: dict[int, str | None] = {}
    for t in raw_tracks:
        props = t.get("properties") or {}
        tid = t.get("id")
        ietf_by_id[tid] = props.get("language_ietf")
        tracks.append({
            "id": tid,
            "type": t.get("type"),
            "codec": t.get("codec"),
            "language": props.get("language"),
            "current_name": props.get("track_name"),
            "default_before": bool(props.get("default_track")),
            "forced": bool(props.get("forced_track")),
            "audio_channels": props.get("audio_channels"),
            "pixel_dimensions": props.get("pixel_dimensions"),
        })

    video = [t for t in tracks if t["type"] == "video"]
    audio = [t for t in tracks if t["type"] == "audio"]
    subs = [t for t in tracks if t["type"] == "subtitles"]

    for t in audio + subs:
        t["_priority"] = lang_priority(t["language"], ietf_by_id.get(t["id"]), t["current_name"])

    audio_sorted = sorted(audio, key=lambda t: t["_priority"])
    subs_sorted = sorted(subs, key=lambda t: t["_priority"])

    new_order = [t["id"] for t in video] + [t["id"] for t in audio_sorted] + [t["id"] for t in subs_sorted]

    for t in video:
        res = known_resolution or _resolution_label(t["pixel_dimensions"])
        codec = _video_codec_label(t["codec"])
        t["new_name"] = " ".join(x for x in (res, codec) if x) or codec
        t["default_after"] = t["default_before"]  # never touch video default

    for i, t in enumerate(audio_sorted):
        lang_name = lang_display_name(t["language"], ietf_by_id.get(t["id"]), t["current_name"])
        codec = _audio_codec_label(t["codec"])
        ch = _channels_label(t["audio_channels"])
        t["new_name"] = f"{lang_name} - {codec} {ch}"
        t["default_after"] = (i == 0)  # first in the new order becomes default

    for t in subs_sorted:
        lang_name = lang_display_name(t["language"], ietf_by_id.get(t["id"]), t["current_name"])
        t["new_name"] = f"{lang_name} (Forzado)" if t["forced"] else lang_name
        t["default_after"] = t["forced"]  # forced subs stay auto-shown; the rest don't

    ordered_tracks = video + audio_sorted + subs_sorted
    order_changed = [t["id"] for t in tracks] != new_order
    for t in ordered_tracks:
        t["changed"] = (
            order_changed
            or t.get("current_name") != t.get("new_name")
            or t.get("default_before") != t.get("default_after")
        )
        t.pop("_priority", None)

    return {
        "tracks": tracks,                  # original file order
        "ordered_tracks": ordered_tracks,  # video, then audio (sorted), then subs (sorted)
        "new_order": new_order,
        "order_changed": order_changed,
        "any_changed": any(t["changed"] for t in ordered_tracks),
    }


def apply_track_overrides(plan: dict, overrides: dict[int, dict] | None) -> dict:
    """Layer manual edits (from the upload wizard's editable table) on top of
    an auto-computed plan — the user can override the proposed `new_name`
    and/or `default_after` per track id. Pure function: returns a NEW plan,
    doesn't mutate the input. Track order/grouping (video→audio→subs, language
    priority) is never overridable — only the name and the default flag."""
    if not overrides:
        return plan

    def _apply(t: dict) -> dict:
        ov = overrides.get(t["id"])
        if not ov:
            return t
        t = dict(t)
        if ov.get("new_name") is not None and str(ov["new_name"]).strip():
            t["new_name"] = str(ov["new_name"]).strip()
        if ov.get("default_after") is not None and t["type"] != "video":
            t["default_after"] = bool(ov["default_after"])
        t["changed"] = (
            plan["order_changed"]
            or t.get("current_name") != t.get("new_name")
            or t.get("default_before") != t.get("default_after")
        )
        return t

    ordered_tracks = [_apply(t) for t in plan["ordered_tracks"]]
    return {
        **plan,
        "ordered_tracks": ordered_tracks,
        "any_changed": any(t["changed"] for t in ordered_tracks),
    }


def build_mkvmerge_args(output_path: str, source_path: str, plan: dict) -> list[str]:
    args: list[str] = ["mkvmerge", "-o", output_path]
    for t in plan["ordered_tracks"]:
        args += ["--track-name", f"{t['id']}:{t['new_name']}"]
        if t["type"] in ("audio", "subtitles"):
            args += ["--default-track-flag", f"{t['id']}:{'1' if t['default_after'] else '0'}"]
    args += ["--track-order", ",".join(f"0:{tid}" for tid in plan["new_order"])]
    args += [source_path]
    return args


def _preview_command(args: list[str]) -> str:
    return " ".join(f'"{a}"' if " " in a else a for a in args)


# ---------------------------------------------------------------------------
# Preview / apply — DB + filesystem orchestration
# ---------------------------------------------------------------------------

def _get_known_resolution(library_item_id: int, conn) -> str | None:
    """The resolution already resolved elsewhere in the app (from Radarr/
    Sonarr's quality profile), preferred over deriving it from raw pixel
    height for the video track's name — see build_track_plan's docstring."""
    row = conn.execute(
        "SELECT resolution FROM library_items WHERE id = ?", (library_item_id,)
    ).fetchone()
    return (row["resolution"] or None) if row else None


def build_remux_plan(library_item_id: int, conn=None) -> dict:
    own = conn is None
    conn = conn or connect()
    try:
        mkvmerge_check = check_mkvmerge_available()
        prepared_path, using_prepared_copy = _get_target_path(library_item_id, conn)
        base = {
            "library_item_id": library_item_id,
            "prepared_path": prepared_path,
            "using_prepared_copy": using_prepared_copy,
            "mkvmerge_available": mkvmerge_check.get("available", False),
            "mkvmerge_path": mkvmerge_check.get("path"),
            "tracks": [], "ordered_tracks": [], "warnings": [],
        }
        if not prepared_path:
            return {**base, "status": "blocked",
                    "errors": ["El elemento no tiene ningún archivo (ni preparado ni original) para operar."]}
        p = Path(prepared_path)
        if p.suffix.lower() != ".mkv":
            return {**base, "status": "blocked", "errors": [f"El archivo no es .mkv: {p.suffix}"]}
        if not p.is_file():
            return {**base, "status": "blocked",
                    "errors": [f"El archivo no existe o no es accesible: {prepared_path}"]}
        if not mkvmerge_check.get("available"):
            return {**base, "status": "blocked",
                    "errors": ["mkvmerge no está instalado. Instala mkvtoolnix para reordenar/renombrar pistas."]}

        read = read_tracks_json(prepared_path)
        if not read.get("ok"):
            return {**base, "status": "blocked", "errors": [f"mkvmerge -J falló: {read.get('error')}"]}

        plan = build_track_plan(read["data"], known_resolution=_get_known_resolution(library_item_id, conn))
        if not plan["tracks"]:
            return {**base, "status": "blocked", "errors": ["mkvmerge no encontró pistas en el archivo."]}

        warnings: list[str] = []
        if not using_prepared_copy:
            warnings.append(
                "Aún no se ha aplicado la nomenclatura: esto operará sobre el archivo ORIGINAL "
                "que gestionan Radarr/Sonarr (mismo nombre y carpeta, se sobrescribe en sitio)."
            )
        if not any(t["type"] == "audio" for t in plan["tracks"]):
            warnings.append("El archivo no tiene pistas de audio.")
        if not plan["any_changed"]:
            warnings.append("Las pistas ya están en el orden y con los nombres correctos; no hay nada que aplicar.")

        args = build_mkvmerge_args(prepared_path, prepared_path, plan)

        return {
            **base,
            "status": "ready" if plan["any_changed"] else "warning",
            "errors": [],
            "warnings": warnings,
            "tracks": plan["tracks"],
            "ordered_tracks": plan["ordered_tracks"],
            "order_changed": plan["order_changed"],
            "command_preview": _preview_command(args),
        }
    finally:
        if own:
            conn.close()


def apply_remux(
    library_item_id: int,
    *,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
    overrides: dict[int, dict] | None = None,
    conn=None,
) -> dict:
    """Apply or preview the track reorder/rename.

    Real execution requires: dry_run=False, apply=True,
    confirmation=REMUX_CONFIRMATION_TOKEN.

    `overrides` (track id -> {new_name?, default_after?}) lets a caller (the
    upload wizard's editable table) override the auto-computed name/default
    per track — grouping and priority order are never overridable, only what
    each track ends up called and whether it's marked default.
    """
    own = conn is None
    conn = conn or connect()
    try:
        preview = build_remux_plan(library_item_id, conn=conn)

        if preview["status"] == "blocked":
            return {**preview, "dry_run": True, "apply": False}

        if dry_run or not apply:
            return {**preview, "dry_run": True, "apply": False}

        if confirmation != REMUX_CONFIRMATION_TOKEN:
            return {
                **preview, "status": "blocked", "dry_run": dry_run, "apply": False,
                "errors": preview.get("errors", []) + [
                    f"Para reordenar/renombrar pistas debes confirmar escribiendo: {REMUX_CONFIRMATION_TOKEN}"
                ],
            }

        prepared_path = preview["prepared_path"]
        p = Path(prepared_path)
        if not p.is_file():
            return {**preview, "status": "blocked", "dry_run": False, "apply": False,
                     "errors": [f"El archivo no existe: {prepared_path}"]}

        read = read_tracks_json(prepared_path)
        if not read.get("ok"):
            return {**preview, "status": "blocked", "dry_run": False, "apply": False,
                     "errors": [f"mkvmerge -J falló: {read.get('error')}"]}
        plan = build_track_plan(read["data"], known_resolution=_get_known_resolution(library_item_id, conn))
        plan = apply_track_overrides(plan, overrides)

        # Write to a temp file in the SAME directory (same filesystem — works
        # over SSHFS/NFS), then atomically replace the original.
        fd, tmp_path = tempfile.mkstemp(suffix=".mkv.part", dir=str(p.parent))
        os.close(fd)
        os.remove(tmp_path)  # mkvmerge must create the file itself

        args = build_mkvmerge_args(tmp_path, prepared_path, plan)
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=1800, shell=False)
        except FileNotFoundError:
            return {**preview, "status": "error", "dry_run": False, "apply": True,
                     "errors": ["mkvmerge no encontrado al ejecutar."]}
        except subprocess.TimeoutExpired:
            _cleanup(tmp_path)
            _update_status(conn, library_item_id, "error", "mkvmerge agotó el timeout (30 min).")
            return {**preview, "status": "error", "dry_run": False, "apply": True,
                     "errors": ["mkvmerge agotó el timeout (30 min)."]}

        # mkvmerge: 0 = OK, 1 = OK with warnings, 2 = failed (no output file).
        if result.returncode not in (0, 1) or not os.path.isfile(tmp_path):
            _cleanup(tmp_path)
            err = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
            _update_status(conn, library_item_id, "error", err[:2000])
            logger.warning("Reordenar/renombrar pistas falló (item %s): %s", library_item_id, err[:300])
            return {**preview, "status": "error", "dry_run": False, "apply": True, "errors": [err[:2000]]}

        os.replace(tmp_path, prepared_path)
        now = datetime.now(timezone.utc).isoformat()
        _update_status(conn, library_item_id, "aplicado", None, applied_at=now)
        logger.info("Pistas reordenadas/renombradas (item %s): %s", library_item_id, prepared_path)

        return {
            **preview, "status": "applied", "dry_run": False, "apply": True,
            "applied_at": now, "exit_code": result.returncode,
        }
    finally:
        if own:
            conn.close()


def _cleanup(tmp_path: str) -> None:
    try:
        os.remove(tmp_path)
    except OSError:
        pass


def _update_status(conn, library_item_id: int, status: str, error: str | None, *, applied_at: str | None = None) -> None:
    try:
        conn.execute(
            """UPDATE library_items
               SET track_remux_status = ?, track_remux_error = ?, track_remux_applied_at = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (status, error, applied_at, library_item_id),
        )
        conn.commit()
    except Exception:
        pass
