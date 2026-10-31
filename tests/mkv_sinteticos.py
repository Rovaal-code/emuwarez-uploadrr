"""MKV pequeños de verdad, hechos con ffmpeg y mkvmerge.

Para las pruebas que tienen que pasar por mediainfo y mkvmerge reales: un
diccionario inventado no dice cómo escribe MediaInfo un "es-MX" ni qué
banderas devuelve mkvmerge. Sin las herramientas, esas pruebas se saltan.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HAY_HERRAMIENTAS = all(shutil.which(t) for t in ("ffmpeg", "mediainfo", "mkvmerge", "mkvpropedit"))
requiere_herramientas = pytest.mark.skipif(
    not HAY_HERRAMIENTAS, reason="faltan ffmpeg/mediainfo/mkvmerge/mkvpropedit en este entorno",
)

_DISPOSICION = {1: "mono", 2: "stereo", 6: "5.1"}


def hacer_mkv(destino: Path, *, ancho: int = 1920, alto: int = 1080,
              audios: tuple = (), subs: tuple = ()) -> Path:
    """Un MKV de un segundo con las pistas pedidas.

    `audios`: dicts con `lang` (BCP-47, como lo escribe mkvmerge), `codec`
    (de ffmpeg: ac3, eac3, aac, flac), `canales` (1, 2 o 6) y, opcionales,
    `titulo`, `comentario` y `ad` (banderas de mkvmerge).
    `subs`: dicts con `lang` y, opcionales, `titulo`, `forzado` y `sdh`."""
    base = destino.with_name(destino.stem + ".base.mkv")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "lavfi", "-i", f"color=c=black:s={ancho}x{alto}:d=1:r=5"]
    for a in audios:
        cmd += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl={_DISPOSICION[a.get('canales', 6)]}:d=1"]
    cmd += ["-map", "0:v"]
    for i, _ in enumerate(audios):
        cmd += ["-map", f"{i + 1}:a"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast"]
    for i, a in enumerate(audios):
        cmd += [f"-c:a:{i}", a.get("codec", "ac3")]
    cmd.append(str(base))
    subprocess.run(cmd, check=True, timeout=60)

    merge = ["mkvmerge", "-q", "-o", str(destino)]
    for i, a in enumerate(audios, 1):
        merge += ["--language", f"{i}:{a['lang']}"]
        if a.get("titulo"):
            merge += ["--track-name", f"{i}:{a['titulo']}"]
        if a.get("comentario"):
            merge += ["--commentary-flag", f"{i}:1"]
        if a.get("ad"):
            merge += ["--visual-impaired-flag", f"{i}:1"]
    merge.append(str(base))
    for n, s in enumerate(subs):
        srt = destino.with_name(f"{destino.stem}.{n}.srt")
        srt.write_text("1\n00:00:00,000 --> 00:00:00,500\nHola\n", encoding="utf-8")
        merge += ["--language", f"0:{s['lang']}"]
        if s.get("titulo"):
            merge += ["--track-name", f"0:{s['titulo']}"]
        if s.get("forzado"):
            merge += ["--forced-display-flag", "0:1"]
        if s.get("sdh"):
            merge += ["--hearing-impaired-flag", "0:1"]
        merge.append(str(srt))
    # mkvmerge sale con 1 cuando solo hay avisos.
    r = subprocess.run(merge, capture_output=True, text=True, timeout=60)
    assert r.returncode in (0, 1), r.stdout + r.stderr
    base.unlink()
    for srt in destino.parent.glob(f"{destino.stem}.*.srt"):
        srt.unlink()
    return destino
