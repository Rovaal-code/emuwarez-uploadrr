"""Semantic tagging of audio/subtitle track names — spec section 10.

Track *names* are freely editable by whoever muxed the file, so on their own
they're weak evidence (a "Commentary" label proves nothing about the actual
source). They're kept separate from the technical flags (mkvmerge's actual
`forced_track`/`default_track` booleans, which are medium-strength evidence)
and are never given much weight by evidence.py — see its module docstring
for the strength hierarchy.
"""
from __future__ import annotations

import re

# Multi-language keyword groups. Each tuple is (tag, patterns) where patterns
# are matched case-insensitively as whole-word-ish substrings.
_COMMENTARY = [
    "commentary", "director's commentary", "cast commentary", "audio commentary",
    "comentario", "comentarios del director", "comentario del reparto",
    "commentaire", "commentaire du réalisateur",
    "kommentar", "audiokommentar",
    "commento", "commento audio",
    "comentário", "comentário do diretor",
]
_DESCRIPTIVE = [
    "audio description", "descriptive audio", "visually impaired", "narración",
    "audiodescripción", "audio descripción", "descripción de audio",
    "audiodescription", "vision malvoyants",
    "hörfilm", "audiodeskription",
    "audiodescrizione",
    "audiodescrição",
]
_HEARING_IMPAIRED = [
    "sdh", "hearing impaired", "hard of hearing", "sordos",
    "sourds et malentendants", "malentendants",
    "hörgeschädigte",
    "non udenti",
    "surdos",
]
_FORCED = [
    "forced", "forzado", "forzados", "forcé", "forcés", "erzwungen", "forzati", "forçado",
]
_SIGNS_SONGS = [
    "signs & songs", "signs and songs", "carteles y canciones",
]
_ORIGINAL = [
    "original", "vo", "version originale", "originalfassung", "originale", "original mix",
]
_DUB = [
    "dub", "doblaje", "doblada", "doublage", "synchronisation", "doppiaggio", "dublagem", "dublado",
]
_ISOLATED_SCORE = [
    "isolated score", "banda sonora aislada", "musique isolée",
]
_THEATRICAL = [
    "theatrical mix", "mezcla de cine", "mezcla teatral",
]
_NEAR_FIELD = [
    "near field", "campo cercano",
]

_GROUPS = {
    "commentary": _COMMENTARY,
    "descriptive": _DESCRIPTIVE,
    "hearing_impaired": _HEARING_IMPAIRED,
    "forced": _FORCED,
    "signs_songs": _SIGNS_SONGS,
    "original": _ORIGINAL,
    "dub": _DUB,
    "isolated_score": _ISOLATED_SCORE,
    "theatrical_mix": _THEATRICAL,
    "near_field_mix": _NEAR_FIELD,
}

_COMPILED = {
    tag: re.compile(r"(?i)\b(?:" + "|".join(re.escape(p) for p in patterns) + r")\b")
    for tag, patterns in _GROUPS.items()
}


def tag_track_name(name: str | None) -> dict[str, bool]:
    """Returns {tag: True} for every keyword group matched in `name`. An
    empty/None name returns an all-False dict — no evidence either way."""
    text = name or ""
    return {tag: bool(rx.search(text)) for tag, rx in _COMPILED.items()}


def tag_all_tracks(tracks: list[dict]) -> dict[int, dict[str, bool]]:
    return {i: tag_track_name(t.get("title")) for i, t in enumerate(tracks)}
