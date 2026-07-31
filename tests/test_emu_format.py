"""Tests de services/emu_format.py."""
from __future__ import annotations

def test_the_guide_lists_the_same_codec_priority_as_the_code():
    """La Guía documenta el orden de calidad de los códecs, y el frontend no
    puede llamar a Python, así que hay dos copias. Este test es lo que impide
    que se separen: una guía que dice un orden y un código que aplica otro es
    peor que no documentarlo."""
    import pathlib, re
    from emuwarez_uploadrr.services.emu_format import _AUDIO_CODEC_QUALITY

    guide = pathlib.Path(__file__).resolve().parents[1] / "frontend/src/pages/GuidePage.tsx"
    block = re.search(r"const AUDIO_QUALITY_ROWS.*?\n\]", guide.read_text(), re.S)
    assert block, "no se encontró AUDIO_QUALITY_ROWS en la Guía"

    listados: list[str] = []
    for label in re.findall(r"\['([^']+)',", block.group(0)):
        # La guía junta las variantes de AAC en una fila para no repetir
        # cuatro veces "con pérdida"; aquí se desdoblan para comparar.
        listados.extend(part.strip() for part in label.split("/"))

    assert listados == list(_AUDIO_CODEC_QUALITY), (
        f"\nGuía:   {listados}\nCódigo: {list(_AUDIO_CODEC_QUALITY)}"
    )
