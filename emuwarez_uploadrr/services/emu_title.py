"""El nombre eMuwarez construido a partir de una lectura real del fichero.

Es el constructor ORIGINAL, el del monolito: recibe un `MediaInfoData` (lo que
`media_probe.read_media_info` saca del archivo) y devuelve el título. Vivía en
`legacy.py` y se movió aquí el 2026-08-01.

**No es el que se usa para subir.** El camino moderno construye el nombre desde
los campos ya resueltos de la propuesta (`services/nomenclature.py` con
`services/emu_format.py`), y es ese el que decide cómo se llama un torrent.
Este se conserva porque `nomenclature_check` lo necesita para otra cosa:
calcular cómo DEBERÍA llamarse un fichero mirando lo que hay dentro, y
compararlo con cómo se llama de verdad.

Que existan dos constructores es deuda conocida (auditoría, hallazgo 1.2:
`legacy.audio_name` frente a `emu_format.build_audio_string`). Unificarlos
cambia nombres, así que es un paso aparte y con sus propias pruebas, no un
movimiento de ficheros.
"""
from __future__ import annotations

from typing import Optional

from .media_probe import MediaInfoData


def audio_name(audio_items: list[dict[str, str]]) -> str:
    if not audio_items:
        return "Mudo"

    langs: list[str] = []
    for item in audio_items:
        if item["lang"] not in langs:
            langs.append(item["lang"])

    same_codec_channels = len({(a["codec"], a["channels"]) for a in audio_items}) == 1

    if same_codec_channels and len(langs) == 2 and "ESP" in langs:
        return f"DUAL {audio_items[0]['codec']} {audio_items[0]['channels']}"

    if same_codec_channels and len(langs) >= 4:
        return f"MULTI {audio_items[0]['codec']} {audio_items[0]['channels']}"

    parts: list[str] = []
    for item in audio_items:
        parts.extend([item["lang"], item["codec"], item["channels"]])
    return " ".join(parts)


def build_emu_title(
    title: str,
    year: str,
    media: MediaInfoData,
    tag: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    pack: bool = False,
) -> str:
    prefix = title
    if pack and season:
        prefix += f" S{season:02d}"
    elif season and episode:
        prefix += f" S{season:02d}E{episode:02d}"

    parts = [
        prefix,
        year,
        media.resolution,
        media.source,
        *media.hdr_tokens,
        media.video_codec,
        audio_name(media.audio),
    ]
    if media.has_subs:
        parts.append("SUBS")

    return " ".join(part for part in parts if part).strip() + f"-{tag}"
