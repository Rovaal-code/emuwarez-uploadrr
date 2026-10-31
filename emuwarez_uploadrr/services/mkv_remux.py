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
- Nunca escribe en un fichero con más de un enlace duro: sería escribir también
  en el torrent que lo siembra. La cola edita entonces una copia por reflink en
  la carpeta de subidas (upload_queue._preparar_fichero).
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
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..database import connect
from .uploadrr_progress import parse_mkvmerge_gui_progress

logger = logging.getLogger("emuwarez.mkv_remux")

REMUX_CONFIRMATION_TOKEN = "REORDENAR_PISTAS"


def _get_target_path(library_item_id: int, conn) -> tuple[str | None, bool]:
    """Track reorder/rename is independent of nomenclature — it only needs a
    real .mkv on disk, so it can be tried before nomenclature has ever run.
    Prefers `prepared_path` (the copy about to be uploaded, from a hardlink or
    a rename) when nomenclature already ran AND that copy still exists on
    disk; otherwise falls back to the item's own file, resolved to the local
    mount — same rule as everywhere else that reads from a library item, see
    path_mapping.py::ruta_de_lectura. Returns (path, is_prepared)."""
    from .path_mapping import resolve_local_path, ruta_de_lectura
    row = conn.execute(
        "SELECT path, prepared_path FROM library_items WHERE id = ?", (library_item_id,)
    ).fetchone()
    if not row:
        return None, False
    item = {"path": row["path"], "prepared_path": row["prepared_path"]}
    elegida = ruta_de_lectura(item, conn=conn)
    if not elegida:
        return None, False
    local = resolve_local_path(elegida, conn=conn) or elegida
    is_prepared = bool(item["prepared_path"]) and elegida == item["prepared_path"]
    return local, is_prepared

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
    "nb": "Noruego (Bokmål)", "nob": "Noruego (Bokmål)",
    "nn": "Noruego (Nynorsk)", "nno": "Noruego (Nynorsk)",
    "fil": "Filipino",
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
# El valenciano comparte código ISO con el catalán ("cat"), así que la única
# forma de distinguirlo es el BCP-47 de la pista ("ca-valencia"). Mismo caso
# que el castellano y el latino, que también comparten "spa".
_VALENCIAN_NAME = "Valencià"
_UNKNOWN_LANG_NAME = "Desconocido"

# Sort priority for the top 3 (0 = highest); everything else is bucket 3 and
# keeps its original relative order (Python's sort is stable).
_PRIORITY_CASTILIAN, _PRIORITY_CATALAN, _PRIORITY_ENGLISH, _PRIORITY_OTHER = 0, 1, 2, 3


# Real-world audit (2802 files, MAX/HBO Max releases) found `es-x-01`..`es-x-09`
# — a private-use BCP47 subtag some streaming services attach to disambiguate
# tracks, NOT a region code. It shows up even on natively Castilian-Spanish
# content (e.g. "Aquí no hay quien viva", a Spanish-produced sitcom) — so
# matching on `es-` prefix alone (anything but "es-es") mislabeled ~100 native
# Castilian tracks as Latin American. Only a real Latin American region code
# counts now.
_LATIN_SPANISH_REGIONS = {
    "419",  # UN M49 region code for Latin America & the Caribbean
    "mx", "ar", "co", "cl", "pe", "ve", "ec", "gt", "cu", "bo",
    "do", "hn", "py", "sv", "ni", "cr", "pa", "uy", "pr",
}


def _is_latin_spanish(lang_ietf: str | None, existing_name: str | None) -> bool:
    """Castilian vs Latin American Spanish can't be told apart from the plain
    639-2 'spa' tag (it has no regional variant) — only from the BCP47
    `language_ietf` tag (e.g. 'es-419', 'es-MX') when the source set a REAL
    Latin American region, or from the track's own existing name already
    saying so."""
    if lang_ietf:
        parts = lang_ietf.strip().lower().split("-")
        if parts and parts[0] == "es" and len(parts) > 1 and parts[1] in _LATIN_SPANISH_REGIONS:
            return True
    if existing_name:
        n = existing_name.strip().lower()
        if "latino" in n or "latin america" in n or "latinoameric" in n:
            return True
    return False


