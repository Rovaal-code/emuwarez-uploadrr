"""El CSS del frontend no escribe `-webkit-backdrop-filter` a mano.

lightningcss (el minificador CSS de Vite 8) ya añade el prefijo para Safari < 18 a partir de `backdrop-filter`, pero si
el fuente trae las dos, el CSS de producción se queda solo con la prefijada: Chrome y Firefox pierden el desenfoque, y
con él el bloque contenedor que ancla el panel de la campana a la cabecera.
"""
from __future__ import annotations

from pathlib import Path

ESTILOS = Path(__file__).resolve().parents[1] / "frontend" / "src"


def test_ningun_css_del_frontend_escribe_el_prefijo_de_backdrop_filter_a_mano():
    culpables = [
        f"{ruta.relative_to(ESTILOS.parent)}:{n}"
        for ruta in sorted(ESTILOS.rglob("*.css"))
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        if linea.strip().startswith("-webkit-backdrop-filter")
    ]
    assert not culpables, f"Quita el prefijo (lo pone lightningcss): {culpables}"
