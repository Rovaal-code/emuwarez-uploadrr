#!/usr/bin/env python3
"""Sube el número de versión del paquete.

Se ejecuta ANTES de construir la imagen, y esto no es un detalle: la imagen
sella la versión al construirse (`emuwarez_uploadrr/__init__.py` es la fuente y
`pyproject.toml` la lee de ahí). Subirla después de publicar dejaría la imagen
con el número viejo y el manifiesto anunciando otro.

El orden completo de un despliegue:

    python3 scripts/subir_version.py patch     # 0.2.0 -> 0.2.1
    git commit -am "..."                       # la versión entra en el commit
    docker build --build-arg APP_COMMIT=$(git rev-parse HEAD) ...
    docker push ...
    python3 scripts/publicar_version.py --digest sha256:... --repo

Qué escala usar:
  patch  un arreglo o un retoque              0.2.0 -> 0.2.1
  minor  algo nuevo que se usa                0.2.1 -> 0.3.0
  major  algo que rompe lo anterior           0.3.0 -> 1.0.0
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
INIT = RAIZ / "emuwarez_uploadrr" / "__init__.py"
_PATRON = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.M)


def leer_version(texto: str) -> str:
    m = _PATRON.search(texto)
    if not m:
        raise ValueError("no se encontró __version__")
    return m.group(1)


def siguiente(version: str, escala: str) -> str:
    """La versión siguiente. Solo entiende MAJOR.MINOR.PATCH."""
    partes = version.split(".")
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        raise ValueError(f"versión no reconocida: {version!r} (se espera X.Y.Z)")
    mayor, menor, parche = (int(p) for p in partes)
    if escala == "major":
        return f"{mayor + 1}.0.0"
    if escala == "minor":
        return f"{mayor}.{menor + 1}.0"
    return f"{mayor}.{menor}.{parche + 1}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("escala", nargs="?", default="patch",
                   choices=["patch", "minor", "major"],
                   help="qué parte se sube (por defecto: patch)")
    p.add_argument("--exacta", help="poner esta versión en vez de calcularla")
    p.add_argument("--ver", action="store_true", help="solo enseñar la versión actual")
    args = p.parse_args()

    texto = INIT.read_text()
    actual = leer_version(texto)
    if args.ver:
        print(actual)
        return 0

    nueva = args.exacta or siguiente(actual, args.escala)
    if nueva == actual:
        print(f"✗ La versión ya es {actual}", file=sys.stderr)
        return 1

    INIT.write_text(_PATRON.sub(f'__version__ = "{nueva}"', texto, count=1))
    print(f"{actual} -> {nueva}")
    print("\nAhora: commit, build (con --build-arg APP_COMMIT), push y publicar el manifiesto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