def _normalize_lang_code(lang: str | None) -> str:
    return (lang or "und").strip().lower()


def _is_valencian(lang: str | None, lang_ietf: str | None, existing_name: str | None) -> bool:
    """Valenciano, que no se puede distinguir del catalán por el código ISO.

    mkvmerge da DOS campos: `language` ("cat", sin variante) y `language_ietf`
    ("ca-valencia", con ella). La columna Idioma leía el primero y por eso un
    valenciano salía como catalán, aunque Ver MediaInfo enseñara la variante.
    """
    for texto in (lang_ietf, lang):
        if texto and "valencia" in str(texto).strip().lower():
            return True
    if existing_name and "valenci" in existing_name.strip().lower():
        return True
    return False


def lang_display_name(lang: str | None, lang_ietf: str | None = None, existing_name: str | None = None) -> str:
    """Human-readable, Spanish-audience display name for a track's language."""
    code = _normalize_lang_code(lang)
    if code in ("es", "spa") and _is_latin_spanish(lang_ietf, existing_name):
        return _LATIN_SPANISH_NAME
    if _is_valencian(lang, lang_ietf, existing_name):
        return _VALENCIAN_NAME
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
    # MLP is TrueHD's underlying codec name — mkvmerge/MediaInfo sometimes
    # report it as e.g. "MLP FBA 16-ch" with no "TrueHD" substring at all
    # (confirmed against a real library: 3 tracks would've fallen through to
    # the raw codec string otherwise). Kept as its own label ("MLP"), matching
    # legacy.py's existing audio_codec() convention.
    if "mlp" in text:
        return "MLP"
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

# Qué se le hace a las pistas antes de subir. Son DOS cosas independientes
# —colocarlas en orden y ponerles nombre— y hasta ahora el ajuste solo decidía
# la primera, dando por hecho que renombrar se hacía siempre.
#
# Los dos costes son muy distintos, y por eso interesa poder elegirlos por
# separado:
#
#   renombrar   mkvpropedit edita la cabecera EN EL SITIO, sin copiar los
#               datos. Casi instantáneo por grande que sea el fichero.
#   reordenar   obliga a rehacer el contenedor con mkvmerge y a sustituir el
#               fichero (os.replace), y tarda en proporción al tamaño.
#
# Los dos escriben en el fichero, así que solo se hacen en uno que no comparte
# nadie (st_nlink == 1). Si lo comparte un torrent, renombrar va a una copia
# por reflink y reordenar se omite (ver upload_queue._preparar_fichero).
MODO_REORDENAR_Y_RENOMBRAR = "reordenar_y_renombrar"
MODO_SOLO_RENOMBRAR = "solo_renombrar"
MODO_SOLO_REORDENAR = "solo_reordenar"
MODO_NINGUNO = "ninguno"

MODOS_PISTAS = (
    MODO_REORDENAR_Y_RENOMBRAR,
    MODO_SOLO_RENOMBRAR,
    MODO_SOLO_REORDENAR,
    MODO_NINGUNO,
)

# Lo que enseña la interfaz. Aquí y no en el frontend para que no haya dos
# listas que se puedan desincronizar (lo vigila tests/test_copias_frontend).
ETIQUETAS_MODO_PISTAS = {
    MODO_REORDENAR_Y_RENOMBRAR: "Reordenar y renombrar",
    MODO_SOLO_RENOMBRAR: "Solo renombrar",
    MODO_SOLO_REORDENAR: "Solo reordenar",
    MODO_NINGUNO: "Ninguno",
}

# Sigue siendo el de antes: reordenar reescribe el fichero entero, así que de
# fábrica solo se renombra.
MODO_PISTAS_POR_DEFECTO = MODO_SOLO_RENOMBRAR


def modo_pistas(conn=None) -> str:
    """Qué se le hace a las pistas: uno de MODOS_PISTAS.

    Lee el ajuste nuevo (`remux.track_mode`) y, si no está escrito todavía,
    traduce el viejo de sí/no (`remux.reorder_tracks`) en vez de caer al valor
    de fábrica: quien tuviera reordenar activado se lo encontraría apagado
    después de actualizar, sin haber tocado nada.
    """
    own = conn is None
    if own:
        from ..database import connect as _connect
        conn = _connect()
    try:
        from .settings import get_setting_canonical
        valor = (get_setting_canonical(conn, "remux.track_mode") or "").strip()
        if valor in MODOS_PISTAS:
            return valor
        viejo = get_setting_canonical(conn, "remux.reorder_tracks")
        if viejo is not None:
            return (MODO_REORDENAR_Y_RENOMBRAR if (viejo or "") == "true"
                    else MODO_SOLO_RENOMBRAR)
        return MODO_PISTAS_POR_DEFECTO
    except Exception:
        return MODO_PISTAS_POR_DEFECTO
    finally:
        if own:
            conn.close()


def reordena(modo: str) -> bool:
    return modo in (MODO_REORDENAR_Y_RENOMBRAR, MODO_SOLO_REORDENAR)


def renombra(modo: str) -> bool:
    return modo in (MODO_REORDENAR_Y_RENOMBRAR, MODO_SOLO_RENOMBRAR)


def toca_el_fichero(modo: str) -> bool:
    """Con "Ninguno" no hay nada que ejecutar y la fase se salta entera."""
    return modo != MODO_NINGUNO


def reorder_tracks_enabled(conn=None) -> bool:
    """Si además de lo demás se REORDENAN las pistas. Se mantiene porque hay
    llamadas que solo preguntan eso; el estado completo es modo_pistas()."""
    return reordena(modo_pistas(conn))


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

# Forced subtitles: the MKV container's own forced_track bit is the reliable
# signal and the one players obey, but plenty of releases never set it and only
# say so in the track NAME ("Spanish [ForcedNarrative]"), which used to be
# ignored entirely here — so a genuinely forced track showed up as a regular
# one, both in the label and in the ordering below (`forced` is the tiebreaker
# that keeps a regular track ahead of a forced one, and the first track is the
# one marked default).
#
# The lookbehind stops "reinforced" from counting, and the negative pattern
# keeps names that explicitly say the opposite ("Full, not forced",
# "NonForced") from being flipped into forced by the word they contain.
_FORCED_NAME_RE = re.compile(r"(?<![a-záéíóúñ])for[cz](?:ed|ad[oa]s?)", re.IGNORECASE)
_NOT_FORCED_NAME_RE = re.compile(r"(?:non|not|no|un|sin)[\s._·-]*for[cz]", re.IGNORECASE)


def _is_forced(props: dict) -> bool:
    """Whether a track is forced, from the container flag first and the track
    name second. The flag wins when set: it is what a player actually acts on,
    so a name that disagrees with it doesn't get to override it."""
    if props.get("forced_track"):
        return True
    name = props.get("track_name") or ""
    if _NOT_FORCED_NAME_RE.search(name):
        return False
    return bool(_FORCED_NAME_RE.search(name))



def _default_subtitle_id(audio_sorted: list[dict], subs_sorted: list[dict]) -> int | None:
    """Which subtitle track (if any) should come out flagged as default.

    Audio just takes the first track after sorting, but subtitles can't: which
    one you want on depends on what the audio gives you.

    | Audio                     | Subtítulo activado                          |
    |---------------------------|---------------------------------------------|
    | Castellano                | el castellano FORZADO — ves el doblaje y se |
    |                           | traducen carteles y diálogos en otro idioma |
    | Castellano, sin forzado   | ninguno — doblada y sin subtítulos          |
    | Sin castellano            | el castellano COMPLETO — ves la versión     |
    |                           | original y hacen falta todos los diálogos   |

    Last resort, when there's no Castilian subtitle at all (say a Japanese film
    subtitled only in English): the first of the sorted order, so the file
    isn't shipped with every subtitle off.

    Returns the track id, or None when nothing should be default.
    """
    castilian_audio = any(t["_priority"] == _PRIORITY_CASTILIAN for t in audio_sorted)
    castilian_subs = [t for t in subs_sorted if t["_priority"] == _PRIORITY_CASTILIAN]

    if castilian_audio:
        forced = next((t for t in castilian_subs if t["forced"]), None)
        return forced["id"] if forced else None

    full = next((t for t in castilian_subs if not t["forced"]), None)
    if full:
        return full["id"]
    return subs_sorted[0]["id"] if subs_sorted else None

def build_track_plan(mkv_json: dict, *, known_resolution: str | None = None,
                     reorder: bool = True, rename: bool = True,
                     mark_default: bool = True) -> dict:
    """Turn a parsed `mkvmerge -J` structure into a reorder+rename plan: which
    track ids go where, and what name each gets. Pure function — no I/O.

    `rename=False`: cada pista conserva el nombre que ya tiene. No es lo mismo
    que "no calcular nombres": el plan sigue teniendo su columna `new_name`
    para que la tabla de Ver Pistas se lea igual, solo que repitiendo el actual.
    Así lo que se enseña es exactamente lo que va a quedar en el fichero, sin
    que la tabla tenga que saber en qué modo está.

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
            # El BCP-47, cuando el archivo lo trae. Es lo ÚNICO que distingue
            # el valenciano del catalán y el latino del castellano: el código
            # ISO de `language` es el mismo para los dos ("cat", "spa"). La
            # columna Idioma de "Ver Pistas" enseñaba solo `language`, así que
            # un valenciano salía como "cat" aunque Ver MediaInfo lo dijera.
            "language_ietf": props.get("language_ietf"),
            "current_name": props.get("track_name"),
            "default_before": bool(props.get("default_track")),
            "forced": _is_forced(props),
            "audio_channels": props.get("audio_channels"),
            "pixel_dimensions": props.get("pixel_dimensions"),
            # UID de la pista dentro del MKV: es como mkvpropedit la
            # selecciona sin depender de su posición.
            "uid": props.get("uid"),
        })

    video = [t for t in tracks if t["type"] == "video"]
    audio = [t for t in tracks if t["type"] == "audio"]
    subs = [t for t in tracks if t["type"] == "subtitles"]

    for t in audio + subs:
        t["_priority"] = lang_priority(t["language"], ietf_by_id.get(t["id"]), t["current_name"])

    audio_sorted = sorted(audio, key=lambda t: t["_priority"])
    # Secondary key `not t["forced"]` (False < True, so forced wins the tie):
    # within a language the forced track goes FIRST, giving
    #   Español Forzado, Español, Català Forzado, Català, Inglés Forzado, Inglés, resto
    # The language priority is untouched — forced only reorders inside its own
    # group, it never jumps ahead of a higher-priority language.
    subs_sorted = sorted(subs, key=lambda t: (t["_priority"], not t["forced"]))

    # `reorder=False`: las pistas se quedan donde están y solo se renombran y
    # se marcan las predeterminadas. Los nombres y el flag se siguen decidiendo
    # con el orden de prioridad de arriba (es una regla de IDIOMA, no de
    # posición), así que el castellano queda igual de marcado; simplemente no
    # se mueve de sitio.
    if reorder:
        new_order = [t["id"] for t in video] + [t["id"] for t in audio_sorted] + [t["id"] for t in subs_sorted]
    else:
        new_order = [t["id"] for t in tracks]

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

    default_sub_id = _default_subtitle_id(audio_sorted, subs_sorted)
    for t in subs_sorted:
        lang_name = lang_display_name(t["language"], ietf_by_id.get(t["id"]), t["current_name"])
        # Same "{Idioma} - {Cualificador}" format as audio's "{Idioma} - {Códec}
        # {Canales}" — consistent separator across track types, whatever the
        # qualifier ends up being (Forzado today; Full/SDH etc. would follow
        # the same pattern if ever added).
        t["new_name"] = f"{lang_name} - Forzado" if t["forced"] else lang_name
        # Unlike audio, the default subtitle is NOT simply the first one: it
        # depends on what the audio offers (see _default_subtitle_id).
        t["default_after"] = (t["id"] == default_sub_id)

    # Sin renombrar, cada pista se queda con el nombre que ya tiene. Se hace
    # AQUÍ y no antes para no repetir la regla del nombre predeterminado: los
    # `default_after` de arriba se calculan igual, porque marcar la pista no es
    # renombrarla y se sigue haciendo en los tres modos que tocan el fichero.
    if not rename:
        for t in video + audio_sorted + subs_sorted:
            t["new_name"] = t.get("current_name")

    # Igual con la pista predeterminada cuando no se va a tocar el fichero
    # ("Ninguno"): la columna tiene que enseñar la que ya trae, no la que se
    # elegiría. Marcada la que se elegiría, la tabla prometía un cambio que
    # nadie iba a hacer (visto en el navegador con un MKV real).
    if not mark_default:
        for t in video + audio_sorted + subs_sorted:
            t["default_after"] = t["default_before"]

    # La tabla de "Ver Pistas" sigue el orden que va a quedar en el fichero.
    by_id = {t["id"]: t for t in (video + audio_sorted + subs_sorted)}
    ordered_tracks = [by_id[i] for i in new_order if i in by_id]
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


def _sin_nombres(overrides: dict[int, dict] | None) -> dict[int, dict] | None:
    """Los mismos overrides pero sin la parte del nombre, para los modos que no
    renombran. Se quedan los `default_after`, que sí se aplican."""
    if not overrides:
        return overrides
    limpios = {tid: {k: v for k, v in ov.items() if k != "new_name"}
               for tid, ov in overrides.items()}
    return {tid: ov for tid, ov in limpios.items() if ov}


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


def build_mkvmerge_args(
    output_path: str, source_path: str, plan: dict, *, gui_mode: bool = False
) -> list[str]:
    args: list[str] = ["mkvmerge"]
    if gui_mode:
        # Emits "#GUI#progress N%" lines on stdout as it works — real,
        # precise progress instead of a fabricated estimate.
        args.append("--gui-mode")
    args += ["-o", output_path]
    for t in plan["ordered_tracks"]:
        args += ["--track-name", f"{t['id']}:{t['new_name']}"]
        if t["type"] in ("audio", "subtitles"):
            args += ["--default-track-flag", f"{t['id']}:{'1' if t['default_after'] else '0'}"]
    args += ["--track-order", ",".join(f"0:{tid}" for tid in plan["new_order"])]
    args += [source_path]
    return args


def build_mkvpropedit_args(path: str, plan: dict) -> list[str]:
    """Aplicar SOLO nombres y banderas de predeterminada, editando la cabecera.

    Cuando el plan no cambia el orden de las pistas, mkvmerge está de más:
    reescribe el contenedor entero para tocar unas cadenas de la cabecera. Eso
    significa leer y escribir el fichero completo (20 GB en una película), y
    además sustituirlo por uno nuevo, lo que rompe cualquier hardlink que
    compartiera con el cliente de torrent.

    mkvpropedit edita en el sitio: no copia los datos, no cambia el inodo y no
    escala con el tamaño del fichero. Medido sobre un MKV de 52 MB, 5 veces
    más rápido; sobre uno de 20 GB la diferencia es de otro orden, porque
    mkvmerge crece con el tamaño y esto se queda plano.

    Las pistas se seleccionan por UID (`track:=<uid>`), no por posición: es
    estable aunque el fichero se lea de otra manera. Sin UID se cae a la
    posición 1-based, que es como las numera mkvpropedit.
    """
    args: list[str] = ["mkvpropedit", path]
    for t in plan["ordered_tracks"]:
        uid = t.get("uid")
        selector = f"track:={uid}" if uid else f"track:{int(t['id']) + 1}"
        args += ["--edit", selector, "--set", f"name={t['new_name']}"]
        if t["type"] in ("audio", "subtitles"):
            args += ["--set", f"flag-default={'1' if t['default_after'] else '0'}"]
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


def build_remux_plan(library_item_id: int, conn=None, *, ruta: str | None = None,
                     reordenar: bool = True) -> dict:
    """`ruta`: el fichero que se mira, si no es el del elemento. `reordenar=False`:
    aunque el modo reordene, el orden no se toca (fichero compartido)."""
    own = conn is None
    conn = conn or connect()
    try:
        mkvmerge_check = check_mkvmerge_available()
        prepared_path, using_prepared_copy = (ruta, False) if ruta else _get_target_path(library_item_id, conn)
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

        modo = modo_pistas(conn)
        plan = build_track_plan(read["data"], known_resolution=_get_known_resolution(library_item_id, conn),
                                reorder=reordena(modo) and reordenar, rename=renombra(modo),
                                mark_default=toca_el_fichero(modo))
        # Si el modo reordena y aquí no se puede, para avisar de lo que se omite.
        reorden_omitido = bool(reordena(modo) and not reordenar
                               and build_track_plan(read["data"], reorder=True)["order_changed"])
        if not plan["tracks"]:
            return {**base, "status": "blocked", "errors": ["mkvmerge no encontró pistas en el archivo."]}

        warnings: list[str] = []
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
            # Sin esto la vista previa es correcta pero se lee mal: enseña las
            # pistas en su orden actual y no hay nada que distinga "ya están
            # bien" de "no se van a tocar porque está desactivado". La tarjeta
            # de Ver Pistas usa `track_mode` para decir en qué modo está y para
            # saber si la columna de nombre se puede editar.
            "track_mode": modo,
            "reorden_omitido": reorden_omitido,
            "reorder_enabled": reordena(modo),
            "rename_enabled": renombra(modo),
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
    on_progress: Callable[[int], None] | None = None,
    ruta: str | None = None,
    reordenar: bool = True,
) -> dict:
    """Apply or preview the track reorder/rename.

    Real execution requires: dry_run=False, apply=True,
    confirmation=REMUX_CONFIRMATION_TOKEN.

    `overrides` (track id -> {new_name?, default_after?}) lets a caller (the
    upload wizard's editable table) override the auto-computed name/default
    per track — grouping and priority order are never overridable, only what
    each track ends up called and whether it's marked default.

    `on_progress`, if given, is called with a 0-100 int each time mkvmerge's
    `--gui-mode` output reports a new percentage — lets the caller surface
    real remux progress (e.g. a job's progress_json) instead of a binary
    0/100 state.

    `ruta`/`reordenar`: como en build_remux_plan. El resultado dice si se
    escribió en el fichero (`escrito`) y con qué pistas quedó (`ordered_tracks`).
    """
    own = conn is None
    conn = conn or connect()
    try:
        preview = build_remux_plan(library_item_id, conn=conn, ruta=ruta, reordenar=reordenar)

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

        # "Ninguno": el fichero se sube tal cual. La cola ya se salta la fase
        # entera, así que aquí no debería llegar nadie; se comprueba igual
        # porque este es el único punto por el que se toca el fichero, y una
        # llamada suelta (un reintento, el endpoint a mano) no puede saltarse
        # el ajuste.
        if not toca_el_fichero(modo_pistas(conn)):
            return {**preview, "status": "skipped", "dry_run": False, "apply": False,
                    "errors": [],
                    "warnings": preview.get("warnings", []) + [
                        "Renombrar/Ordenar pistas está en Ninguno: el archivo se sube sin tocar."]}

        prepared_path = preview["prepared_path"]
        p = Path(prepared_path)
        if not p.is_file():
            return {**preview, "status": "blocked", "dry_run": False, "apply": False,
                     "errors": [f"El archivo no existe: {prepared_path}"]}

        read = read_tracks_json(prepared_path)
        if not read.get("ok"):
            return {**preview, "status": "blocked", "dry_run": False, "apply": False,
                     "errors": [f"mkvmerge -J falló: {read.get('error')}"]}
        modo = modo_pistas(conn)
        plan = build_track_plan(read["data"], known_resolution=_get_known_resolution(library_item_id, conn),
                                reorder=reordena(modo) and reordenar, rename=renombra(modo),
                                mark_default=toca_el_fichero(modo))
        # Sin renombrar, la columna del nombre sale bloqueada en la tarjeta y
        # aquí se descarta lo que traiga: un nombre escrito ANTES de cambiar el
        # ajuste sigue guardado en el trabajo y se colaría por detrás.
        #
        # Solo el nombre. La pista predeterminada se marca en los tres modos
        # que tocan el fichero y se puede seguir eligiendo cuál, así que esa
        # mitad del override se respeta.
        plan = apply_track_overrides(plan, overrides if renombra(modo) else _sin_nombres(overrides))

        if not plan["any_changed"]:
            # Tracks already in the right order with the right names (even
            # after overrides) — skip mkvmerge entirely instead of doing a
            # full rewrite of the file for nothing (same total runtime as a
            # real remux, just to produce an ~identical file).
            now = datetime.now(timezone.utc).isoformat()
            _update_status(conn, library_item_id, "aplicado", None, applied_at=now)
            logger.info("Reordenar/renombrar pistas: sin cambios que aplicar (item %s), mkvmerge omitido.", library_item_id)
            if on_progress:
                on_progress(100)
            return {
                **preview, "status": "applied", "dry_run": False, "apply": True,
                "applied_at": now, "exit_code": 0, "escrito": False,
                "ordered_tracks": plan["ordered_tracks"],
            }

        # Un enlace duro es el MISMO fichero: escribir aquí cambiaría también el
        # torrent que lo siembra, y sus piezas dejarían de cuadrar.
        enlaces = p.stat().st_nlink
        if enlaces > 1:
            return {**preview, "status": "blocked", "dry_run": False, "apply": False,
                    "errors": [f"No se edita {p.name}: lo comparten {enlaces} enlaces duros "
                               "(un torrent que siembra o una subida anterior)."]}

        if not plan["order_changed"]:
            # Solo cambian nombres y banderas: eso se edita EN LA CABECERA con
            # mkvpropedit, sin reescribir el contenedor ni leer el fichero
            # entero (20 GB en una película).
            #
            # mkvmerge se reserva para cuando de verdad hay que mover pistas,
            # que es lo único que obliga a rehacer el contenedor.
            args = build_mkvpropedit_args(prepared_path, plan)
            logger.info("Renombrado de pistas del item %s con mkvpropedit (sin reordenar): "
                        "edición en el sitio, sin reescribir el contenedor.", library_item_id)
            try:
                proc = subprocess.run(args, capture_output=True, text=True, timeout=300)
            except FileNotFoundError:
                return {**preview, "status": "error", "dry_run": False, "apply": True,
                        "errors": ["mkvpropedit no encontrado al ejecutar (instala mkvtoolnix)."]}
            except subprocess.TimeoutExpired:
                return {**preview, "status": "error", "dry_run": False, "apply": True,
                        "errors": ["mkvpropedit agotó el timeout de 300s."]}
            if proc.returncode != 0:
                salida = (proc.stdout or "") + (proc.stderr or "")
                return {**preview, "status": "error", "dry_run": False, "apply": True,
                        "exit_code": proc.returncode,
                        "errors": [f"mkvpropedit falló: {salida.strip()[:500]}"]}
            now = datetime.now(timezone.utc).isoformat()
            _update_status(conn, library_item_id, "aplicado", None, applied_at=now)
            if on_progress:
                on_progress(100)
            return {
                **preview, "status": "applied", "dry_run": False, "apply": True,
                "applied_at": now, "exit_code": 0, "escrito": True,
                "ordered_tracks": plan["ordered_tracks"],
            }

        # Write to a temp file in the SAME directory (same filesystem — works
        # over SSHFS/NFS), then atomically replace the original. Nombre fijo:
        # un reintento pisa el que dejó un intento matado en vez de sumar otro.
        tmp_path = str(p.with_name(p.stem + _SUFIJO_PARTE))
        _barrer_restos(p.parent, tmp_path)
        falta = _falta_espacio(p)
        if falta:
            return {**preview, "status": "error", "dry_run": False, "apply": True, "errors": [falta]}
        antes = _huella(p)

        args = build_mkvmerge_args(tmp_path, prepared_path, plan, gui_mode=True)
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError:
            return {**preview, "status": "error", "dry_run": False, "apply": True,
                     "errors": ["mkvmerge no encontrado al ejecutar."]}

        output_lines: list[str] = []

        def _read_output() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                output_lines.append(line)
                if on_progress:
                    pct = parse_mkvmerge_gui_progress(line)
                    if pct is not None:
                        on_progress(pct)

        reader = threading.Thread(target=_read_output, daemon=True)
        reader.start()
        reader.join(timeout=1800)
        if reader.is_alive():
            proc.kill()
            reader.join(timeout=5)
            _cleanup(tmp_path)
            _update_status(conn, library_item_id, "error", "mkvmerge agotó el timeout (30 min).")
            return {**preview, "status": "error", "dry_run": False, "apply": True,
                     "errors": ["mkvmerge agotó el timeout (30 min)."]}
        returncode = proc.wait()

        # mkvmerge: 0 = OK, 1 = OK with warnings, 2 = failed (no output file).
        if returncode not in (0, 1) or not os.path.isfile(tmp_path):
            _cleanup(tmp_path)
            err = ("".join(output_lines) or f"exit code {returncode}").strip()
            _update_status(conn, library_item_id, "error", err[:2000])
            logger.warning("Reordenar/renombrar pistas falló (item %s): %s", library_item_id, err[:300])
            return {**preview, "status": "error", "dry_run": False, "apply": True, "errors": [err[:2000]]}

        # Si mientras tanto Radarr/Sonarr lo sustituyó, o alguien lo enlazó, no se pisa.
        if _huella(p) != antes:
            _cleanup(tmp_path)
            return {**preview, "status": "error", "dry_run": False, "apply": True,
                    "errors": [f"{p.name} cambió mientras se reordenaba; no se sustituye."]}
        os.replace(tmp_path, prepared_path)
        now = datetime.now(timezone.utc).isoformat()
        _update_status(conn, library_item_id, "aplicado", None, applied_at=now)
        logger.info("Pistas reordenadas/renombradas (item %s): %s", library_item_id, prepared_path)
        if on_progress:
            on_progress(100)

        return {
            **preview, "status": "applied", "dry_run": False, "apply": True,
            "applied_at": now, "exit_code": returncode, "escrito": True,
            "ordered_tracks": plan["ordered_tracks"],
        }
    finally:
        if own:
            conn.close()


# El temporal de un reordenado; el patrón viejo es el de tempfile.mkstemp.
_SUFIJO_PARTE = ".remux.mkv.part"
_PARTE_VIEJA = re.compile(r"^tmp[a-z0-9_]{8}\.mkv\.part$")
# Más que el timeout de mkvmerge: lo que pase de aquí ya no lo escribe nadie.
_RESTO_ABANDONADO_S = 1800 + 300


def _barrer_restos(carpeta: Path, propio: str) -> None:
    """Borra los .mkv.part que dejó un reordenado matado (docker restart, OOM)."""
    limite = time.time() - _RESTO_ABANDONADO_S
    try:
        for f in carpeta.iterdir():
            if str(f) == propio or (
                    (f.name.endswith(_SUFIJO_PARTE) or _PARTE_VIEJA.match(f.name))
                    and f.stat().st_mtime < limite):
                _cleanup(str(f))
    except OSError:
        logger.warning("No se pudieron barrer los restos de %s", carpeta, exc_info=True)


def _gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


def _falta_espacio(p: Path) -> str | None:
    """Reordenar escribe el fichero entero otra vez antes de sustituirlo."""
    necesario = p.stat().st_size * 102 // 100
    libre = shutil.disk_usage(p.parent).free
    if libre >= necesario:
        return None
    return (f"No hay espacio para reordenar {p.name}: hacen falta {_gb(necesario)} "
            f"y quedan {_gb(libre)} libres en {p.parent}.")


def _huella(p: Path) -> tuple:
    st = p.stat()
    return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_nlink)


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
